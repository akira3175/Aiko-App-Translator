"""Polish metadata must describe final prose and never leak into chapter text."""

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores.postprocess.language_check import fix_translation
from cores.postprocess.outputs import parse_polish_output
from cores.postprocess.pipeline import run_post_translation_pipeline
from cores.postprocess.polish import polish_translation
from cores.pronouns import load_pronouns, resolve_direction, save_pronouns, update_pronoun_memory
from cores.pronouns.extraction import apply_pronoun_payload, build_pronoun_instructions


PAIR = {"speaker": "Ally", "listener": "Bob", "speaker_self": "I", "speaker_to_listener": "you"}
PAYLOAD = {"character_pairs": [PAIR]}
MISSING = object()


def output(content="Polished dialogue", payload=PAYLOAD, title="Title"):
    pronouns = "" if payload is MISSING else "\n###PRONOUNS###\n" + (
        payload if isinstance(payload, str) else json.dumps(payload)
    )
    return f"###TITLE###\n{title}\n###CONTENT###\n{content}{pronouns}\n###END###"


class PolishOutputTests(unittest.TestCase):
    def test_valid_and_fenced_json_are_separated(self):
        for payload in (PAYLOAD, '```json\n' + json.dumps(PAYLOAD) + '\n```'):
            with self.subTest(payload=payload):
                self.assertEqual(parse_polish_output(output(payload=payload)), ("Title", "Polished dialogue", PAYLOAD))

    def test_missing_bad_or_truncated_json_keeps_prose_only(self):
        cases = [output(payload=payload) for payload in (
            MISSING, "not JSON", '{"character_pairs":[', {}, [],
            {"character_pairs": None}, {"character_pairs": [{}]},
            {"character_pairs": [PAIR, {"speaker": "Bob"}]},
        )]
        cases.extend([
            output().replace("###END###", '###PRONOUNS###\n{}\n###END###'),
        ])
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_polish_output(text), ("Title", "Polished dialogue", None))

    def test_empty_list_is_valid_output(self):
        self.assertEqual(parse_polish_output(output(payload={"character_pairs": []}))[2], {"character_pairs": []})

    def test_missing_or_misplaced_end_marker_is_rejected(self):
        for text in (
            output().removesuffix("###END###"),
            output(payload=MISSING).removesuffix("###END###"),
            output() + '\n###PRONOUNS###\n{}',
            output() + '\n###END###',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_polish_output(text)

    def test_inline_and_escaped_markers_do_not_leak_json(self):
        for text in (output().replace("\n", ""), output().replace("###", "\\###")):
            with self.subTest(text=text):
                self.assertEqual(parse_polish_output(text), ("Title", "Polished dialogue", PAYLOAD))

    def test_wrong_order_duplicates_and_empty_prose_are_rejected(self):
        for text in (
            "###CONTENT###\nText\n###TITLE###\nTitle\n###END###",
            "###TITLE###\nTitle\n###PRONOUNS###\n{}\n###CONTENT###\nText\n###END###",
            output(content=""), output(title=""),
            output().replace("###CONTENT###", "###TITLE###\nAgain\n###CONTENT###"),
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_polish_output(text)

    def test_shared_prompt_example_is_valid_json(self):
        text = build_pronoun_instructions()
        schema = text.split("format:", 1)[1].split("Quy tắc", 1)[0].strip()
        self.assertIn("character_pairs", json.loads(schema))


class FakeRuntime:
    """Real parsing, language check and memory persistence; injected AI text."""
    def __init__(self, project, responses, *, polish=True, pronouns=True, fallback=PAYLOAD):
        self.project = project
        self.responses = iter(responses)
        self.flags = {"polish": polish, "pronouns": pronouns}
        self.fallback = fallback
        self.calls = []
        self.FIX_MAX_RETRY = 2
        self.MANUAL_CHECK_JSON = project / "manual-check.json"

    def enabled(self, stage):
        return self.flags.get(stage, False)

    def provider(self, stage):
        return "test" if self.enabled(stage) else "off"

    def model_and_thinking(self, stage):
        return "test-model", "high"

    def generate(self, stage, prompt, attachments=()):
        self.calls.append((stage, prompt, attachments))
        if stage == "polish":
            return next(self.responses), "test", "test-model"
        return json.dumps(self.fallback), "test", "test-model"

    def polish_translation(self, chapter, number, context, pronouns, **kwargs):
        return polish_translation(self, chapter, number, context, pronouns, self.project / "characters.md", **kwargs)

    def fix_translation(self, *args):
        return fix_translation(self, *args)

    def update_pronoun_memory(self, chapter_id, number, content, path, source_text=""):
        return update_pronoun_memory(
            chapter_id, number, content, path, "test-model",
            lambda prompt: self.generate("pronouns", prompt)[0],
            sleep=lambda _: None, source_text=source_text,
        )

    apply_pronoun_payload = staticmethod(apply_pronoun_payload)
    int_option = staticmethod(lambda _key, default, **_kwargs: default)
    project_polish_prompt = staticmethod(lambda: ("Editor", "Polish the translation"))
    wrap_r19_prompt = staticmethod(lambda text: text)
    _r19_placeholder_instruction = staticmethod(lambda: "")
    with_character_document_instruction = staticmethod(lambda text: text)
    log_api_call = staticmethod(lambda *_args, **_kwargs: None)
    has_foreign = staticmethod(lambda text: "漢" in text)
    setup_browser = staticmethod(lambda _provider: None)
    close_browsers = staticmethod(lambda: None)


class PolishPronounPipelineTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.project = Path(directory.name)
        self.path = self.project / "pronouns.json"
        (self.project / "characters.md").write_text("## Alice / Ally\n\n## Bob\n", encoding="utf-8")
        self.chapter = {"id": "c1", "title": "Raw", "content": "Alice and Bob talk.", "title_translation": "Old title", "translation": "Old dialogue"}

    def run_pipeline(self, runtime):
        return run_post_translation_pipeline(runtime, self.chapter, 1, "context", "memory", self.path)

    def test_valid_polish_uses_one_ai_call_and_canonical_names(self):
        runtime = FakeRuntime(self.project, [output()])
        result = self.run_pipeline(runtime)
        self.assertEqual(result, ("Title", "Polished dialogue"))
        self.assertEqual([call[0] for call in runtime.calls], ["polish"])
        self.assertIn("###PRONOUNS###", runtime.calls[0][1])
        self.assertIn("Alice (còn gọi: Ally)", runtime.calls[0][1])
        self.assertIn("bản hoàn chỉnh ở ###CONTENT###", runtime.calls[0][1])
        saved = load_pronouns(self.path)["Alice---Bob"]["timeline"]
        self.assertEqual(saved[0]["speaker"], "Alice")
        self.assertEqual(saved[0]["chapter_id"], "c1")

    def test_missing_or_invalid_payload_falls_back_without_losing_polish(self):
        for payload in (MISSING, "bad JSON", {"character_pairs": [{}]}):
            with self.subTest(payload=payload):
                runtime = FakeRuntime(self.project, [output(payload=payload)])
                self.assertEqual(self.run_pipeline(runtime), ("Title", "Polished dialogue"))
                self.assertEqual([call[0] for call in runtime.calls], ["polish", "pronouns"])
                self.assertIn("Polished dialogue", runtime.calls[-1][1])
                self.assertIn("Alice---Bob", load_pronouns(self.path))

    def test_empty_payload_clears_old_ai_history_without_fallback(self):
        apply_pronoun_payload("c1", 1, PAYLOAD, self.path)
        runtime = FakeRuntime(self.project, [output(payload={"character_pairs": []})])
        self.run_pipeline(runtime)
        self.assertEqual(load_pronouns(self.path), {})
        self.assertEqual(len(runtime.calls), 1)

    def test_language_fix_uses_final_text_and_discards_old_metadata(self):
        fallback = {"character_pairs": [{**PAIR, "speaker_self": "FINAL"}]}
        runtime = FakeRuntime(self.project, [
            output(content="Polished 漢 dialogue"),
            # A provider may repeat the new format during the language fix.
            output(content="Corrected dialogue"),
        ], fallback=fallback)
        self.assertEqual(self.run_pipeline(runtime), ("Title", "Corrected dialogue"))
        self.assertEqual([call[0] for call in runtime.calls], ["polish", "polish", "pronouns"])
        self.assertIn("Corrected dialogue", runtime.calls[-1][1])
        self.assertNotIn("Polished 漢 dialogue", runtime.calls[-1][1])
        saved = load_pronouns(self.path)["Alice---Bob"]["timeline"]
        self.assertEqual(resolve_direction(saved)["speaker_self"], "FINAL")

    def test_title_only_language_fix_reuses_content_metadata(self):
        runtime = FakeRuntime(self.project, [output(title="漢"), output(payload=MISSING)])
        self.run_pipeline(runtime)
        self.assertEqual([call[0] for call in runtime.calls], ["polish", "polish"])
        self.assertIn("Alice---Bob", load_pronouns(self.path))

    def test_disabled_polish_keeps_standalone_extractor(self):
        runtime = FakeRuntime(self.project, [], polish=False)
        self.assertEqual(self.run_pipeline(runtime), ("Old title", "Old dialogue"))
        self.assertEqual([call[0] for call in runtime.calls], ["pronouns"])

    def test_disabled_pronouns_neither_requests_nor_saves_metadata(self):
        runtime = FakeRuntime(self.project, [output()], pronouns=False)
        self.assertEqual(self.run_pipeline(runtime), ("Title", "Polished dialogue"))
        self.assertNotIn("###PRONOUNS###", runtime.calls[0][1])
        self.assertFalse(self.path.exists())
        self.assertEqual(len(runtime.calls), 1)

    def test_polish_payload_respects_manual_records_and_alias_locks(self):
        original = {
            "Alice---Bob": {"characters": ["Alice", "Bob"], "timeline": [
                {**PAIR, "speaker": "Alice", "chapter_id": "c1", "chapter_number": 1, "source": "manual", "speaker_self": "MANUAL"}
            ]},
            "Carol---Dora": {"characters": ["Carol", "Dora"], "locked": True, "timeline": [
                {**PAIR, "speaker": "Carol", "listener": "Dora", "chapter_id": "c1", "chapter_number": 1}
            ]},
        }
        save_pronouns(original, self.path)
        payload = {"character_pairs": [PAIR, {**PAIR, "speaker": "Carol", "listener": "Dora", "speaker_self": "AI"}]}
        self.run_pipeline(FakeRuntime(self.project, [output(payload=payload)]))
        saved = load_pronouns(self.path)
        self.assertEqual(saved["Carol---Dora"], original["Carol---Dora"])
        self.assertEqual(resolve_direction(saved["Alice---Bob"]["timeline"])["speaker_self"], "MANUAL")

    def test_failed_polish_clears_old_collector_and_preserves_translation(self):
        runtime = FakeRuntime(self.project, ["wrong output"])
        collector = dict(PAYLOAD)
        result = runtime.polish_translation(self.chapter, 1, "", "", pronouns_file=self.path, pronoun_output=collector)
        self.assertEqual(result, ("Old title", "Old dialogue"))
        self.assertEqual(collector, {})

    def test_image_markers_are_validated_separately_from_json(self):
        self.chapter["_image_markers"] = {"[[IMAGE_001]]": "![image](image.png)"}
        self.chapter["translation"] = "Old [[IMAGE_001]] dialogue"
        runtime = FakeRuntime(self.project, [output(content="New [[IMAGE_001]] dialogue")])
        self.assertEqual(self.run_pipeline(runtime)[1], "New [[IMAGE_001]] dialogue")
        self.assertEqual(len(runtime.calls), 1)

    def test_image_retry_does_not_reuse_metadata_from_rejected_output(self):
        self.chapter["_image_markers"] = {"[[IMAGE_001]]": "![image](image.png)"}
        self.chapter["translation"] = "Old [[IMAGE_001]] dialogue"
        fallback = {"character_pairs": [{**PAIR, "speaker_self": "FINAL"}]}
        runtime = FakeRuntime(self.project, [
            output(content="Lost image"),
            output(content="New [[IMAGE_001]] dialogue", payload=MISSING),
        ], fallback=fallback)
        with patch("cores.postprocess.polish.time.sleep"):
            self.run_pipeline(runtime)
        self.assertEqual([call[0] for call in runtime.calls], ["polish", "polish", "pronouns"])
        saved = load_pronouns(self.path)["Alice---Bob"]["timeline"]
        self.assertEqual(resolve_direction(saved)["speaker_self"], "FINAL")

    def test_standalone_polish_saves_metadata_and_clean_markdown(self):
        module = importlib.import_module("cores.postprocess.__main__")
        raw_dir = self.project / "raw"
        translated_dir = self.project / "translated"
        raw_dir.mkdir()
        translated_dir.mkdir()
        name = "v1_c1_s1.md"
        (raw_dir / name).write_text("# Raw\n\nAlice and Bob talk.\n", encoding="utf-8")
        (translated_dir / name).write_text("# Old title\n\nOld dialogue\n", encoding="utf-8")
        runtime = FakeRuntime(self.project, [output()])
        with patch.dict(os.environ), patch.object(module, "RAW_DIR", raw_dir), patch.object(
            module, "TRANSLATED_DIR", translated_dir
        ), patch.object(module, "task_config", return_value={}), patch.object(
            module, "option", return_value=name
        ), patch.object(module, "filtered_context_and_names", return_value=("", [], self.path)), patch.object(
            module, "runtime", runtime
        ):
            module.main()
        self.assertEqual((translated_dir / name).read_text(encoding="utf-8"), "# Title\n\nPolished dialogue\n")
        self.assertIn("Alice---Bob", load_pronouns(self.path))
        self.assertEqual(len(runtime.calls), 1)


if __name__ == "__main__":
    unittest.main()
