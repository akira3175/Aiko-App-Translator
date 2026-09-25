import asyncio
import unittest
from unittest.mock import patch

from up import edit_hako, up_md


class HakoR2ConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(account_id="account", access_key_id="access",
                           secret_access_key="secret", bucket="images",
                           public_url="https://images.example.com")
        self.settings = {f"r2_{key}": value for key, value in self.config.items()}
        previous = up_md._r2_config
        self.addCleanup(setattr, up_md, "_r2_config", previous)
        up_md._r2_config = {}

    def test_edit_entrypoint_loads_settings_before_browser_starts(self):
        with patch.object(up_md, "option", side_effect=self.settings.get), \
             patch.object(edit_hako, "edit_targets", return_value=[]), \
             patch.object(edit_hako, "grouped_local_chapters", return_value={}), \
             patch.object(edit_hako, "option", return_value="test"), \
             patch.object(edit_hako, "async_playwright", side_effect=RuntimeError("browser boundary")):
            with self.assertRaisesRegex(RuntimeError, "browser boundary"):
                asyncio.run(edit_hako.main())
        self.assertEqual(up_md._r2_config, self.config)

    def test_web_publishing_prefers_app_settings_over_legacy_config(self):
        with patch.object(up_md, "web_mode", return_value=True), \
             patch.object(up_md, "option", side_effect=self.settings.get):
            self.assertTrue(up_md.configure_r2({"cloudflare_r2": {}}))
        self.assertEqual(up_md._r2_config, self.config)

    def test_standalone_publishing_keeps_legacy_config(self):
        with patch.object(up_md, "web_mode", return_value=False):
            self.assertTrue(up_md.configure_r2({"cloudflare_r2": self.config}))
        self.assertEqual(up_md._r2_config, self.config)

    def test_incomplete_settings_clear_previous_credentials(self):
        up_md._r2_config = self.config
        self.settings.pop("r2_secret_access_key")
        with patch.object(up_md, "option", side_effect=self.settings.get):
            self.assertFalse(up_md.configure_r2())
        self.assertEqual(up_md._r2_config, {})


if __name__ == "__main__":
    unittest.main()
