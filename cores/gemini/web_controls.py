"""Gemini Web model controls with multi-signal fallbacks.

Thiết kế chống gãy khi Google đổi giao diện Gemini Web:
  1. Không phụ thuộc cứng vào một `role` (`menuitem` vs `menuitemradio`) hay
     một vùng chứa (`.cdk-overlay-pane` vs `[popover]` nội bộ).
  2. Đọc đồng thời `.label`, `.sublabel`, `element.text`, `data-mode-id`,
     `data-test-id`, `aria-checked` và metadata base64 trong `jslog`
     (`BardVeMetadataKey`), vì Google có thể đảo vị trí tên model/mô tả giữa
     `.label` và `.sublabel`.
  3. Tìm submenu Cấp độ tư duy qua `value="thinking_level"`, nhãn văn bản,
     hoặc thuộc tính ngữ nghĩa `aria-haspopup="true"` + `aria-controls`.
  4. Chọn mức tư duy theo 4 tầng: nhãn chính -> mô tả phụ -> mã `jslog` ->
     vị trí thứ tự (Thấp / Trung bình / Cao).
"""

import base64
import json
import re
import time

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


MODEL_BUTTON_SELECTORS = (
    '[data-test-id="bard-mode-menu-button"]',
    "bard-mode-switcher button.input-area-switch",
    "button.input-area-switch",
    "bard-mode-switcher button",
    ".pill-ui-logo-container button",
    'button[aria-haspopup="true"][aria-label*="chế độ"]',
    'button[aria-haspopup="true"][aria-label*="mode" i]',
)
MENU_ITEM_SELECTORS = (
    '[data-test-id="gem-mode-menu"] gem-menu-item',
    '[data-test-id="bard-mode-desktop-gem-menu"] gem-menu-item',
    ".cdk-overlay-pane gem-menu-item",
    'gem-menu[role="menu"] gem-menu-item',
    '[data-test-id="gem-mode-menu"] [role^="menuitem"]',
    '.cdk-overlay-pane [role^="menuitem"]',
)
THINKING_MENU_SELECTOR = 'gem-menu-item[value="thinking_level"]'
SUBMENU_ITEM_SELECTORS = (
    ".submenu-container gem-menu-item",
    '.submenu-container [role="menuitemradio"]',
    '.submenu-container [role="menuitem"]',
)
SUBMENU_ITEM_SELECTOR = SUBMENU_ITEM_SELECTORS[0]
SPARK_SEGMENT_SELECTORS = (
    "chat-spark-toggle gem-segmented-button",
    "gem-segmented-button-row gem-segmented-button",
)
SPARK_TASK_KEYWORDS = ("nhiệm vụ", "tác vụ", "task", "tasks", "spark")
SPARK_CHAT_KEYWORDS = ("cuộc trò chuyện", "trò chuyện", "chat")

THINKING_KEYWORDS = (
    "argon",
    "thinking",
    "tư duy",
    "code & analysis",
    "lập trình và phân tích",
    "reasoning",
)
THINKING_MENU_LABELS = (
    "cấp độ tư duy",
    "mức độ tư duy",
    "thinking level",
    "thinking budget",
    "reasoning effort",
)

# Nhãn chính của submenu cấp độ tư duy.
LEVEL_LABELS = {
    "low": ("thấp", "low", "tối thiểu", "minimal"),
    "medium": ("trung bình", "medium", "tiêu chuẩn", "standard", "balanced", "vừa"),
    "high": ("cao", "high", "mở rộng", "extended", "tối đa", "max", "maximum", "deep"),
}
# Mô tả phụ (.sublabel) của từng cấp độ tư duy.
LEVEL_SUBLABELS = {
    "low": ("fast and efficient", "nhanh và hiệu quả", "nhanh gọn"),
    "medium": ("độ sâu cân bằng", "balanced depth", "cân bằng"),
    "high": ("cực kỳ kỹ lưỡng", "extra thorough", "most thorough", "chuyên sâu"),
}
# Mã số mức tư duy trong BardVeMetadataKey của Gemini: ["argon", <code_int>, 8]
LEVEL_JSLOG_CODES = {
    "low": 1,
    "medium": 4,
    "high": 2,
}
LEVEL_ORDER = ("low", "medium", "high")
LEVEL_ALIASES = {
    "low": "low", "thấp": "low", "off": "low", "minimal": "low", "tối thiểu": "low",
    "medium": "medium", "trung bình": "medium", "vừa": "medium",
    "standard": "medium", "tiêu chuẩn": "medium", "balanced": "medium",
    "high": "high", "cao": "high", "extended": "high", "mở rộng": "high",
    "max": "high", "maximum": "high", "tối đa": "high",
}
# Giao diện cũ: một item bật/tắt "Mở rộng" nằm phẳng trong menu chính.
LEGACY_EXTENDED_LABELS = ("mở rộng", "extended")

# Mã mode_id đã biết của Gemini Web (dùng làm tín hiệu phụ khi nhãn bị dịch khác).
KNOWN_MODE_IDS = {
    "thinking": ("argon", "95a4c0abcba24364"),
    "pro": ("e6fa609c3fa255c0",),
    "flash": ("56fdd199312815e2",),
    "flash-lite": ("8c46e95b1a07cecc",),
}


def _safe_text(element, selector):
    try:
        return element.find_element(By.CSS_SELECTOR, selector).text.strip().lower()
    except Exception:
        return ""


def _primary_label(element):
    return (
        _safe_text(element, "span.label")
        or _safe_text(element, ".label")
        or (element.text or "").strip().lower()
    )


def _sublabel(element):
    return (
        _safe_text(element, ".sublabel")
        or _safe_text(element, "div.sublabel")
        or _safe_text(element, ".description")
    )


def _label(element):
    """Ghép cả sublabel + label + text để khớp đúng dù Google đặt tên model ở đâu."""
    primary = _primary_label(element)
    sub = _sublabel(element)
    raw = re.sub(r"\s+", " ", (element.text or "").strip().lower())
    parts = [part for part in (sub, primary, raw) if part]
    if not parts:
        return ""
    merged = []
    for part in parts:
        if part not in merged:
            merged.append(part)
    return " | ".join(merged)


def _attr(element, name):
    try:
        return element.get_attribute(name) or ""
    except Exception:
        return ""


def _jslog_metadata(element):
    """Giải mã BardVeMetadataKey (base64 JSON) trong thuộc tính jslog nếu có."""
    jslog = _attr(element, "jslog")
    if "BardVeMetadataKey:" not in jslog:
        return None
    try:
        encoded = jslog.split("BardVeMetadataKey:", 1)[1].split(";", 1)[0].strip()
        padding = "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(encoded + padding).decode("utf-8", errors="ignore")
        return json.loads(decoded)
    except Exception:
        return None


def _jslog_tail(element):
    data = _jslog_metadata(element)
    if not isinstance(data, list):
        return None
    for item in reversed(data):
        if item is not None:
            return item
    return None


def _is_selected(element):
    aria_checked = _attr(element, "aria-checked").strip().lower()
    if aria_checked == "true":
        return True
    if _attr(element, "aria-selected").strip().lower() == "true":
        return True
    if "selected" in _attr(element, "class").split():
        return True
    try:
        content = element.find_element(By.CSS_SELECTOR, "gem-menu-item-content")
        if "selected" in _attr(content, "class").split():
            return True
    except Exception:
        pass
    try:
        icon = element.find_element(
            By.CSS_SELECTOR,
            'mat-icon[data-mat-icon-name="check"], mat-icon[fonticon="check"], '
            'gem-icon[aria-label="Đã chọn"], gem-icon[aria-label="Selected"]',
        )
        if icon is not None:
            return True
    except Exception:
        pass
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
    secondary = _safe_text(button, ".picker-secondary-text")
    if secondary:
        return secondary
    # Dự phòng nếu Google bỏ class .picker-secondary-text nhưng vẫn giữ text nhiều dòng
    lines = [line.strip().lower() for line in (button.text or "").splitlines() if line.strip()]
    if len(lines) >= 2:
        for candidate in lines[1:]:
            if any(candidate in labels for labels in LEVEL_LABELS.values()):
                return candidate
    return ""


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
        for marker in ("hiện tại là", "currently", "current mode:"):
            if marker in lowered:
                current = lowered.split(marker)[-1].strip()
                break
    if not current:
        tail = _jslog_tail(button)
        if isinstance(tail, list) and tail and isinstance(tail[0], str):
            current = tail[0].strip().lower()
    if not current:
        current = re.sub(r"\s+", " ", (button.text or "").strip().lower())
    return button, current


def _is_thinking_menu_trigger(item):
    if _attr(item, "value") == "thinking_level":
        return True
    if _attr(item, "aria-haspopup").strip().lower() == "true":
        return True
    return _primary_label(item) in THINKING_MENU_LABELS


def _model_menu_items(driver):
    submenu_items = set(_visible(driver, SUBMENU_ITEM_SELECTORS))
    return [
        item
        for item in _visible(driver, MENU_ITEM_SELECTORS)
        if item not in submenu_items and not _is_thinking_menu_trigger(item)
    ]


def _matches_mode_id(item, mode_ids):
    if not mode_ids:
        return False
    mode_id = _attr(item, "data-mode-id").strip().lower()
    test_id = _attr(item, "data-test-id").strip().lower()
    tail = _jslog_tail(item)
    jslog_id = tail[0].strip().lower() if isinstance(tail, list) and tail and isinstance(tail[0], str) else ""
    for wanted in mode_ids:
        wanted = wanted.lower()
        if mode_id == wanted or test_id.endswith(f"-{wanted}") or jslog_id == wanted:
            return True
    return False


def click_menu_item(driver, keywords, label, exclude=(), mode_ids=()):
    """Click item model đầu tiên khớp từ khóa hoặc `mode_ids`, ưu tiên theo thứ tự.

    Đọc cả `.sublabel` (nơi giao diện Gemini mới đặt tên model như "4 Argon",
    "3.1 Pro", "3.8 Flash") lẫn `.label` (mô tả như "Code & analysis").
    """
    items = _model_menu_items(driver)
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

    if not target and mode_ids:
        target = next(
            (item for item in items if _matches_mode_id(item, mode_ids)),
            None,
        )

    if not target:
        print(f"⚠️ Không tìm thấy option '{label}' trong menu")
        _close_menu(driver)
        return False
    if _is_selected(target):
        print(f"✅ Đã ở model: {label}")
        _close_menu(driver)
        return True
    _click(driver, target)
    print(f"✅ Đã chọn: {label}")
    return True


def _select_model(driver, is_current, keywords, label, exclude=(), mode_ids=()):
    try:
        button, current = open_model_dropdown(driver)
        if not button:
            return False
        if current and is_current(current):
            print(f"✅ Đã chọn model {label}")
            return True
        print(f"📌 Model hiện tại: {current}. Đang chuyển sang {label}...")
        _click(driver, button, 1.5)
        return click_menu_item(driver, keywords, label, exclude, mode_ids=mode_ids)
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
        [
            "4 Argon",
            "Argon",
            "Thinking",
            "Tư duy",
            "Code & analysis",
            "Lập trình và phân tích",
            "Reasoning",
        ],
        "Thinking/Argon",
        mode_ids=KNOWN_MODE_IDS["thinking"],
    )


def select_pro_model(driver, max_wait=10):
    del max_wait
    return _select_model(
        driver,
        lambda current: "pro" in current and not _is_thinking(current),
        [
            "3.1 Pro",
            "Pro",
            "Detailed research",
            "Nghiên cứu chuyên sâu",
            "Nghiên cứu chi tiết",
        ],
        "Pro",
        mode_ids=KNOWN_MODE_IDS["pro"],
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
        [
            "3.8 Flash",
            "Flash",
            "Fast",
            "Nhanh",
            "Trợ giúp toàn diện",
            "All-round",
        ],
        "Flash/Fast",
        exclude=("lite", "quick answers", "câu trả lời nhanh"),
        mode_ids=KNOWN_MODE_IDS["flash"],
    )


def select_flash_lite_model(driver, max_wait=10):
    del max_wait
    return _select_model(
        driver,
        lambda current: "lite" in current,
        ["3.5 Flash-Lite", "Flash-Lite", "Lite", "Quick answers", "Câu trả lời nhanh"],
        "Flash-Lite",
        mode_ids=KNOWN_MODE_IDS["flash-lite"],
    )


def select_custom_model(driver, model_name):
    """Fallback cho mọi tên model mới trong tương lai mà không cần sửa code."""
    cleaned = str(model_name or "").strip()
    if not cleaned:
        return False
    lowered = cleaned.lower()
    return _select_model(
        driver,
        lambda current: lowered in current,
        [cleaned],
        cleaned,
        mode_ids=(lowered,),
    )


def _submenu_items(driver, thinking_item=None):
    items = _visible(driver, SUBMENU_ITEM_SELECTORS)
    if items:
        return items
    if thinking_item is not None:
        controls_id = _attr(thinking_item, "aria-controls").strip()
        if controls_id:
            controlled = _visible(
                driver,
                (
                    f"#{controls_id} gem-menu-item",
                    f'#{controls_id} [role="menuitemradio"]',
                    f'#{controls_id} [role="menuitem"]',
                ),
            )
            if controlled:
                return controlled
    return []


def _open_thinking_submenu(driver):
    items = _visible(driver, (THINKING_MENU_SELECTOR,))
    if not items:
        items = [
            item
            for item in _visible(driver, MENU_ITEM_SELECTORS)
            if _is_thinking_menu_trigger(item)
        ]
    if not items:
        return None
    thinking_item = items[0]
    _click(driver, thinking_item)
    if not _submenu_items(driver, thinking_item):
        # Một số phiên bản chỉ mở submenu khi hover.
        try:
            ActionChains(driver).move_to_element(thinking_item).perform()
            time.sleep(1)
        except Exception:
            pass
    return thinking_item


def _match_submenu_level_item(items, target):
    wanted_labels = LEVEL_LABELS[target]
    wanted_sublabels = LEVEL_SUBLABELS[target]
    wanted_code = LEVEL_JSLOG_CODES[target]

    # Tầng 1: Khớp chính xác nhãn chính (.label hoặc dòng đầu tiên của text)
    for item in items:
        primary = _primary_label(item)
        first_line = (
            primary.splitlines()[0].strip() if primary else ""
        )
        if primary in wanted_labels or first_line in wanted_labels:
            return item, first_line or primary

    # Tầng 2: Khớp theo mô tả phụ (.sublabel) hoặc text đầy đủ
    for item in items:
        sub = _sublabel(item)
        full = _label(item)
        if any(phrase in sub or phrase in full for phrase in (*wanted_sublabels, *wanted_labels)):
            return item, _primary_label(item) or target

    # Tầng 3: Khớp theo mã nội bộ trong jslog BardVeMetadataKey (["argon", code, 8])
    for item in items:
        tail = _jslog_tail(item)
        if isinstance(tail, list) and len(tail) >= 2 and tail[1] == wanted_code:
            return item, _primary_label(item) or target

    # Tầng 4: Nếu submenu có đúng 3 mức theo thứ tự chuẩn (Thấp, Trung bình, Cao)
    if len(items) == 3 and target in LEVEL_ORDER:
        chosen = items[LEVEL_ORDER.index(target)]
        return chosen, _primary_label(chosen) or target

    return None, ""


def _select_submenu_level(driver, target, level_label, thinking_item=None):
    items = _submenu_items(driver, thinking_item)
    matched, text = _match_submenu_level_item(items, target)
    if matched is not None:
        if _is_selected(matched):
            print(f"✅ Đã ở cấp độ tư duy: {text}")
        else:
            _click(driver, matched)
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
            and _primary_label(item) in LEGACY_EXTENDED_LABELS
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

        current_lvl = _current_level(button)
        if current_lvl in LEVEL_LABELS[target]:
            print(f"✅ Đã ở cấp độ tư duy: {current_lvl}")
            return True

        _click(driver, button, 1.5)

        thinking_item = _open_thinking_submenu(driver)
        if thinking_item:
            return _select_submenu_level(driver, target, level_label, thinking_item)

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
