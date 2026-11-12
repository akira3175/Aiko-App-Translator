"""ChatGPT Web model and reasoning controls."""

import re
import time
import unicodedata

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait


_THINKING_TIER_ALIASES = {
    "none": (
        "tuc thi", "instant", "khong suy luan", "none", "off", "tat",
    ),
    "minimal": (
        "nhanh", "fast", "minimal", "rat nhe",
    ),
    "low": (
        "nhe nhang", "nhe", "thap", "low", "light",
    ),
    "medium": (
        "vua", "medium", "trung binh", "chuan", "standard", "normal", "balanced",
    ),
    "high": (
        "cao", "high",
    ),
    "xhigh": (
        "chuyen sau", "xhigh", "extra high", "very high", "deep", "rat cao", "sau",
    ),
    "max": (
        "max", "toi da", "maximum",
    ),
    "ultra": (
        "ultra", "sieu cap", "lien tuc", "persistent",
    ),
}

_KEYWORD_TO_THINKING_TIER = {
    alias: tier
    for tier, aliases in _THINKING_TIER_ALIASES.items()
    for alias in aliases
}

# Mapping from (vmax_int, tier) -> slider integer index (0..vmax_int).
# Observed in ChatGPT snapshots:
# - vmax=2 (3 ticks): 0=Tức thì (none), 1=Vừa (medium), 2=Cao (high)
# - vmax=4 (5 ticks): 0=Nhẹ nhàng (low), 1=Vừa (medium), 2=Cao (high), 3=Chuyên sâu (xhigh), 4=Max (max)
_SLIDER_TIER_INDEX_BY_MAX = {
    1: {
        "none": 0, "minimal": 0, "low": 0,
        "medium": 1, "high": 1, "xhigh": 1, "max": 1, "ultra": 1,
    },
    2: {
        "none": 0, "minimal": 0, "low": 0,
        "medium": 1,
        "high": 2, "xhigh": 2, "max": 2, "ultra": 2,
    },
    3: {
        "none": 0, "minimal": 0, "low": 0,
        "medium": 1,
        "high": 2,
        "xhigh": 3, "max": 3, "ultra": 3,
    },
    4: {
        "none": 0, "minimal": 0, "low": 0,
        "medium": 1,
        "high": 2,
        "xhigh": 3,
        "max": 4, "ultra": 4,
    },
    5: {
        "none": 0, "minimal": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "xhigh": 4,
        "max": 5, "ultra": 5,
    },
}

_INTELLIGENCE_PICKER_SELECTOR = (
    '[data-testid="composer-intelligence-picker-content"], '
    '[role="menu"]:has([data-model-picker-view]), '
    '[role="menu"]:has([data-reasoning-slider]), '
    '[role="menu"]:has([data-model-picker-power-slider]), '
    '[role="menu"]:has([data-model-picker-view-toggle]), '
    '[role="menu"][class*="ModelPickerDropdownContent"]'
)

_EXCLUDED_MENU_BUTTON_KEYWORDS = (
    "chuyen che do",
    "switch mode",
    "mo menu ho so",
    "profile",
    "thanh ben",
    "sidebar",
    "gan day",
    "hanh dong trong tro chuyen",
    "conversation actions",
    "chon tep",
    "them tep",
    "add files",
    "plugin",
    "chon du an",
)

_EXCLUDED_NAVIGATION_TARGETS = {
    "add-context",
    "plugins",
    "workspace-project",
}


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
        except Exception:
            continue

    pill_button = None
    if purpose == "thinking":
        thinking_words = (
            "tuc thi", "instant", "nhanh", "fast", "nhe", "thap", "low",
            "vua", "medium", "cao", "high", "chuyen sau", "xhigh", "max",
            "toi da", "ultra", "thinking", "reasoning", "suy nghi", "suy luan",
            "no luc",
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
    value = value.replace("đ", "d")
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(value.split())


def _canonical_model_label(value):
    normalized = _normalized_chatgpt_label(value)
    normalized = re.sub(r"\b(gpt)\s*-\s*(\d)", r"\1 \2", normalized)
    return " ".join(normalized.split())


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
  .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  .replace(/[đĐ]/g, 'd').toLowerCase()
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
            By.CSS_SELECTOR, _INTELLIGENCE_PICKER_SELECTOR
        ):
            if not picker.is_displayed():
                continue
            state = picker.get_attribute("data-state")
            if isinstance(state, str) and state.strip().lower() == "closed":
                continue
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


def _has_slider_or_view_picker(picker):
    for selector in (
        '[data-model-picker-view]',
        '[data-reasoning-slider]',
        '[data-model-picker-power-slider]',
        '[data-model-picker-view-toggle]',
    ):
        try:
            if picker.find_elements(By.CSS_SELECTOR, selector):
                return True
        except Exception:
            continue
    return False


def _select_chatgpt_advanced_option(driver, row_label, target_keywords):
    """Select a model/reasoning radio item in the current intelligence picker."""
    has_new_picker = bool(
        driver.find_elements(
            By.CSS_SELECTOR, _INTELLIGENCE_PICKER_SELECTOR
        )
    )
    picker = _open_chatgpt_intelligence_picker(driver)
    if not picker:
        return False if has_new_picker else None

    try:
        if _has_slider_or_view_picker(picker):
            return _select_chatgpt_slider_option(driver, picker, row_label, target_keywords)
        advanced = picker.find_element(
            By.CSS_SELECTOR,
            '[data-testid="composer-model-picker-slider-advanced-view"]',
        )
        if advanced.get_attribute("data-active") != "true":
            toggle = picker.find_element(
                By.CSS_SELECTOR,
                '[role="menuitem"][aria-label*="tùy chọn nâng cao" i], '
                '[role="menuitem"][aria-label*="advanced" i]',
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
        row_aliases = {normalized_row}
        if normalized_row == "mo hinh":
            row_aliases.update({"mo hinh", "model", "chon mo hinh"})
        elif normalized_row == "muc suy luan":
            row_aliases.update({
                "muc suy luan", "muc no luc", "nang luong", "suy luan",
                "reasoning", "thinking", "effort", "power",
            })

        row = None
        for item in advanced.find_elements(
            By.CSS_SELECTOR, '[role="menuitem"][aria-haspopup="menu"]'
        ):
            labels = item.find_elements(By.CSS_SELECTOR, ".truncate")
            first_label = labels[0].text if labels else item.text
            if _normalized_chatgpt_label(first_label) in row_aliases:
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


def _extract_model_item_label(item):
    try:
        labels = item.find_elements(By.CSS_SELECTOR, ".truncate")
    except Exception:
        labels = []
    if labels:
        return _chatgpt_item_text(labels[0])
    return _chatgpt_item_text(item)


def _match_model_radio_item(items, keywords):
    normalized_kws = [_normalized_chatgpt_label(k) for k in keywords if k]
    canonical_kws = [_canonical_model_label(k) for k in keywords if k]

    # Pass 1: Exact match on normalized or canonicalized label
    for item in items:
        label = _extract_model_item_label(item)
        if not label:
            continue
        if label in normalized_kws or _canonical_model_label(label) in canonical_kws:
            return item

    # Pass 2: Version prefix match (e.g., "gpt-5.6" matching "GPT-5.6 Sol" when no plain "GPT-5.6" exists)
    prefix_matches = []
    for item in items:
        label = _extract_model_item_label(item)
        canon = _canonical_model_label(label)
        if not canon:
            continue
        for ck in canonical_kws:
            if ck and canon.startswith(ck + " "):
                prefix_matches.append((item, canon))
                break

    if prefix_matches:
        for item, canon in prefix_matches:
            if " sol" in canon:
                return item
        return prefix_matches[0][0]

    return None


def _is_model_item_checked(item):
    checked = item.get_attribute("aria-checked")
    if checked == "true":
        return True
    selected = item.get_attribute("data-model-selected")
    return selected == "true" if isinstance(selected, str) else False


def _is_advanced_model_view_open(picker):
    try:
        groups = picker.find_elements(By.CSS_SELECTOR, '[data-model-picker-view="advanced"]')
        if groups:
            return True
    except Exception:
        pass
    return False


def _click_element_reliably(driver, element):
    try:
        element.click()
    except (ElementClickInterceptedException, ElementNotInteractableException):
        driver.execute_script("arguments[0].click();", element)


def _resolve_slider_desired_index(keywords, vmin, vmax):
    if vmin != "0" or vmax not in {"1", "2", "3", "4", "5"}:
        return None
    vmax_int = int(vmax)
    tier_map = _SLIDER_TIER_INDEX_BY_MAX[vmax_int]

    for kw in keywords:
        norm = _normalized_chatgpt_label(kw)
        if norm in _KEYWORD_TO_THINKING_TIER:
            tier = _KEYWORD_TO_THINKING_TIER[norm]
            return tier_map[tier]
        if norm.isdigit():
            idx = int(norm)
            if 0 <= idx <= vmax_int:
                return idx
    return None


def _slider_int_value(slider):
    raw = slider.get_attribute("aria-valuenow")
    if raw is None:
        return None
    try:
        return int(round(float(str(raw).strip())))
    except (ValueError, TypeError):
        return None


def _fallback_step_slider(driver, control, key, expected):
    """Fallback when Radix menu item ignores send_keys due to tabindex=-1."""
    key_name = "ArrowRight" if key == Keys.ARROW_RIGHT else "ArrowLeft"
    try:
        driver.execute_script(
            """
            const ctrl = arguments[0];
            const keyName = arguments[1];
            ctrl.focus();
            const ev = new KeyboardEvent('keydown', {
                key: keyName, code: keyName, bubbles: true, cancelable: true
            });
            ctrl.dispatchEvent(ev);
            """,
            control,
            key_name,
        )
        WebDriverWait(driver, 2, poll_frequency=0.1).until(
            lambda _: _slider_int_value(
                control.find_element(By.CSS_SELECTOR, '[role="slider"]')
            ) == expected
        )
        return True
    except Exception:
        pass

    try:
        ticks = control.find_elements(
            By.CSS_SELECTOR, '[class*="TickRail"] > *, [class*="Tick-"]'
        )
        if 0 <= expected < len(ticks):
            ActionChains(driver).move_to_element(ticks[expected]).click().perform()
            WebDriverWait(driver, 2, poll_frequency=0.1).until(
                lambda _: _slider_int_value(
                    control.find_element(By.CSS_SELECTOR, '[role="slider"]')
                ) == expected
            )
            return True
    except Exception:
        pass
    return False


def _select_chatgpt_slider_option(driver, picker, row_label, keywords):
    """Model list and multi-position effort slider observed in the new picker."""
    if row_label == "Mô hình":
        def target_item():
            items = picker.find_elements(By.CSS_SELECTOR, '[role="menuitemradio"]')
            return _match_model_radio_item(items, keywords)

        target = target_item()
        if target is None:
            # If the model list is lazily rendered only after opening the toggle
            try:
                if not picker.find_elements(By.CSS_SELECTOR, '[role="menuitemradio"]'):
                    toggle = picker.find_element(By.CSS_SELECTOR, '[data-model-picker-view-toggle]')
                    _click_element_reliably(driver, toggle)
                    target = WebDriverWait(driver, 5).until(
                        lambda _: target_item() or False
                    )
            except Exception:
                target = None
        if target is None:
            return False

        if not _is_model_item_checked(target):
            if not _is_advanced_model_view_open(picker):
                toggle = picker.find_element(By.CSS_SELECTOR, '[data-model-picker-view-toggle]')
                _click_element_reliably(driver, toggle)
            target = WebDriverWait(driver, 5).until(
                lambda _: (item if (item := target_item()) is not None and item.is_displayed() else False)
            )
            _click_element_reliably(driver, target)
            WebDriverWait(driver, 5).until(
                lambda _: (item := target_item()) is not None
                and _is_model_item_checked(item)
            )
    else:
        control = picker.find_element(By.CSS_SELECTOR, '[data-reasoning-slider]')
        if control.get_attribute("aria-disabled") == "true" and _is_advanced_model_view_open(picker):
            try:
                toggle = picker.find_element(By.CSS_SELECTOR, '[data-model-picker-view-toggle]')
                _click_element_reliably(driver, toggle)
                control = WebDriverWait(driver, 5).until(
                    lambda _: (
                        ctrl if (ctrl := picker.find_element(By.CSS_SELECTOR, '[data-reasoning-slider]'))
                        and ctrl.get_attribute("aria-disabled") != "true"
                        else False
                    )
                )
            except Exception:
                pass

        slider = control.find_element(By.CSS_SELECTOR, '[role="slider"]')
        vmin = slider.get_attribute('aria-valuemin')
        vmax = slider.get_attribute('aria-valuemax')
        desired = _resolve_slider_desired_index(keywords, vmin, vmax)
        if desired is None:
            return False
        current = _slider_int_value(slider)
        if current is None:
            return False
        key = Keys.ARROW_RIGHT if desired > current else Keys.ARROW_LEFT
        for _ in range(abs(desired - current)):
            expected = current + (1 if desired > current else -1)
            control.send_keys(key)
            try:
                WebDriverWait(driver, 5).until(
                    lambda _: _slider_int_value(
                        control.find_element(By.CSS_SELECTOR, '[role="slider"]')
                    ) == expected
                )
            except TimeoutException:
                if not _fallback_step_slider(driver, control, key, expected):
                    raise
            current = expected
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    return True


def _is_excluded_menu_button(button, normalized_text):
    try:
        nav_target = button.get_attribute("data-composer-navigation-target")
        if isinstance(nav_target, str) and nav_target.strip().lower() in _EXCLUDED_NAVIGATION_TARGETS:
            return True
    except Exception:
        pass
    return any(excl in normalized_text for excl in _EXCLUDED_MENU_BUTTON_KEYWORDS)


def _find_chatgpt_model_button(driver):
    explicit_selectors = (
        'button[data-composer-navigation-target="reasoning"]',
        'button[data-composer-navigation-target*="model" i]',
        'button[data-selected-reasoning-effort]',
        'button[data-testid="model-switcher-dropdown-button"]',
        'button[data-testid*="model-picker" i]',
        'button[data-testid*="intelligence-picker" i]',
        'button[aria-label*="chọn mô hình" i]',
        'button[aria-label*="mức nỗ lực" i]',
        'button[aria-label*="mức suy luận" i]',
        'button[aria-label*="select model" i]',
        'button[aria-label*="choose model" i]',
    )
    for selector in explicit_selectors:
        try:
            for button in driver.find_elements(By.CSS_SELECTOR, selector):
                if button.is_displayed():
                    return button
        except Exception:
            continue

    fallback_selectors = (
        'button[aria-label*="model" i]',
        'button[aria-haspopup="menu"]',
    )
    valid_keywords = (
        "model", "mo hinh", "gpt", "chatgpt", "sol", "terra", "luna", "astra",
        "thinking", "instant", "suy luan", "no luc", "tuc thi", "vua", "cao",
        "nhe", "chuyen sau", "max", "ultra",
    )
    for selector in fallback_selectors:
        try:
            for button in driver.find_elements(By.CSS_SELECTOR, selector):
                if not button.is_displayed():
                    continue
                text = _normalized_chatgpt_label(
                    (button.text or "")
                    + " "
                    + (button.get_attribute("aria-label") or "")
                )
                if _is_excluded_menu_button(button, text):
                    continue
                if any(keyword in text for keyword in valid_keywords):
                    return button
        except Exception:
            continue
    return None


def _expand_chatgpt_thinking_keywords(level):
    normalized_level = _normalized_chatgpt_label(level)
    tier = _KEYWORD_TO_THINKING_TIER.get(normalized_level)
    if tier:
        return list(_THINKING_TIER_ALIASES[tier])
    return [normalized_level]


def _expand_chatgpt_model_keywords(model):
    target_model = _normalized_chatgpt_label(model)
    canonical = _canonical_model_label(model)
    hyphenated = re.sub(r"\b(gpt)\s+(\d)", r"\1-\2", canonical)

    keywords = []
    for candidate in (target_model, hyphenated, canonical):
        if candidate and candidate not in keywords:
            keywords.append(candidate)

    if canonical in {"mac dinh", "default", "auto", "tu dong"}:
        for alias in ("mac dinh", "default", "auto", "tu dong"):
            if alias not in keywords:
                keywords.append(alias)
    elif re.fullmatch(r"gpt\s+\d+(?:\.\d+)?", canonical):
        # e.g., user passed "gpt-5.6" or "gpt-6" -> also allow exact and "-sol" fallback via _match_model_radio_item
        pass
    elif canonical == "gpt 5.6 sol":
        for alias in ("gpt-5.6 sol", "gpt 5.6 sol", "gpt-5.6", "gpt 5.6"):
            if alias not in keywords:
                keywords.append(alias)

    return keywords


def select_chatgpt_thinking(driver, level="cao"):
    """
    Chọn cấp độ thinking trên ChatGPT.

    Hỗ trợ cả thanh trượt 3 mức (0..2: Tức thì / Vừa / Cao) lẫn thanh trượt
    5 mức (0..4: Nhẹ nhàng / Vừa / Cao / Chuyên sâu / Max) và menu phụ cũ.
    """
    if not level:
        return True

    target_kws = _expand_chatgpt_thinking_keywords(level)

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
    Chọn model cụ thể trên ChatGPT (GPT-6, GPT-6.1 Sol, GPT-6 Sol, GPT-5.6 Sol, Mặc định, v.v.).
    """
    if not model:
        return True

    model_keywords = _expand_chatgpt_model_keywords(model)

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


_MODE_GROUP_BUTTON_SELECTORS = (
    '[role="group"][aria-label*="chế độ trình soạn thảo" i] button',
    '[role="group"][aria-label*="chế độ" i] button',
    '[role="group"][aria-label*="composer mode" i] button',
    '[role="group"][aria-label*="mode" i] button',
    '[class*="home-mode-toggle"] [role="group"] button',
    '[class*="home-mode-toggle"] button[aria-pressed]',
    '[role="group"] > button[aria-pressed]',
)

_CHAT_MODE_KEYWORDS = ("tro chuyen", "chat", "cuoc tro chuyen", "conversation")
_WORK_MODE_KEYWORDS = ("cong viec", "work", "nhiem vu", "task", "tasks", "workspace")


def _normalize_chatgpt_mode(mode):
    if isinstance(mode, bool):
        return "work" if mode else "chat"
    norm = _normalized_chatgpt_label(mode)
    if norm in {"work", "cong viec", "nhiem vu", "task", "tasks", "workspace", "on", "true", "1"}:
        return "work"
    return "chat"


def _button_combined_label(btn):
    parts = []
    for raw in (
        btn.get_attribute("textContent"),
        getattr(btn, "text", ""),
        btn.get_attribute("aria-label"),
    ):
        if isinstance(raw, str) and raw.strip():
            parts.append(raw.strip())
    return _normalized_chatgpt_label(" ".join(parts))


def _find_chatgpt_mode_buttons(driver):
    for selector in _MODE_GROUP_BUTTON_SELECTORS:
        try:
            buttons = [
                btn for btn in driver.find_elements(By.CSS_SELECTOR, selector)
                if btn.is_displayed()
            ]
            if buttons:
                return buttons
        except Exception:
            continue

    # Fallback: scan standalone button[aria-pressed] matching chat/work keywords
    fallback = []
    try:
        for btn in driver.find_elements(By.CSS_SELECTOR, "button[aria-pressed]"):
            if not btn.is_displayed():
                continue
            label = _button_combined_label(btn)
            if any(k in label for k in _CHAT_MODE_KEYWORDS + _WORK_MODE_KEYWORDS):
                fallback.append(btn)
    except Exception:
        pass
    return fallback


def _match_chatgpt_mode_button(buttons, want_work):
    wanted_keywords = _WORK_MODE_KEYWORDS if want_work else _CHAT_MODE_KEYWORDS
    for btn in buttons:
        label = _button_combined_label(btn)
        if label and any(k == label or k in label for k in wanted_keywords):
            return btn

    # Positional fallback inside the 2-button mode toggle group (0=Chat, 1=Work)
    if len(buttons) == 2 and any(
        btn.get_attribute("aria-pressed") in ("true", "false") for btn in buttons
    ):
        return buttons[1] if want_work else buttons[0]

    return None


def _is_chatgpt_mode_selected(button):
    for attr in ("aria-pressed", "aria-selected", "aria-checked"):
        val = button.get_attribute(attr)
        if val == "true":
            return True
        if val == "false":
            return False
    classes = str(button.get_attribute("class") or "").split()
    return "text-mode-toggle-primary" in classes


def select_chatgpt_mode(driver, mode="chat"):
    """
    Chuyển đổi giữa chế độ 'Trò chuyện' (Chat) và 'Công việc' (Work) trên ChatGPT Web.
    """
    target_mode = _normalize_chatgpt_mode(mode)
    want_work = target_mode == "work"
    mode_label = "Công việc (Work)" if want_work else "Trò chuyện (Chat)"

    try:
        buttons = _find_chatgpt_mode_buttons(driver)
        if not buttons:
            if want_work:
                print("⚠️ Không tìm thấy thanh chuyển chế độ Trò chuyện/Công việc trên ChatGPT")
                return False
            return True

        target = _match_chatgpt_mode_button(buttons, want_work)
        if target is None:
            if want_work:
                print(f"⚠️ Không tìm thấy nút chế độ '{mode_label}' trên ChatGPT")
                return False
            return True

        if _is_chatgpt_mode_selected(target):
            if want_work:
                print(f"✅ Đã ở chế độ ChatGPT: {mode_label}")
            return True

        print(f"🔀 Đang chuyển chế độ ChatGPT sang: {mode_label}...")
        _click_element_reliably(driver, target)
        WebDriverWait(driver, 5, poll_frequency=0.2).until(
            lambda current_driver: (
                (btn := _match_chatgpt_mode_button(_find_chatgpt_mode_buttons(current_driver), want_work))
                is not None
                and _is_chatgpt_mode_selected(btn)
            )
        )
        time.sleep(0.5)
        print(f"✅ Đã chọn chế độ ChatGPT: {mode_label}")
        return True
    except Exception as e:
        print(f"⚠️ Lỗi khi chọn chế độ ChatGPT ({mode_label}): {e}")
        return False
