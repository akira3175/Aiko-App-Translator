import unittest
from unittest.mock import patch

from cores.gemini.web_controls import (
    click_menu_item,
    open_model_dropdown,
    select_flash_model,
    select_pro_model,
    select_thinking_level,
    select_thinking_model,
)


class _Text:
    def __init__(self, text):
        self.text = text


class _Element:
    """Fake WebElement dựa trên DOM Gemini Web thực tế (2026-10)."""

    def __init__(self, label="", attrs=None, classes="", children=None):
        self.text = label
        self.attrs = dict(attrs or {})
        self.classes = classes
        self.children = dict(children or {})
        self.displayed = True

    def is_displayed(self):
        return self.displayed

    def get_attribute(self, name):
        if name == "class":
            return self.classes
        return self.attrs.get(name, "")

    def find_element(self, _by, selector):
        if selector == "span.label" and self.text:
            return _Text(f" {self.text} ")
        if selector in self.children:
            return _Text(self.children[selector])
        raise LookupError(selector)


def _model_button(primary, secondary=""):
    children = {".picker-primary-text": primary}
    if secondary:
        children[".picker-secondary-text"] = secondary
    return _Element(
        attrs={"aria-label": f"Mở công cụ chọn chế độ, hiện tại là {primary} {secondary}"},
        children=children,
    )


class _GeminiDriver:
    def __init__(self, primary="Argon", secondary="Trung bình", level="Trung bình"):
        self.button = _model_button(primary, secondary)
        self.models = [
            _Element(label, {"data-mode-id": mode_id})
            for label, mode_id in (
                ("3.5 Flash-Lite", "8c46e95b1a07cecc"),
                ("3.8 Flash", "56fdd199312815e2"),
                ("3.1 Pro", "e6fa609c3fa255c0"),
                ("4 Argon", "95a4c0abcba24364"),
            )
        ]
        self.thinking = _Element("Cấp độ tư duy", {"value": "thinking_level"})
        self.levels = [
            _Element(label, classes="ng-star-inserted selected" if label == level else "")
            for label in ("Thấp", "Trung bình", "Cao")
        ]
        self.has_thinking = True
        self.submenu_open = False
        self.clicked = []

    def find_elements(self, _by, selector):
        if "bard-mode-menu-button" in selector:
            return [self.button]
        if 'value="thinking_level"' in selector:
            return [self.thinking] if self.has_thinking else []
        if "submenu-container" in selector:
            return self.levels if self.submenu_open else []
        if "gem-menu-item" in selector:
            items = list(self.models)
            if self.has_thinking:
                items.append(self.thinking)
            return items
        return []

    def execute_script(self, _script, *args):
        if args:
            self.clicked.append(args[0])
            if args[0] is self.thinking:
                self.submenu_open = True


class GeminiWebControlsTests(unittest.TestCase):
    def setUp(self):
        sleep = patch("cores.gemini.web_controls.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_reads_model_and_thinking_level_from_button(self):
        driver = _GeminiDriver()
        self.assertEqual((driver.button, "argon trung bình"), open_model_dropdown(driver))

    def test_skips_reselecting_current_pro_model(self):
        driver = _GeminiDriver(primary="3.1 Pro", secondary="")
        self.assertTrue(select_pro_model(driver))
        self.assertEqual([], driver.clicked)

    def test_argon_counts_as_thinking_model(self):
        driver = _GeminiDriver()
        self.assertTrue(select_thinking_model(driver))
        self.assertEqual([], driver.clicked)

    def test_switches_to_argon_from_flash(self):
        driver = _GeminiDriver(primary="3.8 Flash", secondary="")
        self.assertTrue(select_thinking_model(driver))
        self.assertEqual([driver.button, driver.models[3]], driver.clicked)

    def test_flash_prefers_full_flash_over_flash_lite(self):
        driver = _GeminiDriver(primary="3.1 Pro", secondary="")
        self.assertTrue(select_flash_model(driver))
        self.assertIs(driver.models[1], driver.clicked[-1])

    def test_flash_lite_is_not_treated_as_flash(self):
        driver = _GeminiDriver(primary="3.5 Flash-Lite", secondary="")
        self.assertTrue(select_flash_model(driver))
        self.assertIs(driver.models[1], driver.clicked[-1])

    def test_click_menu_item_respects_keyword_priority(self):
        driver = _GeminiDriver()
        self.assertTrue(click_menu_item(driver, ["3.1 Pro", "Flash"], "Pro"))
        self.assertIs(driver.models[2], driver.clicked[-1])

    def test_keeps_matching_thinking_level_without_opening_menu(self):
        driver = _GeminiDriver(secondary="Trung bình")
        self.assertTrue(select_thinking_level(driver, "medium"))
        self.assertTrue(select_thinking_level(driver, "standard"))
        self.assertEqual([], driver.clicked)

    def test_selects_high_level_through_submenu(self):
        driver = _GeminiDriver(secondary="Trung bình")
        self.assertTrue(select_thinking_level(driver, "extended"))
        self.assertEqual(
            [driver.button, driver.thinking, driver.levels[2]], driver.clicked
        )

    def test_does_not_reclick_already_selected_submenu_level(self):
        driver = _GeminiDriver(secondary="", level="Cao")
        self.assertTrue(select_thinking_level(driver, "high"))
        self.assertNotIn(driver.levels[2], driver.clicked)

    def test_model_without_thinking_option_is_left_unchanged(self):
        driver = _GeminiDriver(primary="3.1 Pro", secondary="")
        driver.has_thinking = False
        self.assertFalse(select_thinking_level(driver, "high"))
        self.assertEqual([driver.button], driver.clicked)

    def test_legacy_extended_toggle_is_kept_when_selected(self):
        driver = _GeminiDriver(primary="Pro", secondary="")
        driver.has_thinking = False
        driver.models.append(_Element("Mở rộng", classes="selected"))
        self.assertTrue(select_thinking_level(driver, "extended"))
        self.assertNotIn(driver.models[-1], driver.clicked)


if __name__ == "__main__":
    unittest.main()
