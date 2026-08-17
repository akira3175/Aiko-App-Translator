import tempfile
import unittest
from pathlib import Path

import yaml

from cores.chatgpt_web_v2 import (
    _new_chat,
    apply_pronoun_batch,
    build_pronoun_batch_prompt,
    build_review_batch_prompt,
    parse_polish_batch,
    save_review_batch,
)
from unittest.mock import patch


class ChatGPTWebV2Tests(unittest.TestCase):
    def setUp(self):
        self.chapters = [
            {"id": "v1_c10_s1", "title_translation": "Mười", "translation": "A"},
            {"id": "v1_c11_s1", "title_translation": "Mười một", "translation": "B"},
        ]

    def test_parse_polish_batch_requires_every_section(self):
        text = """###START###
###SECTION 1###
###TITLE###
Chương mười
###CONTENT###
Nội dung A
###SECTION 2###
###TITLE###
Chương mười một
###CONTENT###
Nội dung B
###END###"""
        self.assertEqual(
            parse_polish_batch(text, 2),
            [("Chương mười", "Nội dung A"), ("Chương mười một", "Nội dung B")],
        )
        with self.assertRaises(ValueError):
            parse_polish_batch(text.replace("###SECTION 2###", ""), 2)

    def test_pronoun_batch_uses_actual_chapter_numbers_and_keeps_locked(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pronouns.yaml"
            path.write_text(
                yaml.safe_dump(
                    {"An---Bình": {"characters": ["An", "Bình"], "timeline": [], "locked": True}},
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )
            response = """{"character_pairs":[
              {"chapter_id":"v1_c10_s1","speaker":"An","listener":"Bình","speaker_self":"tôi"},
              {"chapter_id":"v1_c11_s1","speaker":"Chi","listener":"Dung","speaker_self":"mình"}
            ]}"""
            self.assertEqual(apply_pronoun_batch(response, self.chapters, 10, path), 1)
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["An---Bình"]["timeline"], [])
            self.assertEqual(saved["Chi---Dung"]["timeline"][0]["chapter_number"], 11)

    def test_review_batch_rejects_missing_chapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "review.yaml"
            response = '{"reviews":[{"chapter_id":"v1_c10_s1","overall_score":9,"issues":[]}]}'
            with self.assertRaises(ValueError):
                save_review_batch(response, self.chapters, 10, path)

    def test_each_stage_passes_its_own_model_and_thinking(self):
        values = {
            "gpt_v2_review_model": "review-model",
            "gpt_v2_review_thinking": "vừa",
        }
        with patch(
            "cores.chatgpt_web_v2.option",
            side_effect=lambda key, default=None: values.get(key, default),
        ), patch(
            "cores.chatgpt_web_v2.generate_content_with_chatgpt",
            return_value="done",
        ) as generate:
            self.assertEqual(_new_chat("prompt", "review"), "done")
        generate.assert_called_once_with(
            "prompt",
            chat_url="https://chatgpt.com/",
            chatgpt_model="review-model",
            chatgpt_thinking="vừa",
        )

    def test_json_stage_prompts_require_end_marker(self):
        pronouns = build_pronoun_batch_prompt(self.chapters)
        review = build_review_batch_prompt(self.chapters, 10)
        self.assertTrue(pronouns.rstrip().endswith("###END###"))
        self.assertIn("bắt buộc thêm một dòng ###END###", review)


if __name__ == "__main__":
    unittest.main()
