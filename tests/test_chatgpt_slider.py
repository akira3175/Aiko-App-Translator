import unittest
from unittest.mock import Mock, patch
from selenium.webdriver.common.keys import Keys
from cores.chatgpt import web_controls as c


class SliderTests(unittest.TestCase):
    def test_selected_model_in_hidden_list_does_not_need_click(self):
        picker, item, label = Mock(), Mock(), Mock()
        picker.find_elements.return_value = [item]
        item.find_elements.return_value = [label]
        label.get_attribute.return_value = 'GPT-5.6 Sol'
        item.get_attribute.return_value = 'true'
        with patch.object(c, 'ActionChains'):
            self.assertTrue(c._select_chatgpt_slider_option(Mock(), picker, 'Mô hình', ['gpt-5.6 sol']))
        item.click.assert_not_called()

    def test_effort_uses_keyboard_and_verifies_each_step(self):
        picker, control, slider = Mock(), Mock(), Mock()
        picker.find_element.return_value = control
        control.find_element.return_value = slider
        state = {'aria-valuemin': '0', 'aria-valuemax': '2', 'aria-valuenow': '0'}
        slider.get_attribute.side_effect = state.get
        def press(key):
            self.assertEqual(key, Keys.ARROW_RIGHT)
            state['aria-valuenow'] = str(int(state['aria-valuenow']) + 1)
        control.send_keys.side_effect = press
        with patch.object(c, 'ActionChains'):
            self.assertTrue(c._select_chatgpt_slider_option(Mock(), picker, 'Mức suy luận', ['cao']))
        self.assertEqual(state['aria-valuenow'], '2')
        self.assertEqual(control.send_keys.call_count, 2)

    def test_unknown_slider_range_is_not_guessed(self):
        picker = Mock()
        picker.find_element.return_value.find_element.return_value.get_attribute.return_value = '4'
        self.assertFalse(c._select_chatgpt_slider_option(Mock(), picker, 'Mức suy luận', ['cao']))
