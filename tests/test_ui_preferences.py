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

    def test_editor_appearance_round_trips_with_times_new_roman(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(Path(directory))
            saved = service.write_ui_preferences(
                {"editor": {"font": "times", "size": 19, "line_height": 1.9}}
            )
            self.assertEqual(
                {"font": "times", "size": 19, "line_height": 1.9},
                saved["editor"],
            )
            self.assertEqual(saved, service.ui_preferences())

    def test_frontend_has_search_pin_and_reorder_controls(self):
        web = Path(__file__).resolve().parents[1] / "web"
        html = (web / "index.html").read_text(encoding="utf-8")
        script = "\n".join(
            (web / path).read_text(encoding="utf-8")
            for path in ("app.js", "features/app-shell.js")
        )
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
        self.assertIn("data-feature-icon", script)
        self.assertIn('class="sidebar-fixed-navigation"', html)
        self.assertIn('id="sidebarHelpButton" data-view="help" hidden', html)
        self.assertIn('/sidebar-compact.css', html)
        compact_css = (web / "sidebar-compact.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: minmax(0, 1fr)", compact_css)
        self.assertIn(".sidebar-foot .all-features-button", compact_css)
        self.assertIn('.sidebar-fixed-navigation .nav-item[hidden]', compact_css)
        self.assertIn("footerSidebarFeatures", script)
        self.assertIn("/api/ui-preferences", script)
        self.assertIn("Times New Roman", script)
        self.assertIn("editorFontSize", script)
        self.assertIn("editorLineHeight", script)
        self.assertIn('aria-label="Mở chương trước"', html)
        self.assertIn('aria-label="Mở chương tiếp theo"', html)

    def test_aiko_anime_theme_is_optional_and_has_a_transparent_asset(self):
        web = Path(__file__).resolve().parents[1] / "web"
        script = (web / "features" / "app-shell.js").read_text(encoding="utf-8")
        themes = (web / "themes.css").read_text(encoding="utf-8")
        asset = web / "assets" / "anime" / "aiko-blue-mascot.png"
        logo = web / "assets" / "anime" / "aiko-portrait-logo-v2.png"
        cursor = web / "assets" / "anime" / "aiko-quill-cursor-48.png"
        chapter_arrow = web / "assets" / "anime" / "aiko-chapter-arrow-256.png"
        review_loading = web / "assets" / "anime" / "aiko-wand-circle-padded-v15.png"
        nav_icons = [
            "workspace", "chapters", "pipeline", "ai-log", "terminology",
            "characters", "pronouns", "r19", "hako-edit", "sharing", "help",
            "settings",
        ]
        self.assertIn("aiko-anime", script)
        self.assertIn("novel-anime-illustrations", script)
        self.assertIn('data-anime-illustrations="on"', themes)
        self.assertIn('data-anime-illustrations="on"] .chapter-nav', themes)
        self.assertIn("/assets/anime/aiko-blue-mascot.png", themes)
        self.assertTrue(asset.is_file())
        self.assertTrue(logo.is_file())
        self.assertTrue(cursor.is_file())
        self.assertTrue(chapter_arrow.is_file())
        self.assertTrue(review_loading.is_file())
        self.assertIn("/assets/anime/aiko-wand-circle-padded-v15.png", themes)
        self.assertIn("aiko-wand-circle", themes)
        self.assertIn("animation:aiko-wand-circle 1.2s linear infinite", themes)
        self.assertIn("37.5%,49.99%{background-position:100% 0}50%,62.49%{background-position:0 100%}", themes)
        self.assertIn("background-size:400% 200%", themes)
        project_memory = (web / "features" / "project-memory.js").read_text(encoding="utf-8")
        self.assertIn("firstElementChild?.classList.contains('review-loading')", project_memory)
        for name in nav_icons:
            self.assertTrue((web / "assets" / "anime" / f"nav-{name}-96.png").is_file())
        self.assertIn("novel-brush-cursor", script)
        self.assertIn('data-brush-cursor="on"', themes)
        self.assertIn("--anime-nav-icon", themes)


if __name__ == "__main__":
    unittest.main()
