"""Locate, read, and submit the current ChatGPT Web conversation turn."""

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from uuid import uuid4
import pyperclip


def copy_response_markdown(driver, token, old_assistant_count, *, require_end=False, clipboard=None):
    """Copy only the matching assistant turn; never substitute rendered text."""
    clipboard = clipboard or pyperclip
    sentinel = f"aiko-chatgpt-copy-{uuid4()}"
    original = clipboard.paste()
    copied = None
    try:
        def ready_button(_driver):
            try:
                turn = find_new_response(driver, token, old_assistant_count)
                if turn is None:
                    return False
                scope = turn
                for _ in range(5):
                    ActionChains(driver).move_to_element(scope).perform()
                    buttons = scope.find_elements(By.CSS_SELECTOR,
                        '[data-testid="copy-turn-action-button"], '
                        '[aria-label="Copy response"], [aria-label="Copy"], '
                        '[aria-label="Sao chép"], [aria-label="Sao chép câu trả lời"]')
                    button = next((item for item in buttons
                                   if item.is_displayed() and item.is_enabled()
                                   and not item.find_elements(By.XPATH, 'ancestor::pre | ancestor::code')), None)
                    if button is not None:
                        return button
                    parent = scope.find_element(By.XPATH, "..")
                    if parent == scope:
                        break
                    scope = parent
                return False
            except StaleElementReferenceException:
                return False

        button = WebDriverWait(driver, 20, poll_frequency=0.25).until(ready_button)
        clipboard.copy(sentinel)
        button.click()

        def clipboard_ready(_driver):
            value = clipboard.paste()
            return value if value and value != sentinel and (not require_end or '###END###' in value) else False

        copied = WebDriverWait(driver, 10, poll_frequency=0.25).until(clipboard_ready)
        return copied.strip()
    except TimeoutException as error:
        raise TimeoutException('Không sao chép được Markdown của câu trả lời ChatGPT. Thử lại để giữ nguyên định dạng.') from error
    finally:
        # Do not overwrite unrelated clipboard changes made while waiting.
        try:
            if clipboard.paste() in (sentinel, copied):
                clipboard.copy(original)
        except Exception:
            pass


_CHATGPT_SNAPSHOT_SCRIPT = r"""
const token = arguments[0];
const rootOf = (el) =>
    el.closest('[data-testid^="conversation-turn-"]') ||
    el.closest('article') ||
    el.closest('.group\\/conversation-turn') ||
    el.closest('.agent-turn') ||
    el.closest('[data-message-id]') || el;
const uniqueRoots = (selector) => {
    const result = [];
    for (const el of document.querySelectorAll(selector)) {
        const root = rootOf(el);
        if (!result.includes(root)) result.push(root);
    }
    return result;
};
const users = uniqueRoots('[data-message-author-role="user"]');
const assistants = uniqueRoots(
    '[data-message-author-role="assistant"],article[data-turn="assistant"],.agent-turn'
);
for (const root of users) root.setAttribute('data-novel-before-user', token);
for (const root of assistants) {
    root.setAttribute('data-novel-before-assistant', token);
}
return {users: users.length, assistants: assistants.length};
"""


_CHATGPT_NEW_RESPONSE_SCRIPT = r"""
const token = arguments[0];
const oldAssistantCount = arguments[1];
const rootOf = (el) =>
    el.closest('[data-testid^="conversation-turn-"]') ||
    el.closest('article') ||
    el.closest('.group\\/conversation-turn') ||
    el.closest('.agent-turn') ||
    el.closest('[data-message-id]') || el;
const uniqueRoots = (selector) => {
    const result = [];
    for (const el of document.querySelectorAll(selector)) {
        const root = rootOf(el);
        if (!result.includes(root)) result.push(root);
    }
    return result;
};
const users = uniqueRoots('[data-message-author-role="user"]');
const assistants = uniqueRoots(
    '[data-message-author-role="assistant"],article[data-turn="assistant"],.agent-turn'
);

// Chỉ lấy câu trả lời nằm SAU prompt vừa gửi. Nhờ vậy một bản dịch cũ
// có ###END### trong cùng cuộc chat sẽ không thể bị nhận nhầm.
const newUsers = users.filter(
    (root) => root.getAttribute('data-novel-before-user') !== token
);
if (newUsers.length) {
    const latestUser = newUsers[newUsers.length - 1];
    const afterPrompt = assistants.filter((root) =>
        Boolean(latestUser.compareDocumentPosition(root) & Node.DOCUMENT_POSITION_FOLLOWING)
    );
    return afterPrompt.length ? afterPrompt[afterPrompt.length - 1] : null;
}

// Giao diện cũ có thể không gắn role cho tin nhắn user. Khi đó chỉ chấp
// nhận một assistant turn thật sự mới, không dùng response cuối có sẵn.
if (assistants.length > oldAssistantCount) {
    const newAssistants = assistants.filter(
        (root) => root.getAttribute('data-novel-before-assistant') !== token
    );
    return newAssistants.length ? newAssistants[newAssistants.length - 1] : null;
}
return null;
"""


def snapshot_conversation(driver, token):
    snapshot = driver.execute_script(_CHATGPT_SNAPSHOT_SCRIPT, token) or {}
    return int(snapshot.get("assistants", 0))


def find_new_response(driver, token, old_assistant_count):
    return driver.execute_script(
        _CHATGPT_NEW_RESPONSE_SCRIPT, token, old_assistant_count
    )


def response_text(response_turn):
    markdown_blocks = response_turn.find_elements(
        By.CSS_SELECTOR, "div.markdown, div.markdown.prose"
    )
    for block in reversed(markdown_blocks):
        text = block.text.strip()
        if text:
            return text
    return response_turn.text.strip()


_CHATGPT_SEND_SELECTORS = (
    'button[data-testid="send-button"]',
    'button[aria-label="Send prompt"]',
    'button[aria-label="Gửi tin nhắn"]',
    'button[aria-label="Send message"]',
    'form button[type="submit"]',
    "button.bottom-0",
)


def ready_send_button(driver):
    """Return Send only after ChatGPT has finished preparing the pasted prompt."""
    for selector in _CHATGPT_SEND_SELECTORS:
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                disabled = element.get_attribute("disabled")
                aria_disabled = str(element.get_attribute("aria-disabled") or "").lower()
                if (
                    element.is_displayed()
                    and element.is_enabled()
                    and disabled is None
                    and aria_disabled != "true"
                ):
                    return element
        except StaleElementReferenceException:
            continue
        except Exception:
            continue
    return False
