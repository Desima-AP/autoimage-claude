"""Unit tests for the user-driven router."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from router import route, read_preferred_provider, OPENAI_MODEL, GEMINI_MODEL  # noqa: E402


KEYS_BOTH = {"OPENAI_API_KEY": "sk-test", "GEMINI_API_KEY": "gm-test"}
KEYS_OPENAI_ONLY = {"OPENAI_API_KEY": "sk-test"}
KEYS_GEMINI_ONLY = {"GEMINI_API_KEY": "gm-test"}
KEYS_NONE: dict[str, str] = {}


class ExplicitOverrideTests(unittest.TestCase):
    def test_override_openai_with_both_keys(self):
        d = route("hero-home", "", env=KEYS_BOTH, provider_override="openai")
        self.assertEqual(d.provider, "openai")
        self.assertEqual(d.model, OPENAI_MODEL)
        self.assertFalse(d.degraded)

    def test_override_gemini_with_both_keys(self):
        d = route("hero-home", "", env=KEYS_BOTH, provider_override="gemini")
        self.assertEqual(d.provider, "gemini")
        self.assertEqual(d.model, GEMINI_MODEL)
        self.assertFalse(d.degraded)

    def test_override_still_wins_over_preset(self):
        d = route("hero-home", "", env=KEYS_BOTH,
                  provider_override="gemini", preset_preferred="openai")
        self.assertEqual(d.provider, "gemini")

    def test_override_to_provider_without_key_marks_degraded(self):
        d = route("hero-home", "", env=KEYS_GEMINI_ONLY, provider_override="openai")
        self.assertEqual(d.provider, "openai")
        self.assertTrue(d.degraded)
        self.assertFalse(d.api_key_available)


class PresetPreferenceTests(unittest.TestCase):
    def test_preset_openai_with_both_keys(self):
        d = route("hero", "", env=KEYS_BOTH, preset_preferred="openai")
        self.assertEqual(d.provider, "openai")
        self.assertFalse(d.degraded)

    def test_preset_gemini_with_both_keys(self):
        d = route("icon", "", env=KEYS_BOTH, preset_preferred="gemini")
        self.assertEqual(d.provider, "gemini")
        self.assertFalse(d.degraded)

    def test_preset_openai_missing_key_degrades_to_gemini(self):
        d = route("hero", "", env=KEYS_GEMINI_ONLY, preset_preferred="openai")
        self.assertEqual(d.provider, "gemini")
        self.assertTrue(d.degraded)

    def test_preset_gemini_missing_key_degrades_to_openai(self):
        d = route("icon", "", env=KEYS_OPENAI_ONLY, preset_preferred="gemini")
        self.assertEqual(d.provider, "openai")
        self.assertTrue(d.degraded)

    def test_preset_no_keys_at_all(self):
        d = route("hero", "", env=KEYS_NONE, preset_preferred="openai")
        self.assertTrue(d.degraded)
        self.assertFalse(d.api_key_available)


class SingleKeyTests(unittest.TestCase):
    def test_only_openai_key(self):
        d = route("icon", "", env=KEYS_OPENAI_ONLY)
        self.assertEqual(d.provider, "openai")
        self.assertFalse(d.degraded)
        self.assertFalse(d.needs_user_choice)

    def test_only_gemini_key(self):
        d = route("hero", "", env=KEYS_GEMINI_ONLY)
        self.assertEqual(d.provider, "gemini")
        self.assertFalse(d.degraded)


class AmbiguityTests(unittest.TestCase):
    def test_both_keys_no_preference_sets_needs_user_choice(self):
        d = route("hero", "", env=KEYS_BOTH)
        self.assertTrue(d.needs_user_choice)
        self.assertTrue(d.api_key_available)

    def test_no_keys_no_preference(self):
        d = route("hero", "", env=KEYS_NONE)
        self.assertFalse(d.api_key_available)
        self.assertTrue(d.degraded)
        self.assertFalse(d.needs_user_choice)


class WarningsTests(unittest.TestCase):
    def test_gemini_with_text_context_warns(self):
        d = route("card", 'the text "Ship Fast"', env=KEYS_BOTH,
                  provider_override="gemini")
        self.assertTrue(any("text" in w.lower() for w in d.warnings))

    def test_gemini_with_hero_hint_warns(self):
        d = route("hero-home", "", env=KEYS_BOTH, provider_override="gemini")
        self.assertTrue(any("text" in w.lower() for w in d.warnings))

    def test_openai_never_gets_text_warning(self):
        d = route("hero-home", 'the text "Hello"', env=KEYS_BOTH,
                  provider_override="openai")
        self.assertFalse(any("text" in w.lower() for w in d.warnings))

    def test_gemini_transparent_warns_about_rembg(self):
        d = route("icon-cog", "", env=KEYS_BOTH, provider_override="gemini")
        self.assertTrue(any("transparent" in w.lower() or "rembg" in w.lower()
                            for w in d.warnings))


class PresetLoaderTests(unittest.TestCase):
    def test_read_preferred_provider_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_preferred_provider(Path(tmp)))

    def test_read_preferred_provider_valid_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".claude" / "brand-preset.json"
            p.parent.mkdir()
            p.write_text(json.dumps({"preferred_provider": "openai"}))
            self.assertEqual(read_preferred_provider(Path(tmp)), "openai")

    def test_read_preferred_provider_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".claude" / "brand-preset.json"
            p.parent.mkdir()
            p.write_text(json.dumps({"preferred_provider": "midjourney"}))
            self.assertIsNone(read_preferred_provider(Path(tmp)))

    def test_read_preferred_provider_null_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".claude" / "brand-preset.json"
            p.parent.mkdir()
            p.write_text(json.dumps({"preferred_provider": None}))
            self.assertIsNone(read_preferred_provider(Path(tmp)))


class ParamsTests(unittest.TestCase):
    def test_params_always_present(self):
        d = route("default-thing", "", env=KEYS_BOTH, provider_override="openai")
        self.assertIn("target_width", d.params)
        self.assertIn("generation_width", d.params)
        self.assertIn("quality", d.params)
        self.assertIn("transparent", d.params)

    def test_icon_params_transparent_regardless_of_provider(self):
        for provider in ("openai", "gemini"):
            d = route("icon-cog", "", env=KEYS_BOTH, provider_override=provider)
            self.assertTrue(d.params["transparent"],
                            f"icon should be transparent even for {provider}")


if __name__ == "__main__":
    unittest.main()
