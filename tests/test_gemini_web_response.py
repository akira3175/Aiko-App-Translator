import unittest

from cores.gemini.web_response import response_text, snapshot_conversation


class _Driver:
    def execute_script(self, _script, _token):
        return {"users": 2, "responses": 3}


class _Block:
    def __init__(self, text):
        self.text = text


class _Root:
    text = "fallback"

    def find_elements(self, _by, _selector):
        return [_Block("cũ"), _Block(""), _Block("mới")]


class GeminiWebResponseTests(unittest.TestCase):
    def test_snapshot_returns_existing_response_count(self):
        self.assertEqual(3, snapshot_conversation(_Driver(), "token"))

    def test_response_text_prefers_latest_nonempty_content_block(self):
        self.assertEqual("mới", response_text(_Root()))


if __name__ == "__main__":
    unittest.main()
