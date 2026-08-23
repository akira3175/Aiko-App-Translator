"""Gemini Web browser lifecycle."""

import sys

from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.chrome.options import Options


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class GeminiWebSession:
    def __init__(
        self,
        profile_path,
        service_factory,
        configure_chrome,
        orphan_cleanup,
        shared_driver_getter=None,
        shared_driver_closer=None,
        driver_factory=webdriver.Chrome,
        options_factory=Options,
    ):
        self.profile_path = str(profile_path)
        self.service_factory = service_factory
        self.configure_chrome = configure_chrome
        self.orphan_cleanup = orphan_cleanup
        self.shared_driver_getter = shared_driver_getter
        self.shared_driver_closer = shared_driver_closer
        self.driver_factory = driver_factory
        self.options_factory = options_factory
        self.driver = None

    def _new_options(self):
        options = self.options_factory()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"--user-data-dir={self.profile_path}")
        self.configure_chrome(options)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        return options

    def get_driver(self):
        if self.shared_driver_getter is not None:
            return self.shared_driver_getter()
        if self.driver is not None:
            try:
                self.driver.current_url
                return self.driver
            except Exception:
                self.driver = None

        print("🌐 Đang khởi động trình duyệt Gemini web...")
        options = self._new_options()
        for attempt in range(2):
            try:
                self.driver = self.driver_factory(
                    service=self.service_factory(), options=options
                )
                break
            except SessionNotCreatedException:
                self.driver = None
                if attempt == 0:
                    self.orphan_cleanup()
                    continue
                raise
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": (
                    'Object.defineProperty(navigator, "webdriver", '
                    "{get: () => undefined})"
                )
            },
        )
        print("✅ Đã mở trình duyệt. Đảm bảo đã đăng nhập Google trong profile này!")
        return self.driver

    def close(self):
        if self.shared_driver_closer is not None:
            self.shared_driver_closer()
            return
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.driver = None

    def setup(self, skip_login_prompt=False, input_func=input):
        print("\n" + "=" * 60)
        print("🔧 CHẾ ĐỘ CÀI ĐẶT GEMINI")
        print("=" * 60)
        print("Trình duyệt sẽ mở ra để bạn:")
        print("  1. Đăng nhập tài khoản Google")
        print("  2. Truy cập gemini.google.com và cấu hình (nếu cần)")
        print("  3. Chọn model, cài đặt ngôn ngữ, v.v...")
        print("=" * 60 + "\n")
        self.get_driver().get("https://gemini.google.com/app")
        print("🌐 Trình duyệt đã mở tại: https://gemini.google.com/app")
        print("\n🔔 Sau khi đăng nhập và cài đặt xong, nhấn ENTER để bắt đầu dịch...")
        if not skip_login_prompt:
            input_func()
        print("✅ Đã sẵn sàng! Bắt đầu quá trình dịch...\n")
