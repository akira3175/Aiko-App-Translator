import unittest

from cores.google_ai_studio.web_client import (
    _prompt_url,
    _copy_response_as_markdown,
    _is_ui_chrome,
    _paste_parts,
    _select_thinking_level,
    _set_prompt,
    _turn_text,
)
from providers import ProviderRequest
from providers.google_ai_studio_web import GoogleAiStudioWebProvider


class _Element:
    text = "TIẾNG VIỆT OK"

    def is_displayed(self):
        return True

    def get_attribute(self, _name):
        return ""


class _Turn:
    text = "Model\nFallback"

    def find_elements(self, _by, _selector):
        return [_Element()]


class _MultipleNodeTurn:
    text = "Model fallback"

    def find_elements(self, _by, _selector):
        content = _Element()
        content.text = '{"summary": "Bản review hợp lệ"}'
        controls = _Element()
        controls.text = "thumb_up\nthumb_down"
        return [content, controls]


class _Driver:
    def __init__(self):
        self.args = None

    def execute_script(self, _script, *args):
        self.args = args


class _Clipboard:
    def __init__(self, value):
        self.value = value

    def paste(self):
        return self.value

    def copy(self, value):
        self.value = value


class _PasteInput:
    def __init__(self, clipboard):
        self.clipboard = clipboard
        self.pasted = []

    def send_keys(self, *_keys):
        self.pasted.append(self.clipboard.paste())


class _Button(_Element):
    def __init__(self, text="", aria=""):
        self.text = text
        self.aria = aria

    def get_attribute(self, name):
        return self.aria if name == "aria-label" else ""


class _CopyTurn:
    def __init__(self):
        self.options = _Button(aria="Open options")

    def find_elements(self, _by, _selector):
        return [self.options]


class _CopyDriver:
    def __init__(self, clipboard):
        self.clipboard = clipboard
        self.copy_button = _Button("markdown_copy\nCopy as markdown")

    def find_elements(self, _by, _selector):
        return [self.copy_button]

    def execute_script(self, _script, element):
        if element is self.copy_button:
            self.clipboard.copy("###TITLE###\nThử\n\n###CONTENT###\nNội dung")


class GoogleAiStudioWebTests(unittest.TestCase):
    def test_unicode_prompt_is_passed_to_browser_script_unchanged(self):
        driver = _Driver()
        input_area = object()
        prompt = "Dịch chính xác tiếng Việt"
        _set_prompt(driver, input_area, prompt)
        self.assertEqual(driver.args, (input_area, prompt))

    def test_prompt_and_reference_are_pasted_as_separate_parts(self):
        clipboard = _Clipboard("clipboard cũ")
        input_area = _PasteInput(clipboard)
        _paste_parts(input_area, ["prompt", "\n\n## Reference file: characters.md\n\nNhân vật"], clipboard)
        self.assertEqual(
            input_area.pasted,
            ["prompt", "\n\n## Reference file: characters.md\n\nNhân vật"],
        )
        self.assertEqual(clipboard.value, "clipboard cũ")

    def test_extracts_rendered_model_markdown(self):
        self.assertEqual(_turn_text(_Turn()), "TIẾNG VIỆT OK")

    def test_dom_fallback_chooses_content_instead_of_feedback_buttons(self):
        self.assertEqual(
            _turn_text(_MultipleNodeTurn()),
            '{"summary": "Bản review hợp lệ"}',
        )
        self.assertTrue(_is_ui_chrome("thumb_up\nthumb_down"))
        self.assertFalse(_is_ui_chrome('{"summary": "ok"}'))

    def test_copy_as_markdown_preserves_unicode_and_restores_clipboard(self):
        clipboard = _Clipboard("nội dung clipboard cũ")
        driver = _CopyDriver(clipboard)
        copied = _copy_response_as_markdown(driver, _CopyTurn(), clipboard)
        self.assertIn("###TITLE###\nThử", copied)
        self.assertEqual(clipboard.value, "nội dung clipboard cũ")

    def test_model_is_passed_through_query_string(self):
        self.assertEqual(
            _prompt_url("gemini-3.7-flash"),
            "https://aistudio.google.com/prompts/new_chat?model=gemini-3.7-flash",
        )
        self.assertEqual(
            _prompt_url(""),
            "https://aistudio.google.com/prompts/new_chat?model=gemini-flash-latest",
        )
        self.assertEqual(_prompt_url("current"), _prompt_url("gemini-flash-latest"))

    def test_rejects_unknown_thinking_level(self):
        with self.assertRaisesRegex(ValueError, "low, medium hoặc high"):
            _select_thinking_level(None, "maximum")

    def test_provider_includes_reference_documents(self):
        calls = []
        provider = GoogleAiStudioWebProvider(
            lambda prompt, **kwargs: calls.append((prompt, kwargs)) or "ok"
        )
        response = provider.generate(
            ProviderRequest(
                stage="translate",
                prompt="prompt",
                model="gemini-flash-latest",
                thinking="high",
                attachments=({"name": "characters.md", "content": "Nhân vật"},),
            )
        )
        self.assertEqual("prompt", calls[0][0])
        self.assertEqual("characters.md", calls[0][1]["ai_studio_references"][0]["name"])
        self.assertEqual(response.text, "ok")


if __name__ == "__main__":
    unittest.main()
