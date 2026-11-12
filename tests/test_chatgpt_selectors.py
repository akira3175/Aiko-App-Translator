import unittest

from cores.chatgpt.web_controls import (
    _expand_chatgpt_model_keywords,
    _expand_chatgpt_thinking_keywords,
    _find_chatgpt_model_button,
    _find_visible_chatgpt_choice,
    _match_model_radio_item,
    _normalized_chatgpt_label,
    _visible_chatgpt_intelligence_picker,
    select_chatgpt_mode,
)
from unittest.mock import Mock, patch


def _make_radio_item(label_text, checked=False):
    item = Mock()
    trunc = Mock()
    trunc.get_attribute.side_effect = lambda attr: label_text if attr == "textContent" else None
    item.find_elements.return_value = [trunc]
    item.get_attribute.side_effect = lambda attr: (
        "true" if (checked and attr in ("aria-checked", "data-model-selected")) else "false"
    )
    return item


class ChatGPTSelectorTests(unittest.TestCase):
    def test_normalizes_vietnamese_thinking_label(self):
        self.assertEqual(_normalized_chatgpt_label("  TỨC   THÌ  "), "tuc thi")
        self.assertEqual(_normalized_chatgpt_label("Mặc định"), "mac dinh")
        self.assertEqual(_normalized_chatgpt_label("Tối đa"), "toi da")

    def test_normalizes_model_label_spacing(self):
        self.assertEqual(_normalized_chatgpt_label("GPT-5.6  Sol"), "gpt-5.6 sol")

    def test_visible_choice_passes_normalized_aliases_to_page(self):
        class Driver:
            def execute_script(self, _script, keywords):
                self.keywords = keywords
                return "instant-button"

        driver = Driver()
        self.assertEqual(
            _find_visible_chatgpt_choice(driver, ["Tức thì", "Instant"]),
            "instant-button",
        )
        self.assertEqual(driver.keywords, ["tuc thi", "instant"])

    def test_find_model_button_skips_mode_switcher_in_fallback(self):
        mode_btn = Mock()
        mode_btn.is_displayed.return_value = True
        mode_btn.text = ""
        mode_btn.get_attribute.side_effect = lambda attr: (
            "Chuyển chế độ, chế độ hiện tại: ChatGPT" if attr == "aria-label" else None
        )

        composer_btn = Mock()
        composer_btn.is_displayed.return_value = True
        composer_btn.text = "Mức nỗ lực suy luận Vừa"
        composer_btn.get_attribute.side_effect = lambda attr: (
            "Chọn mô hình ChatGPT" if attr == "aria-label" else None
        )

        driver = Mock()
        driver.find_elements.side_effect = lambda _by, selector: (
            [mode_btn, composer_btn] if selector == 'button[aria-haspopup="menu"]' else []
        )
        self.assertIs(_find_chatgpt_model_button(driver), composer_btn)

    def test_visible_picker_ignores_closing_radix_menu(self):
        closing = Mock()
        closing.is_displayed.return_value = True
        closing.get_attribute.return_value = "closed"

        open_picker = Mock()
        open_picker.is_displayed.return_value = True
        open_picker.get_attribute.return_value = "open"

        driver = Mock()
        driver.find_elements.return_value = [closing, open_picker]
        self.assertIs(_visible_chatgpt_intelligence_picker(driver), open_picker)

    def test_matches_exact_model_among_multiple_sol_and_gpt6_variants(self):
        items = [
            _make_radio_item("Mặc định"),
            _make_radio_item("GPT-6"),
            _make_radio_item("GPT-6.1 Sol"),
            _make_radio_item("GPT-6.1 Terra"),
            _make_radio_item("GPT-6 Astra"),
            _make_radio_item("GPT-6 Sol"),
            _make_radio_item("GPT-5.6 Sol"),
            _make_radio_item("GPT-5.6 Terra"),
        ]
        self.assertIs(
            _match_model_radio_item(items, _expand_chatgpt_model_keywords("GPT-6")),
            items[1],
        )
        self.assertIs(
            _match_model_radio_item(items, _expand_chatgpt_model_keywords("GPT-6.1 Sol")),
            items[2],
        )
        self.assertIs(
            _match_model_radio_item(items, _expand_chatgpt_model_keywords("GPT-6 Sol")),
            items[5],
        )
        self.assertIs(
            _match_model_radio_item(items, _expand_chatgpt_model_keywords("GPT-5.6 Sol")),
            items[6],
        )
        # Bare version prefix "gpt-5.6" falls back to "GPT-5.6 Sol" when no plain "GPT-5.6" item exists
        self.assertIs(
            _match_model_radio_item(items, _expand_chatgpt_model_keywords("gpt-5.6")),
            items[6],
        )

    def test_select_chatgpt_mode_clicks_work_when_chat_is_active(self):
        chat_btn, work_btn = Mock(), Mock()
        chat_btn.is_displayed.return_value = True
        work_btn.is_displayed.return_value = True
        state = {"chat": "true", "work": "false"}
        chat_btn.get_attribute.side_effect = lambda attr: (
            "Trò chuyện" if attr == "textContent" else state["chat"] if attr == "aria-pressed" else None
        )
        work_btn.get_attribute.side_effect = lambda attr: (
            "Công việc" if attr == "textContent" else state["work"] if attr == "aria-pressed" else None
        )
        work_btn.click.side_effect = lambda: state.update({"chat": "false", "work": "true"})

        driver = Mock()
        driver.find_elements.return_value = [chat_btn, work_btn]

        with patch("cores.chatgpt.web_controls.time.sleep"):
            self.assertTrue(select_chatgpt_mode(driver, "work"))
        work_btn.click.assert_called_once_with()
        chat_btn.click.assert_not_called()

    def test_select_chatgpt_mode_skips_click_when_already_selected(self):
        chat_btn, work_btn = Mock(), Mock()
        chat_btn.is_displayed.return_value = True
        work_btn.is_displayed.return_value = True
        chat_btn.get_attribute.side_effect = lambda attr: (
            "Trò chuyện" if attr == "textContent" else "false" if attr == "aria-pressed" else None
        )
        work_btn.get_attribute.side_effect = lambda attr: (
            "Công việc" if attr == "textContent" else "true" if attr == "aria-pressed" else None
        )

        driver = Mock()
        driver.find_elements.return_value = [chat_btn, work_btn]
        self.assertTrue(select_chatgpt_mode(driver, "work"))
        work_btn.click.assert_not_called()
        chat_btn.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
