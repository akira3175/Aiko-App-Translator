import unittest
from unittest.mock import Mock
from selenium.common.exceptions import TimeoutException
from cores.web_errors import check_quota, WebQuotaError, retryable_transport


class WebErrorsTests(unittest.TestCase):
    def test_quota_notice_detection(self):
        for text in ("You've reached your limit", "Bạn đã đạt giới hạn", "Quota exceeded", "You've reached\nyour limit", "Bạn đã đạt\u00a0giới hạn", "Bạn đã đạt đến hạn mức sử dụng hiện tại", "Đã đạt đến hạn mức · Đặt lại lúc 23:39"):
            driver = Mock()
            driver.execute_script.return_value = [text]
            with self.assertRaises(WebQuotaError):
                check_quota(driver)

    def test_non_quota_notices_do_not_fail(self):
        driver = Mock()
        driver.execute_script.return_value = ['File uploaded', 'Upgrade for higher limits']
        check_quota(driver)
        script = driver.execute_script.call_args.args[0]
        self.assertNotIn('document.body', script)

    def test_format_and_disk_errors_are_not_transport_errors(self):
        self.assertFalse(retryable_transport(ValueError('bad format')))
        self.assertFalse(retryable_transport(OSError('disk full')))
        self.assertTrue(retryable_transport(TimeoutException('network')))
