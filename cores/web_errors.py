"""Typed browser failures and conservative quota detection in UI notices."""

from selenium.common.exceptions import TimeoutException, WebDriverException


class RetryableWebError(ValueError):
    pass


class WebQuotaError(RetryableWebError):
    pass


class WebTaskStopped(ValueError):
    """A terminal browser condition that outer stage loops must not retry."""


class WebSubmissionUncertain(WebTaskStopped):
    pass


class WebLinksExhausted(WebTaskStopped):
    pass


def retryable_transport(error):
    if isinstance(error, RetryableWebError):
        return True
    if isinstance(error, TimeoutException):
        return True
    return isinstance(error, WebDriverException) and any(
        code in str(error) for code in ("net::ERR_", "disconnected", "chrome not reachable")
    )


def check_quota(driver):
    # Read semantic notices only: never scan prompts or generated chapter prose.
    notices = driver.execute_script("""
        return Array.from(document.querySelectorAll(
          '[role="alert"], [role="status"], [role="dialog"], '
          + 'gemini-quota-banner, [data-test-id="gemini-quota-banner-lm"], '
          + 'input-container .inline-upgrade-banner-text'
        ))
          .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
          .map(el => el.innerText || '');
    """)
    if not isinstance(notices, list):
        return
    phrases = (
        "you've reached your limit", "you have reached your limit",
        "you've reached the limit", "usage limit reached", "quota exceeded",
        "resource_exhausted", "exceeded your current quota", "rate limit exceeded",
        "you've reached your daily limit", "đã đạt giới hạn", "đã hết lượt",
        "đã vượt quá hạn mức", "đã hết hạn mức",
        "đã đạt đến hạn mức",
    )
    for notice in notices:
        normalized = ' '.join(notice.lower().replace('’', "'").split()) if isinstance(notice, str) else ''
        if any(phrase in normalized for phrase in phrases):
            raise WebQuotaError("Dịch vụ báo đã hết usage/quota trong thông báo giao diện.")
