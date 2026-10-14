"""Locate and read the Gemini Web response created by the current prompt."""

from selenium.webdriver.common.by import By


SNAPSHOT_SCRIPT = r"""
const token = arguments[0];
const uniqueRoots = (selector, closestSelector) => {
    const result = [];
    for (const el of document.querySelectorAll(selector)) {
        const root = el.closest(closestSelector) || el;
        if (!result.includes(root)) result.push(root);
    }
    return result;
};
const users = uniqueRoots(
    'user-query,.user-query,[data-test-id="user-query"],.query-content',
    'user-query,.user-query,[data-test-id="user-query"]'
);
const responses = uniqueRoots(
    'model-response,message-content .model-response-text,.model-response-text,response-container,.response-container-content',
    'model-response,response-container,[data-test-id*="response"]'
);
for (const root of users) root.setAttribute('data-novel-before-user', token);
for (const root of responses) root.setAttribute('data-novel-before-response', token);
return {users: users.length, responses: responses.length};
"""


NEW_RESPONSE_SCRIPT = r"""
const token = arguments[0];
const oldResponseCount = arguments[1];
const uniqueRoots = (selector, closestSelector) => {
    const result = [];
    for (const el of document.querySelectorAll(selector)) {
        const root = el.closest(closestSelector) || el;
        if (!result.includes(root)) result.push(root);
    }
    return result;
};
const users = uniqueRoots(
    'user-query,.user-query,[data-test-id="user-query"],.query-content',
    'user-query,.user-query,[data-test-id="user-query"]'
);
const responses = uniqueRoots(
    'model-response,message-content .model-response-text,.model-response-text,response-container,.response-container-content',
    'model-response,response-container,[data-test-id*="response"]'
);
const newUsers = users.filter(
    (root) => root.getAttribute('data-novel-before-user') !== token
);
if (newUsers.length) {
    const latestUser = newUsers[newUsers.length - 1];
    const afterPrompt = responses.filter((root) =>
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


def copy_response_text(_driver):
    """Keep response reading independent from the operating-system clipboard."""
    return None
