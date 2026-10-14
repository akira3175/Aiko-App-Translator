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

    def test_response_text_prefers_block_with_end_marker(self):
        class _CustomRoot:
            text = "fallback"

            def find_elements(self, _by, _selector):
                return [
                    _Block("###TITLE### Tiêu đề\n###CONTENT### Nội dung\n###END###"),
                    _Block("Đoạn phụ sau cùng"),
                ]

        self.assertIn("###END###", response_text(_CustomRoot()))

    def test_response_text_prefers_longest_block_containing_end_marker(self):
        class _CustomRoot:
            text = "fallback"

            def find_elements(self, _by, _selector):
                return [
                    _Block("###TITLE### Full\n###CONTENT### Rất dài...\n###END###"),
                    _Block("ngắn ###END###"),
                ]

        self.assertEqual(
            "###TITLE### Full\n###CONTENT### Rất dài...\n###END###",
            response_text(_CustomRoot()),
        )

    def test_response_text_prefers_longest_during_streaming_to_avoid_short_fragment(self):
        class _CustomRoot:
            text = "fallback"

            def find_elements(self, _by, _selector):
                return [
                    _Block("###TITLE### Tiêu đề\n###CONTENT### Đoạn 1 dài 5000 ký tự..."),
                    _Block("Đoạn 2 chỉ 257 ký tự"),
                ]

        self.assertEqual(
            "###TITLE### Tiêu đề\n###CONTENT### Đoạn 1 dài 5000 ký tự...",
            response_text(_CustomRoot()),
        )

    def test_response_text_falls_back_to_root_text_if_root_has_end(self):
        class _CustomRoot:
            text = "###TITLE### A\n###CONTENT### B\n###END###"

            def find_elements(self, _by, _selector):
                return [_Block("thiếu end marker")]

        self.assertEqual(
            "###TITLE### A\n###CONTENT### B\n###END###",
            response_text(_CustomRoot()),
        )


if __name__ == "__main__":
    unittest.main()
