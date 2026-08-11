import unittest

from cores.dich_utils import build_translation_review_prompt
from cores.review_all import build_review_prompt, prepare_review_item


class ReviewAllTests(unittest.TestCase):
    def test_review_item_keeps_full_raw_and_translation(self):
        raw = "中" * 9000 + "RAW_END"
        translation = "bản dịch " * 2000 + "TRANSLATION_END"
        item = prepare_review_item({
            "id": "v1_c174_s1",
            "raw_title": "原题",
            "raw_content": raw,
            "title_translation": "Tiêu đề",
            "translation": translation,
        })
        self.assertEqual(item[3], raw)
        self.assertEqual(item[5], translation)
        self.assertTrue(item[3].endswith("RAW_END"))
        self.assertTrue(item[5].endswith("TRANSLATION_END"))

    def test_prompt_is_language_neutral_and_contains_both_ends(self):
        prompt = build_review_prompt("v1_c1_s1", 1, "原题", "开头 RAW_END", "Tiêu đề", "Mở đầu TRANSLATION_END")
        self.assertIn("ngôn ngữ nguồn bất kỳ sang tiếng Việt", prompt)
        self.assertIn("RAW_END", prompt)
        self.assertIn("TRANSLATION_END", prompt)
        self.assertNotIn("Hàn-Việt", prompt)
        self.assertNotIn("bản gốc tiếng Hàn", prompt)

    def test_review_all_uses_exact_background_review_prompt(self):
        arguments = ("v1_c2_s1", 2, "原题", "原文", "Tiêu đề", "Bản dịch", "glossary")
        self.assertEqual(build_review_prompt(*arguments), build_translation_review_prompt(*arguments))


if __name__ == "__main__":
    unittest.main()
