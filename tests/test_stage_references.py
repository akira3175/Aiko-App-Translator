import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores.stages import references
from providers.base import ProviderRequest
from providers.chatgpt_web import ChatGptWebProvider
from providers.gemini_api import GeminiApiProvider
from providers.gemini_web import GeminiWebProvider


class StageReferenceTests(unittest.TestCase):
    def test_build_documents_reads_and_removes_temporary_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            characters = root / "characters.md"
            pronouns = root / "pronouns.json"
            characters.write_text("# Characters", encoding="utf-8")
            pronouns.write_text(json.dumps({"A---B": {}}), encoding="utf-8")
            with patch.object(
                references, "build_characters_snapshot", return_value=str(characters)
            ), patch.object(
                references, "build_pronouns_snapshot", return_value=str(pronouns)
            ):
                documents = references.build_reference_documents({})
            self.assertEqual(
                [item["name"] for item in documents],
                ["characters.md", "pronouns_snapshot.json"],
            )
            self.assertFalse(characters.exists())
            self.assertFalse(pronouns.exists())

    def test_gemini_api_maps_documents_to_native_reference_parts(self):
        calls = []
        provider = GeminiApiProvider(lambda prompt, **kwargs: calls.append(kwargs) or "ok")
        provider.generate(
            ProviderRequest(
                "translate",
                "prompt",
                "model",
                None,
                attachments=(
                    {"name": "characters.md", "content": "characters"},
                    {"name": "pronouns_snapshot.json", "content": "pronouns"},
                ),
            )
        )
        self.assertEqual(calls[0]["character_document"], "characters")
        self.assertEqual(calls[0]["pronoun_document"], "pronouns")
        self.assertEqual(len(calls[0]["extra_parts"]), 2)

    def test_chatgpt_web_does_not_embed_documents_in_translation_prompt(self):
        prompts = []
        provider = ChatGptWebProvider(
            lambda prompt, **kwargs: prompts.append(prompt) or "ok"
        )
        provider.generate(
            ProviderRequest(
                "translate",
                "prompt",
                "model",
                None,
                attachments=({"name": "characters.md", "content": "Alice"},),
            )
        )
        self.assertEqual(prompts[0], "prompt")

    def test_chatgpt_web_keeps_documents_for_polish_prompt(self):
        prompts = []
        provider = ChatGptWebProvider(
            lambda prompt, **kwargs: prompts.append(prompt) or "ok"
        )
        provider.generate(
            ProviderRequest(
                "polish",
                "prompt",
                "model",
                None,
                attachments=({"name": "characters.md", "content": "Alice"},),
            )
        )
        self.assertIn("## Reference file: characters.md", prompts[0])

    def test_chatgpt_web_does_not_override_configured_conversation_url(self):
        calls = []
        provider = ChatGptWebProvider(
            lambda prompt, **kwargs: calls.append(kwargs) or "ok"
        )
        provider.generate(ProviderRequest("translate", "prompt", "model"))
        self.assertNotIn("chat_url", calls[0])

        provider.generate(
            ProviderRequest(
                "translate",
                "prompt",
                "model",
                options={"chat_url": "https://chatgpt.com/c/test"},
            )
        )
        self.assertEqual("https://chatgpt.com/c/test", calls[1]["chat_url"])

    def test_gemini_web_does_not_embed_documents_in_translation_prompt(self):
        prompts = []
        provider = GeminiWebProvider(
            lambda prompt, **kwargs: prompts.append(prompt) or "ok"
        )
        provider.generate(
            ProviderRequest(
                "translate",
                "prompt",
                "model",
                None,
                attachments=({"name": "characters.md", "content": "Alice"},),
            )
        )
        self.assertEqual(prompts[0], "prompt")


if __name__ == "__main__":
    unittest.main()
