#!/usr/bin/env python3
"""
name_to_params.py — map an asset name / reference to generation parameters.

Given a suggested name like `hero-homepage` or a reference path like
`/public/images/og-image.png`, return target dimensions, generation
dimensions (closest native size for the model), aspect ratio, quality,
and transparency requirements.

Used both by the auto-image skill pipeline and by `/design-regen` when
forcing parameters for a specific asset.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class AssetParams:
    hint_type: str            # one of: hero, banner, og, icon, avatar, feature, card, bg, logo, default
    aspect_ratio: str         # e.g. "16:9"
    target_width: int
    target_height: int
    generation_width: int     # closest natively supported size for OpenAI gpt-image-2
    generation_height: int
    quality: str              # "high" | "medium" | "low"
    transparent: bool
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# (regex, params-builder) — order matters, first match wins.
# Background patterns (bg-*, background*) must come BEFORE hero/banner,
# because "bg-hero" should route to the bg hint, not the hero hint.
_RULES: list[tuple[re.Pattern, AssetParams]] = [
    (re.compile(r"\bbg[-_]|\bbackground\b|\bwallpaper\b", re.IGNORECASE), AssetParams(
        hint_type="bg",
        aspect_ratio="16:9",
        target_width=1920, target_height=1080,
        generation_width=1536, generation_height=1024,
        quality="high",
        transparent=False,
        notes="Background — atmospheric, low-contrast to not compete with foreground copy.",
    )),
    (re.compile(r"\b(hero|banner)\b", re.IGNORECASE), AssetParams(
        hint_type="hero",
        aspect_ratio="16:9",
        target_width=1920, target_height=1080,
        generation_width=1536, generation_height=1024,
        quality="high",
        transparent=False,
        notes="Full-bleed hero — upscale from 1536x1024 to 1920x1080 with bicubic + slight sharpen.",
    )),
    (re.compile(r"\bog[-_:]?image|^og[-_]", re.IGNORECASE), AssetParams(
        hint_type="og",
        aspect_ratio="1.91:1",
        target_width=1200, target_height=630,
        generation_width=1536, generation_height=1024,
        quality="high",
        transparent=False,
        notes="Open Graph card — centre-crop from 1536x1024 to 1200x630.",
    )),
    (re.compile(r"\bicon\b|\bfavicon\b|\bglyph\b", re.IGNORECASE), AssetParams(
        hint_type="icon",
        aspect_ratio="1:1",
        target_width=512, target_height=512,
        generation_width=1024, generation_height=1024,
        quality="medium",
        transparent=True,
        notes="Icon — flat vector-like, centred on transparent canvas.",
    )),
    (re.compile(r"\blogo\b|\bmark\b|\bbrand\b", re.IGNORECASE), AssetParams(
        hint_type="logo",
        aspect_ratio="1:1",
        target_width=1024, target_height=1024,
        generation_width=1024, generation_height=1024,
        quality="high",
        transparent=True,
        notes="Logo — geometric, minimal palette, transparent background for overlay.",
    )),
    (re.compile(r"\bavatar\b|\bprofile[-_]?pic\b|\bheadshot\b", re.IGNORECASE), AssetParams(
        hint_type="avatar",
        aspect_ratio="1:1",
        target_width=512, target_height=512,
        generation_width=1024, generation_height=1024,
        quality="medium",
        transparent=False,
        notes="Avatar — portrait-safe framing, soft background.",
    )),
    (re.compile(r"\bfeature\b|\bcard\b|\btile\b", re.IGNORECASE), AssetParams(
        hint_type="feature",
        aspect_ratio="4:3",
        target_width=1024, target_height=768,
        generation_width=1536, generation_height=1024,
        quality="medium",
        transparent=False,
        notes="Feature card — crop from 1536x1024 to 1024x768.",
    )),
    (re.compile(r"\bthumb(nail)?\b", re.IGNORECASE), AssetParams(
        hint_type="feature",
        aspect_ratio="16:9",
        target_width=1280, target_height=720,
        generation_width=1536, generation_height=1024,
        quality="medium",
        transparent=False,
        notes="Thumbnail — crop from 1536x1024 to 1280x720.",
    )),
]

_DEFAULT = AssetParams(
    hint_type="default",
    aspect_ratio="1:1",
    target_width=1024, target_height=1024,
    generation_width=1024, generation_height=1024,
    quality="medium",
    transparent=False,
    notes="Generic square asset — no matching rule.",
)


def params_for(name: str) -> AssetParams:
    """Return AssetParams for the given suggested name or reference path."""
    if not name:
        return _DEFAULT
    for pattern, params in _RULES:
        if pattern.search(name):
            # return a copy so callers can mutate without side effects
            return AssetParams(**asdict(params))
    return AssetParams(**asdict(_DEFAULT))


def override_from_context(params: AssetParams, context_snippet: str) -> AssetParams:
    """Detect transparent-background hints and text-heavy hints in code context."""
    ctx = context_snippet.lower()
    if any(tok in ctx for tok in ("transparent", "alpha", "png:transparent", "cutout")):
        params.transparent = True
    if any(tok in ctx for tok in ("text-heavy", "with text", "logo text", "headline")):
        params.quality = "high"
    return params


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: name_to_params.py <name> [context-snippet]", file=sys.stderr)
        return 2
    name = sys.argv[1]
    context = sys.argv[2] if len(sys.argv) > 2 else ""
    p = override_from_context(params_for(name), context)
    print(json.dumps(p.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
