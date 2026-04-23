"""Unit tests for post_process.py — exercises resize/crop + output detection."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PIL_AVAILABLE = False

if PIL_AVAILABLE:
    import post_process


@unittest.skipUnless(PIL_AVAILABLE, "Pillow not installed")
class PostProcessTests(unittest.TestCase):
    def _gen_bytes(self, w: int, h: int, transparent: bool = False) -> bytes:
        if transparent:
            img = Image.new("RGBA", (w, h), (0, 128, 255, 128))
        else:
            img = Image.new("RGB", (w, h), (10, 95, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_resize_hero_upscales_to_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = post_process.process(
                self._gen_bytes(1536, 1024),
                target_w=1920, target_h=1080,
                project_root=root,
                filename_stem="hero",
                transparent=False,
            )
            self.assertTrue(result.png_path.exists())
            self.assertTrue(result.webp_path.exists())
            with Image.open(result.png_path) as img:
                self.assertEqual(img.size, (1920, 1080))

    def test_og_crop_preserves_target_aspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = post_process.process(
                self._gen_bytes(1536, 1024),
                target_w=1200, target_h=630,
                project_root=root,
                filename_stem="og-image",
                transparent=False,
            )
            with Image.open(result.png_path) as img:
                self.assertEqual(img.size, (1200, 630))

    def test_transparent_icon_preserves_alpha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = post_process.process(
                self._gen_bytes(1024, 1024, transparent=True),
                target_w=512, target_h=512,
                project_root=root,
                filename_stem="icon-bell",
                transparent=True,
            )
            with Image.open(result.png_path) as img:
                self.assertEqual(img.mode, "RGBA")
                self.assertEqual(img.size, (512, 512))

    def test_auto_output_dir_prefers_existing_public_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "public" / "images").mkdir(parents=True)
            result = post_process.process(
                self._gen_bytes(1024, 1024),
                target_w=512, target_h=512,
                project_root=root,
                filename_stem="test",
                transparent=False,
            )
            self.assertEqual(result.png_path.parent, root / "public" / "images")

    def test_auto_output_dir_prefers_src_assets_when_public_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "assets" / "images").mkdir(parents=True)
            result = post_process.process(
                self._gen_bytes(1024, 1024),
                target_w=512, target_h=512,
                project_root=root,
                filename_stem="test",
                transparent=False,
            )
            self.assertEqual(result.png_path.parent, root / "src" / "assets" / "images")

    def test_auto_output_dir_creates_public_images_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = post_process.process(
                self._gen_bytes(1024, 1024),
                target_w=512, target_h=512,
                project_root=root,
                filename_stem="test",
                transparent=False,
            )
            self.assertEqual(result.png_path.parent, root / "public" / "images")
            self.assertTrue((root / "public" / "images").exists())

    def test_overwrite_vs_unique_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out1 = post_process.process(
                self._gen_bytes(1024, 1024), target_w=512, target_h=512,
                project_root=root, filename_stem="hero", transparent=False,
            )
            out2 = post_process.process(
                self._gen_bytes(1024, 1024), target_w=512, target_h=512,
                project_root=root, filename_stem="hero", transparent=False,
            )
            self.assertNotEqual(out1.png_path, out2.png_path)
            self.assertTrue(out2.png_path.name.startswith("hero-2"))

            out3 = post_process.process(
                self._gen_bytes(1024, 1024), target_w=512, target_h=512,
                project_root=root, filename_stem="hero", transparent=False,
                overwrite=True,
            )
            self.assertEqual(out3.png_path, out1.png_path)


if __name__ == "__main__":
    unittest.main()
