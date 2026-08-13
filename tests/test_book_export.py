import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree
from PIL import Image

import app


class BookExportTests(unittest.TestCase):
    def project(self, root: Path):
        project = root / "Truyện thử"
        raw = project / "raw"
        translated = project / "translated"
        raw.mkdir(parents=True)
        translated.mkdir()
        image = project / "image"
        image.mkdir()
        Image.new("RGB", (200, 100), "blue").save(image / "minh-hoa.png")
        (raw / "v1_c1_s1.md").write_text("# Chương một\n\n原文 một", encoding="utf-8")
        (translated / "v1_c1_s1.md").write_text("# Chương một\n\nBản dịch một\n\n![Minh họa](../image/minh-hoa.png)", encoding="utf-8")
        (raw / "v2_c2_s1.md").write_text("# Chương hai\n\n原文 hai", encoding="utf-8")
        (translated / "v2_c2_s1.md").write_text("# Chương hai\n\nBản dịch hai", encoding="utf-8")
        return project

    def test_markdown_export_respects_volume(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(app, "LIBRARY", Path(directory)):
            self.project(Path(directory))
            body, content_type, filename = app.export_book(
                "Truyện thử",
                {"format": "markdown", "source": "translated", "scope": "volume", "volume": 2},
            )
            text = body.decode("utf-8")
            self.assertIn("Bản dịch hai", text)
            self.assertNotIn("Bản dịch một", text)
            self.assertEqual(content_type, "text/markdown; charset=utf-8")
            self.assertTrue(filename.endswith(".md"))

    def test_epub_has_required_container_and_navigation(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(app, "LIBRARY", Path(directory)):
            self.project(Path(directory))
            body, content_type, _ = app.export_book(
                "Truyện thử", {"format": "epub", "source": "translated", "scope": "all"}
            )
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                self.assertEqual(archive.namelist()[0], "mimetype")
                self.assertEqual(archive.read("mimetype"), b"application/epub+zip")
                self.assertIn("OEBPS/nav.xhtml", archive.namelist())
                self.assertIn("Bản dịch một", archive.read("OEBPS/chapter-1.xhtml").decode("utf-8"))
                self.assertIn("OEBPS/images/image-1.png", archive.namelist())
            self.assertEqual(content_type, "application/epub+zip")

    def test_docx_is_valid_ooxml_zip(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(app, "LIBRARY", Path(directory)):
            self.project(Path(directory))
            body, content_type, filename = app.export_book(
                "Truyện thử", {"format": "docx", "source": "bilingual", "scope": "range", "from": "v1_c1_s1.md", "to": "v1_c1_s1.md"}
            )
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                self.assertIn("word/document.xml", archive.namelist())
                document = archive.read("word/document.xml")
                ElementTree.fromstring(document)
                self.assertIn("Bản dịch một".encode("utf-8"), document)
                self.assertIn("原文 một".encode("utf-8"), document)
                self.assertIn("word/media/image1.png", archive.namelist())
                self.assertIn(b"relationships/image", archive.read("word/_rels/document.xml.rels"))
                self.assertIn(b'cx="5257800" cy="2628900"', document)
            self.assertTrue(filename.endswith(".docx"))
            self.assertIn("wordprocessingml", content_type)


if __name__ == "__main__":
    unittest.main()
