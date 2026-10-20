"""Locate and read the Gemini Web response created by the current prompt."""

import time
from uuid import uuid4

import pyperclip
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


COPY_BUTTON_SELECTORS = (
    'gem-icon-button[gemtooltip*="Sao chép câu trả lời"] button',
    'gem-icon-button[gemtooltip*="Copy response"] button',
    'button[jslog^="178035;"]',
    'gem-icon-button[arialabel="Sao chép"] button',
    'gem-icon-button[arialabel="Copy"] button',
    'button[data-test-id="copy-button"]',
    'button mat-icon[data-mat-icon-name="copy"]',
    'button mat-icon[fonticon="copy"]',
    'button mat-icon[data-mat-icon-name="content_copy"]',
    'button mat-icon[fonticon="content_copy"]',
    'button[aria-label="Sao chép"]',
    'button[aria-label="Copy"]',
    'button[aria-label*="Sao chép câu trả lời"]',
    'button[aria-label*="Copy response"]',
)

CLIPBOARD_HOOK_SCRIPT = r"""
window.__aikoGeminiCopiedText = null;
if (!window.__aikoGeminiClipboardHooked) {
    window.__aikoGeminiClipboardHooked = true;
    try {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            const origWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
            navigator.clipboard.writeText = async function(text) {
                window.__aikoGeminiCopiedText = String(text ?? '');
                try {
                    return await origWriteText(text);
                } catch (_) {
                    return undefined;
                }
            };
        }
    } catch (_) {}
    try {
        document.addEventListener('copy', function(e) {
            try {
                const data = e.clipboardData && e.clipboardData.getData('text/plain');
                if (data) window.__aikoGeminiCopiedText = String(data);
            } catch (_) {}
        }, true);
    } catch (_) {}
    try {
        if (typeof document.execCommand === 'function') {
            const origExecCommand = document.execCommand.bind(document);
            document.execCommand = function(cmd, showUI, val) {
                if (String(cmd).toLowerCase() === 'copy') {
                    try {
                        const sel = window.getSelection ? String(window.getSelection()) : '';
                        if (sel) window.__aikoGeminiCopiedText = sel;
                    } catch (_) {}
                }
                return origExecCommand(cmd, showUI, val);
            };
        }
    } catch (_) {}
}
"""


SNAPSHOT_SCRIPT = r"""
const token = arguments[0];
const userRootOf = (el) =>
    el.closest('user-query') ||
    el.closest('.user-query') ||
    el.closest('[data-test-id="user-query"]') ||
    el;
const responseRootOf = (el) =>
    el.closest('model-response') ||
    el.closest('response-container') ||
    el.closest('[data-test-id*="response"]') ||
    el;
const uniqueRoots = (selector, rootFn) => {
    const result = [];
    for (const el of document.querySelectorAll(selector)) {
        const root = rootFn(el);
        if (!result.includes(root)) result.push(root);
    }
    return result;
};
const users = uniqueRoots(
    'user-query,.user-query,[data-test-id="user-query"],.query-content',
    userRootOf
);
const responses = uniqueRoots(
    'model-response,message-content .model-response-text,.model-response-text,response-container,.response-container-content',
    responseRootOf
);
for (const root of users) root.setAttribute('data-novel-before-user', token);
for (const root of responses) root.setAttribute('data-novel-before-response', token);
return {users: users.length, responses: responses.length};
"""


NEW_RESPONSE_SCRIPT = r"""
const token = arguments[0];
const oldResponseCount = arguments[1];
const userRootOf = (el) =>
    el.closest('user-query') ||
    el.closest('.user-query') ||
    el.closest('[data-test-id="user-query"]') ||
    el;
const responseRootOf = (el) =>
    el.closest('model-response') ||
    el.closest('response-container') ||
    el.closest('[data-test-id*="response"]') ||
    el;
const uniqueRoots = (selector, rootFn) => {
    const result = [];
    for (const el of document.querySelectorAll(selector)) {
        const root = rootFn(el);
        if (!result.includes(root)) result.push(root);
    }
    return result;
};
const users = uniqueRoots(
    'user-query,.user-query,[data-test-id="user-query"],.query-content',
    userRootOf
);
const responses = uniqueRoots(
    'model-response,message-content .model-response-text,.model-response-text,response-container,.response-container-content',
    responseRootOf
);
const newUsers = users.filter(
    (root) => root.getAttribute('data-novel-before-user') !== token
);
if (newUsers.length) {
    const latestUser = newUsers[newUsers.length - 1];
    const afterPrompt = responses.filter(
        (root) =>
            root.getAttribute('data-novel-before-response') !== token &&
            Boolean(latestUser.compareDocumentPosition(root) & Node.DOCUMENT_POSITION_FOLLOWING)
    );
    return afterPrompt.length ? afterPrompt[afterPrompt.length - 1] : null;
}
if (responses.length > oldResponseCount) {
    const newResponses = responses.filter(
        (root) => root.getAttribute('data-novel-before-response') !== token
    );
    return newResponses.length ? newResponses[newResponses.length - 1] : null;
}
return null;
"""


def snapshot_conversation(driver, token):
    snapshot = driver.execute_script(SNAPSHOT_SCRIPT, token) or {}
    return int(snapshot.get("responses", 0))


def find_new_response(driver, token, old_response_count):
    return driver.execute_script(NEW_RESPONSE_SCRIPT, token, old_response_count)


def response_text(response_root):
    content_blocks = response_root.find_elements(
        By.CSS_SELECTOR,
        "message-content .model-response-text, .model-response-text, "
        "message-content, .response-container-content, .markdown-main-container",
    )
    texts = []
    for block in content_blocks:
        try:
            t = block.text.strip()
            if t:
                texts.append(t)
        except Exception:
            continue

    try:
        root_text = response_root.text.strip()
    except Exception:
        root_text = ""

    if not texts:
        return root_text

    # 1. Nếu có block chứa marker kết thúc, lấy block dài nhất chứa marker
    end_blocks = [t for t in texts if "###END###" in t or "###CHAR_END###" in t]
    if end_blocks:
        return max(end_blocks, key=len)

    # Nếu không có block con nào chứa marker nhưng root_text có chứa marker
    if "###END###" in root_text or "###CHAR_END###" in root_text:
        return root_text

    # 2. Nếu có block chứa cấu trúc TITLE & CONTENT
    title_content_blocks = [
        t for t in texts if "###TITLE###" in t and "###CONTENT###" in t
    ]
    if title_content_blocks:
        return max(title_content_blocks, key=len)

    # 3. Khi đang stream: ưu tiên block dài nhất để không bị cắt xén vào sub-block con.
    # Nếu các block cùng độ dài, ưu tiên block sau cùng (mới hơn).
    return max(reversed(texts), key=len)


def _resolve_button(element):
    try:
        tag = (element.tag_name or "").lower()
    except Exception:
        tag = ""
    if tag == "mat-icon":
        try:
            return element.find_element(By.XPATH, "./ancestor::button[1]")
        except Exception:
            return None
    return element


def _is_before_token(element, token):
    if not token or element is None:
        return False
    try:
        if (element.get_attribute("data-novel-before-response") or "") == token:
            return True
    except Exception:
        pass
    try:
        old_ancestors = element.find_elements(
            By.XPATH,
            f"ancestor::*[@data-novel-before-response='{token}']",
        )
        if any(
            (anc.get_attribute("data-novel-before-response") or "") == token
            for anc in old_ancestors
        ):
            return True
    except Exception:
        pass
    return False


def _is_valid_copy_button(button, token=None):
    if button is None:
        return False
    try:
        if hasattr(button, "is_displayed") and not button.is_displayed():
            return False
        if hasattr(button, "is_enabled") and not button.is_enabled():
            return False
    except Exception:
        return False

    if _is_before_token(button, token):
        return False

    try:
        label = (button.get_attribute("aria-label") or "").lower()
        if any(word in label for word in ("câu lệnh", "prompt", "code", "mã")):
            return False
    except Exception:
        pass

    try:
        excluded_ancestors = button.find_elements(
            By.XPATH,
            "ancestor::user-query | ancestor::*[contains(@class, 'user-query')] "
            "| ancestor::pre | ancestor::code | ancestor::code-block",
        )
        if excluded_ancestors:
            return False
    except Exception:
        pass

    return True


def _find_copy_button_in_scope(scope, token=None):
    if _is_before_token(scope, token):
        return None
    for selector in COPY_BUTTON_SELECTORS:
        try:
            elements = scope.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            continue
        valid = []
        for elem in elements:
            btn = _resolve_button(elem)
            if _is_valid_copy_button(btn, token=token):
                valid.append(btn)
        if valid:
            return valid[-1]
    return None


def _find_copy_button(driver, response_root=None, token=None):
    if response_root is not None:
        scope = response_root
        for _ in range(5):
            if _is_before_token(scope, token):
                break
            button = _find_copy_button_in_scope(scope, token=token)
            if button is not None:
                return button
            try:
                tag = (scope.tag_name or "").lower()
                if tag in ("model-response", "chat-window", "main", "body"):
                    break
                parent = scope.find_element(By.XPATH, "..")
                if not parent or parent == scope:
                    break
                scope = parent
            except Exception:
                break
        # Nếu đã có token định danh lượt chat mới, tuyệt đối không lấy ngoài phạm vi câu trả lời mới
        if token:
            return None

    try:
        containers = driver.find_elements(
            By.CSS_SELECTOR, "model-response, response-container"
        )
        for container in reversed(containers):
            if _is_before_token(container, token):
                continue
            button = _find_copy_button_in_scope(container, token=token)
            if button is not None:
                return button
    except Exception:
        pass

    if token:
        return None
    return _find_copy_button_in_scope(driver, token=token)


def copy_response_text(driver, response_root=None, clipboard=None, token=None):
    """Click nút Sao chép của Gemini Web (2026-10) để lấy nội dung Markdown đầy đủ."""
    clipboard = clipboard or pyperclip
    sentinel = f"aiko-gemini-copy-{uuid4()}"
    original = None
    copied = None
    try:
        try:
            original = clipboard.paste()
            clipboard.copy(sentinel)
        except Exception:
            original = None

        target_root = response_root
        if target_root is None and not token:
            try:
                roots = driver.find_elements(
                    By.CSS_SELECTOR, "model-response, response-container"
                )
                if roots:
                    target_root = roots[-1]
            except Exception:
                target_root = None

        if target_root is not None:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'end'});", target_root
                )
                time.sleep(0.2)
                ActionChains(driver).move_to_element(target_root).perform()
                time.sleep(0.4)
            except Exception:
                pass

        copy_button = _find_copy_button(driver, target_root, token=token)
        if copy_button is None:
            return None

        try:
            driver.execute_script(CLIPBOARD_HOOK_SCRIPT)
        except Exception:
            pass

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", copy_button
            )
            time.sleep(0.2)
        except Exception:
            pass

        try:
            ActionChains(driver).move_to_element(copy_button).perform()
        except Exception:
            pass

        clicked = False
        try:
            if hasattr(copy_button, "click"):
                copy_button.click()
                clicked = True
        except Exception:
            clicked = False

        if not clicked:
            driver.execute_script("arguments[0].click();", copy_button)

        deadline = time.time() + 3.0
        fallback_js_clicked = clicked is False
        start_poll = time.time()
        while time.time() < deadline:
            try:
                hooked = driver.execute_script("return window.__aikoGeminiCopiedText;")
                if isinstance(hooked, str) and hooked.strip():
                    copied = hooked.strip()
                    return copied
            except Exception:
                pass

            try:
                value = clipboard.paste()
                if isinstance(value, str) and value.strip() and value != sentinel:
                    copied = value.strip()
                    return copied
            except Exception:
                pass

            if not fallback_js_clicked and time.time() - start_poll >= 0.8:
                fallback_js_clicked = True
                try:
                    driver.execute_script("arguments[0].click();", copy_button)
                except Exception:
                    pass

            time.sleep(0.15)

        return None
    except Exception as error:
        print(f"⚠️ Lỗi khi copy response Gemini: {error}")
        return None
    finally:
        if original is not None:
            try:
                if clipboard.paste() in (sentinel, copied):
                    clipboard.copy(original)
            except Exception:
                pass
