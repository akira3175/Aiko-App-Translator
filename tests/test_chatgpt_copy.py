import unittest
from unittest.mock import Mock, patch
from selenium.common.exceptions import TimeoutException
from cores.chatgpt import web_response, web_client


class ImmediateWait:
    def __init__(self, driver, *args, **kwargs):
        self.driver = driver

    def until(self, predicate):
        result = predicate(self.driver)
        if not result:
            raise TimeoutException('Copy unavailable')
        return result


class ChatGPTCopyTests(unittest.TestCase):
    def copy(self, markdown, *, button_present=True, writes=True, require_end=True):
        clipboard = Mock()
        value = ['original clipboard']
        clipboard.paste.side_effect = lambda: value[0]
        clipboard.copy.side_effect = lambda text: value.__setitem__(0, text)
        button = Mock()
        button.is_displayed.return_value = True
        button.is_enabled.return_value = True
        button.find_elements.return_value = []
        if writes:
            button.click.side_effect = lambda: value.__setitem__(0, markdown)
        turn = Mock()
        turn.find_elements.return_value = [button] if button_present else []
        driver = Mock()
        with patch.object(web_response, 'find_new_response', return_value=turn) as locate, patch.object(web_response, 'ActionChains'), patch.object(web_response, 'WebDriverWait', ImmediateWait):
            try:
                result = web_response.copy_response_markdown(driver, 'new-turn', 4, require_end=require_end, clipboard=clipboard)
                locate.assert_called_with(driver, 'new-turn', 4)
                button.click.assert_called_once_with()
                driver.find_elements.assert_not_called()
                return result
            finally:
                self.assertEqual('original clipboard', value[0])

    def test_copy_preserves_markdown_and_end_marker(self):
        text = '###TITLE###\nTitle\n###CONTENT###\n**Bold** and *italic*\n\n---\n\n[[IMAGE_001]]\n###END###'
        self.assertEqual(text, self.copy(text))

    def test_copy_failure_does_not_return_old_clipboard_or_plain_text(self):
        with self.assertRaises(TimeoutException):
            self.copy('new', writes=False)
        with self.assertRaises(TimeoutException):
            self.copy('new', button_present=False)

    def test_settle_returns_markdown_even_if_rendered_text_is_longer(self):
        with patch.object(web_client.time, 'sleep'), patch.object(web_client, '_chatgpt_response_text', return_value='rendered long text ###END###'), patch.object(web_client, 'copy_response_markdown', return_value='---\n###END###') as copy:
            result = web_client._settle_end_marker_response('driver','turn','token',2,'###END###')
        self.assertEqual('---\n###END###', result)
        copy.assert_called_once_with('driver','token',2,require_end=True)

    def test_json_is_also_copied_as_text(self):
        self.assertEqual('{"issues": []}',self.copy('{"issues": []}', require_end=False))
