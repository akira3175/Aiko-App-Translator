import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores.characters import generation
from cores.characters.parser import (
    extract_character_block,
    merge_characters,
    parse_characters,
)
from cores.characters.storage import load_index, save_index


class CharactersPackageTests(unittest.TestCase):
    def test_all_four_engines_generate_valid_character_blocks(self):
        response = "###CHAR_START###\n## An\n- **Giới tính**: Nam\n###CHAR_END###"
        for provider in ("gemini-api", "gemini-web", "openai-api", "chatgpt-web"):
            calls = []

            def transport(prompt, **kwargs):
                calls.append((prompt, kwargs))
                return response

            values = {
                "characters_stage_model": "test-model",
                "characters_stage_thinking": "high",
            }
            with (
                patch.dict(
                    generation.TRANSPORT_OVERRIDES, {provider: transport}, clear=True
                ),
                patch.object(
                    generation,
                    "option",
                    side_effect=lambda key, default=None: values.get(key, default),
                ),
            ):
                block = generation.request_character_block(
                    "prompt", provider=provider, max_retries=1
                )

            self.assertIn("## An", block)
            self.assertEqual(len(calls), 1)

    def test_extracts_marked_character_blocks(self):
        response = """###CHAR_START###
## An

### Thông tin cơ bản
- **Giới tính**: Nam
###CHAR_END###"""
        block = extract_character_block(response)
        self.assertIn("## An", block)
        self.assertEqual(list(parse_characters(block)), ["An"])

    def test_merge_preserves_fields_missing_from_new_block(self):
        existing = "## An\n- **Tên gốc**: 安\n- **Giới tính**: Nam"
        incoming = "## An\n- **Giới tính**: Nam"
        merged = merge_characters(existing, incoming)
        self.assertIn("- **Tên gốc**: 安", merged)
        self.assertIn("### Thông tin được bảo toàn", merged)

    def test_character_index_uses_project_state_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project_state.json"
            save_index(5, path)
            save_index(12, path)
            self.assertEqual(load_index(path), 12)
            self.assertTrue(path.with_name("project_state.json.bak").exists())


if __name__ == "__main__":
    unittest.main()
