import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class UiPreferencesTests(unittest.TestCase):
    def test_new_user_gets_compact_default_sidebar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ui_preferences.json"
            with patch.object(app, "UI_PREFERENCES_FILE", path):
                self.assertEqual(
                    app.ui_preferences_data()["sidebar"]["pinned"],
                    ["workspace", "chapters", "pipeline", "terminology", "characters", "help"],
                )

    def test_sidebar_order_round_trips_in_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ui_preferences.json"
            with patch.object(app, "UI_PREFERENCES_FILE", path):
                saved = app.write_ui_preferences(
                    {"sidebar": {"pinned": ["pipeline", "workspace", "ai-log"]}}
                )
                loaded = app.ui_preferences_data()
            self.assertEqual(saved, loaded)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["sidebar"]["pinned"],
                ["pipeline", "workspace", "ai-log"],
            )

    def test_empty_sidebar_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ui_preferences.json"
            with patch.object(app, "UI_PREFERENCES_FILE", path):
                app.write_ui_preferences({"sidebar": {"pinned": []}})
                self.assertEqual(app.ui_preferences_data()["sidebar"]["pinned"], [])

    def test_help_can_be_unpinned_but_settings_stays_fixed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ui_preferences.json"
            with patch.object(app, "UI_PREFERENCES_FILE", path):
                saved = app.write_ui_preferences(
                    {"sidebar": {"pinned": ["workspace", "help", "settings"]}}
                )
                self.assertEqual(saved["sidebar"]["pinned"], ["workspace", "help"])
                saved = app.write_ui_preferences(
                    {"sidebar": {"pinned": ["workspace"]}}
                )
                self.assertEqual(saved["sidebar"]["pinned"], ["workspace"])

    def test_invalid_feature_is_rejected(self):
        with self.assertRaises(ValueError):
            app.write_ui_preferences({"sidebar": {"pinned": ["unknown"]}})

    def test_frontend_has_search_pin_and_reorder_controls(self):
        html = (app.WEB / "index.html").read_text(encoding="utf-8")
        script = (app.WEB / "app.js").read_text(encoding="utf-8")
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
        compact_css = (app.WEB / "sidebar-compact.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: minmax(0, 1fr)", compact_css)
        self.assertIn(".sidebar-foot .all-features-button", compact_css)
        self.assertIn('.sidebar-fixed-navigation .nav-item[hidden]', compact_css)
        self.assertIn("footerSidebarFeatures", script)
        self.assertIn("/api/ui-preferences", script)


if __name__ == "__main__":
    unittest.main()
