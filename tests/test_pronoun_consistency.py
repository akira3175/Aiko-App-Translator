import json
import tempfile
import unittest
from pathlib import Path

from cores.context.selection import find_glossary_targets
from cores.pronouns import (
    NameResolver,
    _name_matches_glossary,
    clean_pronoun,
    format_pronoun_context,
    load_pronouns,
    resolve_direction,
    save_pronouns,
    update_pronoun_memory,
)
from cores.pronouns.normalize import parse_character_roster
from cores.storage.project import save_context
from services.pronouns import PronounService


CHARACTERS_MD = """## Eginaya

### Thông tin cơ bản
- **Tên gốc**: 에기나야
- **Biệt danh / Danh hiệu**: Egi, Tinh linh tri thức

## Elysia
- **Biệt danh / Danh hiệu**: Ele, Người phụ nữ tóc đỏ

## Roland
- **Biệt danh / Danh hiệu**: Tôi, Nhân vật chính
"""


def _record(chapter, speaker, listener, self_pronoun, to_listener, **extra):
    return {
        "chapter_id": f"c{chapter}",
        "chapter_number": chapter,
        "speaker": speaker,
        "listener": listener,
        "speaker_self": self_pronoun,
        "speaker_to_listener": to_listener,
        **extra,
    }


class PronounNormalizationTests(unittest.TestCase):
    def test_placeholders_are_removed(self):
        self.assertEqual(clean_pronoun("không rõ"), "")
        self.assertEqual(clean_pronoun("Không xác định (ngầm định)"), "")
        self.assertEqual(clean_pronoun("tôi / không rõ / Tôi"), "tôi")
        self.assertEqual(clean_pronoun("con / em"), "con / em")

    def test_resolver_maps_aliases_and_narrator(self):
        resolver = NameResolver(parse_character_roster(CHARACTERS_MD))
        self.assertEqual(resolver.canonical("Egi"), "Eginaya")
        self.assertEqual(resolver.canonical("Người phụ nữ tóc đỏ (Mẹ)"), "Elysia")
        self.assertEqual(resolver.canonical("Tôi (Nhân vật chính)"), "Roland")
        self.assertEqual(NameResolver().canonical("Nhân vật chính (Tôi)"), "Nhân vật chính (Tôi)")
        self.assertEqual(NameResolver().canonical("Bạn của nhân vật chính"), "Bạn của nhân vật chính")

    def test_single_token_name_matches_titled_glossary(self):
        self.assertTrue(_name_matches_glossary("Shironia", "Công chúa Shironia"))
        self.assertFalse(_name_matches_glossary("Công", "Công chúa Shironia"))

    def test_direction_inherits_blank_values_and_detects_real_change(self):
        state = resolve_direction(
            [
                _record(5, "Letty", "Carlyle", "tôi", "anh"),
                _record(8, "Letty", "Carlyle", "tôi", "cậu"),
                _record(9, "Letty", "Carlyle", "không rõ", "", temporary_address="cái đồ điên này"),
            ]
        )
        self.assertEqual((state["speaker_self"], state["speaker_to_listener"]), ("tôi", "cậu"))
        self.assertFalse(state["changed"])
        self.assertEqual(state["previous"]["speaker_to_listener"], "anh")
        self.assertEqual(state["temporary_address"], "cái đồ điên này")


class PronounContextTests(unittest.TestCase):
    def test_two_directions_are_not_reported_as_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pronouns.json"
            save_pronouns(
                {
                    "Caleb---Vespa": {
                        "characters": ["Caleb", "Vespa"],
                        "timeline": [
                            _record(5, "Vespa", "Caleb", "Tôi", "Anh"),
                            _record(5, "Caleb", "Vespa", "Ta", "Cô"),
                        ],
                    }
                },
                path,
            )
            context = format_pronoun_context(6, path)
            self.assertIn("Vespa → Caleb: tự xưng [Tôi] | gọi đối phương [Anh]", context)
            self.assertIn("Caleb → Vespa: tự xưng [Ta] | gọi đối phương [Cô]", context)
            self.assertNotIn("đổi", context.split("Cách áp dụng")[1].split("▸")[1])

    def test_legacy_fragmented_names_are_merged_with_characters_md(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "characters.md").write_text(CHARACTERS_MD, encoding="utf-8")
            path = project / "pronouns.json"
            save_pronouns(
                {
                    "Egi---Người phụ nữ tóc đỏ (Mẹ)": {
                        "characters": ["Egi", "Người phụ nữ tóc đỏ (Mẹ)"],
                        "timeline": [_record(10, "Người phụ nữ tóc đỏ (Mẹ)", "Egi", "tớ", "cậu")],
                    },
                    "Eginaya---Elysia": {
                        "characters": ["Eginaya", "Elysia"],
                        "timeline": [_record(11, "Elysia", "Eginaya", "", "Egi")],
                    },
                },
                path,
            )
            context = format_pronoun_context(12, path)
            self.assertEqual(context.count("▸"), 1)
            self.assertIn("Elysia → Eginaya: tự xưng [tớ] | gọi đối phương [Egi]", context)

    def test_locked_pair_ranks_first_and_single_token_names_survive_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pronouns.json"
            save_pronouns(
                {
                    "Nera---Shironia": {
                        "characters": ["Nera", "Shironia"],
                        "locked": True,
                        "timeline": [_record(2, "Nera", "Shironia", "em", "Công chúa")],
                    },
                    "An---Bình": {
                        "characters": ["An", "Bình"],
                        "timeline": [_record(3, "An", "Bình", "tôi", "cậu")],
                    },
                },
                path,
            )
            context = format_pronoun_context(
                4, path, glossary_names=["Công chúa Shironia", "An"]
            )
            self.assertLess(context.index("Nera ↔ Shironia"), context.index("An ↔ Bình"))
            self.assertIn("🔒", context)

    def test_locked_pair_is_excluded_with_zero_glossary_relevance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pronouns.json"
            save_pronouns(
                {
                    "Nera---Shironia": {
                        "characters": ["Nera", "Shironia"],
                        "locked": True,
                        "timeline": [_record(2, "Nera", "Shironia", "em", "Công chúa")],
                    },
                    "An---Bình": {
                        "characters": ["An", "Bình"],
                        "timeline": [_record(3, "An", "Bình", "tôi", "cậu")],
                    },
                    "Cường---Dũng": {
                        "characters": ["Cường", "Dũng"],
                        "timeline": [_record(3, "Cường", "Dũng", "ta", "ngươi")],
                    },
                },
                path,
            )
            context = format_pronoun_context(4, path, glossary_names=["An"])
            self.assertIn("An ↔ Bình", context)
            self.assertNotIn("Nera ↔ Shironia", context)
            self.assertNotIn("Cường ↔ Dũng", context)

    def test_find_glossary_targets_resolves_character_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "characters.md").write_text(CHARACTERS_MD, encoding="utf-8")
            save_context(project, {"glossary": "에기나야 = Eginaya"})
            pronouns = project / "pronouns.json"
            save_pronouns(
                {"Egi---Roland": {"characters": ["Egi", "Roland"], "timeline": []}},
                pronouns,
            )
            targets = find_glossary_targets(
                project / "context.json", "에기나야", pronouns
            )
            self.assertEqual(targets, ["Eginaya"])


class PronounUpdateTests(unittest.TestCase):
    def _update(self, path, chapter_id, chapter_number, response):
        update_pronoun_memory(
            chapter_id,
            chapter_number,
            "text",
            pronouns_file=path,
            model="test-model",
            generate=lambda _prompt: response,
            sleep=lambda _seconds: None,
        )

    def test_rerun_replaces_chapter_and_merges_duplicate_directions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pronouns.json"
            first = json.dumps(
                {
                    "character_pairs": [
                        {"speaker": "An", "listener": "Bình", "speaker_self": "tôi", "speaker_to_listener": "không rõ"},
                        {"speaker": "An", "listener": "Bình", "speaker_self": "Tôi", "speaker_to_listener": "cậu"},
                    ]
                },
                ensure_ascii=False,
            )
            self._update(path, "c1", 1, first)
            self._update(path, "c1", 1, first)
            timeline = load_pronouns(path)["An---Bình"]["timeline"]
            self.assertEqual(len(timeline), 1)
            self.assertEqual(timeline[0]["speaker_self"], "tôi")
            self.assertEqual(timeline[0]["speaker_to_listener"], "cậu")

    def test_prompt_contains_roster_and_source(self):
        prompts = []
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "characters.md").write_text(CHARACTERS_MD, encoding="utf-8")
            update_pronoun_memory(
                "c1", 1, "bản dịch", pronouns_file=project / "pronouns.json",
                model="m", generate=lambda prompt: prompts.append(prompt) or '{"character_pairs":[]}',
                sleep=lambda _s: None, source_text="원문 텍스트",
            )
        self.assertIn("- Eginaya (còn gọi:", prompts[0])
        self.assertIn("원문 텍스트", prompts[0])
        self.assertIn('dùng tên "Roland"', prompts[0])

    def test_invalid_json_does_not_retry_forever(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            update_pronoun_memory(
                "c1", 1, "text", pronouns_file=Path(directory) / "pronouns.json",
                model="m", generate=lambda _p: calls.append(1) or "không phải json",
                sleep=lambda _s: None,
            )
        self.assertEqual(len(calls), 2)


class PronounServiceDirectionTests(unittest.TestCase):
    def test_changed_flag_is_per_direction(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "pronouns.json").write_text(
                json.dumps(
                    {
                        "Caleb---Vespa": {
                            "characters": ["Caleb", "Vespa"],
                            "timeline": [
                                _record(5, "Vespa", "Caleb", "Tôi", "Anh"),
                                _record(5, "Caleb", "Vespa", "Ta", "Cô"),
                                _record(8, "Caleb", "Vespa", "Không tự xưng rõ", "Cô"),
                            ],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            pair = PronounService(lambda _name: project).data("p")["pairs"][0]
            self.assertFalse(pair["changed"])
            self.assertEqual(pair["latest"]["speaker_self"], "Ta")
            self.assertEqual(len(pair["directions"]), 2)


if __name__ == "__main__":
    unittest.main()
