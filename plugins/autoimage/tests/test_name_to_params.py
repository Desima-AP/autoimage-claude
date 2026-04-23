"""Unit tests for name_to_params.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from name_to_params import params_for, override_from_context  # noqa: E402


class ParamsForTests(unittest.TestCase):
    def test_hero(self):
        p = params_for("hero-home")
        self.assertEqual(p.hint_type, "hero")
        self.assertEqual((p.target_width, p.target_height), (1920, 1080))
        self.assertEqual((p.generation_width, p.generation_height), (1536, 1024))
        self.assertFalse(p.transparent)

    def test_og_image(self):
        p = params_for("og-image")
        self.assertEqual(p.hint_type, "og")
        self.assertEqual((p.target_width, p.target_height), (1200, 630))

    def test_og_underscore(self):
        p = params_for("og_share")
        self.assertEqual(p.hint_type, "og")

    def test_icon_is_transparent_square(self):
        p = params_for("icon-settings")
        self.assertEqual(p.hint_type, "icon")
        self.assertTrue(p.transparent)
        self.assertEqual(p.target_width, p.target_height)

    def test_avatar(self):
        p = params_for("avatar-jane")
        self.assertEqual(p.hint_type, "avatar")
        self.assertFalse(p.transparent)

    def test_feature_card(self):
        p = params_for("feature-analytics")
        self.assertEqual(p.hint_type, "feature")
        self.assertEqual((p.target_width, p.target_height), (1024, 768))

    def test_bg_dash_pattern(self):
        p = params_for("bg-hero")
        self.assertEqual(p.hint_type, "bg")

    def test_background_word(self):
        p = params_for("background-noise")
        self.assertEqual(p.hint_type, "bg")

    def test_logo_is_transparent(self):
        p = params_for("logo-mark")
        self.assertEqual(p.hint_type, "logo")
        self.assertTrue(p.transparent)

    def test_thumbnail(self):
        p = params_for("thumb-video")
        self.assertEqual((p.target_width, p.target_height), (1280, 720))

    def test_default_fallback(self):
        p = params_for("something-weird")
        self.assertEqual(p.hint_type, "default")


class ContextOverrideTests(unittest.TestCase):
    def test_transparent_hint_elevates(self):
        p = params_for("hero-home")
        self.assertFalse(p.transparent)
        p = override_from_context(p, "transparent background please")
        self.assertTrue(p.transparent)

    def test_text_heavy_bumps_quality(self):
        p = params_for("default-thing")
        p = override_from_context(p, "headline text-heavy promo")
        self.assertEqual(p.quality, "high")

    def test_empty_context_no_change(self):
        p = params_for("icon-x")
        before = (p.transparent, p.quality)
        p = override_from_context(p, "")
        self.assertEqual((p.transparent, p.quality), before)


if __name__ == "__main__":
    unittest.main()
