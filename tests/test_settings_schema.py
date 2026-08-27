import unittest

from services import settings_schema


class SettingsSchemaTests(unittest.TestCase):
    def test_every_setting_has_a_label(self):
        self.assertEqual(
            set(settings_schema.SETTING_DEFAULTS),
            set(settings_schema.SETTING_LABELS),
        )

    def test_schema_references_only_known_settings(self):
        known = set(settings_schema.SETTING_DEFAULTS)
        self.assertLessEqual(set(settings_schema.SETTING_META), known)
        self.assertLessEqual(set(settings_schema.SETTING_RANGES), known)
        self.assertLessEqual(settings_schema.SECRET_SETTINGS, known)
        self.assertLessEqual(settings_schema.OPTIONAL_SETTINGS, known)
        self.assertLessEqual(settings_schema.HIDDEN_SETTINGS, known)

    def test_important_defaults_are_preserved(self):
        defaults = settings_schema.SETTING_DEFAULTS
        self.assertEqual("gemini-api", defaults["pipeline_translate_provider"])
        self.assertEqual("gemini-3.5-flash", defaults["pipeline_translate_model"])
        self.assertEqual("off", defaults["gemini_api_streaming"])
        self.assertEqual("off", defaults["lan_enabled"])
        self.assertEqual(
            settings_schema.DEFAULT_R19_MODEL,
            defaults["r19_model"],
        )

    def test_pipeline_source_models_remain_available_to_the_frontend(self):
        self.assertNotIn("review_model", settings_schema.HIDDEN_SETTINGS)
        self.assertNotIn("context_model", settings_schema.HIDDEN_SETTINGS)


if __name__ == "__main__":
    unittest.main()
