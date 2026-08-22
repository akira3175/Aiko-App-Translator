"""ChatGPT Web browser lifecycle and shared-profile recovery."""

import os
import subprocess
import time

from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.chrome.options import Options


class ChatGPTWebSession:
    def __init__(
        self,
        profile_path,
        service_factory,
        configure_chrome,
        driver_factory=webdriver.Chrome,
        options_factory=Options,
        process_runner=subprocess.run,
    ):
        self.profile_path = str(profile_path)
        self.service_factory = service_factory
        self.configure_chrome = configure_chrome
        self.driver_factory = driver_factory
        self.options_factory = options_factory
        self.process_runner = process_runner
        self.driver = None

    def close_orphans(self):
        if os.name != "nt":
            return
        environment = os.environ.copy()
        environment["CHATGPT_PROFILE_PATH_TO_CLOSE"] = self.profile_path
        command = r"""
$profile = [Environment]::GetEnvironmentVariable('CHATGPT_PROFILE_PATH_TO_CLOSE')
$targets = @(Get-CimInstance Win32_Process -Filter "name = 'chrome.exe'" |
    Where-Object {
        $_.CommandLine -like "*--user-data-dir=$profile*" -or
        $_.CommandLine -like "*--user-data-dir=`"$profile`"*"
    })
foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Output $targets.Count
"""
        try:
            result = self.process_runner(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=10,
                env=environment,
            )
            output = (result.stdout or "").strip().splitlines()
            closed_count = int(output[-1]) if output else 0
            if closed_count:
                print(
                    f"Closed {closed_count} old app Chrome process(es) "
                    "using the shared profile."
                )
                time.sleep(2)
        except Exception:
            pass

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
        if self.driver is not None:
            try:
                self.driver.current_url
                return self.driver
            except Exception:
                self.close(close_orphans=True)

        print("🌐 Đang khởi động trình duyệt ChatGPT web...")
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
                    self.close_orphans()
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
        print("✅ Đã mở trình duyệt ChatGPT. Đảm bảo đã đăng nhập trong profile này!")
        return self.driver

    def close(self, close_orphans=False):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.driver = None
        if close_orphans:
            self.close_orphans()

    def setup(self, skip_login_prompt=False, input_func=input):
        print("\n" + "=" * 60)
        print("🔧 CHẾ ĐỘ CÀI ĐẶT CHATGPT")
        print("=" * 60)
        print("Trình duyệt sẽ mở ra để bạn:")
        print("  1. Đăng nhập tài khoản OpenAI/ChatGPT")
        print("  2. Chọn model (GPT-4o, o3, v.v.)")
        print("  3. Cài đặt khác (nếu cần)")
        print("=" * 60 + "\n")
        self.get_driver().get("https://chatgpt.com/")
        print("🌐 Trình duyệt đã mở tại: https://chatgpt.com/")
        print("\n🔔 Sau khi đăng nhập và cài đặt xong, nhấn ENTER để bắt đầu dịch...")
        if not skip_login_prompt:
            input_func()
        print("✅ Đã sẵn sàng! Bắt đầu quá trình dịch...\n")
