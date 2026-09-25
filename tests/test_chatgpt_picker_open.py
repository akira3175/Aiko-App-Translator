import unittest
from unittest.mock import Mock, patch

from selenium.common.exceptions import TimeoutException
from cores.chatgpt import web_controls as controls


class PickerOpenTests(unittest.TestCase):
    def test_reuses_open_picker_without_toggling_it_closed(self):
        picker = Mock()
        with patch.object(controls, "_visible_chatgpt_intelligence_picker", return_value=picker), \
             patch.object(controls, "ActionChains") as actions:
            self.assertIs(controls._open_chatgpt_intelligence_picker(Mock()), picker)
            actions.assert_not_called()

    def test_clicks_model_button_without_keyboard_shortcut(self):
        button, picker = Mock(), Mock()
        with patch.object(controls, "_visible_chatgpt_intelligence_picker", return_value=None), \
             patch.object(controls, "_find_chatgpt_model_button", return_value=button), \
             patch.object(controls, "WebDriverWait") as wait, \
             patch.object(controls, "ActionChains") as actions:
            wait.return_value.until.return_value = picker
            self.assertIs(controls._open_chatgpt_intelligence_picker(Mock()), picker)
            button.click.assert_called_once_with()
            actions.assert_not_called()

    def test_failed_click_wait_still_tries_shortcut(self):
        with patch.object(controls, "_visible_chatgpt_intelligence_picker", return_value=None), \
             patch.object(controls, "_find_chatgpt_model_button", return_value=Mock()), \
             patch.object(controls, "WebDriverWait") as wait, \
             patch.object(controls, "ActionChains") as actions:
            wait.return_value.until.side_effect = TimeoutException()
            self.assertIsNone(controls._open_chatgpt_intelligence_picker(Mock()))
            actions.assert_called_once()


if __name__ == "__main__":
    unittest.main()
