import unittest
from unittest.mock import patch

from cores.gemini.web_controls import (
    click_menu_item,
    open_model_dropdown,
    select_custom_model,
    select_flash_lite_model,
    select_flash_model,
    select_pro_model,
    select_task_mode,
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
            child = self.children[selector]
            return child if isinstance(child, _Element) else _Text(child)
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
    def __init__(
        self,
        primary="Argon",
        secondary="Trung bình",
        level="Trung bình",
        spark_selected="0",
    ):
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
        self.spark_chat_button = _Element("Cuộc trò chuyện")
        self.spark_task_button = _Element("Nhiệm vụ")
        self.spark_segments = [
            _Element(
                "Cuộc trò chuyện",
                {"data-value": "0"},
                classes=(
                    "gem-segmented-button gem-segmented-button-selected"
                    if spark_selected == "0"
                    else "gem-segmented-button"
                ),
                children={
                    ".gds-body-m": "Cuộc trò chuyện",
                    "button.gem-segmented-button-action, button": self.spark_chat_button,
                },
            ),
            _Element(
                "Nhiệm vụ",
                {"data-value": "40"},
                classes=(
                    "gem-segmented-button gem-segmented-button-selected"
                    if spark_selected == "40"
                    else "gem-segmented-button"
                ),
                children={
                    ".gds-body-m": "Nhiệm vụ",
                    "button.gem-segmented-button-action, button": self.spark_task_button,
                },
            ),
        ]
        self.has_spark_toggle = True
        self.has_thinking = True
        self.submenu_open = False
        self.clicked = []

    def find_elements(self, _by, selector):
        if "gem-segmented-button" in selector:
            return list(self.spark_segments) if self.has_spark_toggle else []
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

    def test_selects_task_mode_when_enabled(self):
        driver = _GeminiDriver(spark_selected="0")
        self.assertTrue(select_task_mode(driver, True))
        self.assertEqual([driver.spark_task_button], driver.clicked)

    def test_skips_clicking_task_mode_when_already_selected(self):
        driver = _GeminiDriver(spark_selected="40")
        self.assertTrue(select_task_mode(driver, True))
        self.assertEqual([], driver.clicked)

    def test_switches_back_to_chat_mode_when_disabled(self):
        driver = _GeminiDriver(spark_selected="40")
        self.assertTrue(select_task_mode(driver, False))
        self.assertEqual([driver.spark_chat_button], driver.clicked)

    def test_returns_false_when_spark_toggle_is_absent(self):
        driver = _GeminiDriver()
        driver.has_spark_toggle = False
        self.assertFalse(select_task_mode(driver, True))
        self.assertEqual([], driver.clicked)

    def test_selects_models_when_name_is_in_sublabel_and_role_is_menuitemradio(self):
        """Giao diện mới (2026-11): span.label là mô tả, div.sublabel là tên model."""
        driver = _GeminiDriver(primary="Argon", secondary="Cao")
        driver.models = [
            _Element(
                "Quick answers",
                {"data-mode-id": "8c46e95b1a07cecc", "role": "menuitemradio", "aria-checked": "false"},
                children={".sublabel": "3.5 Flash-Lite"},
            ),
            _Element(
                "Trợ giúp toàn diện",
                {"data-mode-id": "56fdd199312815e2", "role": "menuitemradio", "aria-checked": "false"},
                children={".sublabel": "3.8 Flash"},
            ),
            _Element(
                "Detailed research",
                {"data-mode-id": "e6fa609c3fa255c0", "role": "menuitemradio", "aria-checked": "false"},
                children={".sublabel": "3.1 Pro"},
            ),
            _Element(
                "Code & analysis",
                {"data-mode-id": "argon", "role": "menuitemradio", "aria-checked": "true"},
                children={".sublabel": "4 Argon"},
            ),
        ]

        self.assertTrue(select_pro_model(driver))
        self.assertIs(driver.models[2], driver.clicked[-1])

        driver.clicked.clear()
        self.assertTrue(select_flash_model(driver))
        self.assertIs(driver.models[1], driver.clicked[-1])

        driver.clicked.clear()
        self.assertTrue(select_flash_lite_model(driver))
        self.assertIs(driver.models[0], driver.clicked[-1])

    def test_selects_thinking_level_via_sublabel_jslog_and_position_fallbacks(self):
        driver = _GeminiDriver(secondary="")
        # Tầng 3: khớp qua jslog BardVeMetadataKey ngay cả khi nhãn đổi hoàn toàn
        driver.levels = [
            _Element(
                "Tier A",
                {
                    "role": "menuitemradio",
                    "aria-checked": "false",
                    "jslog": "323336;track:generic_click;BardVeMetadataKey:W251bGwsWyJhcmdvbiIsMSw4XV0=;mutable:true",
                },
            ),
            _Element(
                "Tier B",
                {
                    "role": "menuitemradio",
                    "aria-checked": "false",
                    "jslog": "323336;track:generic_click;BardVeMetadataKey:W251bGwsWyJhcmdvbiIsNCw4XV0=;mutable:true",
                },
            ),
            _Element(
                "Tier C",
                {
                    "role": "menuitemradio",
                    "aria-checked": "true",
                    "jslog": "323336;track:generic_click;BardVeMetadataKey:W251bGwsWyJhcmdvbiIsMiw4XV0=;mutable:true",
                },
            ),
        ]
        # Đang ở mức Cao (aria-checked="true") -> không click lại khi yêu cầu high
        self.assertTrue(select_thinking_level(driver, "high"))
        self.assertNotIn(driver.levels[2], driver.clicked)

        # Chuyển sang mức Trung bình (code=4 -> levels[1])
        driver.clicked.clear()
        self.assertTrue(select_thinking_level(driver, "medium"))
        self.assertIs(driver.levels[1], driver.clicked[-1])

    def test_selects_custom_future_model_name(self):
        driver = _GeminiDriver(primary="3.1 Pro", secondary="")
        future = _Element("Next-gen reasoning", children={".sublabel": "5.0 Ultra"})
        driver.models.append(future)
        self.assertTrue(select_custom_model(driver, "5.0 Ultra"))
        self.assertIs(future, driver.clicked[-1])


if __name__ == "__main__":
    unittest.main()
