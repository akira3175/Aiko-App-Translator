import json
import tempfile
import unittest
from pathlib import Path

from services.settings import ConfigurationService
from services.settings_schema import (
    DEFAULT_PINNED_SIDEBAR,
    FIXED_SIDEBAR_FEATURES,
    SIDEBAR_FEATURES,
)


class UiPreferencesTests(unittest.TestCase):
    @staticmethod
    def service(root):
        return ConfigurationService(
            settings_path=root / "settings.json",
            ui_preferences_path=root / "ui_preferences.json",
            setting_defaults={},
            setting_labels={},
            setting_ranges={},
            setting_meta={},
            secret_settings=set(),
            optional_settings=set(),
            hidden_settings=set(),
            default_pinned_sidebar=DEFAULT_PINNED_SIDEBAR,
            sidebar_features=SIDEBAR_FEATURES,
            fixed_sidebar_features=FIXED_SIDEBAR_FEATURES,
            api_keys=object(),
            api_keys_path=root / "keys.txt",
            api_key_state_path=root / "key-state.json",
        )

    def test_new_user_gets_compact_default_sidebar(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(Path(directory))
            self.assertEqual(
                service.ui_preferences()["sidebar"]["pinned"],
                ["workspace", "chapters", "pipeline", "terminology", "characters", "help"],
            )

    def test_sidebar_order_round_trips_in_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = self.service(root)
            saved = service.write_ui_preferences(
                {"sidebar": {"pinned": ["pipeline", "workspace", "ai-log"]}}
            )
            self.assertEqual(saved, service.ui_preferences())
            stored = json.loads((root / "ui_preferences.json").read_text(encoding="utf-8"))
            self.assertEqual(
                stored["sidebar"]["pinned"], ["pipeline", "workspace", "ai-log"]
            )

    def test_empty_sidebar_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(Path(directory))
            service.write_ui_preferences({"sidebar": {"pinned": []}})
            self.assertEqual(service.ui_preferences()["sidebar"]["pinned"], [])

    def test_help_can_be_unpinned_but_settings_stays_fixed(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(Path(directory))
            saved = service.write_ui_preferences(
                {"sidebar": {"pinned": ["workspace", "help", "settings"]}}
            )
            self.assertEqual(saved["sidebar"]["pinned"], ["workspace", "help"])
            saved = service.write_ui_preferences(
                {"sidebar": {"pinned": ["workspace"]}}
            )
            self.assertEqual(saved["sidebar"]["pinned"], ["workspace"])

    def test_invalid_feature_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self.service(Path(directory)).write_ui_preferences(
                    {"sidebar": {"pinned": ["unknown"]}}
                )

    def test_frontend_has_search_pin_and_reorder_controls(self):
        web = Path(__file__).resolve().parents[1] / "web"
        html = (web / "index.html").read_text(encoding="utf-8")
        script = (web / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="allFeaturesButton"', html)
        self.assertIn('id="featureSearch"', html)
        self.assertIn('id="featureMenuTabs"', html)
        self.assertIn('id="pinnedFeatureCount"', html)
        self.assertIn('id="bookExportModal"', html)
        self.assertIn('id="exportBookButton"', html)
        self.assertIn('/book-export.css', html)
        self.assertIn("data-feature-pin", script)
        self.assertIn("data-feature-drag", script)
        self.assertIn("ondragstart", script)
        self.assertIn("normalized?searchContent", script)
        self.assertIn("data-feature-open", script)
        self.assertIn('class="sidebar-fixed-navigation"', html)
        self.assertIn('id="sidebarHelpButton" data-view="help" hidden', html)
        self.assertIn('/sidebar-compact.css', html)
        compact_css = (web / "sidebar-compact.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: minmax(0, 1fr)", compact_css)
        self.assertIn(".sidebar-foot .all-features-button", compact_css)
        self.assertIn('.sidebar-fixed-navigation .nav-item[hidden]', compact_css)
        self.assertIn("footerSidebarFeatures", script)
        self.assertIn("/api/ui-preferences", script)


if __name__ == "__main__":
    unittest.main()
