import tempfile
import unittest
from pathlib import Path

from cores.chapters.files import (
    export_recent_translations,
    has_foreign,
    load_md_chapter,
    save_translated_md,
    scan_md_dir,
)


class ChapterFilesTests(unittest.TestCase):
    def test_scan_and_load_markdown_chapters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "v2_c1_s1.md").write_text("# Sau\n\nNội dung", encoding="utf-8")
            first = root / "v1_c2_s1.md"
            first.write_text("# Trước\n\nĐoạn một\n\n![ảnh](a.jpg)\n\nĐoạn hai", encoding="utf-8")

            paths = scan_md_dir(directory)
            self.assertEqual(["v1_c2_s1.md", "v2_c1_s1.md"], [Path(path).name for path in paths])

            chapter = load_md_chapter(first)
            self.assertEqual("Trước", chapter["title"])
            self.assertEqual("Đoạn một\n\nĐoạn hai", chapter["content"])
            self.assertEqual("image", chapter["_elements"][1]["type"])

    def test_detects_supported_foreign_scripts(self):
        self.assertTrue(has_foreign("中文"))
        self.assertTrue(has_foreign("한국어"))
        self.assertTrue(has_foreign("ภาษาไทย"))
        self.assertFalse(has_foreign("Tiếng Việt"))

    def test_ignores_kaomoji_without_hiding_real_source_text(self):
        self.assertFalse(has_foreign("(　-`ω-)✧ (╬￣皿￣) (•́ω•̀ ٥)"))
        self.assertFalse(has_foreign("Được rồi (╬￣皿￣)!"))
        self.assertTrue(has_foreign("(中文)"))
        self.assertTrue(has_foreign("Nội dung 中文 (╬￣皿￣)"))

    def test_save_restores_images_and_export_stops_before_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            translated = root / "translated"
            raw.mkdir()
            translated.mkdir()
            source = raw / "v1_c1_s1.md"
            source.write_text("# Gốc\n\nĐoạn\n\n![ảnh](a.jpg)", encoding="utf-8")
            saved = Path(
                save_translated_md(source, translated, "Dịch", "Nội dung")
            )
            self.assertIn("![ảnh](a.jpg)", saved.read_text(encoding="utf-8"))
            (translated / "v1_c2_s1.md").write_text("# Sau", encoding="utf-8")

            output = root / "context.txt"
            export_recent_translations(
                raw, translated, output, target_chapter_id="v1_c2_s1"
            )
            context = output.read_text(encoding="utf-8")
            self.assertIn("# Dịch", context)
            self.assertNotIn("# Sau", context)


if __name__ == "__main__":
    unittest.main()
