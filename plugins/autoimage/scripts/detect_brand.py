#!/usr/bin/env python3
"""
detect_brand.py — infer a project's visual brand from common source files.

Reads:
  * tailwind.config.{js,ts,mjs,cjs}  → colour palette
  * package.json                     → name, description
  * README.md                        → first 2000 chars → mood keywords + tone
  * app/layout.* / src/App.* / pages/_app.* / index.html  → <meta description>
                                                           + font-family hints

Writes:
  $CLAUDE_PROJECT_DIR/.claude/brand-preset.json

Schema (v1):
{
  "version": 1,
  "project_name": "…",
  "short_description": "…",
  "palette": {
    "primary":   "#RRGGBB",
    "secondary": "#RRGGBB",
    "accent":    "#RRGGBB",
    "neutral":   "#RRGGBB",
    "extras":    ["#RRGGBB", ...]
  },
  "mood": ["minimal", "editorial", ...],
  "copy_tone": "friendly-technical",
  "typography": { "primary_font": "Inter", "display_font": null },
  "locked": { "palette": false, "mood": false, "copy_tone": false },
  "updated_at": "…"
}

Fields marked `locked: true` are preserved verbatim on re-detection.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


HEX_RE = re.compile(r"#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})\b")
TW_CONFIG_NAMES = (
    "tailwind.config.ts", "tailwind.config.js",
    "tailwind.config.mjs", "tailwind.config.cjs",
)
LAYOUT_CANDIDATES = (
    "app/layout.tsx", "app/layout.jsx", "app/layout.ts", "app/layout.js",
    "src/App.tsx", "src/App.jsx", "src/App.ts", "src/App.js",
    "pages/_app.tsx", "pages/_app.jsx", "pages/_app.ts", "pages/_app.js",
    "index.html", "public/index.html", "src/index.html",
)
META_DESCRIPTION_RE = re.compile(
    r"""<meta[^>]*name=["']description["'][^>]*content=["'](?P<value>[^"']+)["']""",
    re.IGNORECASE,
)
FONT_FAMILY_RE = re.compile(
    r"""font-family\s*:\s*(?P<value>[^;]+);""",
    re.IGNORECASE,
)
NEXT_FONT_RE = re.compile(
    r"""from\s+["']next/font/google["'];[\s\S]{0,400}?\b(?P<name>[A-Z][A-Za-z_]+)\s*\(""",
    re.MULTILINE,
)

MOOD_KEYWORDS = {
    # mood  → phrases that suggest it when found in README / description
    "minimal":       ("minimal", "clean", "simple", "sparse", "whitespace"),
    "editorial":     ("editorial", "magazine", "longform", "storytelling"),
    "playful":       ("playful", "fun", "quirky", "whimsical", "delightful"),
    "technical":     ("technical", "developer", "api", "infrastructure", "sdk", "cli"),
    "luxurious":     ("luxury", "premium", "high-end", "elegant", "refined"),
    "bold":          ("bold", "vivid", "striking", "energetic", "loud"),
    "dark":          ("dark mode", "dark theme", "cyberpunk", "noir"),
    "warm":          ("warm", "cozy", "friendly", "welcoming", "community"),
    "corporate":     ("enterprise", "saas", "b2b", "business", "team", "workflow"),
    "creative":      ("creative", "art", "design", "portfolio", "studio", "gallery"),
    "scientific":    ("research", "lab", "science", "data", "analytics"),
    "ecommerce":     ("shop", "store", "checkout", "cart", "product", "retail"),
}


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def first_existing(root: Path, names: tuple[str, ...]) -> Optional[Path]:
    for n in names:
        p = root / n
        if p.exists():
            return p
    return None


def find_tailwind_config(root: Path) -> Optional[Path]:
    return first_existing(root, TW_CONFIG_NAMES)


def find_main_layout(root: Path) -> Optional[Path]:
    return first_existing(root, LAYOUT_CANDIDATES)


# ---------------------------------------------------------------------------
# Palette extraction from Tailwind
# ---------------------------------------------------------------------------

def extract_hex_palette(content: str, limit: int = 16) -> list[str]:
    """Return up to `limit` unique hex colours in order of appearance."""
    seen: list[str] = []
    for m in HEX_RE.finditer(content):
        h = "#" + m.group(1).lower()
        if len(h) == 4:  # expand #abc → #aabbcc
            h = "#" + "".join(c * 2 for c in h[1:])
        if h not in seen:
            seen.append(h)
        if len(seen) >= limit:
            break
    return seen


def slot_palette(hexes: list[str]) -> dict[str, Any]:
    slots = {"primary": None, "secondary": None, "accent": None, "neutral": None, "extras": []}
    if not hexes:
        return slots
    slots["primary"] = hexes[0]
    if len(hexes) > 1:
        slots["secondary"] = hexes[1]
    if len(hexes) > 2:
        slots["accent"] = hexes[2]
    # pick the closest-to-grey value as neutral (simple heuristic)
    best_idx, best_delta = None, 999
    for i, h in enumerate(hexes):
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        delta = max(abs(r - g), abs(g - b), abs(r - b))
        if delta < best_delta:
            best_delta = delta
            best_idx = i
    if best_idx is not None and best_delta < 30:
        slots["neutral"] = hexes[best_idx]
    used = {v for v in (slots["primary"], slots["secondary"], slots["accent"], slots["neutral"]) if v}
    slots["extras"] = [h for h in hexes if h not in used][:8]
    return slots


# ---------------------------------------------------------------------------
# Package / README reading
# ---------------------------------------------------------------------------

def read_package_json(root: Path) -> tuple[Optional[str], Optional[str]]:
    pkg = root / "package.json"
    if not pkg.exists():
        return None, None
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    return data.get("name"), data.get("description")


def read_readme(root: Path, limit: int = 2000) -> str:
    for name in ("README.md", "README.MD", "Readme.md", "readme.md"):
        p = root / name
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="replace")[:limit]
            except OSError:
                return ""
    return ""


def read_meta_description(layout_path: Optional[Path]) -> Optional[str]:
    if not layout_path or not layout_path.exists():
        return None
    try:
        text = layout_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = META_DESCRIPTION_RE.search(text)
    return m.group("value") if m else None


# ---------------------------------------------------------------------------
# Mood + tone inference
# ---------------------------------------------------------------------------

def infer_mood(texts: list[str]) -> list[str]:
    joined = " ".join(t.lower() for t in texts if t)
    if not joined:
        return []
    hits: list[tuple[str, int]] = []
    for mood, keywords in MOOD_KEYWORDS.items():
        score = sum(joined.count(kw) for kw in keywords)
        if score:
            hits.append((mood, score))
    hits.sort(key=lambda pair: pair[1], reverse=True)
    return [mood for mood, _ in hits[:4]] or ["neutral"]


def infer_copy_tone(texts: list[str]) -> str:
    joined = " ".join(t.lower() for t in texts if t)
    if not joined:
        return "neutral"
    if any(w in joined for w in ("enterprise", "scalable", "compliance", "sla", "b2b")):
        return "corporate-confident"
    if any(w in joined for w in ("delightful", "friendly", "let's", "hey", "fun")):
        return "warm-casual"
    if any(w in joined for w in ("researcher", "engineer", "developer", "sdk", "api")):
        return "technical-precise"
    if any(w in joined for w in ("curated", "crafted", "bespoke", "premium")):
        return "editorial-refined"
    return "neutral"


# ---------------------------------------------------------------------------
# Typography inference
# ---------------------------------------------------------------------------

def infer_typography(layout_path: Optional[Path], css_hints: list[Path]) -> dict[str, Optional[str]]:
    primary = None
    display = None

    if layout_path and layout_path.exists():
        try:
            text = layout_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        nf = NEXT_FONT_RE.search(text)
        if nf:
            primary = nf.group("name")

    for css in css_hints:
        if not css.exists():
            continue
        try:
            text = css.read_text(encoding="utf-8", errors="replace")[:20_000]
        except OSError:
            continue
        for m in FONT_FAMILY_RE.finditer(text):
            value = m.group("value").strip().strip(";").strip()
            # take first quoted family
            qm = re.search(r"""['"]([^'"]+)['"]""", value)
            family = qm.group(1) if qm else value.split(",")[0].strip()
            if family and not primary:
                primary = family
            elif family and not display and family.lower() != (primary or "").lower():
                display = family
                break
        if primary and display:
            break

    return {"primary_font": primary, "display_font": display}


# ---------------------------------------------------------------------------
# Output assembly
# ---------------------------------------------------------------------------

def load_existing_preset(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def merge_with_locks(new: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """Overlay freshly-detected fields on top of the existing preset.

    Locked fields are preserved verbatim from `existing`. The user-chosen
    `preferred_provider` is also preserved whenever it is non-null — it
    cannot be detected from project files, so losing it would silently
    break consistency for the next batch.
    """
    locks = existing.get("locked") or {}
    out = dict(new)
    for field, is_locked in locks.items():
        if is_locked and field in existing:
            out[field] = existing[field]
    if existing.get("preferred_provider") and not out.get("preferred_provider"):
        out["preferred_provider"] = existing["preferred_provider"]
    out["locked"] = locks
    return out


def detect(project_root: Path) -> dict[str, Any]:
    tw_path = find_tailwind_config(project_root)
    layout = find_main_layout(project_root)
    pkg_name, pkg_desc = read_package_json(project_root)
    readme_chunk = read_readme(project_root)
    meta_desc = read_meta_description(layout)

    palette_hexes: list[str] = []
    if tw_path:
        try:
            palette_hexes = extract_hex_palette(tw_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    # Fallback: scan CSS for hex colours
    if not palette_hexes:
        for css_name in ("src/index.css", "src/app.css", "app/globals.css", "styles/globals.css"):
            css_path = project_root / css_name
            if css_path.exists():
                try:
                    palette_hexes = extract_hex_palette(css_path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
                if palette_hexes:
                    break

    mood = infer_mood([pkg_desc or "", meta_desc or "", readme_chunk])
    tone = infer_copy_tone([pkg_desc or "", meta_desc or "", readme_chunk])
    typography = infer_typography(layout, [
        project_root / "src" / "index.css",
        project_root / "app" / "globals.css",
        project_root / "styles" / "globals.css",
    ])

    preset = {
        "version": 1,
        "project_name": pkg_name or project_root.name,
        "short_description": pkg_desc or meta_desc or "",
        "palette": slot_palette(palette_hexes),
        "mood": mood,
        "copy_tone": tone,
        "typography": typography,
        # preferred_provider: "openai" | "gemini" | null
        # null = ask the user on the first generation, then optionally
        # save their choice here so the whole project stays consistent.
        "preferred_provider": None,
        "locked": {
            "palette": False, "mood": False, "copy_tone": False,
            "typography": False, "preferred_provider": False,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return preset


def main() -> int:
    project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()

    out_path = project_root / ".claude" / "brand-preset.json"
    existing = load_existing_preset(out_path)
    detected = detect(project_root)
    merged = merge_with_locks(detected, existing)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(merged, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
