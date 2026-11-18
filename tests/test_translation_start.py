import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from cores.translation import runner
from cores.translation.orchestration import run_requested_chapters


class TranslationStartTests(unittest.TestCase):
    def run_translation(self, start, limit, translated=(14,)):
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
