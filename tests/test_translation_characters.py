import os
import base64
import json
import tempfile
import unittest
from unittest.mock import patch

from cores import dich_gpt_api, dich_interactions, dich_utils, dich_v1, gpt_api_client
from cores.gemini_interactions import stream_interaction


CHARACTERS = """# Hồ Sơ Nhân Vật

## Alice / 앨리스
- **Giới tính**: Nữ
- **Vai trò**: Hiệp sĩ

---

## Bob / 밥
- **Giới tính**: Nam
"""


class TranslationCharacterTests(unittest.TestCase):
    def test_interactions_keeps_running_after_high_demand_error(self):
        error = RuntimeError(
            "gemini-3.7-flash is currently experiencing high demand, "
            "spikes in demand are usually temporary. Please try again later."
        )
        with patch.object(dich_interactions.dich_v1, "run_translation", side_effect=error), \
                patch.object(dich_interactions, "stop_requested", return_value=False), \
                patch.object(dich_interactions.time, "sleep") as sleep:
            self.assertEqual(dich_interactions._run_translation_with_retry(), 0)
        self.assertEqual(sleep.call_count, 15)

    def test_snapshot_contains_only_characters_relevant_to_chapter(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "characters.md")
            with open(source, "w", encoding="utf-8") as file:
                file.write(CHARACTERS)
            snapshot = dich_utils._build_characters_snapshot(source, "앨리스가 검을 들었다.")
            self.assertIsNotNone(snapshot)
            try:
                with open(snapshot, encoding="utf-8") as file:
                    content = file.read()
                self.assertIn("Alice / 앨리스", content)
                self.assertNotIn("Bob / 밥", content)
            finally:
                os.unlink(snapshot)

    def test_snapshot_is_omitted_when_no_character_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "characters.md")
            with open(source, "w", encoding="utf-8") as file:
                file.write(CHARACTERS)
            self.assertIsNone(dich_utils._build_characters_snapshot(source, "Không có tên nào."))

    def test_v1_attaches_snapshot_to_primary_translation_request(self):
        response = "###TITLE###\nTiêu đề\n###CONTENT###\nNội dung\n###END###"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as snapshot:
            snapshot.write(CHARACTERS)
            snapshot_path = snapshot.name
        with patch.object(dich_v1, "_build_characters_snapshot", return_value=snapshot_path), \
                patch.object(dich_v1, "call_gemini", return_value=response) as call:
            title, content = dich_v1.translate_chapter(
                {"id": "v1_c1_s1", "title": "앨리스", "content": "본문"}, 1
            )
        self.assertEqual((title, content), ("Tiêu đề", "Nội dung"))
        kwargs = call.call_args.kwargs
        self.assertTrue(kwargs["as_chat_parts"])
        self.assertEqual(kwargs["extra_parts"][0]["text"], f"## Reference file: characters.md\n\n{CHARACTERS}")
        self.assertTrue(kwargs["character_document"])
        self.assertIn("giới tính", call.call_args.args[0])
        self.assertLess(
            call.call_args.args[0].index("Hồ sơ nhân vật đính kèm"),
            call.call_args.args[0].index("Tiêu đề gốc"),
        )

    def test_interactions_sends_markdown_snapshot_as_text(self):
        captured = {}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def __iter__(self):
                yield b'data: {"event_type":"interaction.completed","interaction":{"status":"completed"}}\n'

        def opener(request, timeout):
            captured.update(json.loads(request.data.decode("utf-8")))
            return Response()

        stream_interaction(
            api_key="key", model="model", prompt="prompt", opener=opener,
            document={"name": "characters.md", "content": "# Alice", "mime_type": "text/markdown"},
        )
        self.assertEqual(captured["input"][1]["type"], "text")
        self.assertEqual(
            captured["input"][1]["text"], "## Reference file: characters.md\n\n# Alice"
        )

    def test_interactions_keeps_supported_csv_as_document(self):
        captured = {}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def __iter__(self):
                yield b'data: {"event_type":"interaction.completed","interaction":{"status":"completed"}}\n'

        def opener(request, timeout):
            captured.update(json.loads(request.data.decode("utf-8")))
            return Response()

        stream_interaction(
            api_key="key", model="model", prompt="prompt", opener=opener,
            document={"name": "terms.csv", "content": "a,b", "mime_type": "text/csv"},
        )
        self.assertEqual(captured["input"][1]["type"], "document")
        self.assertEqual(captured["input"][1]["mime_type"], "text/csv")
        self.assertEqual(
            base64.b64decode(captured["input"][1]["data"]).decode("utf-8"), "a,b"
        )

    def test_gemini_polish_logs_character_snapshot_without_path_error(self):
        response = "###TITLE###\nTiêu đề\n###CONTENT###\nNội dung"
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "characters.md")
            with open(source, "w", encoding="utf-8") as file:
                file.write(CHARACTERS)
            chapter = {
                "id": "v1_c1_s1",
                "title": "앨리스",
                "content": "본문",
                "title_translation": "Cũ",
                "translation": "Bản dịch cũ",
            }
            with patch.object(dich_utils, "call_gemini", return_value=response) as call, \
                    patch.object(dich_utils, "log_api_call") as log:
                result = dich_utils.polish_translation(
                    chapter, 1, pronoun_context="Alice: cô", characters_md_path=source
                )
        self.assertEqual(result, ("Tiêu đề", "Nội dung"))
        attachments = log.call_args.kwargs["attachments"]
        self.assertEqual(attachments[0]["name"], "characters.md")
        self.assertIn("Alice", attachments[0]["content"])
        request_parts = call.call_args.kwargs["extra_parts"]
        self.assertEqual(
            request_parts[0]["text"],
            f"## Reference file: characters.md\n\n{attachments[0]['content']}",
        )
        self.assertFalse(any("file_data" in part for part in request_parts))
        prompt = log.call_args.args[3]
        self.assertLess(
            prompt.index("Hồ sơ nhân vật đính kèm"),
            prompt.index("Văn bản gốc"),
        )

    def test_gpt_translation_attaches_snapshot_to_primary_request(self):
        response = "###TITLE###\nTiêu đề\n###CONTENT###\nNội dung\n###END###"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False
        ) as snapshot:
            snapshot.write(CHARACTERS)
            snapshot_path = snapshot.name
        with patch.object(
            dich_gpt_api, "_build_characters_snapshot", return_value=snapshot_path
        ), patch.object(dich_gpt_api, "call_gpt_api", return_value=response) as call, \
                patch.object(dich_gpt_api, "log_api_call"):
            result = dich_gpt_api.translate_chapter(
                {"id": "v1_c1_s1", "title": "앨리스", "content": "본문"}, 1
            )
        self.assertEqual(result, ("Tiêu đề", "Nội dung"))
        document = next(item for item in call.call_args.kwargs["documents"] if item["name"] == "characters.md")
        self.assertEqual(document["name"], "characters.md")
        self.assertIn("Alice", document["content"])
        self.assertIn("Hồ sơ nhân vật đính kèm", call.call_args.args[0])
        self.assertIn("chuyển sinh, TS", call.call_args.args[0])
        self.assertNotIn("{CHARACTER_DOCUMENT_INSTRUCTION}", call.call_args.args[0])
        self.assertLess(
            call.call_args.args[0].index("Hồ sơ nhân vật đính kèm"),
            call.call_args.args[0].index("Tiêu đề gốc"),
        )
        self.assertFalse(os.path.exists(snapshot_path))

    def test_gpt_polish_reads_snapshot_with_ts_instruction(self):
        response = "###TITLE###\nTiêu đề\n###CONTENT###\nNội dung\n###END###"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False
        ) as snapshot:
            snapshot.write(CHARACTERS)
            snapshot_path = snapshot.name
        chapter = {
            "title": "앨리스",
            "content": "본문",
            "title_translation": "Cũ",
            "translation": "Bản dịch cũ",
        }
        with patch.object(
            dich_gpt_api, "_build_characters_snapshot", return_value=snapshot_path
        ), patch.object(dich_gpt_api, "call_gpt_api", return_value=response) as call, \
                patch.object(dich_gpt_api, "log_api_call"):
            result = dich_gpt_api.polish_chapter(chapter, 1)
        self.assertEqual(result, ("Tiêu đề", "Nội dung"))
        self.assertIn("chuyển sinh, TS", call.call_args.args[0])
        character_document = next(
            item for item in call.call_args.kwargs["documents"]
            if item["name"] == "characters.md"
        )
        self.assertIn("Alice", character_document["content"])
        self.assertLess(
            call.call_args.args[0].index("Hồ sơ nhân vật đính kèm"),
            call.call_args.args[0].index("Nguyên tác"),
        )
        self.assertFalse(os.path.exists(snapshot_path))

    def test_gpt_client_encodes_inline_file_for_responses_api(self):
        captured = {}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self):
                return json.dumps({"output_text": "done"}).encode("utf-8")

        def opener(request, timeout):
            captured.update(json.loads(request.data.decode("utf-8")))
            return Response()

        def fake_option(name, default=""):
            values = {
                "gpt_api_key": "key",
                "gpt_api_endpoint": "https://api.openai.com/v1/responses",
                "gpt_api_temperature": "",
            }
            return values.get(name, default)

        with patch.object(gpt_api_client, "option", side_effect=fake_option), \
                patch.object(gpt_api_client, "urlopen", side_effect=opener):
            result = gpt_api_client.call_gpt_api(
                "prompt", model="model", reasoning_effort="medium", stage="dịch",
                document={
                    "name": "characters.md",
                    "mime_type": "text/markdown",
                    "content": "# Alice",
                },
            )
        self.assertEqual(result, "done")
        content = captured["input"][0]["content"]
        self.assertEqual(content[0], {"type": "input_text", "text": "prompt"})
        self.assertEqual(content[1]["type"], "input_file")
        encoded = content[1]["file_data"].split(",", 1)[1]
        self.assertEqual(base64.b64decode(encoded).decode("utf-8"), "# Alice")


if __name__ == "__main__":
    unittest.main()
