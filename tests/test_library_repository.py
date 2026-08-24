import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import services.library.repository as repository

from services.library.repository import (
    chapter_images,
    chapters,
    projects,
    safe_file,
    safe_project,
    validate_new_project_name,
)
from services.library import LibraryService


class LibraryRepositoryTests(unittest.TestCase):
    def test_service_binds_library_root(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            (library / "Story" / "raw").mkdir(parents=True)
            service = LibraryService(library)

            self.assertEqual(["Story"], service.projects())
            self.assertEqual(library / "Story", service.safe_project("Story"))

    def test_lists_project_and_builds_chapter_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            project = library / "Truyện thử"
            raw = project / "raw"
            translated = project / "translated"
            raw.mkdir(parents=True)
            translated.mkdir()
            (raw / "v1_c2_s1.md").write_text(
                "# 第二章\n\n中文内容", encoding="utf-8"
            )
            (raw / "v1_c1_s1.md").write_text(
                "# 第一章\n\n更多中文", encoding="utf-8"
            )
            (translated / "v1_c1_s1.md").write_text(
                "# Chương một\n\nBản dịch", encoding="utf-8"
            )

            self.assertEqual(projects(library), ["Truyện thử"])
            items = chapters(library, "Truyện thử")
            self.assertEqual([item["name"] for item in items], ["v1_c1_s1.md", "v1_c2_s1.md"])
            self.assertEqual(items[0]["title"], "Chương một")
            self.assertEqual({item["word_unit"] for item in items}, {"ký tự"})

    def test_rejects_unsafe_names_and_existing_project(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            (library / "Existing" / "raw").mkdir(parents=True)
            with self.assertRaises(ValueError):
                safe_project(library, "../outside")
            with self.assertRaisesRegex(ValueError, "Windows"):
                validate_new_project_name(library, "CON")
            with self.assertRaisesRegex(ValueError, "đã tồn tại"):
                validate_new_project_name(library, "existing")
            with self.assertRaises(ValueError):
                safe_file(library, "../chapter.md")

    def test_chapter_metadata_cache_reuses_unchanged_files_and_invalidates_on_add(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            raw = library / "Story" / "raw"
            (library / "Story" / "translated").mkdir(parents=True)
            raw.mkdir()
            (raw / "v1_c1_s1.md").write_text("# One\n\nText", encoding="utf-8")

            with patch.object(
                repository, "read_live_utf8", wraps=repository.read_live_utf8
            ) as reader:
                self.assertEqual(1, len(chapters(library, "Story")))
                first_read_count = reader.call_count
                self.assertEqual(1, len(chapters(library, "Story")))
                self.assertEqual(first_read_count, reader.call_count)

                (raw / "v1_c2_s1.md").write_text("# Two\n\nMore text", encoding="utf-8")
                self.assertEqual(2, len(chapters(library, "Story")))
                self.assertGreater(reader.call_count, first_read_count)

    def test_returns_existing_local_and_remote_images(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            image = library / "Story" / "image"
            image.mkdir(parents=True)
            (image / "cover.png").write_bytes(b"png")
            result = chapter_images(
                library,
                "Story",
                "![Bìa](../image/cover.png)\n[img]https://example.com/a.jpg[/img]",
            )
            self.assertEqual(result[0]["id"], "cover")
            self.assertEqual(result[1]["url"], "https://example.com/a.jpg")


if __name__ == "__main__":
    unittest.main()
