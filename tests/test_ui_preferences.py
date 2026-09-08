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

    def test_sidebar_navigation_height_is_stable_with_anime_icons(self):
        web = Path(__file__).resolve().parents[1] / "web"
        refinement_css = (web / "ui-refinement.css").read_text(encoding="utf-8")
        compact_css = (web / "sidebar-compact.css").read_text(encoding="utf-8")
        self.assertIn(
            ".sidebar nav .nav-item,\n.sidebar-fixed-navigation .nav-item {\n  min-height: 44px;\n}",
            refinement_css,
        )
        self.assertIn("min-height: 36px", compact_css)

    def test_standard_themes_are_available(self):
        web = Path(__file__).resolve().parents[1] / "web"
        html = (web / "index.html").read_text(encoding="utf-8")
        script = (web / "features" / "app-shell.js").read_text(encoding="utf-8")
        themes = (web / "themes.css").read_text(encoding="utf-8")
        for theme_id in (
            "github-dark",
            "one-dark-pro",
            "everforest-dark-medium",
            "night-owl",
            "catppuccin-mocha",
        ):
            self.assertIn(f"'{theme_id}'", html)
            self.assertIn(f"id:'{theme_id}'", script)
            self.assertIn(f'html[data-theme="{theme_id}"]', themes)
            self.assertIn(f'data-theme-option="{theme_id}"', themes)
        self.assertIn("themes.includes(saved)?saved:'aiko-anime'", html)
        self.assertIn('<html lang="vi" data-theme="aiko-anime">', html)
        self.assertIn("dataset.theme||'aiko-anime'", script)

    def test_anime_illustrations_are_optional_for_every_theme(self):
        web = Path(__file__).resolve().parents[1] / "web"
        script = (web / "features" / "app-shell.js").read_text(encoding="utf-8")
        themes = (web / "themes.css").read_text(encoding="utf-8")
        refinement = (web / "ui-refinement.css").read_text(encoding="utf-8")
        asset = web / "assets" / "anime" / "aiko-blue-mascot.png"
        logo = web / "assets" / "anime" / "aiko-portrait-logo-v2.png"
        cursor = web / "assets" / "anime" / "aiko-quill-cursor-48.png"
        chapter_arrow = web / "assets" / "anime" / "aiko-chapter-chevron-v1.svg"
        review_loading = web / "assets" / "anime" / "aiko-reading-loading-v2.webp"
        review_loading_still = web / "assets" / "anime" / "aiko-reading-loading-still-v2.webp"
        nav_icons = [
            "workspace", "chapters", "pipeline", "ai-log", "terminology",
            "characters", "pronouns", "r19", "hako-edit", "sharing", "help",
            "settings",
        ]
        self.assertIn("aiko-anime", script)
        self.assertIn("name:'Aiko Midnight'", script)
        self.assertNotIn("name:'Aiko Anime'", script)
        self.assertIn("novel-anime-illustrations", script)
        self.assertIn("localStorage.getItem('novel-anime-illustrations')==='on'", script)
        self.assertIn("localStorage.getItem('novel-anime-illustrations')==='on'?'on':'off'", (web / "index.html").read_text(encoding="utf-8"))
        self.assertIn('data-anime-illustrations="on"', themes)
        self.assertIn('data-anime-illustrations="on"] .chapter-nav', themes)
        self.assertNotIn('data-theme="aiko-anime"][data-anime-illustrations="on"]', themes)
        self.assertNotIn('data-theme="aiko-anime"][data-anime-illustrations="on"]', refinement)
        self.assertIn("/assets/anime/aiko-blue-mascot.png", themes)
        self.assertTrue(asset.is_file())
        self.assertTrue(logo.is_file())
        self.assertTrue(cursor.is_file())
        self.assertTrue(chapter_arrow.is_file())
        self.assertTrue(review_loading.is_file())
        self.assertTrue(review_loading_still.is_file())
        self.assertIn("/assets/anime/aiko-reading-loading-v2.webp", themes)
        self.assertIn("/assets/anime/aiko-reading-loading-still-v2.webp", themes)
        self.assertNotIn("aiko-wand-circle", themes)
        project_memory = (web / "features" / "project-memory.js").read_text(encoding="utf-8")
        self.assertIn("firstElementChild?.classList.contains('review-loading')", project_memory)
        for name in nav_icons:
            asset_name = f"nav-{name}-v2.png"
            self.assertTrue((web / "assets" / "anime" / asset_name).is_file())
            self.assertEqual(themes.count(f"/assets/anime/{asset_name}"), 2)
        self.assertNotIn("-96.png?v=2", themes)
        self.assertTrue((web / "assets" / "anime" / "nav-all-v2.png").is_file())
        self.assertIn("/assets/anime/nav-all-v2.png", (web / "sidebar-icons.css").read_text(encoding="utf-8"))
        self.assertNotIn("background-position:right -1px center", themes)
        self.assertNotIn("background-position:right -2px center", themes)
        self.assertIn("novel-brush-cursor", script)
        self.assertIn('data-brush-cursor="on"', themes)
        self.assertIn("--anime-nav-icon", themes)


if __name__ == "__main__":
    unittest.main()
