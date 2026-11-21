import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cores.browser import content
from cores.gemini.web_session import GeminiWebSession
from split import ai_txt


class ImportBrowserSetupTests(unittest.TestCase):
    def test_gemini_setup_opens_saved_url_without_console_input(self):
        driver, read_input = Mock(), Mock(side_effect=AssertionError('Must not wait for Enter'))
        session = GeminiWebSession('profile', Mock(), Mock(), Mock(), shared_driver_getter=lambda: driver)
        session.setup(skip_login_prompt=True, input_func=read_input, link='https://gemini.google.com/gem/saved')
        driver.get.assert_called_once_with('https://gemini.google.com/gem/saved')
        read_input.assert_not_called()

    def test_setup_and_generation_use_current_saved_url(self):
        for url in ('https://gemini.google.com/gem/first', 'https://gemini.google.com/gem/changed'):
            with self.subTest(url=url), patch.object(content, 'option', side_effect=lambda key, default=None: url if key == 'link_gemini' else default), \
                 patch('cores.link_rotation.option', side_effect=lambda key, default=None: default), \
                 patch.object(content.browser_runtime, 'setup_gemini') as setup, \
                 patch.object(content.browser_runtime, 'generate_gemini', return_value='ok') as generate:
                content.setup_gemini_browser(skip_login_prompt=True)
                setup.assert_called_once_with(skip_login_prompt=True, link=url)
                content.generate_content_with_selenium('prompt')
                self.assertEqual(url, generate.call_args.kwargs['link'])

    def test_import_explicitly_skips_terminal_login_prompt(self):
        for provider in ('gemini-web', 'chatgpt-web'):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'source.txt'
                source.write_text('Chapter 1\nBody', encoding='utf-8')
                setup, close = Mock(), Mock()
                with patch.object(ai_txt, 'option', side_effect=lambda key, default=None: provider if key == 'pipeline_import_provider' else default), \
                     patch.object(ai_txt, 'browser_lifecycle', return_value=(setup, close)), \
                     patch.object(ai_txt, 'detect_chapters', return_value=[{
                         'title': 'Chapter 1', 'text': 'Chapter 1\nBody', 'heading': True,
                         'source_line': 1, 'end_line': 2} ]):
                    ai_txt.split_txt_with_ai(source, 1, root, project_dir=root / 'out')
                setup.assert_called_once_with(skip_login_prompt=True)
                close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
