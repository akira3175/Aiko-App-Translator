import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from up import up_md


class HakoStartupTests(unittest.TestCase):
    def test_app_reaches_chapter_scan_without_legacy_config(self):
        settings = {'hako_username': 'user', 'hako_password': 'password'}
        with patch.object(up_md, 'web_mode', return_value=True), \
             patch('builtins.open', side_effect=AssertionError('Must not read legacy config')), \
             patch.object(up_md, 'option', side_effect=lambda key, default=None: settings.get(key, default)), \
             patch.object(up_md, 'configure_r2', return_value=False), \
             patch.object(up_md, 'load_book_mappings', return_value=[{'volume': 1, 'book_id': 123}]), \
             patch.object(up_md, 'scan_translated_dir', return_value=[]) as scan:
            asyncio.run(up_md.main())
        scan.assert_called_once_with(up_md.TRANSLATED_DIR)

    def test_app_reports_missing_credentials(self):
        with patch.object(up_md, 'web_mode', return_value=True), \
             patch.object(up_md, 'option', side_effect=lambda key, default=None: default), \
             patch.object(up_md, 'configure_r2', return_value=False), \
             patch.object(up_md, 'load_book_mappings', return_value=[{'volume': 1, 'book_id': 123}]):
            with self.assertRaisesRegex(RuntimeError, 'Cài đặt'):
                asyncio.run(up_md.main())

    def test_standalone_reads_config_relative_to_project_root_with_or_without_bom(self):
        for encoding in ('utf-8', 'utf-8-sig'):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as folder:
                path = Path(folder, 'up', 'config_md.json')
                path.parent.mkdir()
                expected = {'management_url': 'https://example.com', 'credentials': {'username': 'test'}}
                path.write_text(json.dumps(expected), encoding=encoding)
                with patch.object(up_md, 'web_mode', return_value=False), patch.object(up_md, '_PROJECT_ROOT', folder):
                    self.assertEqual(expected, up_md.load_publish_config())

    def test_standalone_missing_config_reports_absolute_path(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(up_md, 'web_mode', return_value=False), patch.object(up_md, '_PROJECT_ROOT', folder):
            with self.assertRaises(RuntimeError) as caught:
                up_md.load_publish_config()
            self.assertIn(str(Path(folder, 'up', 'config_md.json')), str(caught.exception))

    def test_cache_keeps_entries_with_or_without_bom(self):
        expected = {'chapter.jpg': 'https://cdn.example/chapter.jpg'}
        for encoding in ('utf-8', 'utf-8-sig'):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as folder:
                path = Path(folder, 'image_cache.json')
                path.write_text(json.dumps(expected), encoding=encoding)
                original = path.read_bytes()
                with patch.object(up_md, '_CACHE_FILE', str(path)):
                    self.assertEqual(expected, up_md._load_cache())
                self.assertEqual(original, path.read_bytes())
