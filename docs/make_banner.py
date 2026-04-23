#!/usr/bin/env python3
"""
make_banner.py — render `docs/banner.png` (1280×640, GitHub social preview).

Uses only Pillow, no API calls. The banner follows the plugin's own
brand palette and layout approach: dark background, heavy typography,
small accent strip, tiny attribution footer. Re-run this script any
time the palette or tagline changes; commit the resulting PNG.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------------------------------------------------------------------------
# Brand palette (mirrors the autoimage preset)
# ---------------------------------------------------------------------------

PRIMARY = (11, 95, 255)      # #0B5FFF — electric blue
SECONDARY = (30, 27, 75)     # #1E1B4B — deep indigo
ACCENT = (249, 115, 22)      # #F97316 — warm coral
NEUTRAL = (245, 245, 244)    # #F5F5F4 — off-white
MUTED = (160, 160, 180)      # subtitle grey

W, H = 1280, 640
OUT = Path(__file__).resolve().parent / "banner.png"

# ---------------------------------------------------------------------------
# Font discovery
# ---------------------------------------------------------------------------

FONT_CANDIDATES_BOLD = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_CANDIDATES_REG = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size: int, bold: bool) -> ImageFont.FreeTypeFont:
    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REG
    for path in candidates:
        try:
            # Some TTC files have multiple faces; index 0 is a safe default,
            # but the bold variant often sits at a later index for Helvetica.
            if path.endswith(".ttc") and bold:
                for idx in (1, 2, 0):
                    try:
                        return ImageFont.truetype(path, size=size, index=idx)
                    except Exception:
                        continue
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def linear_gradient(image: Image.Image, top: tuple, bottom: tuple) -> None:
    draw = ImageDraw.Draw(image)
    for y in range(H):
        t = y / (H - 1)
        # easing: quad-in-out keeps both ends saturated, middle blends softer
        t = t * t * (3 - 2 * t)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def soft_glow(image: Image.Image, center: tuple, radius: int, colour: tuple, alpha: int) -> Image.Image:
    """Paste a blurred circle for a halo effect."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = center
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill=colour + (alpha,),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=radius // 3))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------

def compose() -> Image.Image:
    img = Image.new("RGB", (W, H), SECONDARY)

    # 1. Diagonal gradient from electric blue (top-left) to deep indigo (bottom-right)
    linear_gradient(img, PRIMARY, SECONDARY)

    # 2. Warm accent halo, off-centre — catches the eye
    img = soft_glow(img, center=(int(W * 0.78), int(H * 0.28)),
                    radius=260, colour=ACCENT, alpha=90)

    # 3. Dimmer primary halo bottom-left — adds depth without cluttering
    img = soft_glow(img, center=(int(W * 0.12), int(H * 0.85)),
                    radius=220, colour=PRIMARY, alpha=70)

    draw = ImageDraw.Draw(img)

    # 4. Small accent bar above the title — typography anchor
    bar_y = 210
    draw.rectangle([(120, bar_y), (200, bar_y + 6)], fill=ACCENT)

    # 5. Main title
    title = "autoimage"
    title_font = load_font(190, bold=True)
    tw, th = text_size(draw, title, title_font)
    draw.text(((W - tw) // 2, 228), title, font=title_font, fill=NEUTRAL)

    # 6. Tagline
    tagline = "brand-aligned images for frontend · a Claude Code plugin"
    tag_font = load_font(34, bold=False)
    tw, th = text_size(draw, tagline, tag_font)
    draw.text(((W - tw) // 2, 456), tagline, font=tag_font, fill=MUTED)

    # 7. Provider badges at bottom centre
    badges = [
        ("OpenAI  gpt-image-2", ACCENT),
        ("Google  gemini-3.1-flash-image", PRIMARY),
    ]
    badge_font = load_font(22, bold=True)
    badge_y = 530
    gap = 40
    widths = [text_size(draw, b[0], badge_font)[0] + 36 for b in badges]
    total_w = sum(widths) + gap
    x = (W - total_w) // 2
    for (label, border), bw in zip(badges, widths):
        draw.rounded_rectangle(
            [(x, badge_y), (x + bw, badge_y + 42)],
            radius=21, outline=border, width=2,
        )
        lw, lh = text_size(draw, label, badge_font)
        draw.text((x + (bw - lw) // 2, badge_y + (42 - lh) // 2 - 2),
                  label, font=badge_font, fill=NEUTRAL)
        x += bw + gap

    # 8. Corner attribution
    attrib_font = load_font(18, bold=False)
    draw.text((40, H - 40), "Desima-AP", font=attrib_font, fill=MUTED)
    version = "v0.2.0  ·  MIT"
    vw, vh = text_size(draw, version, attrib_font)
    draw.text((W - vw - 40, H - 40), version, font=attrib_font, fill=MUTED)

    return img


def main() -> int:
    img = compose()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, format="PNG", optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.1f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
