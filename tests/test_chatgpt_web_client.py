import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from cores.browser import content
from cores.chatgpt.web_response import snapshot_conversation
from cores.chatgpt import web_client as client


class _Driver:
    def execute_script(self, _script, _token):
        return {"users": 1, "assistants": 4}


class ChatGPTWebClientTests(unittest.TestCase):
    def run_response(self, text, copied=None, retries=1):
        stack = ExitStack()
        self.addCleanup(stack.close)
        driver = Mock()
        close = Mock()
        for name in ('select_chatgpt_mode', 'select_chatgpt_model',
                     'select_chatgpt_thinking', '_paste_prompt'):
            stack.enter_context(patch.object(client, name, return_value=True))
        stack.enter_context(patch.object(client, 'WebDriverWait'))
        stack.enter_context(patch.object(client.time, 'sleep'))
        # One response poll followed by timeout for each attempt.
        stack.enter_context(patch.object(client.time, 'monotonic',
                                        side_effect=[0, 1, 1801] * retries))
        stack.enter_context(patch.object(client, '_snapshot_chatgpt_conversation', return_value=0))
        stack.enter_context(patch.object(client, '_find_new_chatgpt_response', return_value=Mock()))
        stack.enter_context(patch.object(client, '_chatgpt_response_text', return_value=text))
        copy = stack.enter_context(patch.object(client, 'copy_response_markdown', return_value=copied))
        save = stack.enter_context(patch.object(client, '_save_incomplete_response'))
        def generate():
            return client.generate_content(
                'prompt', get_driver=lambda: driver, close_driver=close,
                link='https://chatgpt.com/', default_model='', default_thinking='',
                max_retries=retries,
            )
        return generate, close, copy, save

    def test_incomplete_response_retries_then_fails_without_copying(self):
        generate, close, copy, save = self.run_response('unfinished translation', retries=2)
        with self.assertRaisesRegex(ValueError, '###END###'):
            generate()
        self.assertEqual(close.call_count, 2)
        self.assertEqual(save.call_count, 2)
        save.assert_any_call('unfinished translation', 1)
        copy.assert_not_called()

    def test_empty_response_fails(self):
        generate, close, copy, save = self.run_response('')
        with self.assertRaisesRegex(ValueError, 'Timeout'):
            generate()
        copy.assert_not_called()
        close.assert_called_once()

    def test_end_marker_requires_marker_in_markdown_copy(self):
        text = 'translation ###END###'
        generate, close, copy, save = self.run_response(text, copied=text)
        self.assertEqual(generate(), text)
        self.assertTrue(copy.call_args.kwargs['require_end'])
        close.assert_not_called()

    def test_structured_json_without_marker_is_accepted(self):
        for text in ('{"character_pairs": []}', '{"overall_score": 9, "issues": []}'):
            with self.subTest(text=text):
                generate, close, copy, save = self.run_response(text, copied=text)
                self.assertEqual(generate(), text)
                self.assertFalse(copy.call_args.kwargs['require_end'])
                close.assert_not_called()

    def test_invalid_copied_json_is_not_accepted_at_timeout(self):
        generate, close, copy, save = self.run_response('{"character_pairs": []}', copied='{"character_pairs":')
        with self.assertRaises(ValueError):
            generate()
        close.assert_called_once()

    def test_partial_text_is_saved_outside_translation_output(self):
        with TemporaryDirectory() as directory:
            with patch.object(client, 'INCOMPLETE_RESPONSE_DIR', Path(directory)):
                client._save_incomplete_response('Bản dịch dang dở', 2)
            files = list(Path(directory).glob('*-attempt-2.txt'))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_text(encoding='utf-8'), 'Bản dịch dang dở')

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
