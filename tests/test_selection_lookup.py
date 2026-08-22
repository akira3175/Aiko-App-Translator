import json
import unittest
from urllib.parse import parse_qs

from services.source_translation import SourceTranslationService


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
        lookup = SourceTranslationService.source_language

        self.assertEqual(lookup("hello"), "en")
        self.assertEqual(lookup("猫"), "zh-CN")
        self.assertEqual(lookup("食べる"), "ja")
        self.assertEqual(lookup("사랑"), "ko")
        self.assertEqual(lookup("123"), "auto")

    def test_translate_details_returns_translation_and_language(self):
        payload = [
            [["chạy", "run", None, None, 10], [None, None, None, "rʌn"]],
            [["verb", ["chạy", "vận hành"]], ["noun", ["lượt chạy"]]],
            "en",
        ]
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return _Response(payload)

        result = SourceTranslationService(opener).translate_details(" run ")

        self.assertEqual(result, {"translated": "chạy", "detected_language": "en"})
        query = parse_qs(calls[0][0].data.decode("utf-8"))
        self.assertEqual(["run"], query["q"])
        self.assertEqual(["en"], query["sl"])
        self.assertEqual(15, calls[0][1])

    def test_translate_details_limits_long_selection(self):
        with self.assertRaisesRegex(ValueError, "5.000"):
            SourceTranslationService().translate_details("a" * 5001)

    def test_translate_details_rejects_empty_provider_result(self):
        service = SourceTranslationService(lambda *_args, **_kwargs: _Response([]))

        with self.assertRaisesRegex(ValueError, "không trả về"):
            service.translate_details("run")

    def test_translate_details_propagates_network_timeout(self):
        def timeout(*_args, **_kwargs):
            raise TimeoutError("timed out")

        with self.assertRaisesRegex(TimeoutError, "timed out"):
            SourceTranslationService(timeout).translate_details("run")


if __name__ == "__main__":
    unittest.main()
