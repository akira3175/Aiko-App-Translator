import unittest
from unittest.mock import patch

from cores.context import generation


class ContextGenerationTests(unittest.TestCase):
    def test_all_four_engines_use_glossary_stage(self):
        chapters = [{"title": "原題", "content": "原文"}]
        for provider in ("gemini-api", "gemini-web", "openai-api", "chatgpt-web"):
            calls = []

            def transport(prompt, **kwargs):
                calls.append((prompt, kwargs))
                return "###START###\n原文 = Bản dịch\n###END###"

            with (
                patch.object(generation, "context_provider", return_value=provider),
                patch.object(
                    generation,
                    "context_model_and_thinking",
                    return_value=("test-model", "high"),
                ),
                patch.dict(
                    generation.TRANSPORT_OVERRIDES, {provider: transport}, clear=True
                ),
                patch.object(generation, "int_option", return_value=1),
            ):
                result = generation.generate_glossary(chapters, "")

            self.assertIn("原文 = Bản dịch", result)
            self.assertEqual(len(calls), 1)

    def test_prompt_contains_old_glossary_and_required_markers(self):
        prompt = generation.build_glossary_prompt(
            [{"title": "原題", "content": "原文"}], "既存 = Đã có"
        )
        self.assertIn("既存 = Đã có", prompt)
        self.assertIn("原文", prompt)
        self.assertIn("###START###", prompt)
        self.assertIn("###END###", prompt)


if __name__ == "__main__":
    unittest.main()
