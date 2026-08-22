import unittest
from unittest.mock import patch

from cores.browser import content
from cores.chatgpt.web_response import snapshot_conversation


class _Driver:
    def execute_script(self, _script, _token):
        return {"users": 1, "assistants": 4}


class ChatGPTWebClientTests(unittest.TestCase):
    def test_snapshot_returns_existing_assistant_count(self):
        self.assertEqual(4, snapshot_conversation(_Driver(), "token"))

    def test_compatibility_wrapper_forwards_runtime_configuration(self):
        with patch.object(
            content, "generate_chatgpt_content", return_value="result"
        ) as generate:
            original = content.browser_runtime._chatgpt_generate
            content.browser_runtime._chatgpt_generate = generate
            result = content.generate_content_with_chatgpt(
                "prompt",
                max_retries=2,
                chatgpt_model="gpt-test",
                chatgpt_thinking="high",
                chat_url="https://chatgpt.com/c/test",
            )
            content.browser_runtime._chatgpt_generate = original

        self.assertEqual("result", result)
        generate.assert_called_once_with(
            "prompt",
            get_driver=content.browser_runtime.get_chatgpt_driver,
            close_driver=content.browser_runtime.close_chatgpt,
            link=content.LINK_CHATGPT,
            default_model=content.CHATGPT_SELECT_MODEL,
            default_thinking=content.CHATGPT_SELECT_THINKING,
            max_retries=2,
            chatgpt_model="gpt-test",
            chatgpt_thinking="high",
            chat_url="https://chatgpt.com/c/test",
        )


if __name__ == "__main__":
    unittest.main()
