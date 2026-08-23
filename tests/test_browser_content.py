import unittest
from unittest.mock import patch

from cores.browser import content


class BrowserContentTests(unittest.TestCase):
    def test_chatgpt_setup_uses_configured_link(self):
        with patch.object(content, "option", return_value=" https://chatgpt.com/c/user-link "), patch.object(
            content.browser_runtime, "setup_chatgpt"
        ) as setup:
            content.setup_chatgpt_browser()

        self.assertEqual(setup.call_args.kwargs["link"], "https://chatgpt.com/c/user-link")

    def test_chatgpt_generation_uses_configured_link(self):
        with patch.object(content, "option", return_value="https://chatgpt.com/c/user-link"), patch.object(
            content.browser_runtime, "generate_chatgpt", return_value="ok"
        ) as generate:
            result = content.generate_content_with_chatgpt("prompt")

        self.assertEqual(result, "ok")
        self.assertEqual(generate.call_args.kwargs["link"], "https://chatgpt.com/c/user-link")


if __name__ == "__main__":
    unittest.main()
