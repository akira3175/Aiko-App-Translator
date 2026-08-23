import tempfile
import unittest
from pathlib import Path

from cores.browser.chrome import apply_portable_chrome, create_chrome_service
from cores.browser.runtime import BrowserRuntime


class _Session:
    def __init__(
        self, profile, service, configure, close_other=None,
        shared_driver_getter=None, shared_driver_closer=None,
    ):
        self.profile = profile
        self.close_other = close_other
        self.shared_driver_getter = shared_driver_getter
        self.shared_driver_closer = shared_driver_closer
        self.driver = object()
        self.setup_value = None
        self.setup_link = None
        self.closed = None
        self.orphans_closed = False

    def get_driver(self):
        return self.shared_driver_getter() if self.shared_driver_getter else self.driver

    def setup(self, skip_login_prompt=False, link=None):
        self.setup_value = skip_login_prompt
        self.setup_link = link

    def close(self, close_orphans=False):
        self.closed = close_orphans
        if self.shared_driver_closer:
            self.shared_driver_closer()

    def close_orphans(self):
        self.orphans_closed = True


class BrowserRuntimeTests(unittest.TestCase):
    def _runtime(self, gemini_generate=lambda *args, **kwargs: None, chatgpt_generate=lambda *args, **kwargs: None):
        return BrowserRuntime(
            "profile",
            lambda: None,
            lambda _options: None,
            gemini_generate,
            chatgpt_generate,
            gemini_session_class=_Session,
            chatgpt_session_class=_Session,
        )

    def test_owns_both_sessions_and_forwards_lifecycle(self):
        runtime = self._runtime()
        self.assertIs(runtime.get_gemini_driver(), runtime.chatgpt.driver)
        self.assertIs(runtime.get_chatgpt_driver(), runtime.chatgpt.driver)
        runtime.setup_gemini(skip_login_prompt=True)
        runtime.setup_chatgpt(skip_login_prompt=True, link="https://chatgpt.com/c/test")
        runtime.close_gemini()
        runtime.close_chatgpt(close_orphans=True)
        self.assertTrue(runtime.gemini.setup_value)
        self.assertTrue(runtime.chatgpt.setup_value)
        self.assertEqual("https://chatgpt.com/c/test", runtime.chatgpt.setup_link)
        self.assertTrue(runtime.chatgpt.closed)

    def test_gemini_and_chatgpt_share_one_driver(self):
        runtime = self._runtime()
        self.assertIs(runtime.get_gemini_driver(), runtime.get_chatgpt_driver())
        self.assertIs(runtime.gemini.shared_driver_getter.__self__, runtime.chatgpt)

    def test_forwards_generation_configuration(self):
        calls = []
        runtime = self._runtime(
            gemini_generate=lambda *args, **kwargs: calls.append((args, kwargs)) or "ok"
        )
        result = runtime.generate_gemini(
            "prompt", "url", "extended", max_retries=2,
            web_model="thinking", thinking_level="high",
        )
        self.assertEqual(result, "ok")
        self.assertEqual(calls[0][0], ("prompt",))
        self.assertIs(calls[0][1]["get_driver"].__self__, runtime)
        self.assertEqual(calls[0][1]["web_model"], "thinking")

    def test_portable_chrome_paths_are_preferred(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = Path(directory) / "chromedriver.exe"
            browser = Path(directory) / "chrome.exe"
            driver.touch()
            browser.touch()
            service = create_chrome_service(driver)
            options = type("Options", (), {"binary_location": None})()
            apply_portable_chrome(options, browser)
            self.assertIsInstance(service.path, str)
            self.assertEqual(service.path, str(driver))
            self.assertIsInstance(options.binary_location, str)
            self.assertEqual(options.binary_location, str(browser))

    def test_driver_manager_is_fallback_when_portable_driver_is_missing(self):
        class Manager:
            def install(self):
                return "managed-driver.exe"

        service = create_chrome_service("missing.exe", driver_manager_factory=Manager)
        self.assertEqual(service.path, "managed-driver.exe")


if __name__ == "__main__":
    unittest.main()
