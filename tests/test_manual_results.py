import unittest

from cores.manual import parse_manual_result_text


class ManualResultTests(unittest.TestCase):
    def test_parses_valid_result(self):
        text = "###TITLE###\nTiêu đề\n###CONTENT###\nNội dung\n###END###"
        self.assertEqual(parse_manual_result_text(text), ("Tiêu đề", "Nội dung"))

    def test_rejects_blank_and_placeholder_results(self):
        for text in (
            "###TITLE###\n\n###CONTENT###\nNội dung",
            "###TITLE###\n<tiêu đề dịch>\n###CONTENT###\nNội dung",
            "###TITLE###\nTiêu đề\n###CONTENT###\n<translated content>",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_manual_result_text(text)


if __name__ == "__main__":
    unittest.main()
