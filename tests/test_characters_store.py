import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores.characters import generation, workflow
from cores.characters.parser import extract_character_payload
from cores.characters.prompt import build_character_prompt
from cores.characters.store import (
    JSON_NAME,
    LEGACY_BACKUP_NAME,
    MD_NAME,
    commit_ai_updates,
    load_document,
    merge_ai_updates,
    normalize_chapter,
    parse_legacy_markdown,
    render_batch_snapshot,
    render_markdown,
    render_snapshot,
    restore_backup,
    save_document,
    validate_document,
)
from cores.postprocess.review import build_translation_review_prompt
from cores.postprocess.snapshots import build_batch_characters_snapshot, build_characters_snapshot
from cores.pronouns.normalize import load_character_roster
from cores.translation.prompts import (
    build_batch_prompt,
    build_single_prompt,
    with_character_document_instruction,
)


class CharacterStoreTests(unittest.TestCase):
    def test_pending_ai_keeps_manual_rename_and_locked_address(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = save_document(folder, {"characters": [{"name": "Alice"}]})
            char = doc["characters"][0]
            payload = {"characters": [{"id": char["id"], "name": "Alice", "updates": [
                {"field": "address", "value": "Bob: tao/may", "chapter": "v1_c2_s1.md"},
                {"field": "voice", "value": "quiet", "chapter": "v1_c2_s1.md"},
            ]}]}
            char["name"] = "Alicia"
            char["fields"]["address"] = [{"value": "Bob: toi/anh", "confirmed": True}]
            save_document(folder, doc, expected_revision=doc["revision"])
            saved, stats = commit_ai_updates(folder, payload, ["v1_c2_s1.md"])
            self.assertEqual(stats["added_entries"], 1)
            snapshot = render_snapshot(saved, "v1_c3_s1.md")
            for value in ("Alicia", "quiet", "toi/anh"):
                self.assertIn(value, snapshot)
            self.assertNotIn("tao/may", snapshot)

    def test_broken_primary_skips_export_and_can_restore_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            doc = save_document(project, {"characters": [{"name": "Alice"}]})
            doc["characters"][0]["fields"]["status"] = [
                {"chapter": "v1_c50_s1.md", "value": "future secret"}]
            save_document(project, doc)
            (project / JSON_NAME).write_text("{broken", encoding="utf-8")
            chapter = "v1_c2_s1.md"
            self.assertIsNone(build_characters_snapshot(project / MD_NAME, "Alice", chapter_id=chapter))
            self.assertIsNone(build_batch_characters_snapshot(project / MD_NAME, [chapter], "Alice"))
            restored = restore_backup(project)
            self.assertEqual(restored["characters"][0]["name"], "Alice")
            self.assertEqual(next(project.glob("*.corrupt")).read_text(), "{broken")

    def test_normalize_chapter_accepts_with_or_without_md(self):
        self.assertEqual(normalize_chapter("v7_c11_s1"), "v7_c11_s1.md")
        self.assertEqual(normalize_chapter("V7_C11_S1.MD"), "v7_c11_s1.md")
        self.assertIsNone(normalize_chapter("  "))
        with self.assertRaises(ValueError):
            normalize_chapter("chapter 11")

    def test_legacy_migration_preserves_backup_and_unclassified_text(self):
        legacy_md = """# Hồ Sơ Nhân Vật

## Lâm Phong / Lin Feng

### Thông tin cơ bản
- **Tên gốc**: 林峰
- **Giới tính**: Nam
- **Cảnh giới bí mật**: Nguyên Anh sơ kỳ

### Thông tin được bảo toàn
- **Giới tính**: Nam

### Ghi chú đặc biệt
Đoạn ghi chú tự do không theo chuẩn.

### Ghi chú dịch thuật
- Từng bị phong ấn tu vi.
"""
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / MD_NAME).write_text(legacy_md, encoding="utf-8")

            doc = load_document(project, migrate=True)

            self.assertTrue((project / JSON_NAME).exists())
            self.assertTrue((project / LEGACY_BACKUP_NAME).exists())
            self.assertEqual((project / LEGACY_BACKUP_NAME).read_text(encoding="utf-8"), legacy_md)
            self.assertEqual(len(doc["characters"]), 1)
            char = doc["characters"][0]
            self.assertEqual(char["name"], "Lâm Phong")
            self.assertEqual(char["fields"]["original_name"][0]["value"], "林峰")
            self.assertIsNone(char["fields"]["original_name"][0]["chapter"])
            self.assertEqual(char["fields"]["original_name"][0]["source"], "legacy")
            self.assertEqual(char["fields"]["aliases"][0]["value"], "Lin Feng")
            self.assertEqual(char["notes"][0]["text"], "Từng bị phong ấn tu vi.")
            self.assertIsNone(char["notes"][0]["chapter"])
            self.assertIn("Cảnh giới bí mật", char["unclassified"])
            self.assertIn("Đoạn ghi chú tự do không theo chuẩn.", char["unclassified"])
            self.assertNotIn("Thông tin được bảo toàn", char["unclassified"])

    def test_snapshot_filters_strictly_before_current_chapter_and_numeric_order(self):
        doc = validate_document(
            {
                "characters": [
                    {
                        "id": "ch_lin",
                        "name": "Lâm Phong",
                        "fields": {
                            "original_name": [{"value": "林峰", "chapter": "v1_c1_s1.md"}],
                            "status": [
                                {"value": "Đệ tử ngoại môn", "chapter": "v1_c2_s1.md"},
                                {"value": "Trưởng lão", "chapter": "v1_c10_s1.md"},
                                {"value": "Tông chủ", "chapter": "v7_c11_s1.md"},
                            ],
                            "aliases": [
                                {"value": "Tiểu Lâm", "chapter": "v1_c1_s1.md"},
                                {"value": "Bạch Y Kiếm Khách", "chapter": "v1_c10_s1.md"},
                                {"value": "Hắc Ma Tôn", "chapter": "v7_c11_s1.md"},
                            ],
                            "address": [
                                {"value": "Sư tôn → ta / sư tôn", "chapter": "v1_c2_s1.md"},
                                {"value": "Lý Thanh → sư đệ / sư tỷ", "chapter": "v1_c5_s1.md"},
                                {"value": "Ma Đế → bản tọa / ngươi", "chapter": "v7_c11_s1.md"},
                            ],
                            "voice": [{"value": "Lạnh lùng, nói ngắn", "chapter": "v1_c2_s1.md"}],
                        },
                        "notes": [
                            {"chapter": "v1_c2_s1.md", "text": "Bái nhập Thanh Vân Tông."},
                            {"chapter": "v1_c10_s1.md", "text": "Lên chức Trưởng lão vào cuối chương."},
                            {"chapter": "v7_c11_s1.md", "text": "Kế nhiệm Tông chủ."},
                        ],
                    }
                ]
            }
        )

        # At v1_c10_s1.md: state BEFORE v1_c10_s1.md only -> NOT Trưởng lão yet!
        snap_c10 = render_snapshot(doc, chapter_id="v1_c10_s1.md", relevant_text="林峰 bước vào đại điện.")
        self.assertIn("Đệ tử ngoại môn (từ v1_c2_s1.md)", snap_c10)
        self.assertNotIn("Trưởng lão", snap_c10)
        self.assertNotIn("Tông chủ", snap_c10)
        self.assertIn("Tiểu Lâm (từ v1_c1_s1.md)", snap_c10)
        self.assertNotIn("Bạch Y Kiếm Khách", snap_c10)
        self.assertNotIn("Hắc Ma Tôn", snap_c10)
        # Cumulative address keeps BOTH earlier relationships
        self.assertIn("Sư tôn → ta / sư tôn", snap_c10)
        self.assertIn("Lý Thanh → sư đệ / sư tỷ", snap_c10)
        self.assertNotIn("Ma Đế", snap_c10)

        # Future-only alias does NOT match early chapter text
        snap_future_alias = render_snapshot(doc, chapter_id="v1_c5_s1.md", relevant_text="Hắc Ma Tôn xuất hiện.")
        self.assertEqual(snap_future_alias, "")

        # At v1_c11_s1.md: numeric comparison (1,10,1) < (1,11,1) works properly
        snap_c11 = render_snapshot(doc, chapter_id="v1_c11_s1.md", relevant_text="林峰 mỉm cười.")
        self.assertIn("Trưởng lão (từ v1_c10_s1.md; trước đó: Đệ tử ngoại môn)", snap_c11)
        self.assertIn("Tiểu Lâm (từ v1_c1_s1.md) / Bạch Y Kiếm Khách (từ v1_c10_s1.md)", snap_c11)
        self.assertNotIn("Tông chủ", snap_c11)

        # At v7_c12_s1.md: sees full progression
        snap_v7 = render_snapshot(doc, chapter_id="v7_c12_s1.md", relevant_text="Hắc Ma Tôn đứng dậy.")
        self.assertIn("Tông chủ (từ v7_c11_s1.md; trước đó: Đệ tử ngoại môn → Trưởng lão)", snap_v7)
        self.assertIn("Ma Đế → bản tọa / ngươi", snap_v7)

    def test_batch_snapshot_separates_baseline_and_in_batch_milestones(self):
        doc = validate_document(
            {
                "characters": [
                    {
                        "id": "ch_lin",
                        "name": "Lâm Phong",
                        "fields": {
                            "status": [
                                {"value": "Đệ tử", "chapter": "v1_c1_s1.md"},
                                {"value": "Nội môn đệ tử", "chapter": "v1_c10_s1.md"},
                                {"value": "Trưởng lão", "chapter": "v1_c12_s1.md"},
                            ]
                        },
                        "notes": [
                            {"chapter": "v1_c10_s1.md", "text": "Thăng lên nội môn cuối chương 10."},
                            {"chapter": "v1_c12_s1.md", "text": "Cuối chương 12 thành trưởng lão."},
                        ],
                    }
                ]
            }
        )
        batch_snap = render_batch_snapshot(
            doc, ["v1_c10_s1.md", "v1_c11_s1.md", "v1_c12_s1.md"], relevant_text="Lâm Phong"
        )
        self.assertIn("Đệ tử (từ v1_c1_s1.md)", batch_snap)
        self.assertIn("Thay đổi theo mốc trong batch", batch_snap)
        self.assertIn("[v1_c10_s1.md] Địa vị / Chức vụ: Nội môn đệ tử", batch_snap)
        # v1_c12_s1.md is end of batch -> not leaked into baseline or pre-c12 changes
        self.assertNotIn("Trưởng lão", batch_snap)

    def test_ai_merge_protects_confirmed_entries_and_rejects_out_of_batch_chapters(self):
        doc = validate_document(
            {
                "characters": [
                    {
                        "id": "ch_lin",
                        "name": "Lâm Phong (đã đổi tên)",
                        "fields": {
                            "gender": [{"value": "Nam", "chapter": None, "confirmed": True, "source": "user"}],
                            "status": [{"value": "Đệ tử", "chapter": "v1_c2_s1.md", "confirmed": True, "source": "user"}],
                            "aliases": [{"value": "Tiểu Lâm", "chapter": "v1_c1_s1.md", "confirmed": True, "source": "user"}],
                        },
                        "notes": [],
                    }
                ]
            }
        )
        payload = {
            "characters": [
                {
                    "id": "ch_lin",
                    "name": "Tên cũ AI gửi",
                    "updates": [
                        {"field": "gender", "value": "Nữ", "chapter": "v1_c2_s1.md"},  # blocked by undated confirmed
                        {"field": "status", "value": "Tạp dịch", "chapter": "v1_c2_s1.md"},  # blocked by same-chapter confirmed
                        {"field": "status", "value": "Trưởng lão", "chapter": "v1_c3_s1.md"},  # allowed later milestone
                        {"field": "aliases", "value": "Kiếm Tôn", "chapter": "v1_c3_s1.md"},  # allowed cumulative
                        {"field": "faction", "value": "Ma Giáo", "chapter": "v9_c99_s1.md"},  # rejected out-of-batch
                        {"field": "unknown_field", "value": "x", "chapter": "v1_c3_s1.md"},  # rejected bad field
                    ],
                    "events": [
                        {"chapter": "v1_c3_s1.md", "text": "Đột phá Kim Đan."},
                        {"chapter": "v1_c3_s1.md", "text": "Nhận thêm một đồ đệ mới."},
                        {"chapter": "v9_c99_s1.md", "text": "Spoiler ngoài batch."},
                    ],
                }
            ]
        }
        merged, stats = merge_ai_updates(doc, payload, ["v1_c2_s1.md", "v1_c3_s1.md"])
        char = merged["characters"][0]
        # User's canonical name is kept
        self.assertEqual(char["name"], "Lâm Phong (đã đổi tên)")
        # Confirmed gender & v1_c2 status untouched
        self.assertEqual([e["value"] for e in char["fields"]["gender"]], ["Nam"])
        self.assertEqual(
            [(e["chapter"], e["value"]) for e in char["fields"]["status"]],
            [("v1_c2_s1.md", "Đệ tử"), ("v1_c3_s1.md", "Trưởng lão")],
        )
        self.assertEqual([e["value"] for e in char["fields"]["aliases"]], ["Tiểu Lâm", "Kiếm Tôn"])
        self.assertNotIn("faction", char["fields"])
        # Multiple distinct events in same chapter are both kept
        self.assertEqual(len(char["notes"]), 2)
        self.assertEqual(stats["added_entries"], 2)
        self.assertEqual(stats["added_notes"], 2)
        self.assertEqual(stats["skipped"], 2)
        self.assertEqual(stats["rejected"], 3)

    def test_save_revision_conflict_and_backup_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            doc1 = save_document(
                project,
                {"characters": [{"name": "Alice", "fields": {"gender": [{"value": "Nữ"}]}}]},
                allow_empty=True,
            )
            self.assertEqual(doc1["revision"], 1)

            doc2 = save_document(
                project,
                {"characters": [{"name": "Alice"}, {"name": "Bob"}]},
                expected_revision=1,
            )
            self.assertEqual(doc2["revision"], 2)
            self.assertTrue((project / "characters.json.bak").exists())

            # Stale revision rejected
            with self.assertRaisesRegex(ValueError, "cập nhật ở nơi khác"):
                save_document(project, {"characters": [{"name": "Charlie"}]}, expected_revision=1)

            # Restore backup recovers Alice-only state with bumped revision
            restored = restore_backup(project)
            self.assertEqual([c["name"] for c in restored["characters"]], ["Alice"])
            self.assertEqual(restored["revision"], 3)

    def test_build_character_prompt_and_workflow_json_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            raw_dir = project / "raw"
            raw_dir.mkdir()
            (raw_dir / "v7_c11_s1.md").write_text("# Chương 11\n\nLâm Phong bước vào đại điện.", encoding="utf-8")
            (raw_dir / "v7_c12_s1.md").write_text("# Chương 12\n\nLâm Phong được phong làm Tông chủ.", encoding="utf-8")
            state_path = project / "project_state.json"
            context_path = project / "context.json"
            characters_md = project / "characters.md"

            captured_prompts = []
            ai_json = """```json
###START###
{
  "characters": [
    {
      "id": "",
      "name": "Lâm Phong",
      "updates": [
        {"field": "status", "value": "Tông chủ", "chapter": "v7_c12_s1.md"}
      ],
      "events": [
        {"chapter": "v7_c12_s1.md", "text": "Chính thức kế nhiệm Tông chủ."}
      ]
    }
  ]
}
###END###
```"""

            def fake_call(prompt, *, provider, max_retries):
                captured_prompts.append(prompt)
                return ai_json

            with patch.object(generation, "call_character_analysis", side_effect=fake_call):
                workflow.run_character_generation(
                    raw_dir=str(raw_dir),
                    context_path=str(context_path),
                    characters_path=str(characters_md),
                    state_path=str(state_path),
                    provider="gemini-api",
                    model="test-model",
                )

            self.assertEqual(len(captured_prompts), 1)
            self.assertIn("[v7_c11_s1.md]", captured_prompts[0])
            self.assertIn("[v7_c12_s1.md]", captured_prompts[0])
            self.assertTrue((project / JSON_NAME).exists())
            self.assertTrue((project / MD_NAME).exists())
            doc = load_document(project, migrate=False)
            self.assertEqual(doc["characters"][0]["name"], "Lâm Phong")
            self.assertEqual(doc["characters"][0]["fields"]["status"][0]["chapter"], "v7_c12_s1.md")

    def test_extract_character_payload_rejects_bad_chapters_and_accepts_empty_list(self):
        ok, err = extract_character_payload('###START###\n{"characters": []}\n###END###', ["v1_c1_s1.md"])
        self.assertEqual(ok, {"characters": []})
        self.assertEqual(err, "")

        bad, err = extract_character_payload(
            '{"characters": [{"name": "A", "updates": [{"field": "status", "value": "X", "chapter": "v9_c9_s1.md"}]}]}',
            ["v1_c1_s1.md"],
        )
        self.assertIsNone(bad)
        self.assertIn("mã chương", err)

    def test_prompts_include_chapter_codes_and_keep_batch_markers(self):
        single = build_single_prompt(
            {"id": "v7_c11_s1", "title": "Tiêu đề", "content": "Nội dung"},
            "ctx",
            "",
            "prev",
        )
        self.assertIn("### Mã chương đang dịch:\nv7_c11_s1.md", single)

        batch = build_batch_prompt(
            [
                {"id": "v7_c11_s1", "title": "T1", "content": "C1"},
                {"id": "v7_c12_s1", "title": "T2", "content": "C2"},
            ],
            "ctx",
            "",
            "prev",
        )
        self.assertIn("###CHAPTER 1###\nMã chương: v7_c11_s1.md\nTiêu đề gốc:", batch)
        self.assertIn("###CHAPTER 2###\nMã chương: v7_c12_s1.md\nTiêu đề gốc:", batch)

        polish_stub = "# Vai trò hiệu đính\nRole\n\n## Thuật ngữ và quy tắc\nctx"
        positioned = with_character_document_instruction(polish_stub)
        self.assertLess(positioned.index("# Vai trò hiệu đính"), positioned.index("## Hồ sơ nhân vật đính kèm"))
        self.assertLess(positioned.index("## Hồ sơ nhân vật đính kèm"), positioned.index("## Thuật ngữ và quy tắc"))

        review_prompt = build_translation_review_prompt("v7_c11_s1", 11, "R", "RC", "T", "TC", "ctx", "crit")
        review_with_doc = with_character_document_instruction(review_prompt)
        self.assertLess(review_with_doc.index("## Tiêu chí review:"), review_with_doc.index("## Hồ sơ nhân vật đính kèm"))
        self.assertLess(review_with_doc.index("## Hồ sơ nhân vật đính kèm"), review_with_doc.index("## Thuật ngữ tham chiếu:"))

    def test_snapshot_and_roster_read_characters_json_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            save_document(
                project,
                {
                    "characters": [
                        {
                            "name": "Lâm Phong",
                            "fields": {
                                "aliases": [{"value": "Kiếm Tôn", "chapter": "v1_c1_s1.md"}],
                                "status": [
                                    {"value": "Đệ tử", "chapter": "v1_c1_s1.md"},
                                    {"value": "Tông chủ", "chapter": "v7_c11_s1.md"},
                                ],
                            },
                        }
                    ]
                },
                allow_empty=True,
            )
            md_path = project / MD_NAME
            snap_path = build_characters_snapshot(
                str(md_path), "Kiếm Tôn ra tay.", chapter_id="v7_c11_s1"
            )
            self.assertIsNotNone(snap_path)
            try:
                content = Path(snap_path).read_text(encoding="utf-8")
                self.assertIn("Đệ tử", content)
                self.assertNotIn("Tông chủ", content)
            finally:
                os.unlink(snap_path)

            batch_path = build_batch_characters_snapshot(
                str(md_path), ["v1_c2_s1.md", "v7_c12_s1.md"], "Kiếm Tôn ra tay."
            )
            self.assertIsNotNone(batch_path)
            try:
                bcontent = Path(batch_path).read_text(encoding="utf-8")
                self.assertIn("[v7_c11_s1.md] Địa vị / Chức vụ: Tông chủ", bcontent)
            finally:
                os.unlink(batch_path)

            loaded_roster = load_character_roster(str(md_path))
            self.assertEqual(loaded_roster, [("Lâm Phong", ["Kiếm Tôn"])])

    def test_address_can_return_to_an_earlier_value(self):
        doc = validate_document({"characters": [{"name": "Alice"}]})
        for chapter, relation in enumerate(("A", "B", "A", "A"), 1):
            code = f"v1_c{chapter}_s1.md"
            update = {"field": "address", "value": f"Bob: {relation}", "chapter": code}
            doc, stats = merge_ai_updates(doc, {"characters": [
                {"name": "Alice", "updates": [update]}]}, [code])
            self.assertEqual(stats["added_entries"], int(chapter < 4))
        entries = doc["characters"][0]["fields"]["address"]
        self.assertEqual(entries[-1]["value"], "Bob: A")
        self.assertEqual(entries[-1]["chapter"], "v1_c3_s1.md")

    def test_address_snapshot_resolves_latest_state_per_listener(self):
        doc = validate_document(
            {
                "characters": [
                    {
                        "id": "ch_lin",
                        "name": "Lâm Phong",
                        "fields": {
                            "address": [
                                {"value": "Sư tôn → tại hạ / tiền bối", "chapter": "v1_c2_s1.md"},
                                {"value": "Lý Thanh → sư đệ / sư tỷ", "chapter": "v1_c5_s1.md"},
                                {"value": "Sư tôn → đồ nhi / sư tôn", "chapter": "v1_c8_s1.md", "confirmed": True},
                                {"value": "Sư tôn → bản tọa / ngươi", "chapter": "v7_c11_s1.md"},
                            ]
                        },
                    }
                ]
            }
        )
        snap = render_snapshot(doc, chapter_id="v1_c10_s1.md", relevant_text="Lâm Phong hành lễ.")
        self.assertIn("Sư tôn → đồ nhi / sư tôn 🔒 (từ v1_c8_s1.md; trước đó: tại hạ / tiền bối)", snap)
        self.assertIn("Lý Thanh → sư đệ / sư tỷ (từ v1_c5_s1.md)", snap)
        self.assertNotIn("bản tọa / ngươi", snap)
        self.assertEqual(snap.count("Sư tôn →"), 1)

        # AI repeating the same active relation for Sư tôn at v1_c9_s1.md is skipped
        merged, stats = merge_ai_updates(
            doc,
            {
                "characters": [
                    {
                        "id": "ch_lin",
                        "name": "Lâm Phong",
                        "updates": [
                            {"field": "address", "value": "Sư tôn → đồ nhi / sư tôn", "chapter": "v1_c9_s1.md"},
                            {"field": "address", "value": "Sư tôn → tao / mày", "chapter": "v1_c8_s1.md"},
                            {"field": "address", "value": "Trưởng lão → vãn bối / tiền bối", "chapter": "v1_c9_s1.md"},
                        ],
                    }
                ]
            },
            ["v1_c8_s1.md", "v1_c9_s1.md"],
        )
        self.assertEqual(stats["added_entries"], 1)
        self.assertEqual(stats["skipped"], 2)
        self.assertTrue(
            any("Trưởng lão → vãn bối / tiền bối" in e["value"] for e in merged["characters"][0]["fields"]["address"])
        )

    def test_workflow_reloads_latest_document_before_next_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            raw_dir = project / "raw"
            raw_dir.mkdir()
            (raw_dir / "v1_c1_s1.md").write_text("# Ch1\n\nLâm Phong.", encoding="utf-8")
            (raw_dir / "v1_c2_s1.md").write_text("# Ch2\n\nLâm Phong.", encoding="utf-8")
            prompts = []

            def fake_call(prompt, *, provider, max_retries):
                prompts.append(prompt)
                if len(prompts) == 1:
                    return '###START###\n{"characters":[{"id":"","name":"Lâm Phong","updates":[{"field":"status","value":"Đệ tử","chapter":"v1_c1_s1.md"}]}]}\n###END###'
                return '###START###\n{"characters":[]}\n###END###'

            def edit_between_batches(_seconds):
                current = load_document(project, migrate=False)
                current["characters"][0]["fields"]["voice"] = [
                    {"value": "Lạnh lùng ít nói", "chapter": "v1_c1_s1.md", "confirmed": True, "source": "user"}
                ]
                save_document(project, current, expected_revision=current["revision"])

            with (
                patch.object(generation, "call_character_analysis", side_effect=fake_call),
                patch.object(workflow, "int_option", side_effect=lambda key, default=10, minimum=1: 1 if key == "character_batch_size" else default),
                patch.object(workflow.time, "sleep", side_effect=edit_between_batches),
            ):
                workflow.run_character_generation(
                    raw_dir=str(raw_dir),
                    context_path=str(project / "context.json"),
                    characters_path=str(project / MD_NAME),
                    state_path=str(project / "project_state.json"),
                    provider="gemini-api",
                    model="test-model",
                )

            self.assertEqual(len(prompts), 2)
            self.assertIn("Lạnh lùng ít nói", prompts[1])


if __name__ == "__main__":
    unittest.main()
