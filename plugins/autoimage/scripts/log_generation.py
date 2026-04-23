#!/usr/bin/env python3
"""
log_generation.py — append one CSV row per generation to
`$CLAUDE_PROJECT_DIR/.claude/generation-log.csv`.

Columns: timestamp, target_file, model, prompt_short, cost_est_usd, sha256

Cost table (2026-04 indicative; update as providers publish new rates):
  gpt-image-2                      1024x1024 high     $0.019
  gpt-image-2                      1536x1024 high     $0.025
  gpt-image-2                      1024x1024 medium   $0.010
  gemini-3.1-flash-image-preview   any                $0.039
  gemini-2.5-flash-image           any                $0.030
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


HEADER = ["timestamp", "target_file", "model", "prompt_short", "cost_est_usd", "sha256"]


COST_TABLE = {
    # (model, size, quality) → USD
    ("gpt-image-2", "1024x1024", "high"): 0.019,
    ("gpt-image-2", "1024x1024", "medium"): 0.010,
    ("gpt-image-2", "1024x1024", "low"): 0.005,
    ("gpt-image-2", "1536x1024", "high"): 0.025,
    ("gpt-image-2", "1536x1024", "medium"): 0.013,
    ("gpt-image-2", "1024x1536", "high"): 0.025,
    ("gpt-image-2", "1024x1536", "medium"): 0.013,
    # Fallback models — used when gpt-image-2 is blocked by the
    # "organization must be verified" gate on a new OpenAI key.
    ("gpt-image-1.5", "1024x1024", "high"): 0.019,
    ("gpt-image-1.5", "1536x1024", "high"): 0.025,
    ("gpt-image-1.5", "1024x1536", "high"): 0.025,
    ("gpt-image-1", "1024x1024", "high"): 0.040,
    ("gpt-image-1", "1536x1024", "high"): 0.060,
    ("gpt-image-1", "1024x1536", "high"): 0.060,
    ("gemini-3.1-flash-image-preview", "*", "*"): 0.039,
    ("gemini-2.5-flash-image", "*", "*"): 0.030,
}


def estimate_cost(model: str, size: str, quality: str) -> float:
    exact = COST_TABLE.get((model, size, quality))
    if exact is not None:
        return exact
    wildcard = COST_TABLE.get((model, "*", "*"))
    if wildcard is not None:
        return wildcard
    return 0.0


def log_path() -> Path:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    return root / ".claude" / "generation-log.csv"


def append_row(row: dict, path: Path | None = None) -> Path:
    path = path or log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in HEADER})
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-file", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--size", required=True, help="e.g. 1024x1024")
    parser.add_argument("--quality", default="high")
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--cost", type=float, default=None,
                        help="override estimated cost")
    args = parser.parse_args()

    cost = args.cost if args.cost is not None else estimate_cost(args.model, args.size, args.quality)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_file": args.target_file,
        "model": args.model,
        "prompt_short": args.prompt[:160].replace("\n", " "),
        "cost_est_usd": f"{cost:.4f}",
        "sha256": args.sha256,
    }
    out = append_row(row)
    print(f"logged → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
