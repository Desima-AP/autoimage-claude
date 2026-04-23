#!/usr/bin/env python3
"""
generate_image.py — single generation end-to-end.

Invoked by the auto-image skill (via Bash) and by the `/design-regen` slash
command. Claude crafts the prompt and passes it in; this script handles
provider routing, the actual API call, resize/crop to target dimensions,
PNG + WebP output, pending-assets bookkeeping, and CSV logging.

Usage:

  python3 scripts/generate_image.py \
    --name hero-home \
    --prompt "<cinematic prompt>" \
    --context "<code-context snippet>" \
    --project-root "$CLAUDE_PROJECT_DIR" \
    [--overwrite] [--asset-id <pending-asset-id>] [--dry-run]

Exit codes:
  0 success
  1 provider error (API / network)
  2 bad args
  3 missing API keys for the chosen provider
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from router import route, read_env, read_preferred_provider  # noqa: E402
from log_generation import append_row, estimate_cost, log_path as cost_log_path  # noqa: E402

# post_process is imported lazily — it pulls in Pillow, which we don't
# need for --dry-run, and we want to give a clean error message if the
# user hasn't installed it yet.


def _update_pending_status(project_root: Path, asset_id: Optional[str], new_status: str,
                           output_path: Optional[Path] = None) -> None:
    if not asset_id:
        return
    pending = project_root / ".claude" / "pending-assets.json"
    if not pending.exists():
        return
    try:
        data = json.loads(pending.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    for asset in data.get("assets") or []:
        if asset.get("id") == asset_id:
            asset["status"] = new_status
            if output_path is not None:
                asset["output_path"] = str(output_path)
            asset["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pending.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _emit(result: dict[str, Any]) -> None:
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one image and save it into the project.")
    parser.add_argument("--name", required=True, help="suggested filename stem (e.g. hero-home)")
    parser.add_argument("--prompt", required=True, help="fully-crafted generation prompt")
    parser.add_argument("--context", default="", help="optional code-context snippet (influences routing)")
    parser.add_argument("--project-root",
                        default=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    parser.add_argument("--asset-id", default=None,
                        help="pending-assets.json entry to mark as generated")
    parser.add_argument("--out-dir", default=None,
                        help="override output directory (default: auto-detected)")
    parser.add_argument("--overwrite", action="store_true",
                        help="overwrite existing filename (default: append -2, -3, ...)")
    parser.add_argument("--provider", choices=["openai", "gemini"], default=None,
                        help="override provider for this call; without it, "
                             "preset.preferred_provider or single-key auto is used")
    parser.add_argument("--quality-override", default=None)
    parser.add_argument("--transparent", action="store_true",
                        help="force transparent background (ignores router)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the routing decision without calling the provider")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    env = read_env(project_root)
    preset_pref = read_preferred_provider(project_root)

    override = args.provider if args.provider in ("openai", "gemini") else None
    decision = route(
        args.name, args.context, env,
        provider_override=override,
        preset_preferred=preset_pref,
    )
    params = decision.params
    if args.transparent:
        params["transparent"] = True
    if args.quality_override:
        params["quality"] = args.quality_override

    if decision.needs_user_choice:
        _emit({
            "ok": False,
            "error": "provider choice required",
            "hint": ("Both OPENAI_API_KEY and GEMINI_API_KEY are set and no preferred "
                     "provider is saved in .claude/brand-preset.json. Pass --provider openai "
                     "or --provider gemini, or run /design-brand to set a project default."),
            "decision": decision.to_dict(),
        })
        return 3

    if args.dry_run:
        would_write: str
        if args.out_dir:
            would_write = args.out_dir
        else:
            try:
                from post_process import detect_output_dir
                would_write = str(detect_output_dir(project_root))
            except ImportError:
                would_write = "<Pillow not installed — run: pip install Pillow>"
        _emit({
            "dry_run": True,
            "decision": decision.to_dict(),
            "project_root": str(project_root),
            "would_write": would_write,
        })
        return 0

    try:
        from post_process import process
    except ImportError:
        _emit({
            "ok": False,
            "error": "Pillow not installed",
            "hint": "Run: pip install Pillow",
        })
        return 1

    # Acquire image bytes from the chosen provider
    try:
        if decision.provider == "openai":
            from openai_client import generate as openai_generate, OpenAIError
            if not env.get("OPENAI_API_KEY"):
                print(json.dumps({
                    "ok": False, "error": "OPENAI_API_KEY missing",
                    "hint": "Add OPENAI_API_KEY to project .env or environment.",
                    "decision": decision.to_dict(),
                }, indent=2))
                return 3
            result = openai_generate(
                args.prompt, env["OPENAI_API_KEY"],
                width=params["generation_width"], height=params["generation_height"],
                quality=params["quality"], transparent=params["transparent"],
            )
            image_bytes = result.image_bytes
            size_label = result.size
            model_label = result.model
        else:
            from gemini_client import generate as gemini_generate, GeminiError
            if not env.get("GEMINI_API_KEY"):
                print(json.dumps({
                    "ok": False, "error": "GEMINI_API_KEY missing",
                    "hint": "Add GEMINI_API_KEY to project .env or environment.",
                    "decision": decision.to_dict(),
                }, indent=2))
                return 3
            result = gemini_generate(
                args.prompt, env["GEMINI_API_KEY"],
                width=params["generation_width"], height=params["generation_height"],
            )
            image_bytes = result.image_bytes
            size_label = f'{params["generation_width"]}x{params["generation_height"]}'
            model_label = result.model
    except Exception as e:
        _update_pending_status(project_root, args.asset_id, "error")
        _emit({"ok": False, "error": str(e), "decision": decision.to_dict()})
        return 1

    # Post-process, write PNG + WebP
    out_dir = Path(args.out_dir).resolve() if args.out_dir else None
    processed = process(
        image_bytes,
        target_w=params["target_width"],
        target_h=params["target_height"],
        project_root=project_root,
        filename_stem=args.name,
        transparent=params["transparent"],
        output_dir=out_dir,
        overwrite=args.overwrite,
    )

    # Log + bookkeeping
    cost = estimate_cost(model_label, size_label, params["quality"])
    append_row({
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_file": str(processed.png_path),
        "model": model_label,
        "prompt_short": args.prompt[:160].replace("\n", " "),
        "cost_est_usd": f"{cost:.4f}",
        "sha256": processed.sha256,
    })
    _update_pending_status(project_root, args.asset_id, "done", processed.png_path)

    _emit({
        "ok": True,
        "png": str(processed.png_path),
        "webp": str(processed.webp_path),
        "sha256": processed.sha256,
        "width": processed.width,
        "height": processed.height,
        "model": model_label,
        "provider": decision.provider,
        "size_requested": size_label,
        "quality": params["quality"],
        "transparent": params["transparent"],
        "degraded": decision.degraded,
        "cost_est_usd": cost,
        "log": str(cost_log_path()),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
