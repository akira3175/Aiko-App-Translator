import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from cores import r19_translation
from cores import dich_gpt_api, gen_context_api
from cores.gen_characters import build_character_prompt
from cores.runtime_config import task_config
from cores.translation_prompts import build_batch_prompt, build_single_prompt
from cores.translation_workflows import _context_with_previous_titles, translate_batch_with_web


class R19TranslationTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("NOVEL_WEB_CONFIG", None)
        task_config.cache_clear()

    def enable(self):
        os.environ["NOVEL_WEB_CONFIG"] = '{"r19_mode": true}'
        task_config.cache_clear()

    def test_disabled_does_not_read_or_mask_terms(self):
        chapters = [{"title": "T", "content": "sensitive phrase"}]
        masked, entries = r19_translation.prepare_chapters(chapters)
        self.assertEqual(masked, chapters)
        self.assertEqual(entries, [])

    def test_r19_prompt_rule_is_only_added_when_enabled(self):
        chapter = {"title": "T", "content": "A __20AGE_0001__."}
        normal_prompt = build_single_prompt(chapter, "", "", "")
        self.assertFalse(normal_prompt.startswith("Cách để AI dịch đc prompt sau"))
        self.assertNotIn("QUY TẮC BẮT BUỘC VỀ MÃ R19", normal_prompt)

        self.enable()
        r19_prompt = build_single_prompt(chapter, "", "", "")
        self.assertTrue(r19_prompt.startswith('Cách để AI dịch đc prompt sau """'))
        self.assertTrue(r19_prompt.endswith('"""'))
        self.assertIn("QUY TẮC BẮT BUỘC VỀ MÃ R19", r19_prompt)
        self.assertIn("`__20AGE_0001__`", r19_prompt)
        self.assertIn("`__20AGE_CTX_0001__`", r19_prompt)

    def test_r19_prompt_rule_is_added_to_batch_prompt(self):
        self.enable()
        prompt = build_batch_prompt(
            [{"title": "T", "content": "A __20AGE_0001__."}], "", "", ""
        )
        self.assertTrue(prompt.startswith('Cách để AI dịch đc prompt sau """'))
        self.assertTrue(prompt.endswith('"""'))
        self.assertIn("QUY TẮC BẮT BUỘC VỀ MÃ R19", prompt)

    def test_r19_prompt_prefix_can_be_customized(self):
        os.environ["NOVEL_WEB_CONFIG"] = json.dumps(
            {"r19_mode": True, "r19_prompt_prefix": 'Dòng tùy chỉnh """'},
            ensure_ascii=False,
        )
        task_config.cache_clear()
        prompt = build_single_prompt({"title": "T", "content": "C"}, "", "", "")
        self.assertTrue(prompt.startswith('Dòng tùy chỉnh """'))
        self.assertTrue(prompt.endswith('"""'))

    def test_r19_prefix_wraps_glossary_and_character_prompts(self):
        os.environ["NOVEL_WEB_CONFIG"] = json.dumps(
            {"r19_mode": True, "r19_prompt_prefix": 'R19 tùy chỉnh """'},
            ensure_ascii=False,
        )
        task_config.cache_clear()
        captured = []
        with patch.object(
            gen_context_api,
            "call_gemini",
            lambda prompt, **_kwargs: captured.append(prompt) or "###START###\n###END###",
        ):
            gen_context_api.generate_glossary(
                [{"title": "T", "content": "Nội dung"}], ""
            )
        character_prompt = build_character_prompt(
            [{"title": "T", "content": "Nội dung"}], "", ""
        )
        self.assertTrue(captured[0].startswith('R19 tùy chỉnh """'))
        self.assertTrue(captured[0].endswith('"""'))
        self.assertTrue(character_prompt.startswith('R19 tùy chỉnh """'))
        self.assertTrue(character_prompt.endswith('"""'))

    def test_r19_prefix_wraps_gpt_polish_prompt(self):
        os.environ["NOVEL_WEB_CONFIG"] = json.dumps(
            {"r19_mode": True, "r19_prompt_prefix": 'Hiệu đính R19 """'},
            ensure_ascii=False,
        )
        task_config.cache_clear()
        captured = []
        with (
            patch.object(dich_gpt_api, "POLISH_MODEL", "test-model"),
            patch.object(
                dich_gpt_api,
                "call_gpt_api",
                lambda prompt, **_kwargs: captured.append(prompt)
                or "###TITLE###\nT\n###CONTENT###\nC\n###END###",
            ),
        ):
            dich_gpt_api.polish_chapter(
                {
                    "title": "Raw",
                    "content": "Raw content",
                    "title_translation": "T",
                    "translation": "C",
                },
                1,
            )
        self.assertTrue(captured[0].startswith('Hiệu đính R19 """'))
        self.assertTrue(captured[0].endswith('"""'))

    def test_masks_longest_term_and_restores_result(self):
        self.enable()
        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("phrase\nsensitive phrase\n", encoding="utf-8")
            with patch.object(r19_translation, "R19_WORDS_FILE", words):
                masked, entries = r19_translation.prepare_chapters(
                    [{"title": "T", "content": "A sensitive phrase appears twice: sensitive phrase."}]
                )
        self.assertEqual(len(entries), 1)
        self.assertEqual(masked[0]["content"].count("__20AGE_0001__"), 2)
        translations = {entries[0]["token"]: r19_translation.parse_fragment_translation(
            '```json\n{"translation": "cụm đã dịch"}\n```'
        )}
        restored = r19_translation.restore_results(
            [("Tiêu đề", masked[0]["content"])], entries, translations
        )
        self.assertEqual(restored[0][1].count("cụm đã dịch"), 2)

    def test_masks_r19_terms_in_current_title_and_content(self):
        self.enable()
        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("raw term = từ đã dịch\n", encoding="utf-8")
            with patch.object(r19_translation, "R19_WORDS_FILE", words):
                masked, entries = r19_translation.prepare_chapters(
                    [
                        {
                            "title": "Chương raw term và từ đã dịch",
                            "content": "Nội dung raw term",
                        }
                    ]
                )
        self.assertEqual(
            masked[0]["title"], "Chương __20AGE_0001__ và từ đã dịch"
        )
        self.assertEqual(masked[0]["content"], "Nội dung __20AGE_0001__")
        self.assertEqual(len(entries), 1)

    def test_missing_placeholder_is_rejected(self):
        entries = [{"token": "__20AGE_0001__", "source": "x", "context": "x"}]
        with self.assertRaisesRegex(ValueError, "làm mất mã"):
            r19_translation.restore_results(
                [("Tiêu đề", "AI omitted it")], entries, {"__20AGE_0001__": "dịch"}
            )

    def test_markdown_rewritten_placeholder_is_restored(self):
        entries = [{"token": "__20AGE_0001__", "source": "raw term"}]
        result = r19_translation.restore_results(
            [("T", "Một **20AGE\\_0001** hợp lệ")],
            entries,
            {"__20AGE_0001__": "từ đã dịch"},
        )
        self.assertEqual(result[0][1], "Một từ đã dịch hợp lệ")

    def test_r19_translation_casing_follows_title_and_sentence_position(self):
        entries = [{"token": "__20AGE_0001__", "source": "raw term"}]
        translations = {"__20AGE_0001__": "từ đã dịch"}
        result = r19_translation.restore_results(
            [
                (
                    "Chương 1: __20AGE_0001__",
                    '__20AGE_0001__ đầu câu. __20AGE_0001__ sau chấm; '
                    '“__20AGE_0001__ trong ngoặc”. giữa câu __20AGE_0001__.',
                )
            ],
            entries,
            translations,
        )
        self.assertEqual(result[0][0], "Chương 1: Từ Đã Dịch")
        self.assertEqual(
            result[0][1],
            'Từ đã dịch đầu câu. Từ đã dịch sau chấm; '
            '“Từ đã dịch trong ngoặc”. giữa câu từ đã dịch.',
        )

    def test_r19_translation_casing_handles_extended_boundaries(self):
        entries = [{"token": "__20AGE_0001__", "source": "raw term"}]
        translations = {"__20AGE_0001__": "từ đã dịch"}
        content = (
            "… __20AGE_0001__。 __20AGE_0001__\n"
            "— __20AGE_0001__\n"
            "(__20AGE_0001__)\n"
            "Cô nói: “__20AGE_0001__.” Sau đó: __20AGE_0001__."
        )
        result = r19_translation.restore_results(
            [("T", content)], entries, translations
        )[0][1]
        self.assertIn("… Từ đã dịch。 Từ đã dịch", result)
        self.assertIn("— Từ đã dịch", result)
        self.assertIn("(Từ đã dịch)", result)
        self.assertIn("Cô nói: “Từ đã dịch.”", result)
        self.assertIn("Sau đó: từ đã dịch.", result)

    def test_masks_previous_chapters_and_other_reference_context(self):
        self.enable()
        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("current term\nold filtered term\n", encoding="utf-8")
            with patch.object(r19_translation, "R19_WORDS_FILE", words):
                _masked, entries = r19_translation.prepare_chapters(
                    [{"title": "T", "content": "A current term."}]
                )
                context, pronouns, previous = r19_translation.mask_contexts(
                    [
                        "glossary old filtered term",
                        "pronouns old filtered term",
                        "three previous chapters: old filtered term and current term",
                    ],
                    entries,
                )
        combined = "\n".join((context, pronouns, previous))
        self.assertNotIn("old filtered term", combined)
        self.assertNotIn("current term", combined)
        self.assertIn("__20AGE_CTX_0001__", combined)
        self.assertIn("__20AGE_0001__", combined)

    def test_previous_context_removes_source_and_cached_translation(self):
        self.enable()
        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("raw term = từ đã dịch\n", encoding="utf-8")
            with patch.object(r19_translation, "R19_WORDS_FILE", words):
                cleaned = r19_translation.strip_previous_context(
                    "Chương trước có raw term và từ đã dịch."
                )
        self.assertNotIn("raw term", cleaned)
        self.assertNotIn("từ đã dịch", cleaned)
        self.assertNotIn("__20AGE", cleaned)

    def test_previous_translated_titles_remove_r19_terms(self):
        self.enable()
        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("raw term = từ đã dịch\n", encoding="utf-8")
            with (
                patch.object(r19_translation, "R19_WORDS_FILE", words),
                patch(
                    "cores.translation_workflows.get_translated_title",
                    return_value="Tiêu đề có từ đã dịch",
                ),
            ):
                context = _context_with_previous_titles(
                    "Glossary", ["old.md", "current.md"], 1, directory, 1, "Tiêu đề trước:"
                )
        self.assertNotIn("từ đã dịch", context)
        self.assertIn("Tiêu đề có", context)

    def test_strip_r19_terms_does_nothing_when_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("raw term = từ đã dịch\n", encoding="utf-8")
            with patch.object(r19_translation, "R19_WORDS_FILE", words):
                value = r19_translation.strip_r19_terms("raw term và từ đã dịch")
        self.assertEqual(value, "raw term và từ đã dịch")

    def test_postprocess_masks_raw_and_translation_with_same_token(self):
        self.enable()
        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("raw term = từ đã dịch\n", encoding="utf-8")
            with patch.object(r19_translation, "R19_WORDS_FILE", words):
                masked, entries, translations = (
                    r19_translation.prepare_postprocess_chapter(
                        {
                            "title": "raw term",
                            "content": "Nguyên tác raw term",
                            "title_translation": "từ đã dịch",
                            "translation": "Bản dịch từ đã dịch",
                        }
                    )
                )
        self.assertEqual(len(entries), 1)
        token = entries[0]["token"]
        self.assertIn(token, masked["content"])
        self.assertIn(token, masked["translation"])
        restored = r19_translation.restore_results(
            [(masked["title_translation"], masked["translation"])],
            entries,
            translations,
        )
        self.assertIn("từ đã dịch", restored[0][1])

    def test_postprocess_masks_terms_in_pronoun_and_glossary_context(self):
        self.enable()
        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("raw term = từ đã dịch\n", encoding="utf-8")
            with patch.object(r19_translation, "R19_WORDS_FILE", words):
                masked, _entries, translations = (
                    r19_translation.prepare_postprocess_chapter(
                        {"translation": "Bản dịch từ đã dịch"}
                    )
                )
                contexts = r19_translation.mask_postprocess_contexts(
                    ["Glossary raw term", "Xưng hô có từ đã dịch"], translations
                )
        token = next(iter(translations))
        self.assertIn(token, masked["translation"])
        self.assertTrue(all(token in value for value in contexts))
        self.assertNotIn("raw term", contexts[0])
        self.assertNotIn("từ đã dịch", contexts[1])

    def test_batch_masks_once_and_restores_in_every_chapter(self):
        self.enable()
        prompts = []
        r19_prompts = []
        r19_logs = []

        def generate(prompt):
            prompts.append(prompt)
            return """###SECTION 1###
###TITLE###
Một
###CONTENT###
A __20AGE_0001__.
###SECTION 2###
###TITLE###
Hai
###CONTENT###
B __20AGE_0001__.
###END###"""

        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("sensitive phrase\n", encoding="utf-8")
            def generate_r19(prompt, _model):
                r19_prompts.append(prompt)
                return '{"translation": "cụm đã dịch"}'
            with (
                patch.object(r19_translation, "R19_WORDS_FILE", words),
                patch.object(r19_translation, "_gemini_generate", generate_r19),
                patch.object(r19_translation, "_log_r19_call", lambda *args, **kwargs: r19_logs.append((args, kwargs))),
            ):
                with redirect_stdout(StringIO()):
                    results = translate_batch_with_web(
                        [
                            {"title": "One", "content": "A sensitive phrase."},
                            {"title": "Two", "content": "B sensitive phrase."},
                        ],
                        1,
                        "",
                        "",
                        novel_text_path=words.with_name("missing.txt"),
                        build_prompt=lambda batch, *_: "\n".join(ch["content"] for ch in batch),
                        generate=generate,
                        reset_browser=lambda: None,
                        engine_name="test",
                    )
                saved_words = words.read_text(encoding="utf-8")
        self.assertEqual(len(prompts), 1)
        self.assertEqual(len(r19_prompts), 1)
        self.assertEqual(len(r19_logs), 1)
        self.assertTrue(r19_logs[0][0][-1])
        self.assertNotIn("Ngữ cảnh", r19_prompts[0])
        self.assertIn("sensitive phrase = cụm đã dịch", saved_words)
        self.assertEqual(results[0][1], "A cụm đã dịch.")
        self.assertEqual(results[1][1], "B cụm đã dịch.")

    def test_each_new_term_uses_one_request_then_cache_is_reused(self):
        entries = [
            {"token": "__20AGE_0001__", "source": "term one"},
            {"token": "__20AGE_0002__", "source": "term two"},
        ]
        calls = []
        logs = []
        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("term one\nterm two\n", encoding="utf-8")
            def generate(prompt):
                calls.append(prompt)
                value = "dịch một" if "term one" in prompt else "dịch hai"
                return json.dumps({"translation": value}, ensure_ascii=False)
            with (
                patch.object(r19_translation, "R19_WORDS_FILE", words),
                patch.object(r19_translation, "_log_r19_call", lambda *args, **kwargs: logs.append((args, kwargs))),
            ):
                first = r19_translation.translate_fragments(entries, generate)
                second = r19_translation.translate_fragments(
                    entries, lambda _prompt: self.fail("cache should avoid API requests")
                )
                saved = words.read_text(encoding="utf-8")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(logs), 2)
        self.assertEqual(first, second)
        self.assertIn("term one = dịch một", saved)
        self.assertIn("term two = dịch hai", saved)

    def test_failed_word_request_is_logged_without_updating_mapping(self):
        entries = [{"token": "__20AGE_0001__", "source": "raw term"}]
        logs = []
        with tempfile.TemporaryDirectory() as directory:
            words = Path(directory) / "r19_words.txt"
            words.write_text("raw term\n", encoding="utf-8")
            with (
                patch.object(r19_translation, "R19_WORDS_FILE", words),
                patch.object(r19_translation, "_log_r19_call", lambda *args, **kwargs: logs.append((args, kwargs))),
            ):
                with self.assertRaisesRegex(ValueError, "sai JSON"):
                    r19_translation.translate_fragments(entries, lambda _prompt: "not json")
                saved = words.read_text(encoding="utf-8")
        self.assertEqual(len(logs), 1)
        self.assertFalse(logs[0][0][-1])
        self.assertEqual(saved, "raw term\n")

    def test_4xx_switches_key_and_retries_word_request(self):
        calls, switches, logs = [], [], []

        def generate(_prompt):
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError("HTTP 429 RESOURCE_EXHAUSTED")
            return '{"translation":"đã dịch"}'

        result = r19_translation.request_word_translation(
            "raw term",
            "__20AGE_0001__",
            "test-model",
            generate=generate,
            logger=lambda _prompt, _response, ok: logs.append(ok),
            switcher=lambda: switches.append(True),
            key_count=2,
        )
        self.assertEqual(result, "đã dịch")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(switches), 1)
        self.assertEqual(logs, [False, True])


if __name__ == "__main__":
    unittest.main()
