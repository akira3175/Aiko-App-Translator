"""ChatGPT Web model and reasoning controls."""

import time
import unicodedata

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    ElementClickInterceptedException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait


def _open_chatgpt_pill_dropdown(driver, purpose="thinking"):
    """
    Click vào pill chọn model/thinking trên ChatGPT.
    Trả về (pill_button, current_text) hoặc (None, None).

    HTML: <button class="__composer-pill __composer-pill--neutral">Cao</button>
    """
    pill_selectors = [
        "button.__composer-pill",
        'button[class*="composer-pill"]',
    ]
    candidates = []
    for selector in pill_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if el.is_displayed() and el not in candidates:
                    candidates.append(el)
        except:
            continue

    pill_button = None
    if purpose == "thinking":
        thinking_words = (
            "tuc thi", "instant", "nhanh", "fast", "vua", "medium",
            "cao", "high", "thinking", "reasoning", "suy nghi",
        )
        for candidate in candidates:
            label = _normalized_chatgpt_label(
                (candidate.text or "")
                + " "
                + (candidate.get_attribute("aria-label") or "")
            )
            if any(word in label for word in thinking_words):
                pill_button = candidate
                break
    if not pill_button:
        print("⚠️ Không tìm thấy pill chọn thinking ChatGPT")
        return None, None

    current_text = pill_button.text.strip().lower()
    return pill_button, current_text


def _normalized_chatgpt_label(value):
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(value.split())


def _visible_chatgpt_menu_items(driver):
    selectors = (
        '[role="menuitemradio"]',
        '[role="menuitem"]',
        '[role="option"]',
        '[data-radix-collection-item]',
    )
    items = []
    for selector in selectors:
        try:
            for item in driver.find_elements(By.CSS_SELECTOR, selector):
                if item.is_displayed() and item not in items:
                    items.append(item)
        except Exception:
            continue
    return items


def _chatgpt_item_text(item):
    return _normalized_chatgpt_label(
        item.get_attribute("textContent") or getattr(item, "text", "")
    )


_CHATGPT_VISIBLE_CHOICE_SCRIPT = r"""
const keywords = arguments[0];
const normalize = (value) => String(value || '')
  .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  .replace(/\s+/g, ' ').trim();
const visible = (element) => {
  const rect = element.getBoundingClientRect();
  const style = getComputedStyle(element);
  return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden'
    && style.display !== 'none';
};
const roots = [...document.querySelectorAll(
  '[role="menu"],[role="listbox"],[data-radix-popper-content-wrapper],[data-radix-menu-content]'
)].filter(visible);
const selector = 'button,[role="menuitem"],[role="menuitemradio"],[role="option"],[data-radix-collection-item]';
const candidates = [];
for (const root of roots) {
  for (const element of root.querySelectorAll(selector)) {
    if (visible(element) && !candidates.includes(element)) candidates.push(element);
  }
}
const scored = candidates.map((element) => {
  const text = normalize(element.textContent);
  const lines = String(element.textContent || '').split(/\r?\n/).map(normalize);
  const exact = keywords.some((word) => text === word || lines.includes(word));
  const contains = keywords.some((word) => text.includes(word));
  const rect = element.getBoundingClientRect();
  return {element, exact, contains, area: rect.width * rect.height};
}).filter((item) => item.exact || item.contains);
scored.sort((a, b) => Number(b.exact) - Number(a.exact) || a.area - b.area);
return scored.length ? scored[0].element : null;
"""


def _find_visible_chatgpt_choice(driver, keywords):
    normalized = [_normalized_chatgpt_label(keyword) for keyword in keywords]
    return driver.execute_script(_CHATGPT_VISIBLE_CHOICE_SCRIPT, normalized)


def _visible_chatgpt_intelligence_picker(driver):
    try:
        for picker in driver.find_elements(
            By.CSS_SELECTOR, '[data-testid="composer-intelligence-picker-content"], '
            '[role="menu"]:has([data-model-picker-view])'
        ):
            if picker.is_displayed():
                return picker
    except Exception:
        pass
    return None


def _open_chatgpt_intelligence_picker(driver):
    picker = _visible_chatgpt_intelligence_picker(driver)
    if picker:
        return picker
    button = _find_chatgpt_model_button(driver)
    if button:
        try:
            button.click()
            return WebDriverWait(driver, 3, poll_frequency=0.2).until(
                lambda current: _visible_chatgpt_intelligence_picker(current) or False
            )
        except (TimeoutException, StaleElementReferenceException, ElementClickInterceptedException):
            pass
    ActionChains(driver).key_down(Keys.CONTROL).key_down(Keys.SHIFT).send_keys(
        "m"
    ).key_up(Keys.SHIFT).key_up(Keys.CONTROL).perform()
    try:
        return WebDriverWait(driver, 10, poll_frequency=0.2).until(
            lambda current_driver: _visible_chatgpt_intelligence_picker(
                current_driver
            )
            or False
        )
    except TimeoutException:
        return None


def _select_chatgpt_advanced_option(driver, row_label, target_keywords):
    """Select a model/reasoning radio item in the current intelligence picker."""
    has_new_picker = bool(
        driver.find_elements(
            By.CSS_SELECTOR, '[data-testid="composer-intelligence-picker-content"]'
        )
    )
    picker = _open_chatgpt_intelligence_picker(driver)
    if not picker:
        return False if has_new_picker else None

    try:
        if picker.find_elements(By.CSS_SELECTOR, '[data-model-picker-view]'):
            return _select_chatgpt_slider_option(driver, picker, row_label, target_keywords)
        advanced = picker.find_element(
            By.CSS_SELECTOR,
            '[data-testid="composer-model-picker-slider-advanced-view"]',
        )
        if advanced.get_attribute("data-active") != "true":
            toggle = picker.find_element(
                By.CSS_SELECTOR,
                '[role="menuitem"][aria-label*="tùy chọn nâng cao" i]',
            )
            driver.execute_script("arguments[0].click();", toggle)
            advanced = WebDriverWait(driver, 5, poll_frequency=0.2).until(
                lambda _driver: picker.find_element(
                    By.CSS_SELECTOR,
                    '[data-testid="composer-model-picker-slider-advanced-view"]'
                    '[data-active="true"]',
                )
            )

        normalized_row = _normalized_chatgpt_label(row_label)
        row = None
        for item in advanced.find_elements(
            By.CSS_SELECTOR, '[role="menuitem"][aria-haspopup="menu"]'
        ):
            labels = item.find_elements(By.CSS_SELECTOR, ".truncate")
            first_label = labels[0].text if labels else item.text
            if _normalized_chatgpt_label(first_label) == normalized_row:
                row = item
                break
        if row is None:
            return False

        row_text = _normalized_chatgpt_label(row.text)
        normalized_targets = [
            _normalized_chatgpt_label(keyword) for keyword in target_keywords
        ]
        if any(target in row_text for target in normalized_targets):
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return True

        driver.execute_script("arguments[0].click();", row)
        target = WebDriverWait(driver, 5, poll_frequency=0.2).until(
            lambda current_driver: _find_visible_chatgpt_choice(
                current_driver, normalized_targets
            )
            or False
        )
        ActionChains(driver).move_to_element(target).click().perform()
        time.sleep(0.5)
        return True
    except (NoSuchElementException, TimeoutException, StaleElementReferenceException):
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        return False


def _select_chatgpt_slider_option(driver, picker, row_label, keywords):
    """Model list and three-position effort slider observed in the new picker."""
    if row_label == "Mô hình":
        def target_item():
            for item in picker.find_elements(By.CSS_SELECTOR, '[role="menuitemradio"]'):
                labels = item.find_elements(By.CSS_SELECTOR, '.truncate')
                label = _chatgpt_item_text(labels[0] if labels else item)
                if label in keywords:
                    return item
            return None

        target = target_item()
        if target is None:
            return False
        if target.get_attribute('aria-checked') != 'true':
            toggle = picker.find_element(By.CSS_SELECTOR, '[data-model-picker-view-toggle]')
            toggle.click()
            target = WebDriverWait(driver, 5).until(
                lambda _: (item if (item := target_item()) is not None and item.is_displayed() else False)
            )
            target.click()
            WebDriverWait(driver, 5).until(
                lambda _: (item := target_item()) is not None
                and item.get_attribute('aria-checked') == 'true'
            )
    else:
        levels = {'tuc thi': 0, 'instant': 0, 'vua': 1, 'medium': 1, 'cao': 2, 'high': 2}
        desired = next((levels[k] for k in keywords if k in levels), None)
        if desired is None:
            return False
        control = picker.find_element(By.CSS_SELECTOR, '[data-reasoning-slider]')
        slider = control.find_element(By.CSS_SELECTOR, '[role="slider"]')
        if slider.get_attribute('aria-valuemin') != '0' or slider.get_attribute('aria-valuemax') != '2':
            return False
        current = int(slider.get_attribute('aria-valuenow'))
        key = Keys.ARROW_RIGHT if desired > current else Keys.ARROW_LEFT
        for _ in range(abs(desired - current)):
            expected = current + (1 if desired > current else -1)
            control.send_keys(key)
            WebDriverWait(driver, 5).until(
                lambda _: control.find_element(By.CSS_SELECTOR, '[role="slider"]').get_attribute('aria-valuenow') == str(expected)
            )
            current = expected
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    return True


def _find_chatgpt_model_button(driver):
    selectors = (
        'button[data-testid="model-switcher-dropdown-button"]',
        'button[aria-label*="model" i]',
        'button[aria-haspopup="menu"]',
    )
    for selector in selectors:
        try:
            for button in driver.find_elements(By.CSS_SELECTOR, selector):
                text = _normalized_chatgpt_label(
                    (button.text or "")
                    + " "
                    + (button.get_attribute("aria-label") or "")
                )
                if button.is_displayed() and any(
                    keyword in text
                    for keyword in ("model", "gpt", "chatgpt", "sol", "thinking", "instant")
                ):
                    return button
        except Exception:
            continue
    return None


def select_chatgpt_thinking(driver, level="cao"):
    """
    Chọn cấp độ thinking trên ChatGPT.

    Dropdown menu chính có các item (role="menuitemradio" hoặc tương tự):
      - Tức thì / Instant
      - Vừa / Medium
      - Cao / High
    """
    if not level:
        return True

    # Danh sách các từ khóa có thể xuất hiện trong DOM (hỗ trợ cả tiếng Anh lẫn tiếng Việt)
    level_keywords = {
        "tuc thi": ["tuc thi", "instant", "nhanh", "fast"],
        "instant": ["tuc thi", "instant", "nhanh", "fast"],
        "vua": ["vua", "medium"],
        "medium": ["vua", "medium"],
        "cao": ["cao", "high"],
        "high": ["cao", "high"],
    }

    normalized_level = _normalized_chatgpt_label(level)
    target_kws = level_keywords.get(normalized_level, [normalized_level])

    try:
        print(f"🧠 Đang chọn cấp độ thinking ChatGPT: {level}...")

        advanced_result = _select_chatgpt_advanced_option(
            driver, "Mức suy luận", target_kws
        )
        if advanced_result:
            print(f"✅ Đã chọn cấp độ thinking: {level}")
            return True
        if advanced_result is False:
            print("⚠️ Không thể chọn Mức suy luận trong intelligence picker")
            return False
        print("⚠️ Không mở được menu Mô hình/Mức suy luận bằng nút chọn hoặc Ctrl+Shift+M")
        return False

    except Exception as e:
        print(f"⚠️ Lỗi khi chọn thinking level ChatGPT: {e}")
        return False


def select_chatgpt_model(driver, model="gpt-5.6 sol"):
    """
    Chọn model cụ thể trên ChatGPT (GPT-5.6 Sol, GPT-5.5, o3, v.v.).
    """
    if not model:
        return True

    target_model = _normalized_chatgpt_label(model)
    model_keywords = [target_model]
    if target_model in {"gpt-5.6 sol", "gpt 5.6 sol", "gpt-5.6"}:
        model_keywords = ["gpt-5.6 sol", "gpt 5.6 sol", "gpt-5.6", "gpt 5.6", "sol"]

    try:
        print(f"📌 Đang chọn model ChatGPT: {model}...")

        advanced_result = _select_chatgpt_advanced_option(
            driver, "Mô hình", model_keywords
        )
        if advanced_result:
            print(f"✅ Đã chọn model: {model}")
            return True
        if advanced_result is False:
            print("⚠️ Không thể chọn Mô hình trong intelligence picker")
            return False
        print("⚠️ Không mở được menu Mô hình/Mức suy luận bằng nút chọn hoặc Ctrl+Shift+M")
        return False

    except Exception as e:
        print(f"⚠️ Lỗi khi chọn model ChatGPT: {e}")
        return False
