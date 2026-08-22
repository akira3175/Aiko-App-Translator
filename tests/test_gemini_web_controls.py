import unittest
from unittest.mock import patch

from cores.gemini.web_controls import (
    open_model_dropdown,
    select_flash_model,
    select_pro_model,
    select_thinking_level,
)


class _Text:
    text = "Pro"


class _Button:
    text = "fallback"

    def is_displayed(self):
        return True

    def find_element(self, _by, _selector):
        return _Text()


class _Driver:
    def __init__(self):
        self.button = _Button()

    def find_elements(self, _by, _selector):
        return [self.button]


class _ThinkingItem:
    text = "Mở rộng"

    def is_displayed(self):
        return True

    def get_attribute(self, name):
        return "selected" if name == "class" else ""

    def find_element(self, _by, selector):
        if selector == "span.label":
            return _BlockText("Mở rộng")
        raise LookupError(selector)


class _BlockText:
    def __init__(self, text):
        self.text = text


class _ThinkingDriver(_Driver):
    def __init__(self):
        super().__init__()
        self.item = _ThinkingItem()
        self.scripts = []

    def find_elements(self, _by, selector):
        if "gem-menu-item" in selector:
            return [self.item]
        return [self.button]

    def execute_script(self, script, *_args):
        self.scripts.append(script)


class GeminiWebControlsTests(unittest.TestCase):
    def test_reads_current_model_and_skips_reselecting_pro(self):
        driver = _Driver()
        self.assertEqual((driver.button, "pro"), open_model_dropdown(driver))
        self.assertTrue(select_pro_model(driver))

    def test_keeps_selected_extended_thinking_level(self):
        driver = _ThinkingDriver()
        self.assertTrue(select_thinking_level(driver, "extended"))
        self.assertIn("document.body.click();", driver.scripts)

    def test_flash_selects_fast_option_in_current_gemini_menu(self):
        driver = _ThinkingDriver()
        with (
            patch(
                "cores.gemini.web_controls.open_model_dropdown",
                return_value=(driver.button, "pro"),
            ),
            patch(
                "cores.gemini.web_controls.click_menu_item",
                return_value=True,
            ) as click,
            patch("cores.gemini.web_controls.time.sleep"),
        ):
            self.assertTrue(select_flash_model(driver))
        click.assert_called_once_with(
            driver, ["Fast", "Nhanh", "Flash"], "Flash/Fast"
        )


if __name__ == "__main__":
    unittest.main()
