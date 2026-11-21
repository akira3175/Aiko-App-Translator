import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from cores.translation import runner
from cores.translation.orchestration import run_requested_chapters


class TranslationStartTests(unittest.TestCase):
    def run_translation(self, start, limit, translated=(14,), observe=None):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root=Path(folder)
            raw=root/'raw'; raw.mkdir()
            output=root/'translated'; output.mkdir()
            for number in range(1, 17):
                name=f'v1_c{number}_s1.md'
                (raw/name).write_text(f'# Chương {number}\n\nRaw',encoding='utf-8')
                if number in translated:
                    (output/name).write_text('# Đã dịch\n\nNội dung cũ',encoding='utf-8')
            values={'start_chapter':start,'previous_context_chapters':0}
            stack.enter_context(patch.object(runner,'option',side_effect=lambda key,default=None:values.get(key,default)))
            stack.enter_context(patch.object(runner,'bool_option',return_value=False))
            stack.enter_context(patch.object(runner,'filtered_context_and_names',return_value=('',[],None)))
            stack.enter_context(patch.object(runner,'format_pronoun_context',return_value=''))
            stack.enter_context(patch.object(runner,'_export_recent_translations'))
            stack.enter_context(patch.object(runner,'enqueue_background_review'))
            stack.enter_context(patch('cores.translation.orchestration.stop_requested',return_value=False))
            seen=[]
            def translate(chapter,*args):
                if observe:
                    observe()
                seen.append(chapter['id'])
                return 'Dịch','Nội dung dịch đủ dài'
            count=run_requested_chapters(limit,lambda:runner.run_single_translation(
                translate,raw,output,root/'context.json',postprocess=lambda *args:('Dịch','Nội dung dịch đủ dài')))
            return count,seen

    def test_start_skips_existing_translation_and_continues_to_fill_count(self):
        count,seen=self.run_translation('v1_c10_s1.md',5)
        self.assertEqual(5,count)
        self.assertEqual([f'v1_c{i}_s1' for i in (10,11,12,13,15)],seen)

    def test_disabled_option_preserves_first_untranslated_behavior(self):
        self.assertEqual((1,['v1_c1_s1']),self.run_translation('',1))

    def test_stops_at_end_even_if_count_not_reached(self):
        self.assertEqual((1,['v1_c16_s1']),self.run_translation('v1_c16_s1.md',5))

    def test_deleted_start_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError,'không còn tồn tại'):
            self.run_translation('v1_c99_s1.md',5)

    def test_rotation_counts_real_saves_and_keeps_link_on_save_failure(self):
        from cores import link_rotation

        values = {"gemini_web_rotation_enabled": "on", "gemini_web_rotation_chapters": 1,
                  "gemini_web_rotation_links": "https://gemini.google.com/u/1/\nhttps://gemini.google.com/u/2/"}
        seen = []
        def observe():
            seen.append(runner.rotation.link("gemini_web", "fallback"))
        with patch.object(link_rotation, "option", side_effect=lambda key, default=None: values.get(key, default)), patch.dict(runner.rotation.states, {}, clear=True), patch.object(runner.rotation, "can_advance", True):
            with patch.object(runner, "save_translated_md", side_effect=OSError("save failed")):
                with self.assertRaises(OSError):
                    self.run_translation('', 1, observe=observe)
            self.assertEqual(0, runner.rotation.states["gemini_web"]["count"])
            self.run_translation('', 2, observe=observe)
        self.assertEqual(["https://gemini.google.com/u/1/", "https://gemini.google.com/u/1/", "https://gemini.google.com/u/2/"], seen)
