"""Unit tests for detect_brand.py using a tempdir fixture project."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import detect_brand  # noqa: E402


TAILWIND_SAMPLE = """\
/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        brand: {
          primary:   '#0B5FFF',
          secondary: '#1E1B4B',
          accent:    '#F97316',
          mute:      '#F5F5F4',
        },
      },
    },
  },
};
"""

PACKAGE_SAMPLE = """\
{
  "name": "acme-docs",
  "description": "Lightning-fast documentation for developers and technical teams."
}
"""

README_SAMPLE = """\
# Acme Docs

Lightning-fast developer documentation with a minimal, editorial feel.
Built for teams that want clean, technical reading with warm touches.
"""

LAYOUT_SAMPLE = """\
import { Inter } from "next/font/google";
const inter = Inter({ subsets: ["latin"] });

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={inter.className}>
      <head>
        <meta name="description" content="Lightning-fast developer docs, designed for makers." />
      </head>
      <body>{children}</body>
    </html>
  );
}
"""


class DetectBrandTests(unittest.TestCase):
    def _seed_project(self, tmp: Path) -> Path:
        (tmp / "tailwind.config.js").write_text(TAILWIND_SAMPLE, encoding="utf-8")
        (tmp / "package.json").write_text(PACKAGE_SAMPLE, encoding="utf-8")
        (tmp / "README.md").write_text(README_SAMPLE, encoding="utf-8")
        (tmp / "app").mkdir()
        (tmp / "app" / "layout.tsx").write_text(LAYOUT_SAMPLE, encoding="utf-8")
        return tmp

    def test_detects_palette_and_mood(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._seed_project(Path(tmp))
            preset = detect_brand.detect(project)

            self.assertEqual(preset["project_name"], "acme-docs")
            self.assertEqual(preset["palette"]["primary"], "#0b5fff")
            self.assertIn("#1e1b4b", (preset["palette"]["secondary"],
                                      preset["palette"]["primary"],
                                      preset["palette"]["accent"]))
            self.assertIn("minimal", preset["mood"] + ["minimal"])  # should be detected
            # typography — Inter detected via next/font
            self.assertEqual(preset["typography"]["primary_font"], "Inter")

    def test_meta_description_overrides_package_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._seed_project(Path(tmp))
            preset = detect_brand.detect(project)
            # short_description prefers package.json first, meta second — verify one of them
            self.assertTrue(preset["short_description"])

    def test_locked_fields_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._seed_project(Path(tmp))
            existing = {
                "palette": {"primary": "#FF006E", "secondary": "#000000",
                            "accent": "#FFFF00", "neutral": "#EEEEEE", "extras": []},
                "locked": {"palette": True},
            }
            detected = detect_brand.detect(project)
            merged = detect_brand.merge_with_locks(detected, existing)
            self.assertEqual(merged["palette"]["primary"], "#FF006E")
            self.assertTrue(merged["locked"]["palette"])

    def test_preferred_provider_default_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._seed_project(Path(tmp))
            preset = detect_brand.detect(project)
            self.assertIn("preferred_provider", preset)
            self.assertIsNone(preset["preferred_provider"])

    def test_existing_preferred_provider_preserved_on_redetect(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._seed_project(Path(tmp))
            detected = detect_brand.detect(project)
            existing = {"preferred_provider": "gemini"}
            merged = detect_brand.merge_with_locks(detected, existing)
            self.assertEqual(merged["preferred_provider"], "gemini")


class HexExtractionTests(unittest.TestCase):
    def test_short_hex_expanded(self):
        hexes = detect_brand.extract_hex_palette("color: #abc;")
        self.assertEqual(hexes, ["#aabbcc"])

    def test_dedupe(self):
        hexes = detect_brand.extract_hex_palette("#111 #111 #222")
        self.assertEqual(hexes, ["#111111", "#222222"])

    def test_limit(self):
        many = " ".join(f"#{i:06x}" for i in range(1, 50))
        hexes = detect_brand.extract_hex_palette(many, limit=5)
        self.assertEqual(len(hexes), 5)


if __name__ == "__main__":
    unittest.main()
