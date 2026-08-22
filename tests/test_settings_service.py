import json
import tempfile
import unittest
from pathlib import Path

from services.settings import ConfigurationService


class _ApiKeys:
    def __init__(self):
        self.tested = None

    def payload(self, keys_path, state_path):
        return {"paths": [keys_path, state_path]}

    def save(self, payload, keys_path, state_path):
        return {"payload": payload, "paths": [keys_path, state_path]}

    def set_active(self, payload, keys_path, state_path):
        return {"payload": payload, "paths": [keys_path, state_path]}

    def test_key(self, key, model):
        self.tested = (key, model)
        return {"ok": True}


class SettingsServiceTests(unittest.TestCase):
    def _service(self, root):
        api_keys = _ApiKeys()
        service = ConfigurationService(
            settings_path=root / "settings.json",
            ui_preferences_path=root / "ui_preferences.json",
            setting_defaults={
                "translate_model": "default-model",
                "retry": 3,
                "lan_enabled": "off",
                "lan_pin": "",
            },
            setting_labels={
                "translate_model": "Model",
                "retry": "Số lần thử",
                "lan_enabled": "LAN",
                "lan_pin": "PIN",
            },
            setting_ranges={"retry": (1, 5)},
            setting_meta={},
            secret_settings={"lan_pin"},
            optional_settings={"lan_pin"},
            hidden_settings=set(),
            default_pinned_sidebar=["workspace"],
            sidebar_features={"workspace", "help", "settings"},
            fixed_sidebar_features={"settings"},
            api_keys=api_keys,
            api_keys_path=root / "keys.txt",
            api_key_state_path=root / "key-state.json",
        )
        return service, api_keys

    def test_settings_round_trip_and_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, _api_keys = self._service(root)

            result = service.write_settings(
                {
                    "values": {
                        "translate_model": "custom-model",
                        "retry": 4,
                        "lan_enabled": "off",
                        "lan_pin": "",
                    }
                }
            )

            self.assertEqual("custom-model", result["items"][0]["value"])
            self.assertEqual(
                {"translate_model": "custom-model", "retry": 4},
                json.loads((root / "settings.json").read_text(encoding="utf-8")),
            )
            service.write_settings({"reset": True})
            self.assertFalse((root / "settings.json").exists())

    def test_ui_preferences_are_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _api_keys = self._service(Path(directory))

            saved = service.write_ui_preferences(
                {"sidebar": {"pinned": ["help", "settings", "help"]}}
            )

            self.assertEqual({"sidebar": {"pinned": ["help"]}}, saved)
            self.assertEqual(saved, service.ui_preferences())

    def test_api_key_diagnostic_uses_saved_translation_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, api_keys = self._service(root)
            service.write_settings(
                {
                    "values": {
                        "translate_model": "chosen-model",
                        "retry": 3,
                        "lan_enabled": "off",
                        "lan_pin": "",
                    }
                }
            )

            service.test_api_key({"key": "secret"})

            self.assertEqual(("secret", "chosen-model"), api_keys.tested)

    def test_invalid_number_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _api_keys = self._service(Path(directory))
            with self.assertRaisesRegex(ValueError, "Số lần thử"):
                service.write_settings(
                    {
                        "values": {
                            "translate_model": "default-model",
                            "retry": 9,
                            "lan_enabled": "off",
                            "lan_pin": "",
                        }
                    }
                )


if __name__ == "__main__":
    unittest.main()
