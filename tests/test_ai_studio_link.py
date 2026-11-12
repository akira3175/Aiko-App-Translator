import unittest

from cores.google_ai_studio.web_client import _prompt_url


class AiStudioLinkTest(unittest.TestCase):
    def test_blank_link_opens_new_chat(self):
        self.assertEqual(
            _prompt_url("gemini-flash-latest", ""),
            "https://aistudio.google.com/prompts/new_chat?model=gemini-flash-latest",
        )

    def test_saved_prompt_link_gets_stage_model(self):
        self.assertEqual(
            _prompt_url("gemini-pro-latest", "https://aistudio.google.com/prompts/abc123"),
            "https://aistudio.google.com/prompts/abc123?model=gemini-pro-latest",
        )

    def test_model_pinned_in_link_is_kept(self):
        url = _prompt_url(
            "gemini-flash-latest",
            "https://aistudio.google.com/prompts/abc123?model=gemini-3-pro",
        )
        self.assertEqual(url, "https://aistudio.google.com/prompts/abc123?model=gemini-3-pro")

    def test_foreign_or_insecure_link_falls_back_to_new_chat(self):
        for link in ("https://example.com/prompts/x", "http://aistudio.google.com/prompts/x"):
            self.assertTrue(
                _prompt_url("gemini-flash-latest", link).startswith(
                    "https://aistudio.google.com/prompts/new_chat?"
                )
            )


if __name__ == "__main__":
    unittest.main()

