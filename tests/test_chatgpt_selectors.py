import unittest

from cores.dich_utils import (
    _find_visible_chatgpt_choice,
    _normalized_chatgpt_label,
)


class ChatGPTSelectorTests(unittest.TestCase):
    def test_normalizes_vietnamese_thinking_label(self):
        self.assertEqual(_normalized_chatgpt_label("  TỨC   THÌ  "), "tuc thi")

    def test_normalizes_model_label_spacing(self):
        self.assertEqual(_normalized_chatgpt_label("GPT-5.6  Sol"), "gpt-5.6 sol")

    def test_visible_choice_passes_normalized_aliases_to_page(self):
        class Driver:
            def execute_script(self, _script, keywords):
                self.keywords = keywords
                return "instant-button"

        driver = Driver()
        self.assertEqual(
            _find_visible_chatgpt_choice(driver, ["Tức thì", "Instant"]),
            "instant-button",
        )
        self.assertEqual(driver.keywords, ["tuc thi", "instant"])


if __name__ == "__main__":
    unittest.main()
