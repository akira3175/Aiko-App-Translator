import unittest
from unittest.mock import Mock, patch

from selenium.common.exceptions import TimeoutException
from cores.chatgpt.web_client import (
    ChatGPTComposerError, _paste_prompt, _ready_input, generate_content,
)


class ImmediateWait:
    def __init__(self, driver, *args, **kwargs):
        self.driver = driver

    def until(self, predicate):
        value = predicate(self.driver)
        if not value:
            raise TimeoutException()
        return value


class ComposerTests(unittest.TestCase):
    def test_new_home_input_skips_hidden_old_composer(self):
        hidden, visible = Mock(), Mock()
        hidden.is_displayed.return_value = False
        visible.is_displayed.return_value = True
        visible.is_enabled.return_value = True
        driver = Mock()
        driver.find_elements.side_effect = lambda by, selector: (
            [hidden, visible] if selector == '#pending-home-input' else []
        )
        self.assertIs(_ready_input(driver), visible)

    def paste_fixture(self, fallback_works):
        driver, element, clipboard = Mock(), Mock(), Mock()
        element.tag_name = 'textarea'
        state = {'value': '', 'clipboard': 'original'}
        element.get_property.side_effect = lambda name: state['value']
        clipboard.paste.side_effect = lambda: state['clipboard']
        clipboard.copy.side_effect = lambda text: state.update(clipboard=text)
        if fallback_works:
            driver.execute_script.side_effect = lambda script, el, text: state.update(value=text)
        return driver, element, clipboard, state

    def test_paste_does_not_compare_editor_text(self):
        driver, element, clipboard, state = self.paste_fixture(False)
        _paste_prompt(driver, element, 'full prompt', clipboard)
        element.get_property.assert_not_called()
        driver.execute_script.assert_not_called()
        self.assertEqual(state['clipboard'], 'original')

    def test_paste_error_still_restores_clipboard(self):
        driver, element, clipboard, state = self.paste_fixture(False)
        element.send_keys.side_effect = [None, RuntimeError('paste failed')]
        with self.assertRaisesRegex(RuntimeError, 'paste failed'):
            _paste_prompt(driver, element, 'full prompt', clipboard)
        self.assertEqual(state['clipboard'], 'original')

    @patch('cores.chatgpt.web_client.time.sleep')
    @patch('cores.chatgpt.web_client._paste_prompt')
    @patch('cores.chatgpt.web_client.WebDriverWait', ImmediateWait)
    def test_selection_failures_still_paste_send_and_read_response(self, paste, sleep):
        from cores.chatgpt import web_client as client
        for model_ok, thinking_ok in ((False, True), (True, False), (False, False)):
            with self.subTest(model_ok=model_ok, thinking_ok=thinking_ok):
                driver, close, send = Mock(), Mock(), Mock()
                driver.find_elements.return_value = [Mock()]
                paste.reset_mock()
                with patch.object(client, 'select_chatgpt_model', return_value=model_ok), \
                     patch.object(client, 'select_chatgpt_thinking', return_value=thinking_ok), \
                     patch.object(client, '_ready_chatgpt_send_button', return_value=send), \
                     patch.object(client, '_snapshot_chatgpt_conversation', return_value=0), \
                     patch.object(client, '_find_new_chatgpt_response', return_value=Mock()), \
                     patch.object(client, '_chatgpt_response_text', return_value='text ###END###'), \
                     patch.object(client, '_settle_end_marker_response', return_value='text ###END###'):
                    result = generate_content(
                        'prompt', get_driver=lambda: driver, close_driver=close,
                        link='https://chatgpt.com/', default_model='requested',
                        default_thinking='high')
                self.assertEqual(result, 'text ###END###')
                paste.assert_called_once()
                send.click.assert_called_once()
                close.assert_not_called()


if __name__ == '__main__':
    unittest.main()
