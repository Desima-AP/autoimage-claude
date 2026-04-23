"""Unit tests for scan_missing.py — no network, no image generation."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import scan_missing  # noqa: E402


class ScanSrcAttrsTests(unittest.TestCase):
    def _scan(self, content: str, file_name: str = "Home.tsx"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / file_name
            src.write_text(content, encoding="utf-8")
            findings = scan_missing.scan_file(root, src, content)
        return findings

    def test_empty_src_flagged(self):
        findings = self._scan('<img src="" alt="hero" />')
        kinds = {f["kind"] for f in findings}
        self.assertIn("empty_src", kinds)

    def test_placeholder_picsum_flagged(self):
        findings = self._scan('<img src="https://picsum.photos/1920/1080" />')
        self.assertTrue(any(f["kind"] == "placeholder_url" for f in findings))

    def test_placeholder_via_placeholder_flagged(self):
        findings = self._scan('<img src="https://via.placeholder.com/300" />')
        self.assertTrue(any(f["kind"] == "placeholder_url" for f in findings))

    def test_unsplash_random_flagged(self):
        findings = self._scan('<img src="https://source.unsplash.com/random/800x600" />')
        self.assertTrue(any(f["kind"] == "placeholder_url" for f in findings))

    def test_real_external_image_not_flagged(self):
        findings = self._scan('<img src="https://cdn.example.com/real-hero.jpg" />')
        self.assertEqual(findings, [])

    def test_unresolvable_jsx_expression_skipped(self):
        findings = self._scan("<img src={hero.url} />")
        self.assertEqual(findings, [])

    def test_missing_local_file_flagged(self):
        findings = self._scan('<img src="./does-not-exist.png" />')
        kinds = {f["kind"] for f in findings}
        self.assertIn("missing_file", kinds)

    def test_css_placeholder_url_flagged(self):
        findings = self._scan(
            ".hero { background-image: url('https://picsum.photos/1920/1080'); }",
            file_name="styles.css",
        )
        self.assertTrue(any(f["kind"] == "placeholder_url" for f in findings))

    def test_css_data_uri_skipped(self):
        findings = self._scan(
            ".icon { background-image: url('data:image/svg+xml;base64,abc='); }",
            file_name="styles.css",
        )
        self.assertEqual(findings, [])

    def test_todo_comment_flagged(self):
        findings = self._scan("// TODO: replace hero image with a real one")
        self.assertTrue(any(f["kind"] == "todo_comment" for f in findings))

    def test_import_missing_asset_flagged(self):
        findings = self._scan("import hero from './missing-hero.png';\nconsole.log(hero);")
        self.assertTrue(any(f["kind"] == "missing_file" for f in findings))


class StableIdTests(unittest.TestCase):
    def test_same_inputs_produce_same_id(self):
        a = scan_missing.stable_id("src/Home.tsx", "empty_src", "", 10)
        b = scan_missing.stable_id("src/Home.tsx", "empty_src", "", 10)
        self.assertEqual(a, b)

    def test_different_inputs_produce_different_ids(self):
        a = scan_missing.stable_id("src/Home.tsx", "empty_src", "", 10)
        b = scan_missing.stable_id("src/About.tsx", "empty_src", "", 10)
        self.assertNotEqual(a, b)


class PendingPersistenceTests(unittest.TestCase):
    def test_save_and_reload_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / ".claude" / "pending-assets.json"
            data = {"version": 1, "updated_at": None,
                    "assets": [{"id": "abc", "source_file": "Home.tsx"}]}
            scan_missing.save_pending(path, data)
            loaded = scan_missing.load_pending(path)
            self.assertEqual(loaded["assets"][0]["id"], "abc")
            self.assertIsNotNone(loaded["updated_at"])

    def test_rescan_replaces_entries_for_same_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "Home.tsx"

            # First scan: placeholder
            src.write_text('<img src="https://picsum.photos/100" />', encoding="utf-8")
            hook_input = {
                "tool_input": {"file_path": str(src)},
                "cwd": str(root),
            }
            os.environ.pop("CLAUDE_PROJECT_DIR", None)

            # Simulate main() by piping stdin
            import io
            old_stdin = sys.stdin
            try:
                sys.stdin = io.StringIO(json.dumps(hook_input))
                scan_missing.main()

                pending_file = root / ".claude" / "pending-assets.json"
                first = json.loads(pending_file.read_text())
                self.assertEqual(len(first["assets"]), 1)

                # Second scan: placeholder removed
                src.write_text('<img src="/images/real-hero.png" />', encoding="utf-8")
                sys.stdin = io.StringIO(json.dumps(hook_input))
                scan_missing.main()
                second = json.loads(pending_file.read_text())
                # /images/real-hero.png doesn't exist → now reported as missing_file
                self.assertEqual(len(second["assets"]), 1)
                self.assertEqual(second["assets"][0]["kind"], "missing_file")
            finally:
                sys.stdin = old_stdin


if __name__ == "__main__":
    unittest.main()
