import unittest
from unittest.mock import patch

from cores.browser import content


class BrowserContentTests(unittest.TestCase):
    def test_both_providers_failover_preserves_request(self):
        from cores import link_rotation
        from cores.web_errors import RetryableWebError
        for provider, host, target, invoke, link_key in (
            ('gemini_web', 'gemini.google.com', content.browser_runtime, content.generate_content_with_selenium, 'link'),
            ('ai_studio', 'aistudio.google.com', content, content.generate_content_with_ai_studio, 'ai_studio_link'),
        ):
            values = {f'{provider}_rotation_on_error': 'on', f'{provider}_rotation_links': f'https://{host}/u/1/\nhttps://{host}/u/2/'}
            method = 'generate_gemini' if provider == 'gemini_web' else 'generate_ai_studio_content'
            with self.subTest(provider=provider), patch.object(content, 'rotation', link_rotation.LinkRotation()), patch.object(
                link_rotation, 'option', side_effect=lambda key, default=None: values.get(key, default)
            ), patch.object(target, method, side_effect=[RetryableWebError('upload'), 'ok']) as transport:
                self.assertEqual('ok', invoke('original prompt'))
                self.assertEqual(2, transport.call_count)
                first, second = transport.call_args_list
                self.assertEqual(first.args, second.args)
                self.assertIn('/u/1/', first.kwargs[link_key])
                self.assertIn('/u/2/', second.kwargs[link_key])
                self.assertEqual({k:v for k,v in first.kwargs.items() if k != link_key}, {k:v for k,v in second.kwargs.items() if k != link_key})

    def test_gemini_generation_uses_rotated_link(self):
        with patch.object(content.rotation, "link", return_value="https://gemini.google.com/u/2/") as link, patch.object(
            content.browser_runtime, "generate_gemini", return_value="ok"
        ) as generate:
            self.assertEqual("ok", content.generate_content_with_selenium("prompt"))
        self.assertEqual("gemini_web", link.call_args.args[0])
        self.assertEqual("https://gemini.google.com/u/2/", generate.call_args.kwargs["link"])

    def test_ai_studio_rotation_and_explicit_override(self):
        with patch.object(content.rotation, "link", return_value="https://aistudio.google.com/u/2/") as link, patch.object(
            content, "generate_ai_studio_content", return_value="ok"
        ) as generate:
            content.generate_content_with_ai_studio("prompt")
            self.assertEqual("ai_studio", link.call_args.args[0])
            self.assertEqual("https://aistudio.google.com/u/2/", generate.call_args.kwargs["ai_studio_link"])
            content.generate_content_with_ai_studio("prompt", ai_studio_link="https://aistudio.google.com/prompts/explicit")
            self.assertEqual("https://aistudio.google.com/prompts/explicit", generate.call_args.kwargs["ai_studio_link"])
            self.assertEqual(1, link.call_count)

    def test_chatgpt_setup_uses_configured_link(self):
        with patch.object(content, "option", return_value=" https://chatgpt.com/c/user-link "), patch.object(
            content.browser_runtime, "setup_chatgpt"
        ) as setup:
            content.setup_chatgpt_browser()

        self.assertEqual(setup.call_args.kwargs["link"], "https://chatgpt.com/c/user-link")

    def test_chatgpt_generation_uses_configured_link(self):
        with patch.object(content, "option", return_value="https://chatgpt.com/c/user-link"), patch.object(
            content.browser_runtime, "generate_chatgpt", return_value="ok"
        ) as generate:
            result = content.generate_content_with_chatgpt("prompt")

        self.assertEqual(result, "ok")
        self.assertEqual(generate.call_args.kwargs["link"], "https://chatgpt.com/c/user-link")


if __name__ == "__main__":
    unittest.main()
