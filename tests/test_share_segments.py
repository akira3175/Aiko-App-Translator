import tempfile
import unittest
from pathlib import Path

import app


class ShareSegmentTests(unittest.TestCase):
    def test_groups_and_merges_segments_in_numeric_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            segment_two = root / "v1_c7_s2.md"
            segment_one = root / "v1_c7_s1.md"
            segment_two.write_text("# Tiêu đề phần 2\n\nNội dung hai.", encoding="utf-8")
            segment_one.write_text("# Chương bảy\n\nNội dung một.", encoding="utf-8")

            groups = app._share_chapter_groups([segment_two, segment_one])

            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["name"], "v1_c7.md")
            self.assertEqual([path.name for path in groups[0]["paths"]], ["v1_c7_s1.md", "v1_c7_s2.md"])
            content, title = app._share_merged_markdown(groups[0]["paths"])
            self.assertEqual(title, "Chương bảy")
            self.assertEqual(content, "# Chương bảy\n\nNội dung một.\n\nNội dung hai.")
            self.assertNotIn("Tiêu đề phần 2", content)

    def test_recognizes_old_segment_and_new_merged_names_as_same_chapter(self):
        self.assertEqual(app._share_chapter_identity("v2_c10_s3.md"), (2, 10))
        self.assertEqual(app._share_chapter_identity("v2_c10.md"), (2, 10))
        self.assertIsNone(app._share_chapter_identity("ghi-chu.md"))


if __name__ == "__main__":
    unittest.main()
