import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch
from cores.gemini import web_client as client

from cores.browser import content
from cores.gemini.web_client import (
    _has_end_marker,
    _is_known_structured_response,
    _task_mode_enabled,
    normalize_web_model,
)


class GeminiWebClientTests(unittest.TestCase):
    def response_fixture(self, texts, clock, copied=''):
        stack = ExitStack()
        self.addCleanup(stack.close)
        driver = Mock()
        button = Mock()
        button.tag_name = 'button'
        driver.find_elements.return_value = [button]
        for name in ('select_task_mode', '_insert_text', 'WebDriverWait'):
            stack.enter_context(patch.object(client, name))
        stack.enter_context(patch.object(client, '_upload_threshold', return_value=0))
        stack.enter_context(patch.object(client.time, 'sleep'))
        stack.enter_context(patch.object(client.time, 'monotonic', side_effect=clock))
        stack.enter_context(patch.object(client, '_snapshot_gemini_conversation', return_value=0))
        stack.enter_context(patch.object(client, '_find_new_gemini_response', return_value=Mock()))
        stack.enter_context(patch.object(client, '_gemini_response_text', side_effect=texts))
        copy = stack.enter_context(patch.object(client, 'copy_response_text', return_value=copied))
        return driver, copy

    def generate(self, driver, prompt='translate ###END###', retries=2):
        return client.generate_content(
            prompt, get_driver=lambda: driver, link='https://gemini.google.com/',
            default_thinking='off', web_model='auto', task_mode=False, max_retries=retries,
        )

    def test_missing_end_retries_and_never_returns_partial_text(self):
        driver, copy = self.response_fixture(['partial', 'partial'], [0, 1, 1801] * 2)
        with self.assertRaisesRegex(ValueError, '###END###'):
            self.generate(driver)
        self.assertEqual(driver.get.call_count, 2)
        driver.refresh.assert_called_once()
        copy.assert_not_called()

    def test_retry_can_return_complete_response(self):
        complete = 'complete ###END###'
        driver, copy = self.response_fixture(['partial', complete, complete], [0, 1, 1801, 0, 1], complete)
        self.assertEqual(self.generate(driver), complete)
        self.assertEqual(driver.get.call_count, 2)

    def test_marker_disappearing_during_settle_is_rejected(self):
        driver, copy = self.response_fixture(['text ###END###', 'partial'], [0, 1], 'partial')
        with self.assertRaises(ValueError):
            self.generate(driver, retries=1)

    def test_structured_json_still_works_without_end(self):
        text = '{"character_pairs": []}'
        driver, copy = self.response_fixture([text, text], [0, 1], text)
        self.assertEqual(self.generate(driver, prompt='extract JSON', retries=1), text)

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
