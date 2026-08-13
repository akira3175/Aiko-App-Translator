import json
import unittest
from unittest.mock import patch

import app


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class SelectionLookupTests(unittest.TestCase):
    def test_lookup_language_prefers_script_specific_languages(self):
        self.assertEqual(app.lookup_source_language("hello"), "en")
        self.assertEqual(app.lookup_source_language("猫"), "zh-CN")
        self.assertEqual(app.lookup_source_language("食べる"), "ja")
        self.assertEqual(app.lookup_source_language("사랑"), "ko")

    def test_translate_details_returns_translation_and_language(self):
        payload = [
            [["chạy", "run", None, None, 10], [None, None, None, "rən"]],
            [["verb", ["chạy", "vận hành"]], ["noun", ["lượt chạy"]]],
            "en",
        ]
        with patch.object(app, "urlopen", return_value=_Response(payload)):
            result = app.google_translate_details("run")
        self.assertEqual(result["translated"], "chạy")
        self.assertEqual(result["detected_language"], "en")
        self.assertNotIn("pronunciation", result)
        self.assertNotIn("dictionary", result)

    def test_translate_details_limits_long_selection(self):
        with self.assertRaisesRegex(ValueError, "5.000"):
            app.google_translate_details("a" * 5001)


if __name__ == "__main__":
    unittest.main()
