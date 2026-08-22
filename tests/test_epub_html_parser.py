import unittest

from split.chapter_splitter_novelpia_md import EpubHTMLParser


class EpubHtmlParserTests(unittest.TestCase):
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
