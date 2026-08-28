import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from cores.postprocess.language_check import fix_translation, save_manual_check_id
from cores.storage.project import load_json


class ManualCheckStorageTests(unittest.TestCase):
    def test_manual_check_is_saved_as_json_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_check.json"
            save_manual_check_id("v1_c1_s1", path)
            save_manual_check_id("v1_c1_s1", path)
            self.assertEqual(load_json(path, []), ["v1_c1_s1"])

    def test_fix_translation_requires_end_marker_and_strips_it(self):
        response = "###TITLE###\nTiêu đề mới\n###CONTENT###\nNội dung mới\n###END###"
        runtime = Mock()
        runtime.FIX_MAX_RETRY = 2
        runtime.model_and_thinking.return_value = ("model", "high")
        runtime.has_foreign.side_effect = [True, False, False]
        runtime.wrap_r19_prompt.side_effect = lambda prompt: prompt
        runtime._r19_placeholder_instruction.return_value = ""
        runtime.generate.return_value = (response, "provider", "model")
        chapter = {
            "id": "v1_c1_s1",
            "title_translation": "Tiêu đề 中文",
            "translation": "Nội dung",
        }

        result = fix_translation(runtime, chapter, 1)

        self.assertEqual(result, ("Tiêu đề mới", "Nội dung mới"))
        prompt = runtime.generate.call_args.args[1]
        self.assertIn("###END###", prompt)
        self.assertNotIn("###END###", chapter["translation"])


if __name__ == "__main__":
    unittest.main()
