import tempfile
import unittest
from pathlib import Path

from cores.context import filter_glossary, find_glossary_targets, load_context_text
from cores.storage.project import save_context, save_json


class ContextPackageTests(unittest.TestCase):
    def test_filter_glossary_keeps_relevant_cjk_and_latin_entries(self):
        glossary = "김 = Kim\n김철수 = Kim Cheol-su\nAlice = Alice\nBob = Bob"
        result = filter_glossary(glossary, "김 gặp Alice")
        self.assertEqual(
            result.splitlines(),
            ["김 = Kim", "김철수 = Kim Cheol-su", "Alice = Alice"],
        )

    def test_load_context_text_uses_json_and_glossary_txt(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            save_context(
                project,
                {"glossary": "Alice = Alice\nBob = Bob", "style_notes": "Giữ giọng nhẹ."},
            )
            result = load_context_text(project / "context.json", raw_text="Alice")
            self.assertIn("Alice = Alice", result)
            self.assertNotIn("Bob = Bob", result)
            self.assertIn("Giữ giọng nhẹ.", result)

    def test_targets_can_be_limited_to_pronoun_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            save_context(project, {"glossary": "Alice = Alice Smith\nBob = Bob Stone"})
            pronouns = project / "pronouns.json"
            save_json(
                pronouns,
                {"Alice---Carol": {"characters": ["Alice Smith", "Carol"], "timeline": []}},
            )
            targets = find_glossary_targets(
                project / "context.json", "Alice Bob", pronouns,
            )
            self.assertEqual(targets, ["Alice Smith"])


if __name__ == "__main__":
    unittest.main()
