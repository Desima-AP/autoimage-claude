#!/usr/bin/env python3
"""
setup.py — quick environment check for the GenAI gpt-image-2 plugin.

Usage:  python3 scripts/setup.py [--install]

Checks:
  * Python ≥ 3.10
  * Pillow (required)
  * rembg (optional, for transparent PNG fallback when using Gemini)
  * OPENAI_API_KEY / GEMINI_API_KEY in environment or $CLAUDE_PROJECT_DIR/.env

With --install, attempts `pip install Pillow` (and rembg if requested).
"""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path


def check_python() -> tuple[bool, str]:
    major, minor = sys.version_info[:2]
    ok = (major, minor) >= (3, 9)
    return ok, f"Python {major}.{minor} (need ≥ 3.9)"


def check_module(name: str) -> tuple[bool, str]:
    try:
        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", "installed")
        return True, f"{name} {version}"
    except ImportError:
        return False, f"{name} not installed"


def read_dotenv(path: Path) -> dict[str, str]:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def check_keys() -> list[tuple[bool, str]]:
    project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    dotenv = read_dotenv(project_root / ".env")
    merged = {k: os.environ.get(k) or dotenv.get(k) for k in ("OPENAI_API_KEY", "GEMINI_API_KEY")}
    return [
        (bool(merged["OPENAI_API_KEY"]), "OPENAI_API_KEY (routes hero/banner/og/text-heavy to gpt-image-2)"),
        (bool(merged["GEMINI_API_KEY"]), "GEMINI_API_KEY (routes icons/avatars/logos to gemini-3.1-flash-image-preview)"),
    ]


def pip_install(pkgs: list[str]) -> bool:
    print(f"→ pip install {' '.join(pkgs)}")
    result = subprocess.run([sys.executable, "-m", "pip", "install", *pkgs])
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true",
                        help="install missing required packages via pip")
    parser.add_argument("--install-rembg", action="store_true",
                        help="also install rembg (large, optional)")
    args = parser.parse_args()

    print("=== GenAI gpt-image-2 plugin — environment check ===\n")

    py_ok, py_msg = check_python()
    print(f"  [{'✓' if py_ok else '✗'}] {py_msg}")

    pil_ok, pil_msg = check_module("PIL")
    print(f"  [{'✓' if pil_ok else '✗'}] {pil_msg}  (required)")

    rembg_ok, rembg_msg = check_module("rembg")
    print(f"  [{'✓' if rembg_ok else '·'}] {rembg_msg}  (optional — only needed for transparent PNG via Gemini)")

    print()
    for ok, label in check_keys():
        print(f"  [{'✓' if ok else '·'}] {label}")

    needs_install = not pil_ok
    if args.install and needs_install:
        print("\n--- installing required dependencies ---")
        pip_install(["Pillow"])
    if args.install_rembg and not rembg_ok:
        print("\n--- installing rembg (this is large: onnxruntime + model) ---")
        pip_install(["rembg", "onnxruntime"])

    if not py_ok or not pil_ok:
        print("\n⚠  Some required checks failed. Run again with --install.")
        return 1

    print("\nAll required checks passed.")
    if not any(ok for ok, _ in check_keys()):
        print("⚠  No API keys detected — generation will fail until OPENAI_API_KEY or")
        print("   GEMINI_API_KEY is set in the environment or in $CLAUDE_PROJECT_DIR/.env.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
