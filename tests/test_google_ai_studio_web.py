import unittest

from cores.google_ai_studio.web_client import (
    _prompt_url,
    _copy_response_as_markdown,
    _generation_running,
    _is_complete_response,
    _is_ui_chrome,
    _paste_parts,
    _select_thinking_level,
    _set_prompt,
    _strip_ui_chrome,
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


class _ThinkingAndAnswerTurn:
    text = "Thinking\nModel"

    def find_elements(self, _by, _selector):
        thinking = _Element()
        thinking.text = "Thinking\n" + ("suy luận dài " * 40)
        answer = _Element()
        answer.text = "###TITLE###\nTiêu đề\n###CONTENT###\nNội dung\n###END###"
        return [thinking, answer]


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
    def __init__(self, text="", aria="", title=""):
        self.text = text
        self.aria = aria
        self.title = title

    def get_attribute(self, name):
        if name == "aria-label":
            return self.aria
        return self.title if name == "title" else ""


class _ButtonDriver:
    def __init__(self, buttons):
        self.buttons = buttons

    def find_elements(self, _by, _selector):
        return self.buttons


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

    def test_structured_answer_beats_long_thinking_node(self):
        result = _turn_text(_ThinkingAndAnswerTurn())
        self.assertIn("###TITLE###", result)
        self.assertNotIn("suy luận dài", result)

    def test_strips_ai_studio_ui_labels(self):
        self.assertEqual(
            _strip_ui_chrome("Model 2:48 PM\nThinking\nthumb_up\nNội dung\ncontent_copy"),
            "Nội dung",
        )
        self.assertTrue(_is_ui_chrome("Thinking\nExpand to view model thoughts"))

    def test_generation_running_accepts_accessible_stop_label(self):
        driver = _ButtonDriver([_Button(aria="Stop generating")])
        self.assertTrue(_generation_running(driver))
        self.assertFalse(_generation_running(_ButtonDriver([_Button("Run")])))

    def test_translation_requires_all_output_markers(self):
        complete = "###TITLE###\nT\n###CONTENT###\nC\n###END###"
        self.assertTrue(_is_complete_response(complete, "translate"))
        self.assertFalse(
            _is_complete_response("###TITLE###\nT\n###CONTENT###\nC", "translate")
        )
        self.assertFalse(_is_complete_response("En train de réfléchir…", "translate"))

    def test_json_stages_require_complete_expected_shape(self):
        self.assertTrue(
            _is_complete_response('{"character_pairs": []}', "pronouns")
        )
        self.assertFalse(
            _is_complete_response('{"character_pairs": [', "pronouns")
        )
        self.assertTrue(
            _is_complete_response(
                '{"overall_score": 9, "issues": [], "summary": "Ổn"}',
                "review",
            )
        )
        self.assertFalse(_is_complete_response('{"overall_score": 9}', "review"))

    def test_marker_stages_require_complete_blocks(self):
        self.assertTrue(
            _is_complete_response("###START###\na = b\n###END###", "context")
        )
        self.assertTrue(
            _is_complete_response(
                "###CHAR_START###\n## An\n- Nam\n###CHAR_END###",
                "characters",
            )
        )
        self.assertFalse(
            _is_complete_response("###START###\n## An", "characters")
        )

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
        self.assertEqual("translate", calls[0][1]["ai_studio_stage"])
        self.assertEqual(response.text, "ok")


if __name__ == "__main__":
    unittest.main()
