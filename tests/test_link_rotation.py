import unittest
from unittest.mock import patch

from cores.link_rotation import LinkRotation, parse_links
from cores.web_errors import RetryableWebError, WebQuotaError, WebLinksExhausted


class LinkRotationTests(unittest.TestCase):
    def setUp(self):
        self.values = {
            "gemini_web_rotation_enabled": "on",
            "gemini_web_rotation_links": "https://gemini.google.com/u/1/\nhttps://gemini.google.com/u/2/",
            "gemini_web_rotation_chapters": 1,
        }
        self.clock = 0
        self.rotation = LinkRotation()
        self.addCleanup(patch.stopall)
        patch("cores.link_rotation.option", side_effect=lambda key, default=None: self.values.get(key, default)).start()
        patch("cores.link_rotation.time.monotonic", side_effect=lambda: self.clock).start()

    def link(self):
        return self.rotation.link("gemini_web", "fallback")

    def run_chapter(self, result=1):
        links = []

        @self.rotation.chapter_task
        def chapter():
            links.append(self.link())
            self.clock += 120
            links.append(self.link())
            return result

        chapter()
        self.assertEqual(links[0], links[1])
        return links[0]

    def test_chapter_threshold_and_hold_last(self):
        self.values['gemini_web_rotation_loop'] = 'off'
        self.assertIn("/u/1/", self.run_chapter())
        self.assertIn("/u/2/", self.run_chapter())
        self.assertIn("/u/2/", self.run_chapter())

    def test_time_threshold_does_not_interrupt_chapter(self):
        self.values.update(gemini_web_rotation_chapters=0, gemini_web_rotation_minutes=1)
        self.assertIn("/u/1/", self.run_chapter())
        self.assertIn("/u/2/", self.run_chapter())

    def test_loop(self):
        self.values["gemini_web_rotation_loop"] = "on"
        self.run_chapter()
        self.run_chapter()
        self.assertIn("/u/1/", self.run_chapter())

    def test_unsaved_chapter_does_not_count_or_rotate(self):
        self.values.update(gemini_web_rotation_chapters=0, gemini_web_rotation_minutes=5)
        self.run_chapter()
        self.run_chapter(result=None)
        self.clock = 1000
        self.assertIn("/u/1/", self.run_chapter())
        self.assertIn("/u/2/", self.run_chapter())

    def test_exception_does_not_count(self):
        @self.rotation.chapter_task
        def failed():
            self.link()
            raise OSError("save failed")
        with self.assertRaises(OSError):
            failed()
        self.assertIn("/u/1/", self.run_chapter())

    def test_disabled_uses_existing_link(self):
        self.values["gemini_web_rotation_enabled"] = "off"
        self.assertEqual("fallback", self.link())

    def test_error_only_mode_retries_same_step_and_keeps_successful_link(self):
        self.values.update(gemini_web_rotation_enabled="off", gemini_web_rotation_on_error="on")
        seen = []
        def generate(link):
            seen.append(link)
            if len(seen) == 1:
                raise WebQuotaError('quota')
            return 'same step result'
        self.assertEqual('same step result', self.rotation.run('gemini_web', self.link(), generate))
        self.assertEqual(2, len(seen))
        self.assertEqual(seen[-1], self.link())

    def test_exhaustion_visits_each_unique_link_once_even_with_loop(self):
        self.values.update(gemini_web_rotation_on_error="on", gemini_web_rotation_loop="on")
        self.values['gemini_web_rotation_links'] += '\nhttps://gemini.google.com/u/1/'
        seen = []
        def generate(link):
            seen.append(link)
            raise RetryableWebError('upload')
        with self.assertRaises(WebLinksExhausted):
            self.rotation.run('gemini_web', self.link(), generate)
        self.assertEqual(2, len(seen))
        self.assertEqual(2, len(set(seen)))

    def test_format_and_disk_errors_do_not_switch(self):
        self.values['gemini_web_rotation_on_error'] = 'on'
        first = self.link()
        for error in (ValueError('format'), OSError('disk')):
            def generate(link):
                raise error
            with self.assertRaises(type(error)):
                self.rotation.run('gemini_web', first, generate)
            self.assertEqual(first, self.link())

    def test_disabled_failure_switch_propagates_original_error(self):
        def generate(link):
            raise WebQuotaError('quota')
        with self.assertRaises(WebQuotaError):
            self.rotation.run('gemini_web', self.link(), generate)
        self.assertIn('/u/1/', self.link())

    def test_provider_counters_are_independent(self):
        self.values.update(ai_studio_rotation_enabled="on", ai_studio_rotation_chapters=1,
                           ai_studio_rotation_links="https://aistudio.google.com/u/1/\nhttps://aistudio.google.com/u/2/")
        self.rotation.link("ai_studio", "fallback")
        self.run_chapter()
        self.run_chapter()
        self.assertIn("/u/1/", self.rotation.link("ai_studio", "fallback"))

    def test_url_validation_preserves_path_query_and_order(self):
        url = "https://aistudio.google.com/u/2/prompts/abc?model=custom&authuser=2"
        self.assertEqual([url, url], parse_links(f"  {url}\n\n{url}  ", "ai_studio"))
        for url in ("http://gemini.google.com/", "https://gemini.google.com.evil/", "javascript:alert(1)", "https://gemini.google.com/a b"):
            with self.assertRaises(ValueError):
                parse_links(url, "gemini_web")


if __name__ == "__main__":
    unittest.main()
