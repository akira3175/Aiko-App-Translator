import unittest

from cores import config


class AppConfigTests(unittest.TestCase):
    def test_project_storage_paths_use_v1_formats(self):
        self.assertEqual(config.CONTEXT_JSON.name, "context.json")
        self.assertEqual(config.PRONOUNS_JSON.name, "pronouns.json")
        self.assertEqual(config.REVIEW_JSON.name, "review.json")
        self.assertEqual(config.MANUAL_CHECK_JSON.name, "manual_check.json")
        self.assertEqual(config.CHARACTERS_MD.name, "characters.md")

    def test_browser_and_model_defaults_are_available(self):
        self.assertTrue(config.LINK_GEMINI.startswith("https://"))
        self.assertTrue(config.LINK_CHATGPT.startswith("https://"))
        self.assertIsInstance(config.POLISH_MODEL, str)
        self.assertIsInstance(config.CHATGPT_SELECT_MODEL, str)


if __name__ == "__main__":
    unittest.main()
