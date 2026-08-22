import unittest
from unittest.mock import patch

from cores.gemini.api_client import generate_content


class _Models:
    def __init__(self):
        self.request = None

    def generate_content(self, **request):
        self.request = request
        return type("Response", (), {"text": "kết quả"})()


class GeminiApiClientTests(unittest.TestCase):
    def test_builds_chat_parts_and_explicit_token_limit(self):
        client = type("Client", (), {"models": _Models()})()
        with patch("cores.gemini.api_client.option", return_value=""):
            result = generate_content(
                client,
                "prompt",
                "gemini-test",
                max_output_tokens=123,
                as_chat_parts=True,
                extra_parts=[{"text": "attachment"}],
                thinking_level="auto",
            )

        self.assertEqual("kết quả", result)
        self.assertEqual("gemini-test", client.models.request["model"])
        self.assertEqual(
            [{"text": "prompt"}, {"text": "attachment"}],
            client.models.request["contents"][0]["parts"],
        )
        self.assertEqual(123, client.models.request["config"].max_output_tokens)


if __name__ == "__main__":
    unittest.main()
