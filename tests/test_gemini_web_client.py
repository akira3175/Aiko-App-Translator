import unittest
from unittest.mock import patch

from cores.browser import content
from cores.gemini.web_client import (
    _has_end_marker,
    _is_known_structured_response,
    _task_mode_enabled,
    normalize_web_model,
)


class GeminiWebClientTests(unittest.TestCase):
    def test_flash_and_fast_names_use_flash_mode(self):
        self.assertEqual(normalize_web_model("flash"), "flash")
        self.assertEqual(normalize_web_model("Fast"), "flash")
        self.assertEqual(normalize_web_model("Gemini 3 Flash"), "flash")

    def test_argon_names_use_thinking_mode(self):
        self.assertEqual(normalize_web_model("argon"), "thinking")
        self.assertEqual(normalize_web_model("4 Argon"), "thinking")
        self.assertEqual(normalize_web_model("Gemini Argon"), "thinking")

    def test_compatibility_wrapper_forwards_runtime_configuration(self):
        with patch.object(
            content, "generate_gemini_content", return_value="result"
        ) as generate:
            original = content.browser_runtime._gemini_generate
            content.browser_runtime._gemini_generate = generate
            result = content.generate_content_with_selenium(
                "prompt",
                max_retries=2,
                web_model="thinking",
                thinking_level="high",
            )
            content.browser_runtime._gemini_generate = original

        self.assertEqual("result", result)
        generate.assert_called_once_with(
            "prompt",
            get_driver=content.browser_runtime.get_gemini_driver,
            link=content.LINK_GEMINI,
            default_thinking=content.WEB_THINKING_LEVEL,
            max_retries=2,
            web_model="thinking",
            thinking_level="high",
        )

    def test_has_end_marker_detects_standard_and_character_markers(self):
        self.assertTrue(_has_end_marker("Văn bản kết thúc bằng ###END###"))
        self.assertTrue(_has_end_marker("Hồ sơ kết thúc bằng ###CHAR_END###"))
        self.assertFalse(_has_end_marker("Chỉ có ###TITLE### và ###CONTENT###"))
        self.assertFalse(_has_end_marker("Văn bản bình thường 257 ký tự"))

    def test_is_known_structured_response_identifies_json(self):
        self.assertTrue(
            _is_known_structured_response('{"character_pairs": [{"name": "A"}]}')
        )
        self.assertTrue(
            _is_known_structured_response('{"overall_score": 9.5, "issues": []}')
        )
        self.assertFalse(_is_known_structured_response("Chỉ là văn bản thường"))

    def test_task_mode_enabled_reads_explicit_and_configured_values(self):
        self.assertTrue(_task_mode_enabled("on"))
        self.assertTrue(_task_mode_enabled(True))
        self.assertFalse(_task_mode_enabled("off"))
        self.assertFalse(_task_mode_enabled(False))
        with patch("cores.gemini.web_client.option", return_value="on"):
            self.assertTrue(_task_mode_enabled())
        with patch("cores.gemini.web_client.option", return_value="off"):
            self.assertFalse(_task_mode_enabled())



if __name__ == "__main__":
    unittest.main()
