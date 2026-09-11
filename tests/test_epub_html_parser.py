import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from split.chapter_splitter_novelpia_md import (
    EpubHTMLParser, parse_epub_chapter, parse_epub_sections, write_document_segments,
)


class EpubHtmlParserTests(unittest.TestCase):
    def test_svg_images_are_extracted_in_order_and_saved_unchanged(self):
        for image_tag in (
            '<image xlink:href="../Images/picture.webp"/>',
            '<image href="../Images/picture.webp"/>',
            '<svg:image xlink:href="../Images/picture.webp"/>',
            '<img src="../Images/picture.webp"/>',
        ):
            with self.subTest(image_tag=image_tag), zipfile.ZipFile(io.BytesIO(), 'w') as archive:
                archive.writestr('OEBPS/Text/chapter.xhtml',
                    '<html><body><p>Before<svg>' + image_tag + '</svg>After</p></body></html>')
                archive.writestr('OEBPS/Images/picture.webp', b'original-webp-bytes')
                _, elements = parse_epub_chapter(archive, 'OEBPS/', 'Text/chapter.xhtml')
                self.assertEqual([item['type'] for item in elements], ['text', 'image', 'text'])
                self.assertEqual(elements[0]['content'], 'Before')
                self.assertEqual(elements[2]['content'], 'After')
                self.assertEqual(elements[1]['zip_path'], 'OEBPS/Images/picture.webp')
                with tempfile.TemporaryDirectory() as folder:
                    raw, images = Path(folder) / 'raw', Path(folder) / 'image'
                    raw.mkdir()
                    images.mkdir()
                    write_document_segments(elements, 'Chapter', 0, 0, raw, images, 5000, archive)
                    saved = list(images.glob('*.webp'))
                    self.assertEqual(len(saved), 1)
                    self.assertEqual(saved[0].read_bytes(), b'original-webp-bytes')
                    self.assertIn(f'../image/{saved[0].name}', (raw / 'v0_c0_s1.md').read_text(encoding='utf-8'))

    def test_anchored_sections_keep_svg_images_and_surrounding_text(self):
        with zipfile.ZipFile(io.BytesIO(), 'w') as archive:
            archive.writestr('OEBPS/Text/chapter.xhtml', '''
                <html xmlns="http://www.w3.org/1999/xhtml"
                      xmlns:svg="http://www.w3.org/2000/svg"
                      xmlns:xlink="http://www.w3.org/1999/xlink"><body>
                <section id="one"><p>Before<svg:svg><svg:image xlink:href="../Images/picture.webp"/></svg:svg>After</p></section>
                <section id="two"><p>Before<svg:svg><svg:image href="../Images/picture.webp"/></svg:svg>After</p></section>
                </body></html>''')
            archive.writestr('OEBPS/Images/picture.webp', b'original-webp-bytes')
            sections = parse_epub_sections(archive, 'OEBPS/', 'Text/chapter.xhtml', {'one': 'One', 'two': 'Two'})
            self.assertEqual(len(sections), 2)
            for _, elements in sections:
                self.assertEqual([item['type'] for item in elements], ['text', 'image', 'text'])
                self.assertEqual(elements[0]['content'], 'Before')
                self.assertEqual(elements[2]['content'], 'After')
                self.assertEqual(elements[1]['zip_path'], 'OEBPS/Images/picture.webp')

    def test_keeps_text_after_self_closing_breaks_inside_long_paragraph(self):
        parser = EpubHTMLParser()
        parser.feed(
            "<html><body><h1>Tiêu đề</h1>"
            "<p>Đoạn đầu<br /><br />Đoạn giữa<br/>Đoạn cuối</p>"
            "</body></html>"
        )

        content = "\n".join(
            item["content"] for item in parser.elements if item["type"] == "text"
        )
        self.assertEqual(parser.title, "Tiêu đề")
        self.assertIn("Đoạn đầu", content)
        self.assertIn("Đoạn giữa", content)
        self.assertIn("Đoạn cuối", content)
        self.assertIn("Đoạn đầu\n\nĐoạn giữa", content)


if __name__ == "__main__":
    unittest.main()
