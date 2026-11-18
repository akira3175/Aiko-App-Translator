import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.polish_review import (
    ReviewConflict, change_review, create_review, load_review, review_blocks,
    save_translation,
)


class PolishReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "translated" / "v1_c1_s1.md"
        self.old = "# Cũ\n\nCâu cũ.\n\nĐoạn giữ nguyên.\n"
        self.new = "# Mới\n\nCâu mới.\n\nĐoạn giữ nguyên.\n"
        save_translation(self.target, self.old)

    def request(self, review, action, values=None):
        return {"id": review["id"], "revision": review["revision"], "action": action,
                "values": review["values"] if values is None else values}

    def test_diff_roundtrips_insert_delete_merge_unicode_and_whitespace(self):
        cases = [(self.old, self.new), ("", "Xin chào\n"), ("a\n\nb\n", ""),
                 ("a\n\nb\n\nc\n", "a\n\nc\n"),
                 ("a\n\nb\n", "a và b\n"),
                 ("# A\n\n![a](image.png)\n\nNội dung\n", "# B\n\n![a](image.png)\n\nKhác\n"),
                 (" a \n \n\nb\n", " a\n\n b \n\n"), (self.old, self.old)]
        for old, new in cases:
            with self.subTest(old=old, new=new):
                blocks = review_blocks(old, new)
                self.assertEqual(old, "".join(block["old"] for block in blocks))
                self.assertEqual(new, "".join(block["new"] for block in blocks))

    def test_draft_survives_reload_without_changing_translation(self):
        review = create_review(self.target, self.old, self.new)
        values = list(review["values"])
        values[1] = "Tự biên tập.\n\n"
        result = change_review(self.target, self.request(review, "draft", values))
        self.assertEqual(1, result["revision"])
        self.assertEqual(values, load_review(self.target)["values"])
        self.assertEqual(self.old, self.target.read_text(encoding="utf-8"))

    def test_full_document_draft_allows_cross_paragraph_edits_and_exact_save(self):
        review = create_review(self.target, self.old, self.new)
        content = "# Tự sửa\nGộp đoạn và thêm đoạn mới\n\nCuối không có newline"
        request = {"id": review["id"], "revision": 0, "action": "draft", "draft_text": content}
        change_review(self.target, request)
        self.assertEqual(content, load_review(self.target)["draft_text"])
        self.assertEqual(self.old, self.target.read_text(encoding="utf-8"))
        change_review(self.target, {**request, "revision": 1, "action": "accept"})
        self.assertEqual(content, self.target.read_text(encoding="utf-8"))
        self.assertIsNone(load_review(self.target))

    def test_full_document_draft_still_checks_revision_and_external_edits(self):
        review = create_review(self.target, self.old, self.new)
        request = {"id": review["id"], "revision": 0, "action": "draft", "draft_text": "Tự sửa"}
        change_review(self.target, request)
        with self.assertRaises(ReviewConflict):
            change_review(self.target, request)
        save_translation(self.target, "Sửa bên ngoài")
        with self.assertRaises(ReviewConflict):
            change_review(self.target, {**request, "revision": 1, "action": "accept"})
        self.assertEqual("Tự sửa", load_review(self.target)["draft_text"])
        self.assertEqual("Sửa bên ngoài", self.target.read_text(encoding="utf-8"))

    def test_invalid_full_document_and_empty_accept_are_rejected(self):
        review = create_review(self.target, self.old, self.new)
        for content in (None, [], 5, ""):
            with self.subTest(content=content), self.assertRaises(ValueError):
                change_review(self.target, {"id": review["id"], "revision": 0, "action": "accept", "draft_text": content})

    def test_accept_mixed_old_ai_and_manual_with_backup(self):
        review = create_review(self.target, self.old, self.new)
        values = list(review["values"])
        values[0] = review["blocks"][0]["old"]
        values[1] = "Tự sửa.\n\n"
        change_review(self.target, self.request(review, "accept", values))
        self.assertEqual("".join(values), self.target.read_text(encoding="utf-8"))
        self.assertEqual(self.old, self.target.with_name(self.target.name+".bak").read_text(encoding="utf-8"))
        self.assertIsNone(load_review(self.target))

    def test_select_all_replacement_preserves_paragraph_boundaries(self):
        review = create_review(self.target, self.old, self.new)
        values = list(review["values"])
        values[1] = "Thay toàn đoạn"
        change_review(self.target, self.request(review, "accept", values))
        self.assertIn("Thay toàn đoạn\n\nĐoạn giữ nguyên.", self.target.read_text(encoding="utf-8"))

    def test_empty_replacement_deletes_paragraph(self):
        review = create_review(self.target, self.old, self.new)
        values = list(review["values"])
        values[1] = ""
        change_review(self.target, self.request(review, "accept", values))
        self.assertEqual("# Mới\n\nĐoạn giữ nguyên.\n", self.target.read_text(encoding="utf-8"))

    def test_discard_does_not_revert_edits_made_elsewhere(self):
        review = create_review(self.target, self.old, self.new)
        save_translation(self.target, "Sửa ở cửa sổ khác")
        result = change_review(self.target, self.request(review, "discard"))
        self.assertEqual("Sửa ở cửa sổ khác", result["translated"])
        self.assertEqual("Sửa ở cửa sổ khác", self.target.read_text(encoding="utf-8"))
        self.assertIsNone(load_review(self.target))

    def test_conflict_preserves_both_live_translation_and_review(self):
        review = create_review(self.target, self.old, self.new)
        save_translation(self.target, "Bản mới ở nơi khác")
        with self.assertRaises(ReviewConflict):
            change_review(self.target, self.request(review, "accept"))
        self.assertEqual("Bản mới ở nơi khác", self.target.read_text(encoding="utf-8"))
        self.assertEqual(review, load_review(self.target))

    def test_stale_tab_cannot_save_discard_or_accept(self):
        review = create_review(self.target, self.old, self.new)
        change_review(self.target, self.request(review, "draft"))
        for action in ("draft", "accept", "discard"):
            with self.subTest(action=action), self.assertRaises(ReviewConflict):
                change_review(self.target, self.request(review, action))
        with self.assertRaises(ReviewConflict):
            create_review(self.target, self.old, self.new)

    def test_invalid_values_and_empty_accept_are_rejected(self):
        review = create_review(self.target, self.old, self.new)
        for values in (None, [], [42] * len(review["values"]), [""] * len(review["values"])):
            request = self.request(review, "accept")
            request["values"] = values
            with self.subTest(values=values), self.assertRaises(ValueError):
                change_review(self.target, request)
        self.assertEqual(self.old, self.target.read_text(encoding="utf-8"))

    def test_standalone_review_keeps_images_and_does_not_update_pronouns(self):
        module = importlib.import_module("cores.postprocess.__main__")
        raw = self.root / "raw"
        raw.mkdir()
        source = raw / self.target.name
        source.write_text("# Raw\n\nRaw text\n\n![ảnh](image.png)\n", encoding="utf-8")
        with patch.dict(os.environ), patch.object(module, "RAW_DIR", raw), patch.object(module, "TRANSLATED_DIR", self.target.parent), patch.object(module, "task_config", return_value={}), patch.object(module, "option", side_effect=lambda key, default=None: {"target_chapter": self.target.name, "polish_review": True}.get(key, default)), patch.object(module, "filtered_context_and_names", return_value=("", [], self.root/"pronouns.json")), patch.object(module, "format_pronoun_context", return_value=""), patch.object(module, "runtime") as runtime, patch.object(module, "update_final_pronouns") as pronouns:
            runtime.provider.return_value = "test"
            runtime.polish_translation.return_value = ("Mới", "Câu mới.")
            runtime.fix_translation.return_value = ("Mới", "Câu mới.")
            module.main()
            pronouns.assert_not_called()
            runtime.close_browsers.assert_called_once()
        self.assertEqual(self.old, self.target.read_text(encoding="utf-8"))
        self.assertIn("![ảnh](image.png)", load_review(self.target)["proposed"])


if __name__ == "__main__":
    unittest.main()
