#!/usr/bin/env python3
"""
router.py — pick an image-generation provider under user-driven rules.

Both providers (OpenAI `gpt-image-2`, Google `gemini-3.1-flash-image-preview`)
can produce any asset type — the router does NOT silently split a batch
between them based on hint_type. Using two different models within one
project causes inconsistent aesthetics, which is something the user has
to opt into explicitly, not something we do by default.

Decision precedence (first rule that matches wins):

  1. Explicit override (CLI `--provider X`, or caller passed
     `provider_override="openai"|"gemini"`) — honoured even if that
     provider's key is missing (fails cleanly in generate_image.py).
  2. Project preset `.claude/brand-preset.json → preferred_provider` —
     if the preferred key is missing but the other is available, degrade
     with a warning. If neither is available, we mark degraded=True and
     the skill will surface the missing-key error.
  3. Single-key auto: if exactly one of the two keys is available, use
     that provider with a one-line note in `reason`.
  4. Both keys available, no preference: `needs_user_choice=True`. The
     caller (auto-image skill) asks the user once, then re-routes with
     the answer — optionally saving it to the preset for next time.

`reason`, `warnings`, and `params` are always populated. `warnings` is
informational only: for example, Gemini with text-heavy content gets a
hint that gpt-image-2 renders baked-in text more reliably — but the
router never overrides the user's choice on quality grounds.

Env lookup order: process env → `.env` in project root.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

try:
    from name_to_params import params_for, override_from_context
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from name_to_params import params_for, override_from_context  # type: ignore


OPENAI_MODEL = "gpt-image-2"
GEMINI_MODEL = "gemini-3.1-flash-image-preview"

VALID_PROVIDERS = ("openai", "gemini")


@dataclass
class RoutingDecision:
    provider: str            # "openai" | "gemini"
    model: str
    reason: str              # one-line explanation
    degraded: bool           # preferred provider's key is missing
    needs_user_choice: bool  # both keys present, no preference set anywhere
    api_key_available: bool  # whether the chosen provider's key exists
    params: dict
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Env / .env loading
# ---------------------------------------------------------------------------

_DOTENV_RE = re.compile(r"""^\s*(?P<key>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<value>.*?)\s*$""")


def _parse_dotenv(content: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in content.splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        m = _DOTENV_RE.match(line)
        if not m:
            continue
        key = m.group("key")
        value = m.group("value")
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        out[key] = value
    return out


def read_env(project_root: Optional[Path] = None) -> dict[str, str]:
    merged: dict[str, str] = {}
    if project_root is None:
        project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    dotenv = project_root / ".env"
    if dotenv.exists():
        try:
            merged.update(_parse_dotenv(dotenv.read_text(encoding="utf-8")))
        except OSError:
            pass
    for key in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(key):
            merged[key] = os.environ[key]
    if "GEMINI_API_KEY" not in merged and "GOOGLE_API_KEY" in merged:
        merged["GEMINI_API_KEY"] = merged["GOOGLE_API_KEY"]
    return merged


def has_key(env: dict[str, str], name: str) -> bool:
    return bool(env.get(name, "").strip())


def _key_for(provider: str) -> str:
    return "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"


def _model_for(provider: str) -> str:
    return OPENAI_MODEL if provider == "openai" else GEMINI_MODEL


def _other(provider: str) -> str:
    return "gemini" if provider == "openai" else "openai"


# ---------------------------------------------------------------------------
# Preset loading
# ---------------------------------------------------------------------------

def read_preferred_provider(project_root: Optional[Path] = None) -> Optional[str]:
    """Return preset.preferred_provider or None if absent / invalid."""
    if project_root is None:
        project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    preset = project_root / ".claude" / "brand-preset.json"
    if not preset.exists():
        return None
    try:
        data = json.loads(preset.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    value = data.get("preferred_provider")
    return value if value in VALID_PROVIDERS else None


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

_TEXT_TOKENS = (
    "text-heavy", "headline", "title:", "with text", "logo text",
    "wordmark", "the text", "the word", 'text "', "text '",
)

_QUOTED_STRING_RE = re.compile(r"""['"]([A-Za-z][A-Za-z0-9\s!?.\-]{2,40})['"]""")


def _context_has_text(context_snippet: str) -> bool:
    if not context_snippet:
        return False
    lowered = context_snippet.lower()
    if any(tok in lowered for tok in _TEXT_TOKENS):
        return True
    matches = _QUOTED_STRING_RE.findall(context_snippet)
    return any(len(m.split()) >= 2 for m in matches)


def _build_warnings(provider: str, params: dict, context_snippet: str) -> list[str]:
    warnings: list[str] = []
    has_text = _context_has_text(context_snippet)
    text_prone_hint = params.get("hint_type") in ("hero", "og", "banner")

    if provider == "gemini" and (has_text or text_prone_hint):
        warnings.append(
            "This asset has readable text (hint_type or context). gpt-image-2 "
            "renders baked-in text more reliably; consider switching providers "
            "for this batch if text clarity matters."
        )
    if provider == "gemini" and params.get("transparent"):
        warnings.append(
            "Transparent PNG requested on Gemini — output may be opaque unless "
            "`rembg` is installed for the post-processing cut-out."
        )
    return warnings


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route(
    suggested_name: str,
    context_snippet: str,
    env: Optional[dict[str, str]] = None,
    *,
    provider_override: Optional[str] = None,
    preset_preferred: Optional[str] = None,
) -> RoutingDecision:
    """Pick a provider under user-driven rules — see module docstring."""
    env = env if env is not None else read_env()
    params = override_from_context(params_for(suggested_name), context_snippet).to_dict()

    openai_ok = has_key(env, "OPENAI_API_KEY")
    gemini_ok = has_key(env, "GEMINI_API_KEY")
    keys_present = {"openai": openai_ok, "gemini": gemini_ok}

    # 1. Explicit override — respected even if the key is missing
    if provider_override in VALID_PROVIDERS:
        chosen = provider_override
        key_ok = keys_present[chosen]
        return RoutingDecision(
            provider=chosen,
            model=_model_for(chosen),
            reason=f"explicit override: --provider {chosen}",
            degraded=not key_ok,
            needs_user_choice=False,
            api_key_available=key_ok,
            params=params,
            warnings=_build_warnings(chosen, params, context_snippet),
        )

    # 2. Project preset
    if preset_preferred in VALID_PROVIDERS:
        if keys_present[preset_preferred]:
            return RoutingDecision(
                provider=preset_preferred,
                model=_model_for(preset_preferred),
                reason=f"preset.preferred_provider = {preset_preferred}",
                degraded=False,
                needs_user_choice=False,
                api_key_available=True,
                params=params,
                warnings=_build_warnings(preset_preferred, params, context_snippet),
            )
        fallback = _other(preset_preferred)
        if keys_present[fallback]:
            return RoutingDecision(
                provider=fallback,
                model=_model_for(fallback),
                reason=(f"preset.preferred_provider = {preset_preferred} but "
                        f"{_key_for(preset_preferred)} is missing; degraded to {fallback}"),
                degraded=True,
                needs_user_choice=False,
                api_key_available=True,
                params=params,
                warnings=_build_warnings(fallback, params, context_snippet),
            )
        return RoutingDecision(
            provider=preset_preferred,
            model=_model_for(preset_preferred),
            reason=f"preset.preferred_provider = {preset_preferred}, but no API keys configured",
            degraded=True,
            needs_user_choice=False,
            api_key_available=False,
            params=params,
            warnings=_build_warnings(preset_preferred, params, context_snippet),
        )

    # 3. Single-key auto
    if openai_ok and not gemini_ok:
        return RoutingDecision(
            provider="openai",
            model=OPENAI_MODEL,
            reason="only OPENAI_API_KEY present",
            degraded=False,
            needs_user_choice=False,
            api_key_available=True,
            params=params,
            warnings=_build_warnings("openai", params, context_snippet),
        )
    if gemini_ok and not openai_ok:
        return RoutingDecision(
            provider="gemini",
            model=GEMINI_MODEL,
            reason="only GEMINI_API_KEY present",
            degraded=False,
            needs_user_choice=False,
            api_key_available=True,
            params=params,
            warnings=_build_warnings("gemini", params, context_snippet),
        )

    # 4. Both keys + no preference → ask the user
    if openai_ok and gemini_ok:
        return RoutingDecision(
            provider="openai",  # placeholder; caller must re-route after asking
            model=OPENAI_MODEL,
            reason="both keys present, no preference set — user must choose",
            degraded=False,
            needs_user_choice=True,
            api_key_available=True,
            params=params,
            warnings=[],
        )

    # 5. No keys at all
    return RoutingDecision(
        provider="openai",
        model=OPENAI_MODEL,
        reason="no API keys available; set OPENAI_API_KEY or GEMINI_API_KEY",
        degraded=True,
        needs_user_choice=False,
        api_key_available=False,
        params=params,
        warnings=[],
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Routing decision for one asset.")
    parser.add_argument("name")
    parser.add_argument("context", nargs="?", default="")
    parser.add_argument("--provider", choices=VALID_PROVIDERS, default=None)
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve() if args.project_root else None
    preset_pref = read_preferred_provider(project_root)
    env = read_env(project_root)
    decision = route(
        args.name, args.context,
        env=env,
        provider_override=args.provider,
        preset_preferred=preset_pref,
    )
    print(json.dumps(decision.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
