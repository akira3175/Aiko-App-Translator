import base64
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from providers import openai_client
from cores.gemini.interactions import stream_interaction
from cores.postprocess import build_characters_snapshot
from cores.translation import stage as translation_stage
from cores.translation import interactions


CHARACTERS = """# Hồ Sơ Nhân Vật

## Alice / 앨리스
- **Giới tính**: Nữ

## Bob / 밥
- **Giới tính**: Nam
"""


class TranslationCharacterTests(unittest.TestCase):
    def test_interactions_keeps_running_after_high_demand_error(self):
        error = RuntimeError("currently experiencing high demand")
        with patch.object(interactions, "run_single_translation", side_effect=[error, 1]), patch.object(
            interactions, "stop_requested", return_value=False
        ), patch.object(interactions.time, "sleep") as sleep:
            self.assertEqual(interactions._run_translation_with_retry(), 1)
        self.assertEqual(sleep.call_count, 5)

    def test_interactions_does_not_retry_non_transient_error(self):
        with patch.object(
            interactions, "run_single_translation", side_effect=ValueError("bad payload")
        ), patch.object(interactions, "stop_requested", return_value=False), patch.object(
            interactions.time, "sleep"
        ) as sleep:
            with self.assertRaisesRegex(ValueError, "bad payload"):
                interactions._run_translation_with_retry()
        sleep.assert_not_called()

    def test_interactions_delegates_to_shared_postprocess_pipeline(self):
        chapter = {
            "id": "v1_c1_s1",
            "title_translation": "Cũ",
            "translation": "Nội dung cũ",
        }
        with patch.object(
            interactions,
            "run_post_translation_pipeline",
            return_value=("Mới", "Nội dung mới"),
        ) as shared:
            result = interactions.postprocess_interactions(
                chapter, 1, "context", "pronouns"
            )
        self.assertEqual(result, ("Mới", "Nội dung mới"))
        shared.assert_called_once_with(
            chapter,
            1,
            "context",
            "pronouns",
            interactions.PRONOUNS_JSON,
        )
        self.assertIsNone(interactions._stage)

    def test_snapshot_contains_only_relevant_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "characters.md")
            with open(source, "w", encoding="utf-8") as file:
                file.write(CHARACTERS)
            snapshot = build_characters_snapshot(source, "앨리스가 검을 들었다.")
            self.assertIsNotNone(snapshot)
            try:
                with open(snapshot, encoding="utf-8") as file:
                    content = file.read()
                self.assertIn("Alice / 앨리스", content)
                self.assertNotIn("Bob / 밥", content)
            finally:
                os.unlink(snapshot)

    def test_snapshot_is_omitted_without_match(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "characters.md")
            with open(source, "w", encoding="utf-8") as file:
                file.write(CHARACTERS)
            self.assertIsNone(build_characters_snapshot(source, "Không có tên nào."))

    def test_pipeline_routes_character_document_to_gemini_api(self):
        response = "###TITLE###\nTiêu đề\n###CONTENT###\nNội dung\n###END###"
        call = Mock(return_value=response)
        document = {"name": "characters.md", "mime_type": "text/markdown", "content": CHARACTERS}
        values = {"translate_provider": "gemini-api", "translate_stage_model": "gemini-test"}
        with patch.object(translation_stage, "build_reference_documents", return_value=(document,)), patch.object(
            translation_stage, "option", side_effect=lambda key, default=None: values.get(key, default)
        ), patch.dict(translation_stage.TRANSPORT_OVERRIDES, {"gemini-api": call}, clear=True), patch.object(
            translation_stage, "log_api_call"
        ):
            result = translation_stage.translate_chapter({"id": "v1_c1_s1", "title": "앨리스", "content": "본문"}, 1)
        self.assertEqual(result, ("Tiêu đề", "Nội dung"))
        self.assertEqual(call.call_args.kwargs["character_document"], CHARACTERS)
        self.assertTrue(call.call_args.kwargs["as_chat_parts"])

    def test_pipeline_routes_character_document_to_openai_api(self):
        response = "###TITLE###\nTiêu đề\n###CONTENT###\nNội dung\n###END###"
        call = Mock(return_value=response)
        document = {"name": "characters.md", "mime_type": "text/markdown", "content": CHARACTERS}
        values = {"translate_provider": "openai-api", "translate_stage_model": "openai-test"}
        with patch.object(translation_stage, "build_reference_documents", return_value=(document,)), patch.object(
            translation_stage, "option", side_effect=lambda key, default=None: values.get(key, default)
        ), patch.dict(translation_stage.TRANSPORT_OVERRIDES, {"openai-api": call}, clear=True), patch.object(
            translation_stage, "log_api_call"
        ):
            result = translation_stage.translate_chapter({"id": "v1_c1_s1", "title": "앨리스", "content": "본문"}, 1)
        self.assertEqual(result, ("Tiêu đề", "Nội dung"))
        self.assertEqual(call.call_args.kwargs["documents"], [document])

    def test_interactions_sends_markdown_snapshot_as_text(self):
        captured = {}

        class Socket:
            def settimeout(self, timeout):
                captured["idle_timeout"] = timeout

        class Response:
            fp = type("Fp", (), {
                "raw": type("Raw", (), {"_sock": Socket()})()
            })()
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def __iter__(self):
                yield b'data: {"event_type":"interaction.completed","interaction":{"status":"completed"}}\n'

        def opener(request, timeout):
            captured["timeout"] = timeout
            captured.update(json.loads(request.data.decode("utf-8")))
            return Response()

        with patch("builtins.print") as output:
            stream_interaction(
                api_key="key", model="model", prompt="prompt", opener=opener,
                document={"name": "characters.md", "content": "# Alice", "mime_type": "text/markdown"},
            )
        self.assertEqual(captured["input"][1]["type"], "text")
        self.assertEqual(captured["timeout"], 30)
        self.assertEqual(captured["idle_timeout"], 300)
        output.assert_any_call(
            "📤 Đang gửi prompt (6 ký tự) tới Gemini...",
            flush=True,
        )
        output.assert_any_call(
            "📤 Đã gửi prompt (6 ký tự). Đang chờ Gemini phản hồi...",
            flush=True,
        )

    def test_gpt_client_encodes_inline_file_for_responses_api(self):
        captured = {}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return json.dumps({"output_text": "done"}).encode("utf-8")

        def opener(request, timeout):
            captured.update(json.loads(request.data.decode("utf-8")))
            return Response()

        values = {"gpt_api_key": "key", "gpt_api_endpoint": "https://api.openai.com/v1/responses", "gpt_api_temperature": ""}
        with patch.object(openai_client, "option", side_effect=lambda name, default="": values.get(name, default)), patch.object(
            openai_client, "urlopen", side_effect=opener
        ), patch("builtins.print") as output:
            result = openai_client.call_gpt_api(
                "prompt", model="model", reasoning_effort="medium", stage="dịch",
                document={"name": "characters.md", "mime_type": "text/markdown", "content": "# Alice"},
            )
        self.assertEqual(result, "done")
        output.assert_called_once_with(
            "📤 Đã gửi prompt (6 ký tự). Đang chờ OpenAI phản hồi...",
            flush=True,
        )
        encoded = captured["input"][0]["content"][1]["file_data"].split(",", 1)[1]
        self.assertEqual(base64.b64decode(encoded).decode("utf-8"), "# Alice")


if __name__ == "__main__":
    unittest.main()
