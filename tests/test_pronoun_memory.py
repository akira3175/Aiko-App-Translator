import tempfile
import unittest
from pathlib import Path

from cores.pronouns import (
    extract_pronouns_from_translation,
    format_pronoun_context,
    load_pronouns,
    save_pronouns,
    update_pronoun_memory,
)


class PronounMemoryTests(unittest.TestCase):
    def test_save_and_load_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pronouns.json"
            data = {"An---Bình": {"characters": ["An", "Bình"], "timeline": []}}
            save_pronouns(data, path)
            self.assertEqual(load_pronouns(path), data)

    def test_extract_pronouns_uses_injected_generator(self):
        result = extract_pronouns_from_translation(
            "v1_c2_s1",
            2,
            "An gọi Bình là cậu.",
            model="test-model",
            generate=lambda _prompt: '{"character_pairs":[{"speaker":"An","listener":"Bình","speaker_self":"tôi","speaker_to_listener":"cậu"}]}',
            sleep=lambda _seconds: None,
        )
        record = result[("An", "Bình")]["timeline"][0]
        self.assertEqual(record["chapter_id"], "v1_c2_s1")
        self.assertEqual(record["speaker_to_listener"], "cậu")

    def test_update_preserves_locked_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pronouns.json"
            original = {
                "An---Bình": {
                    "characters": ["An", "Bình"],
                    "locked": True,
                    "timeline": [{"chapter_number": 1, "speaker": "An", "listener": "Bình"}],
                }
            }
            save_pronouns(original, path)
            update_pronoun_memory(
                "v1_c2_s1",
                2,
                "text",
                pronouns_file=path,
                model="test-model",
                generate=lambda _prompt: '{"character_pairs":[{"speaker":"An","listener":"Bình"}]}',
                sleep=lambda _seconds: None,
            )
            self.assertEqual(load_pronouns(path), original)

    def test_context_prefers_glossary_relevant_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pronouns.json"
            save_pronouns(
                {
                    "An---Bình": {
                        "characters": ["An", "Bình"],
                        "timeline": [{"chapter_number": 2, "speaker": "An", "listener": "Bình", "speaker_self": "tôi", "speaker_to_listener": "cậu"}],
                    },
                    "Cường---Dũng": {
                        "characters": ["Cường", "Dũng"],
                        "timeline": [{"chapter_number": 3, "speaker": "Cường", "listener": "Dũng", "speaker_self": "ta", "speaker_to_listener": "ngươi"}],
                    },
                },
                path,
            )
            context = format_pronoun_context(4, path, glossary_names=["An"])
            self.assertIn("An → Bình", context)
            self.assertNotIn("Cường → Dũng", context)


if __name__ == "__main__":
    unittest.main()
