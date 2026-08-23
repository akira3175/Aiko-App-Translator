import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores.config import runtime


class RuntimeSettingsTests(unittest.TestCase):
    def setUp(self):
        runtime.task_config.cache_clear()

    def tearDown(self):
        runtime.task_config.cache_clear()

    def test_migrates_legacy_settings_to_shared_user_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "old" / "settings.json"
            shared = root / "shared" / "settings.json"
            legacy.parent.mkdir()
            legacy.write_text(json.dumps({"link_chatgpt": "https://chatgpt.com/c/test"}), encoding="utf-8")
            with patch.object(runtime, "LEGACY_SETTINGS_FILE", legacy), patch.object(
                runtime, "SETTINGS_FILE", shared
            ):
                moved = runtime.ensure_settings_migrated()
                self.assertEqual(legacy, moved)
                self.assertFalse(legacy.exists())
                self.assertEqual(
                    "https://chatgpt.com/c/test",
                    runtime.task_config()["link_chatgpt"],
                )

    def test_existing_shared_settings_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "old.json"
            shared = root / "shared.json"
            legacy.write_text('{"value": "legacy"}', encoding="utf-8")
            shared.write_text('{"value": "shared"}', encoding="utf-8")
            with patch.object(runtime, "LEGACY_SETTINGS_FILE", legacy), patch.object(
                runtime, "SETTINGS_FILE", shared
            ):
                self.assertIsNone(runtime.ensure_settings_migrated())
                self.assertTrue(legacy.exists())
                self.assertEqual("shared", runtime.task_config()["value"])


if __name__ == "__main__":
    unittest.main()
