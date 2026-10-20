"""Gemini Web model controls.

Giao diện Gemini (2026-10):
  - Nút chọn: button[data-test-id="bard-mode-menu-button"]
      .picker-primary-text   -> tên model ("Argon", "3.1 Pro", "3.8 Flash"...)
      .picker-secondary-text -> cấp độ tư duy ("Thấp" / "Trung bình" / "Cao")
  - Menu model: gem-menu[data-test-id="gem-mode-menu"] > gem-menu-item[data-mode-id]
      "3.5 Flash-Lite", "3.8 Flash", "3.1 Pro", "4 Argon"
  - Cấp độ tư duy: gem-menu-item[value="thinking_level"] mở submenu
      .submenu-container gem-menu-item -> "Thấp", "Trung bình", "Cao"
"""

import time

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


MODEL_BUTTON_SELECTORS = (
    '[data-test-id="bard-mode-menu-button"]',
    "button.input-area-switch",
    "bard-mode-switcher button",
    ".pill-ui-logo-container button",
)
MENU_ITEM_SELECTORS = (
    '[data-test-id="gem-mode-menu"] gem-menu-item[role="menuitem"]',
    '.cdk-overlay-pane gem-menu-item[role="menuitem"]',
    'gem-menu[role="menu"] gem-menu-item[role="menuitem"]',
)
THINKING_MENU_SELECTOR = 'gem-menu-item[value="thinking_level"]'
SUBMENU_ITEM_SELECTOR = '.submenu-container gem-menu-item[role="menuitem"]'
SPARK_SEGMENT_SELECTORS = (
    "chat-spark-toggle gem-segmented-button",
    "gem-segmented-button-row gem-segmented-button",
)
SPARK_TASK_KEYWORDS = ("nhiệm vụ", "tác vụ", "task", "tasks", "spark")
SPARK_CHAT_KEYWORDS = ("cuộc trò chuyện", "trò chuyện", "chat")

THINKING_KEYWORDS = ("argon", "thinking", "tư duy")

# Nhãn submenu cấp độ tư duy (so khớp chính xác, không dùng substring).
LEVEL_LABELS = {
    "low": ("thấp", "low"),
    "medium": ("trung bình", "medium"),
    "high": ("cao", "high"),
}
LEVEL_ALIASES = {
    "low": "low", "thấp": "low", "off": "low",
    "medium": "medium", "trung bình": "medium",
    "standard": "medium", "tiêu chuẩn": "medium",
    "high": "high", "cao": "high", "extended": "high", "mở rộng": "high",
}
# Giao diện cũ: một item bật/tắt "Mở rộng" nằm phẳng trong menu chính.
LEGACY_EXTENDED_LABELS = ("mở rộng", "extended")


def _safe_text(element, selector):
    try:
        return element.find_element(By.CSS_SELECTOR, selector).text.strip().lower()
    except Exception:
        return ""


def _label(element):
    return _safe_text(element, "span.label") or (element.text or "").strip().lower()


def _attr(element, name):
    try:
        return element.get_attribute(name) or ""
    except Exception:
        return ""


def _is_selected(element):
    if "selected" in _attr(element, "class").split():
        return True
    try:
        content = element.find_element(By.CSS_SELECTOR, "gem-menu-item-content")
        return "selected" in _attr(content, "class").split()
    except Exception:
        return False


def _segment_label(segment):
    return _safe_text(segment, ".gds-body-m") or (segment.text or "").strip().lower()


def _is_segment_selected(segment):
    classes = _attr(segment, "class").split()
    return "gem-segmented-button-selected" in classes or "selected" in classes


def _find_spark_segment(segments, want_task):
    wanted_value = "40" if want_task else "0"
    wanted_keywords = SPARK_TASK_KEYWORDS if want_task else SPARK_CHAT_KEYWORDS
    for segment in segments:
        if _attr(segment, "data-value") == wanted_value:
            return segment
    for segment in segments:
        text = _segment_label(segment)
        if any(keyword in text for keyword in wanted_keywords):
            return segment
    return None


def select_task_mode(driver, enabled=False):
    """Chuyển đổi giữa chế độ 'Cuộc trò chuyện' và 'Nhiệm vụ' trên Gemini Web."""
    want_task = bool(enabled)
    mode_label = "Nhiệm vụ" if want_task else "Cuộc trò chuyện"
    try:
        segments = _visible(driver, SPARK_SEGMENT_SELECTORS)
        if not segments:
            if want_task:
                print("⚠️ Không tìm thấy thanh chọn Nhiệm vụ trên giao diện, giữ mặc định")
            return False
        target = _find_spark_segment(segments, want_task)
        if not target:
            if want_task:
                print(f"⚠️ Không tìm thấy tùy chọn '{mode_label}' trên thanh chuyển đổi")
            return False
        if _is_segment_selected(target):
            if want_task:
                print(f"✅ Đã ở chế độ: {mode_label}")
            return True
        action = target
        try:
            action = target.find_element(
                By.CSS_SELECTOR, "button.gem-segmented-button-action, button"
            )
        except Exception:
            pass
        _click(driver, action, 1.0)
        print(f"✅ Đã chọn chế độ: {mode_label}")
        return True
    except Exception as error:
        print(f"⚠️ Lỗi khi chọn chế độ {mode_label}: {error}")
        return False


def _visible(driver, selectors):
    found = []
    for selector in selectors:
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                if element not in found and element.is_displayed():
                    found.append(element)
        except Exception:
            continue
    return found


def _click(driver, element, pause=1.0):
    driver.execute_script("arguments[0].click();", element)
    time.sleep(pause)


def _close_menu(driver):
    try:
        driver.execute_script("document.body.click();")
    except Exception:
        pass


def _find_model_button(driver):
    buttons = _visible(driver, MODEL_BUTTON_SELECTORS)
    return buttons[0] if buttons else None


def _current_level(button):
    """Đọc cấp độ tư duy đang hiển thị trên nút chọn ("thấp"/"trung bình"/"cao")."""
    return _safe_text(button, ".picker-secondary-text")


def open_model_dropdown(driver):
    """Tìm nút chọn model và trả về (button, text mô tả model hiện tại).

    Hàm không mở menu; tên giữ nguyên để tương thích với code cũ.
    """
    button = _find_model_button(driver)
    if not button:
        print("⚠️ Không tìm thấy dropdown model, tiếp tục với model mặc định")
        return None, None

    primary = _safe_text(button, ".picker-primary-text")
    secondary = _current_level(button)
    current = " ".join(part for part in (primary, secondary) if part)
    if primary and secondary == primary:
        current = primary
    if not current:
        aria = _attr(button, "aria-label")
        lowered = aria.lower()
        for marker in ("hiện tại là", "currently"):
            if marker in lowered:
                current = lowered.split(marker)[-1].strip()
                break
    if not current:
        current = (button.text or "").strip().lower()
    return button, current


def click_menu_item(driver, keywords, label, exclude=()):
    """Click item model đầu tiên khớp từ khóa, ưu tiên theo thứ tự `keywords`.

    `exclude` loại các item có nhãn chứa chuỗi tương ứng (vd: "lite").
    """
    items = [
        item
        for item in _visible(driver, MENU_ITEM_SELECTORS)
        if _attr(item, "value") != "thinking_level"
    ]
    labels = [(item, _label(item)) for item in items]
    excluded = tuple(word.lower() for word in exclude)
    target = None
    for keyword in keywords:
        keyword = keyword.strip().lower()
        target = next(
            (
                item
                for item, text in labels
                if keyword in text and not any(word in text for word in excluded)
            ),
            None,
        )
        if target:
            break
    if not target:
        print(f"⚠️ Không tìm thấy option '{label}' trong menu")
        _close_menu(driver)
        return False
    _click(driver, target)
    print(f"✅ Đã chọn: {label}")
    return True


def _select_model(driver, is_current, keywords, label, exclude=()):
    try:
        button, current = open_model_dropdown(driver)
        if not button:
            return False
        if is_current(current):
            print(f"✅ Đã chọn model {label}")
            return True
        print(f"📌 Model hiện tại: {current}. Đang chuyển sang {label}...")
        _click(driver, button, 1.5)
        return click_menu_item(driver, keywords, label, exclude)
    except Exception as error:
        print(f"⚠️ Lỗi khi chọn model: {error}")
        _close_menu(driver)
        return False


def _is_thinking(current):
    return any(word in current for word in THINKING_KEYWORDS)


def select_thinking_model(driver, max_wait=10):
    del max_wait
    return _select_model(
        driver,
        _is_thinking,
        ["4 Argon", "Argon", "Thinking", "Tư duy"],
        "Thinking/Argon",
    )


def select_pro_model(driver, max_wait=10):
    del max_wait
    return _select_model(
        driver,
        lambda current: "pro" in current and not _is_thinking(current),
        ["3.1 Pro", "Pro"],
        "Pro",
    )


def select_flash_model(driver, max_wait=10):
    del max_wait
    return _select_model(
        driver,
        lambda current: (
            ("flash" in current and "lite" not in current)
            or "fast" in current
            or "nhanh" in current
        ),
        ["3.8 Flash", "Flash", "Fast", "Nhanh"],
        "Flash/Fast",
        exclude=("lite",),
    )


def _open_thinking_submenu(driver):
    items = _visible(driver, (THINKING_MENU_SELECTOR,))
    if not items:
        items = [
            item
            for item in _visible(driver, MENU_ITEM_SELECTORS)
            if _label(item) in ("cấp độ tư duy", "thinking level")
        ]
    if not items:
        return False
    thinking_item = items[0]
    _click(driver, thinking_item)
    if not _visible(driver, (SUBMENU_ITEM_SELECTOR,)):
        # Một số phiên bản chỉ mở submenu khi hover.
        try:
            ActionChains(driver).move_to_element(thinking_item).perform()
            time.sleep(1)
        except Exception:
            pass
    return True


def _select_submenu_level(driver, target, level_label):
    wanted = LEVEL_LABELS[target]
    for item in _visible(driver, (SUBMENU_ITEM_SELECTOR,)):
        text = _label(item)
        if text not in wanted:
            continue
        if _is_selected(item):
            print(f"✅ Đã ở cấp độ tư duy: {text}")
        else:
            _click(driver, item)
            print(f"✅ Đã chọn cấp độ tư duy: {level_label}")
        _close_menu(driver)
        return True
    print(f"⚠️ Không tìm thấy cấp độ '{level_label}' trong submenu")
    _close_menu(driver)
    return False


def _select_legacy_level(driver, target, level_label):
    toggle = next(
        (
            item
            for item in _visible(driver, MENU_ITEM_SELECTORS)
            if not _attr(item, "data-mode-id")
            and _label(item) in LEGACY_EXTENDED_LABELS
        ),
        None,
    )
    if toggle is None:
        return None
    want_extended = target == "high"
    if want_extended == _is_selected(toggle):
        print(f"✅ Đã ở cấp độ: {'Mở rộng' if want_extended else 'Tiêu chuẩn'}")
        _close_menu(driver)
    else:
        _click(driver, toggle)
        print(f"✅ Đã chọn cấp độ tư duy: {level_label}")
    return True


def select_thinking_level(driver, level="extended", max_wait=10):
    """Chọn cấp độ tư duy (Thấp / Trung bình / Cao).

    Chấp nhận cả giá trị cũ: standard/tiêu chuẩn -> Trung bình,
    extended/mở rộng -> Cao. Model không có cấp độ tư duy thì bỏ qua.
    """
    del max_wait
    normalized = str(level or "").strip().lower()
    target = LEVEL_ALIASES.get(normalized, "high")
    level_label = normalized.upper() or target.upper()

    try:
        print(f"🧠 Đang chọn cấp độ tư duy: {level_label}...")
        button = _find_model_button(driver)
        if not button:
            print("⚠️ Không tìm thấy dropdown model, bỏ qua cấp độ tư duy")
            return False

        if _current_level(button) in LEVEL_LABELS[target]:
            print(f"✅ Đã ở cấp độ tư duy: {_current_level(button)}")
            return True

        _click(driver, button, 1.5)

        if _open_thinking_submenu(driver):
            return _select_submenu_level(driver, target, level_label)

        legacy = _select_legacy_level(driver, target, level_label)
        if legacy is not None:
            return legacy

        print("ℹ️ Model hiện tại không có tùy chọn cấp độ tư duy, giữ mặc định")
        _close_menu(driver)
        return False
    except Exception as error:
        print(f"⚠️ Lỗi khi chọn thinking level: {error}")
        _close_menu(driver)
        return False
