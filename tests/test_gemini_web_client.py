import unittest
from unittest.mock import patch

from cores.browser import content
from cores.gemini.web_client import normalize_web_model


class GeminiWebClientTests(unittest.TestCase):
    def test_flash_and_fast_names_use_flash_mode(self):
        self.assertEqual(normalize_web_model("flash"), "flash")
        self.assertEqual(normalize_web_model("Fast"), "flash")
        self.assertEqual(normalize_web_model("Gemini 3 Flash"), "flash")

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


if __name__ == "__main__":
    unittest.main()
