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
    def test_ambiguous_submission_does_not_retry_or_refresh(self):
        from cores.web_errors import WebSubmissionUncertain
        driver, copy = self.response_fixture([], [])
        client._wait_for_submission.side_effect = WebSubmissionUncertain('pending')
        with self.assertRaises(WebSubmissionUncertain):
            self.generate(driver, retries=3)
        self.assertEqual(1, driver.get.call_count)
        self.assertEqual(1, client._insert_text.call_count)
        driver.refresh.assert_not_called()
        copy.assert_not_called()

    def test_unconfirmed_send_retries_before_response_wait(self):
        from cores.web_errors import RetryableWebError
        complete = 'complete ###END###'
        driver, copy = self.response_fixture([complete, complete], [0, 1], complete)
        client._wait_for_submission.side_effect = [RetryableWebError('not sent'), None]
        self.assertEqual(complete, self.generate(driver))
        self.assertEqual(2, driver.get.call_count)
        self.assertEqual(2, client._insert_text.call_count)
        self.assertEqual(2, client._wait_for_submission.call_count)
        copy.assert_called_once()

    def test_end_marker_while_generating_does_not_finish(self):
        complete = 'complete ###END###'
        driver, copy = self.response_fixture([complete, complete, complete], [0, 1, 2], complete)
        with patch.object(client, '_gemini_response_finished', side_effect=[False, True, True]):
            self.assertEqual(complete, self.generate(driver, retries=1))
        copy.assert_called_once()
        self.assertEqual(3, client._gemini_response_text.call_count)

    def test_bad_title_content_response_retries_same_request(self):
        complete = '###TITLE### T\n###CONTENT### C\n###END###'
        driver, copy = self.response_fixture(['bad ###END###', 'bad ###END###', complete, complete], [0, 1, 0, 1])
        self.assertEqual(complete, self.generate(driver, prompt='###TITLE### ###CONTENT### ###END###'))
        self.assertEqual(2, driver.get.call_count)

    def test_unfinished_response_never_returned_at_timeout(self):
        driver, copy = self.response_fixture(['some partial text'], [0, 1, 1801])
        with patch.object(client, '_gemini_response_finished', return_value=False):
            with self.assertRaises(ValueError):
                self.generate(driver, prompt='plain prompt', retries=1)
        copy.assert_not_called()

    def test_quota_while_waiting_for_input_is_not_swallowed(self):
        from cores.web_errors import WebQuotaError
        driver, _copy = self.response_fixture([], [])
        client.WebDriverWait.return_value.until.side_effect = lambda condition: condition(driver)
        with patch.object(client, 'check_quota', side_effect=[None, WebQuotaError('quota')]):
            with self.assertRaises(WebQuotaError):
                self.generate(driver, retries=3)
        self.assertEqual(1, driver.get.call_count)
        driver.refresh.assert_not_called()
        client._insert_text.assert_not_called()

    def test_quota_skips_local_retries(self):
        from cores.web_errors import WebQuotaError
        driver, _copy = self.response_fixture([], [])
        with patch.object(client, 'check_quota', side_effect=WebQuotaError('quota')):
            with self.assertRaises(WebQuotaError):
                self.generate(driver, retries=3)
        self.assertEqual(1, driver.get.call_count)
        driver.refresh.assert_not_called()

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
        stack.enter_context(patch.object(client, '_wait_for_submission'))
        stack.enter_context(patch.object(client.time, 'sleep'))
        stack.enter_context(patch.object(client.time, 'monotonic', side_effect=clock))
        stack.enter_context(patch.object(client, '_snapshot_gemini_conversation', return_value=0))
        stack.enter_context(patch.object(client, '_find_new_gemini_response', return_value=Mock()))
        stack.enter_context(patch.object(client, '_gemini_response_finished', return_value=True))
        stack.enter_context(patch.object(client, '_gemini_response_text', side_effect=texts))
        copy = stack.enter_context(patch.object(client, 'copy_response_text', return_value=copied))
        return driver, copy

    def generate(self, driver, prompt='translate ###END###', retries=2, **kwargs):
        return client.generate_content(
            prompt, get_driver=lambda: driver, link='https://gemini.google.com/',
            default_thinking='off', web_model='auto', task_mode=False, max_retries=retries,
            **kwargs,
        )

    def test_forced_upload_works_even_when_threshold_disabled(self):
        complete = 'complete ###END###'
        driver, _copy = self.response_fixture([complete, complete], [0, 1], complete)
        with patch.object(client, '_upload_prompt_file', return_value=True) as upload:
            self.assertEqual(complete, self.generate(driver, retries=1, force_upload=True))
        upload.assert_called_once()
        self.assertEqual('translate ###END###', upload.call_args.args[2])
        client._insert_text.assert_called_once_with(driver, unittest.mock.ANY, client._upload_instruction())

    def test_forced_upload_failure_respects_single_attempt_limit(self):
        driver, _copy = self.response_fixture([], [])
        with patch.object(client, '_upload_prompt_file', return_value=False) as upload:
            with self.assertRaisesRegex(ValueError, 'Không đính kèm'):
                self.generate(driver, retries=1, force_upload=True)
        upload.assert_called_once()
        client._insert_text.assert_not_called()
        driver.refresh.assert_not_called()

    def test_upload_failure_retries_file_before_sending_instruction(self):
        complete = 'complete ###END###'
        driver, _copy = self.response_fixture([complete, complete], [0, 1], complete)
        with patch.object(client, '_upload_threshold', return_value=1), patch.object(
            client, '_upload_prompt_file', side_effect=[False, True]
        ) as upload:
            self.assertEqual(complete, self.generate(driver))
        self.assertEqual(2, upload.call_count)
        self.assertEqual(2, driver.get.call_count)
        driver.refresh.assert_called_once()
        client._insert_text.assert_called_once_with(driver, unittest.mock.ANY, client._upload_instruction())
        client._snapshot_gemini_conversation.assert_called_once()
        self.assertEqual(upload.call_args_list[0].args[2], upload.call_args_list[1].args[2])

    def test_upload_exception_retries_and_exhaustion_never_sends_prompt(self):
        driver, _copy = self.response_fixture([], [])
        with patch.object(client, '_upload_prompt_file', side_effect=RuntimeError('upload failed')) as upload:
            with self.assertRaisesRegex(ValueError, 'Không đính kèm'):
                self.generate(driver, retries=3, force_upload=True)
        self.assertEqual(3, upload.call_count)
        self.assertEqual(3, driver.get.call_count)
        client._insert_text.assert_not_called()
        client._snapshot_gemini_conversation.assert_not_called()

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
        ) as generate, patch.object(content, '_gemini_link', return_value=content.LINK_GEMINI):
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
