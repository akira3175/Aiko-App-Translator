import tempfile
import unittest
from pathlib import Path

from up.up_md import parse_md_file


class HakoUploadTests(unittest.TestCase):
    def test_parse_removes_first_body_line_when_it_repeats_title(self):
        title = "[Thông Báo] ✋❗ Minh Họa Bìa Mới!"
        with tempfile.TemporaryDirectory() as directory:
            chapter = Path(directory) / "v1_c1_s1.md"
            chapter.write_text(
                f"# {title}\n\n{title}\nNội dung thật.", encoding="utf-8"
            )
            parsed = parse_md_file(chapter)

        self.assertEqual(title, parsed["title"])
        self.assertEqual(
            [{"type": "text", "content": "Nội dung thật."}], parsed["elements"]
        )

    def test_parse_keeps_first_body_line_when_it_differs_from_title(self):
        with tempfile.TemporaryDirectory() as directory:
            chapter = Path(directory) / "v1_c1_s1.md"
            chapter.write_text(
                "# Tiêu đề\n\nMở đầu khác.\nNội dung.", encoding="utf-8"
            )
            parsed = parse_md_file(chapter)

        self.assertEqual(
            "Mở đầu khác.\nNội dung.", parsed["elements"][0]["content"]
        )


if __name__ == "__main__":
    unittest.main()
