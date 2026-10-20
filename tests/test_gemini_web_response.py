import unittest
from unittest.mock import patch

from cores.gemini.web_response import (
    copy_response_text,
    response_text,
    snapshot_conversation,
)


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

    def test_copy_response_text_clicks_new_gemini_copy_button_and_restores_clipboard(self):
        class _Clipboard:
            def __init__(self):
                self.value = "user-original"

            def paste(self):
                return self.value

            def copy(self, text):
                self.value = text

        class _CopyBtn:
            tag_name = "button"

            def __init__(self, clipboard, aria_label="Sao chép"):
                self.clipboard = clipboard
                self.aria_label = aria_label
                self.clicked = False

            def is_displayed(self):
                return True

            def is_enabled(self):
                return True

            def get_attribute(self, name):
                if name == "aria-label":
                    return self.aria_label
                return ""

            def find_elements(self, _by, _selector):
                return []

        class _ResponseRoot:
            tag_name = "model-response"

            def __init__(self, btn):
                self.btn = btn

            def find_elements(self, _by, selector):
                if 'gemtooltip*="Sao chép câu trả lời"' in selector or 'jslog^="178035;"' in selector:
                    return [self.btn]
                return []

        class _CopyDriver:
            def __init__(self, btn):
                self.btn = btn

            def execute_script(self, script, *args):
                if "arguments[0].click();" in script and args and args[0] is self.btn:
                    self.btn.clicked = True
                    self.btn.clipboard.copy("**Markdown** đã sao chép\n###END###")
                return None

        clipboard = _Clipboard()
        btn = _CopyBtn(clipboard)
        root = _ResponseRoot(btn)
        driver = _CopyDriver(btn)

        with patch("cores.gemini.web_response.time.sleep"):
            result = copy_response_text(driver, root, clipboard=clipboard)

        self.assertTrue(btn.clicked)
        self.assertEqual("**Markdown** đã sao chép\n###END###", result)
        self.assertEqual("user-original", clipboard.paste())

    def test_copy_response_text_ignores_old_responses_marked_with_token(self):
        class _Clipboard:
            value = "initial"

            def paste(self):
                return self.value

            def copy(self, text):
                self.value = text

        class _OldBtn:
            tag_name = "button"
            clicked = False

            def is_displayed(self):
                return True

            def is_enabled(self):
                return True

            def get_attribute(self, name):
                if name == "aria-label":
                    return "Sao chép"
                return ""

            def find_elements(self, _by, xpath):
                if "data-novel-before-response='token-123'" in xpath:
                    return [old_container]
                return []

        class _OldContainer:
            tag_name = "model-response"

            def __init__(self, btn):
                self.btn = btn

            def get_attribute(self, name):
                if name == "data-novel-before-response":
                    return "token-123"
                return ""

            def find_elements(self, _by, _selector):
                return [self.btn]

        class _EmptyNewRoot:
            tag_name = "model-response"

            def get_attribute(self, _name):
                return ""

            def find_elements(self, _by, _selector):
                return []

        class _DriverWithMultipleResponses:
            def __init__(self, old_container):
                self.old_container = old_container

            def find_elements(self, _by, _selector):
                return [self.old_container]

            def execute_script(self, _script, *_args):
                return None

        old_btn = _OldBtn()
        old_container = _OldContainer(old_btn)
        new_root = _EmptyNewRoot()
        driver = _DriverWithMultipleResponses(old_container)

        with patch("cores.gemini.web_response.time.sleep"):
            result = copy_response_text(
                driver, new_root, clipboard=_Clipboard(), token="token-123"
            )

        self.assertIsNone(result)
        self.assertFalse(old_btn.clicked)

    def test_copy_response_text_reads_js_hook_when_browser_unfocused(self):
        class _Clipboard:
            value = "unchanged-os-clipboard"

            def paste(self):
                return self.value

            def copy(self, text):
                self.value = text

        class _Btn:
            tag_name = "button"
            clicked = False

            def is_displayed(self):
                return True

            def is_enabled(self):
                return True

            def get_attribute(self, name):
                return "Sao chép" if name == "aria-label" else ""

            def find_elements(self, _by, _selector):
                return []

            def click(self):
                self.clicked = True

        class _Root:
            tag_name = "model-response"

            def __init__(self, btn):
                self.btn = btn

            def get_attribute(self, _name):
                return ""

            def find_elements(self, _by, _selector):
                return [self.btn]

        class _HookDriver:
            def __init__(self, btn):
                self.btn = btn

            def execute_script(self, script, *_args):
                if "return window.__aikoGeminiCopiedText;" in script and self.btn.clicked:
                    return "###TITLE### Chương 1\n###CONTENT### Nội dung\n###END###"
                return None

        btn = _Btn()
        clipboard = _Clipboard()
        with patch("cores.gemini.web_response.time.sleep"):
            result = copy_response_text(
                _HookDriver(btn), _Root(btn), clipboard=clipboard, token="tok-1"
            )

        self.assertTrue(btn.clicked)
        self.assertEqual(
            "###TITLE### Chương 1\n###CONTENT### Nội dung\n###END###", result
        )
        self.assertEqual("unchanged-os-clipboard", clipboard.paste())


if __name__ == "__main__":
    unittest.main()
