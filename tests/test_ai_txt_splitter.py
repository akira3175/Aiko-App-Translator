import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from split import ai_txt
from services.importing.chapters import create_preview, confirm, previews
from cores.stages.runtime import generate_stage
from providers.registry import PROVIDERS


def response(entries):
    return json.dumps({'chapters': [{'line': line, 'title': title} for line, title in entries]}, ensure_ascii=False) + '\n###END###'


def recognize(prompt):
    # A deterministic transport double: the actual model is not called in tests.
    return response([(int(number), text) for number, text in re.findall(r'^(\d+): (.*)$', prompt, re.M)
                     if text.startswith(('第一章', '[2]', 'Ngoại truyện'))])


class AiTxtSplitterTests(unittest.TestCase):
    def test_normalized_ai_heading_matches_without_changing_source(self):
        source = '第93章\u00a0威胁\nNội dung gốc.\n第９４章\u3000巨氪大佬\nKết.\n'
        generate = Mock(return_value=response([(1, '第93章 威胁'), (3, '第94章 巨氪大佬')]))
        chapters = ai_txt.detect_chapters(source, generate)
        self.assertEqual(['第93章\u00a0威胁', '第９４章\u3000巨氪大佬'], [c['title'] for c in chapters])
        self.assertEqual(source, ''.join(c['text'] for c in chapters))
        generate.assert_called_once()

    def test_normalization_does_not_accept_different_words_or_line(self):
        with self.assertRaisesRegex(ValueError, 'dòng 1'):
            ai_txt.parse_boundaries(response([(1, '第93章 巨氪大佬')]), ['第93章\u00a0威胁'], 0, 1)

    def test_mixed_formats_preamble_and_source_are_preserved(self):
        source = 'Giới thiệu\n\n第一章 Khởi đầu\n' + 'Nội dung một.\n' * 35 + '[2] Tiếp theo\n' + 'Nội dung hai.\n' * 35 + 'Ngoại truyện\n' + 'Kết.\n' * 60
        chapters = ai_txt.detect_chapters(source, recognize)
        self.assertEqual(['Phần đầu file', '第一章 Khởi đầu', '[2] Tiếp theo', 'Ngoại truyện'], [c['title'] for c in chapters])
        self.assertEqual(source, ''.join(c['text'] for c in chapters))
        self.assertEqual(1, chapters[0]['source_line'])

    def test_large_file_is_sent_once_in_full(self):
        source = '第一章\n' + 'nội dung\n' * 6000 + '[2] Cuối\n' + 'kết\n' * 100
        generate = Mock(side_effect=recognize)
        chapters = ai_txt.detect_chapters(source, generate)
        self.assertEqual(['第一章', '[2] Cuối'], [c['title'] for c in chapters])
        self.assertEqual(source, ''.join(c['text'] for c in chapters))
        generate.assert_called_once()
        self.assertIn('6002: [2] Cuối', generate.call_args.args[0])
        self.assertIn('6102: kết', generate.call_args.args[0])

    def test_invalid_or_empty_response_does_not_retry_or_start_batches(self):
        for output in ('{"chapters":[', response([])):
            generate = Mock(return_value=output)
            with self.subTest(output=output), self.assertRaises(ValueError):
                ai_txt.detect_chapters('第一章\n' + 'body\n' * 100, generate)
            generate.assert_called_once()

    def test_rejects_out_of_range_fabricated_and_truncated_responses(self):
        for value in (response([(0, '第一章')]), response([(2, '第一章')]),
                      response([(1, 'Invented')]), '{"chapters":[]',
                      '{"chapters":[{"line":true,"title":"第一章"}]}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ai_txt.parse_boundaries(value, ['第一章\n'], 0, 1)

    def test_segment_offsets_preserve_spacing_and_punctuation(self):
        for source, cjk in [('  one\t two!\r\n\nthree four.  ', False), ('  第一章\n你好，世界！\n', True)]:
            with self.subTest(cjk=cjk):
                parts = list(ai_txt.exact_segments(source, 3, cjk))
                self.assertEqual(source, ''.join(parts))
                self.assertGreater(len(parts), 1)

    def test_all_providers_accept_import_stage_and_selected_model(self):
        for provider in PROVIDERS:
            transport = Mock(return_value=response([]))
            options = {'import_stage_model': 'chosen-model', 'import_stage_thinking': 'high'}
            with self.subTest(provider=provider):
                result, _, model = generate_stage('import', 'prompt', provider=provider,
                    get_option=lambda key, default=None: options.get(key, default), overrides={provider: transport})
                self.assertEqual('chosen-model', model)
                self.assertEqual(response([]), result.text)
                self.assertTrue(transport.called)
                if provider == 'gemini-web':
                    self.assertTrue(transport.call_args.kwargs['force_upload'])
                    self.assertEqual(3, transport.call_args.kwargs['max_retries'])

    def test_preview_then_confirm_with_selected_model_and_original_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'story'
            raw = project / 'raw'
            raw.mkdir(parents=True)
            body = '  Nội dung\tgiữ nguyên!\n\n' * 100
            source = '第一章\n' + body
            calls = []

            def generate(stage, prompt, **kwargs):
                calls.append((stage, kwargs['provider'], kwargs['get_option']('import_stage_model')))
                return SimpleNamespace(text=recognize(prompt)), None, None

            settings = {'pipeline_import_provider': 'openai-api', 'pipeline_import_model': 'my-model'}
            with patch.object(ai_txt, 'option', side_effect=lambda key, default=None: settings.get(key, default)), \
                 patch.object(ai_txt, 'generate_stage', side_effect=generate):
                preview = create_preview('story', project, raw, root / '.runtime', 'txt', 500,
                                         source.encode(), split_method='ai')
            self.assertEqual([], list(raw.iterdir()))
            self.assertEqual(('import', 'openai-api', 'my-model'), calls[0])
            self.assertEqual(1, preview['chapters'][0]['source_line'])
            self.assertEqual(len(body), preview['chapters'][0]['characters'])
            result = confirm('story', project, raw, {'token': preview['token'], 'source_from': 0,
                'source_to': 0, 'target_volume': 1, 'target_start': 1, 'selected': [0], 'conflict': 'skip'})
            self.assertEqual(1, result['imported'])
            saved = ''.join(path.read_text(encoding='utf-8').split('\n\n', 1)[1]
                            for path in sorted(raw.glob('*.md')))
            self.assertEqual(body, saved)

    def test_failed_ai_leaves_existing_files_untouched_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / 'story' / 'raw'
            raw.mkdir(parents=True)
            existing = raw / 'v1_c1_s1.md'
            existing.write_text('Original', encoding='utf-8')
            with patch.object(ai_txt, 'browser_lifecycle', return_value=(None, None)), \
                 patch.object(ai_txt, 'generate_stage', side_effect=RuntimeError('provider failed')):
                with self.assertRaisesRegex(RuntimeError, 'provider failed'):
                    create_preview('story', raw.parent, raw, root / '.runtime', 'txt', 500,
                                   b'Chapter 1\nBody', split_method='ai')
            self.assertEqual('Original', existing.read_text())
            self.assertFalse(list((root / '.runtime' / 'chapter-imports').iterdir()))
            self.assertFalse(ai_txt._IMPORT_LOCK.locked())


if __name__ == '__main__':
    unittest.main()
