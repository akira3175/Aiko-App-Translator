"""
dich_utils.py
=============
Hàm dùng chung cho dich_v2.py (dịch đơn) và dich_v3.py (dịch batch).
Chỉnh sửa tại đây sẽ áp dụng cho CẢ HAI script.
"""

import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata

import yaml
from google import genai
from google.genai import types
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    SessionNotCreatedException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from cores.runtime_config import bool_option, int_option, option, web_mode

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTABLE_CHROME = os.path.join(
    APP_ROOT, "runtime", "chromium", "chrome-win64", "chrome.exe"
)
PORTABLE_CHROMEDRIVER = os.path.join(
    APP_ROOT, "runtime", "chromium", "chromedriver-win64", "chromedriver.exe"
)
USER_DATA_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "NovelTranslatorStudio",
)

# ============================================================
# ★ ĐƯỜNG DẪN MẶC ĐỊNH — chỉnh ở đây nếu muốn thay đổi
# ============================================================
_project_name = os.environ.get("NOVEL_PROJECT", "").strip()
_project_dir = os.path.join("truyen", _project_name) if _project_name else "truyen"
NOVEL_YAML = os.path.join(_project_dir, "novel.yaml")
CONTEXT_YAML = os.path.join(_project_dir, "context.yaml")
PRONOUNS_YAML = os.path.join(_project_dir, "pronouns.yaml")
NOVEL_TXT = os.path.join(_project_dir, "novel.txt")
CHARACTERS_MD = os.path.join(
    _project_dir, "characters.md"
)  # Ho so nhan vat -- truyen vao polish_translation
LINK_GEMINI = str(
    option("link_gemini", "https://gemini.google.com/gem/fdec65ac9c69")
)

# ============================================================
# ★ CẤU HÌNH CHROME SELENIUM
# ============================================================
SELENIUM_PROFILE_PATH = os.path.join(USER_DATA_ROOT, "profiles", "gemini")


def chrome_service():
    if os.path.isfile(PORTABLE_CHROMEDRIVER):
        return Service(PORTABLE_CHROMEDRIVER)
    return Service(ChromeDriverManager().install())


def apply_portable_chrome(options):
    if os.path.isfile(PORTABLE_CHROME):
        options.binary_location = PORTABLE_CHROME

# ============================================================
# ★ CẤU HÌNH DỊCH
# ============================================================
FIX_MAX_RETRY = int_option("fix_max_retry", 3, minimum=1)

# ============================================================
# ★ MỤC 1: CHỌN MODEL — chỉnh ở đây
# ============================================================
# Giá trị hỗ trợ:
#   "pro"      = Tự động chọn model Pro
#   "thinking" = Tự động chọn model Thinking
#   "free"     = Giữ nguyên model đang chọn trên web
WEB_MODEL_FREE = "free"
WEB_MODEL_PRO = "pro"
WEB_MODEL_THINKING = "thinking"

SELECT_MODEL = str(option("gemini_web_model", WEB_MODEL_PRO))

# ============================================================
# ★ MỤC 2: CHỌN CẤP ĐỘ TƯ DUY — chỉnh ở đây
# ============================================================
# Giá trị hỗ trợ:
#   "off"      = Tắt (không dùng tư duy)
#   "low"      = Thấp
#   "medium"   = Trung bình
#   "high"     = Cao
#   "extended" = Mở rộng (cao nhất)
WEB_THINKING_LEVEL = str(option("gemini_thinking", "extended"))

# Model cho pipeline hậu dịch (API)
POLISH_MODEL = str(option("polish_model", "gemini-3-flash-preview"))
REVIEW_BG_MODEL = str(option("review_bg_model", "gemini-3.1-flash-lite-preview"))
REVIEW_YAML = os.path.join(_project_dir, "review.yaml")
LOG_DIR = os.path.join(_project_dir, "logs")

# Lock cho ghi review.yaml từ nhiều thread
_review_lock = threading.Lock()
# Snapshot review mới nhất của từng chương, tránh thread cũ ghi đè kết quả mới.
_latest_review_tokens = {}
# Lock cho ghi log từ nhiều thread
_log_lock = threading.Lock()


# ============================================================
# ★ LOGGING PROMPT / RESPONSE
# ============================================================


def log_api_call(
    chapter_id: str, step: str, model: str, prompt: str, response: str, ok: bool = True
):
    """
    Lưu log một lần gọi API vào truyen/logs/YYYY-MM-DD.jsonl.
    Mỗi dòng là một JSON object độc lập (JSONL format).
    """
    from datetime import datetime

    os.makedirs(LOG_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(LOG_DIR, f"{date_str}.jsonl")
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "chapter_id": chapter_id,
        "step": step,
        "model": model,
        "ok": ok,
        "prompt_len": len(prompt),
        "response_len": len(response),
        "prompt": prompt,
        "response": response,
    }
    with _log_lock:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ==== QUẢN LÝ API KEY ====


def load_api_keys(file_path="apikeys.txt"):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            keys = [line.strip() for line in f if line.strip()]
        if not keys:
            print("⚠️ Không có API key nào trong apikeys.txt! Chỉ dùng Gemini Web.")
            return ["dummy_key"]
        return keys
    except FileNotFoundError:
        print("⚠️ Không tìm thấy apikeys.txt! Chỉ dùng Gemini Web.")
        return ["dummy_key"]


API_KEYS = load_api_keys("apikeys.txt")
current_key_index = 0
last_switch_time = time.time()


def get_client():
    """Trả về client theo API key hiện tại, đổi key sau mỗi 1 tiếng."""
    global current_key_index, last_switch_time, API_KEYS
    now = time.time()
    if now - last_switch_time >= 3600:
        current_key_index = (current_key_index + 1) % len(API_KEYS)
        last_switch_time = now
        print(f"🔄 Đã đổi API key sang key số {current_key_index + 1}")
    return genai.Client(api_key=API_KEYS[current_key_index])


def switch_api_key():
    """Đổi sang API key tiếp theo (dùng khi gặp lỗi 429)."""
    global current_key_index, last_switch_time, API_KEYS
    old_index = current_key_index
    current_key_index = (current_key_index + 1) % len(API_KEYS)
    last_switch_time = time.time()
    print(f"🔄 Lỗi 429! Đổi API key: {old_index + 1} → {current_key_index + 1}")


def call_gemini(
    prompt,
    model,
    temperature=0.5,
    max_output_tokens=None,
    system_instruction=None,
    as_chat_parts=False,
    extra_parts=None,
):
    """
    Wrapper goi Gemini API.

    Args:
        prompt           : Noi dung gui di (str)
        model            : Ten model
        temperature      : Do sang tao (mac dinh 0.5)
        max_output_tokens: Gioi han token output
        system_instruction: System prompt
        as_chat_parts    : Neu True, gui prompt duoi dang role/parts
        extra_parts      : Danh sach types.Part bo sung (file upload,...)
                           -- chi dung khi as_chat_parts=True

    Returns:
        str: response.text
    """
    client = get_client()

    # Tat toan bo bo loc noi dung
    _safety_off = [
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.OFF,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=types.HarmBlockThreshold.OFF,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=types.HarmBlockThreshold.OFF,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.OFF,
        ),
    ]

    configured_temperature = option("gemini_api_temperature", "")
    cfg_kwargs = {
        "temperature": float(configured_temperature) if configured_temperature not in (None, "") else temperature,
        "safety_settings": _safety_off,
    }
    thinking_level = str(option("gemini_api_thinking", "high")).strip().lower()
    if thinking_level == "off":
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    elif thinking_level != "auto":
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
    top_p = option("gemini_api_top_p", "")
    top_k = option("gemini_api_top_k", "")
    configured_max_tokens = option("gemini_api_max_output_tokens", "")
    if top_p not in (None, ""):
        cfg_kwargs["top_p"] = float(top_p)
    if top_k not in (None, ""):
        cfg_kwargs["top_k"] = int(top_k)
    if configured_max_tokens not in (None, ""):
        cfg_kwargs["max_output_tokens"] = int(configured_max_tokens)
    elif max_output_tokens:
        cfg_kwargs["max_output_tokens"] = max_output_tokens
    if system_instruction:
        cfg_kwargs["system_instruction"] = system_instruction

    if as_chat_parts:
        parts = [{"text": prompt}]
        if extra_parts:
            for ep in extra_parts:
                parts.append(ep)
        contents = [{"role": "user", "parts": parts}]
    else:
        contents = [prompt]

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(**cfg_kwargs),
    )
    try:
        res_text = response.text
        if not res_text.strip():
            print(
                f"\n[DEBUG GEMINI] response.text rỗng! In toàn bộ cấu trúc response:\n{response}\n[END DEBUG]\n"
            )
        return res_text
    except Exception as e:
        print(f"\n[DEBUG GEMINI] Xảy ra lỗi khi lấy response.text: {e}")
        print(f"Chi tiết response:\n{response}\n[END DEBUG]\n")
        return ""


# ==== SELENIUM DRIVER ====

_gemini_driver = None


def get_gemini_driver():
    """Lấy hoặc tạo driver cho Gemini web (giữ browser mở suốt phiên)."""
    global _gemini_driver
    if _gemini_driver is not None:
        try:
            _gemini_driver.current_url
            return _gemini_driver
        except:
            _gemini_driver = None

    print("🌐 Đang khởi động trình duyệt Gemini web...")
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-data-dir={SELENIUM_PROFILE_PATH}")
    apply_portable_chrome(options)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    _gemini_driver = webdriver.Chrome(service=chrome_service(), options=options)
    _gemini_driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        },
    )
    print("✅ Đã mở trình duyệt. Đảm bảo đã đăng nhập Google trong profile này!")
    return _gemini_driver


def close_gemini_driver():
    """Đóng driver khi kết thúc."""
    global _gemini_driver
    if _gemini_driver:
        try:
            _gemini_driver.quit()
        except:
            pass
        _gemini_driver = None


def setup_gemini_browser():
    """Mở browser để đăng nhập Google và cấu hình Gemini trước khi dịch."""
    print("\n" + "=" * 60)
    print("🔧 CHẾ ĐỘ CÀI ĐẶT GEMINI")
    print("=" * 60)
    print("Trình duyệt sẽ mở ra để bạn:")
    print("  1. Đăng nhập tài khoản Google")
    print("  2. Truy cập gemini.google.com và cấu hình (nếu cần)")
    print("  3. Chọn model, cài đặt ngôn ngữ, v.v...")
    print("=" * 60 + "\n")
    driver = get_gemini_driver()
    driver.get("https://gemini.google.com/app")
    print("🌐 Trình duyệt đã mở tại: https://gemini.google.com/app")
    print("\n🔔 Sau khi đăng nhập và cài đặt xong, nhấn ENTER để bắt đầu dịch...")
    if not (web_mode() and bool_option("skip_login_prompt", True)):
        input()
    print("✅ Đã sẵn sàng! Bắt đầu quá trình dịch...\n")


def _open_model_dropdown(driver):
    """
    Mở dropdown chọn model.
    Trả về (model_button, current_text) hoặc (None, None).

    Giao diện Gemini mới (2025):
      - Button có data-test-id="bard-mode-menu-button"
      - Text model hiện tại nằm trong <span class="picker-primary-text">
      - aria-label chứa "hiện tại là {Model}" (ví dụ: "Mở công cụ chọn chế độ, hiện tại là Pro")
    """
    model_selectors = [
        # Giao diện mới: button chính có data-test-id
        '[data-test-id="bard-mode-menu-button"]',
        # Fallback: tìm bên trong bard-mode-switcher
        "bard-mode-switcher button.input-area-switch",
        "bard-mode-switcher button",
        ".pill-ui-logo-container button",
    ]
    model_button = None
    for selector in model_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if el.is_displayed():
                    model_button = el
                    break
            if model_button:
                break
        except:
            continue

    if not model_button:
        print("⚠️ Không tìm thấy dropdown model, tiếp tục với model mặc định")
        return None, None

    # Ưu tiên đọc text từ span.picker-primary-text (giao diện mới)
    current_text = ""
    try:
        pill_text = model_button.find_element(By.CSS_SELECTOR, ".picker-primary-text")
        if pill_text:
            current_text = pill_text.text.strip().lower()
    except:
        pass

    # Fallback: đọc từ aria-label ("hiện tại là Pro")
    if not current_text:
        try:
            aria = model_button.get_attribute("aria-label") or ""
            # Parse: "Mở công cụ chọn chế độ, hiện tại là Pro"
            if "hiện tại là" in aria:
                current_text = aria.split("hiện tại là")[-1].strip().lower()
            elif "currently" in aria.lower():
                current_text = aria.lower().split("currently")[-1].strip()
        except:
            pass

    # Fallback cuối: dùng toàn bộ text của button
    if not current_text:
        current_text = model_button.text.strip().lower()

    return model_button, current_text


def _click_gem_menu_item(driver, keywords, label):
    """
    Tìm và click gem-menu-item trong menu Gemini.

    Cấu trúc thật (captured_dropdown.html):
      <gem-menu data-test-id="gem-mode-menu" role="menu">
        <gem-menu-item role="menuitem" data-mode-id="...">
          <gem-menu-item-content>
            <span class="label"> 3.1 Pro </span>
          </gem-menu-item-content>
        </gem-menu-item>
      </gem-menu>
    """
    target_option = None
    item_selectors = [
        '[data-test-id="gem-mode-menu"] gem-menu-item[role="menuitem"]',
        '.cdk-overlay-pane gem-menu-item[role="menuitem"]',
        'gem-menu[role="menu"] gem-menu-item[role="menuitem"]',
        '[role="menuitem"]',
    ]

    for selector in item_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if el.is_displayed():
                    try:
                        label_el = el.find_element(By.CSS_SELECTOR, "span.label")
                        text = label_el.text.strip().lower()
                    except:
                        text = el.text.strip().lower()

                    val = el.get_attribute("value") or ""
                    if val == "thinking_level":
                        continue

                    for keyword in keywords:
                        if keyword.strip().lower() in text:
                            target_option = el
                            break
                if target_option:
                    break
            if target_option:
                break
        except:
            continue

    if target_option:
        driver.execute_script("arguments[0].click();", target_option)
        time.sleep(1)
        print(f"✅ Đã chọn: {label}")
        return True
    else:
        print(f"⚠️ Không tìm thấy option '{label}' trong menu")
        driver.execute_script("document.body.click();")
        return False


def select_thinking_level(driver, level=WEB_THINKING_LEVEL, max_wait=10):
    """
    Chọn cấp độ tư duy. Chỉ có 2 level: "Tiêu chuẩn" và "Mở rộng".

    Giao diện mới (2025-07):
      - "Mở rộng" nằm ngay trong menu chính, sau mat-divider
      - Không còn submenu con value="thinking_level"
      - Là gem-menu-item thường, không có data-mode-id
    """
    level_keywords = {
        "off": ["Tiêu chuẩn", "Standard"],
        "standard": ["Tiêu chuẩn", "Standard"],
        "low": ["Tiêu chuẩn", "Standard"],
        "medium": ["Tiêu chuẩn", "Standard"],
        "high": ["Mở rộng", "Extended"],
        "extended": ["Mở rộng", "Extended"],
    }
    keywords = level_keywords.get(level, ["Mở rộng", "Extended"])
    level_label = level.upper()
    want_extended = level in ("high", "extended")

    try:
        print(f"🧠 Đang chọn cấp độ tư duy: {level_label}...")

        # Mở dropdown model
        model_button, _ = _open_model_dropdown(driver)
        if model_button:
            driver.execute_script("arguments[0].click();", model_button)
            time.sleep(1.5)

        # --- Giao diện mới: "Mở rộng" là item phẳng sau divider ---
        # Tìm tất cả gem-menu-item trong menu chính
        thinking_item = None
        item_selectors = [
            '[data-test-id="gem-mode-menu"] gem-menu-item[role="menuitem"]',
            '.cdk-overlay-pane gem-menu-item[role="menuitem"]',
            'gem-menu[role="menu"] gem-menu-item[role="menuitem"]',
        ]

        for selector in item_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    if not el.is_displayed():
                        continue
                    # Bỏ qua các model item (có data-mode-id)
                    if el.get_attribute("data-mode-id"):
                        continue
                    # Đọc label
                    try:
                        lbl = el.find_element(By.CSS_SELECTOR, "span.label")
                        text = lbl.text.strip().lower()
                    except:
                        text = el.text.strip().lower()
                    # Match với keywords
                    for kw in keywords:
                        if kw.strip().lower() in text:
                            thinking_item = el
                            break
                    if thinking_item:
                        break
                if thinking_item:
                    break
            except:
                continue

        # --- Fallback: giao diện cũ với value="thinking_level" ---
        if not thinking_item:
            try:
                elements = driver.find_elements(
                    By.CSS_SELECTOR, 'gem-menu-item[value="thinking_level"]'
                )
                for el in elements:
                    if el.is_displayed():
                        thinking_item = el
                        # Giao diện cũ: cần check sublabel và mở submenu
                        try:
                            sublabel = el.find_element(By.CSS_SELECTOR, ".sublabel")
                            current = sublabel.text.strip().lower()
                            target_kw = keywords[0].strip().lower()
                            if target_kw in current:
                                print(f"✅ Đã ở cấp độ: {sublabel.text.strip()}")
                                driver.execute_script("document.body.click();")
                                return True
                        except:
                            pass
                        # Click mở submenu cũ
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(1)
                        # Tìm option trong submenu cũ
                        sub_items = driver.find_elements(
                            By.CSS_SELECTOR,
                            '.cdk-overlay-pane gem-menu-item[role="menuitem"]',
                        )
                        for sub_el in sub_items:
                            if sub_el.is_displayed():
                                val = sub_el.get_attribute("value") or ""
                                if val == "thinking_level":
                                    continue
                                try:
                                    sub_lbl = sub_el.find_element(
                                        By.CSS_SELECTOR, "span.label"
                                    )
                                    sub_text = sub_lbl.text.strip().lower()
                                except:
                                    sub_text = sub_el.text.strip().lower()
                                for kw in keywords:
                                    if kw.strip().lower() in sub_text:
                                        driver.execute_script(
                                            "arguments[0].click();", sub_el
                                        )
                                        time.sleep(1)
                                        print(
                                            f"✅ Đã chọn cấp độ tư duy: {level_label} (submenu cũ)"
                                        )
                                        return True
                        print(f"⚠️ Không tìm thấy '{level_label}' trong submenu cũ")
                        driver.execute_script("document.body.click();")
                        return False
            except:
                pass

        if not thinking_item:
            print("⚠️ Không tìm thấy option cấp độ tư duy trong menu")
            driver.execute_script("document.body.click();")
            return False

        # Check nếu đã chọn (class "selected" trên item hoặc gem-menu-item-content)
        is_selected = "selected" in (thinking_item.get_attribute("class") or "")
        if not is_selected:
            try:
                content_el = thinking_item.find_element(
                    By.CSS_SELECTOR, "gem-menu-item-content"
                )
                is_selected = "selected" in (content_el.get_attribute("class") or "")
            except:
                pass

        if want_extended and is_selected:
            print(f"✅ Đã ở cấp độ: Mở rộng")
            driver.execute_script("document.body.click();")
            return True
        elif not want_extended and not is_selected:
            # Muốn Tiêu chuẩn và Mở rộng chưa được chọn → đã ở Tiêu chuẩn
            print(f"✅ Đã ở cấp độ: Tiêu chuẩn")
            driver.execute_script("document.body.click();")
            return True

        # Click toggle
        driver.execute_script("arguments[0].click();", thinking_item)
        time.sleep(1)
        print(f"✅ Đã chọn cấp độ tư duy: {level_label}")
        return True

    except Exception as e:
        print(f"⚠️ Lỗi khi chọn thinking level: {e}")
        return False


def select_thinking_model(driver, max_wait=10):
    """Chọn model Thinking nếu chưa được chọn."""
    try:
        model_button, current_text = _open_model_dropdown(driver)
        if not model_button:
            return False

        if "thinking" in current_text or "tư duy" in current_text:
            print("✅ Đã chọn model Thinking")
            return True

        print(f"📌 Model hiện tại: {current_text}. Đang chuyển sang Thinking...")
        driver.execute_script("arguments[0].click();", model_button)
        time.sleep(1.5)

        return _click_gem_menu_item(driver, ["Thinking", "Tư duy"], "Thinking")

    except Exception as e:
        print(f"⚠️ Lỗi khi chọn model: {e}")
        return False


def select_pro_model(driver, max_wait=10):
    """Chọn model Pro nếu chưa được chọn."""
    try:
        model_button, current_text = _open_model_dropdown(driver)
        if not model_button:
            return False

        # Kiểm tra nếu đã là Pro (nhưng KHÔNG phải "Thinking" vì Thinking cũng chứa "Pro")
        if (
            "pro" in current_text
            and "thinking" not in current_text
            and "tư duy" not in current_text
        ):
            print("✅ Đã chọn model Pro")
            return True

        print(f"📌 Model hiện tại: {current_text}. Đang chuyển sang Pro...")
        driver.execute_script("arguments[0].click();", model_button)
        time.sleep(1.5)

        return _click_gem_menu_item(driver, ["Pro"], "Pro")

    except Exception as e:
        print(f"⚠️ Lỗi khi chọn model: {e}")
        return False


def copy_response_text(driver):
    """Lấy nội dung qua element.text thay vì click Copy (để không dùng OS clipboard)."""
    # Ta trả về None để generator rớt xuống hàm lấy current_text (element.text)
    return None


def generate_content_with_selenium(prompt, max_retries=3, web_model=SELECT_MODEL):
    """
    Gửi prompt đến Gemini web và lấy response.

    Args:
        prompt      : Nội dung gửi đi
        max_retries : Số lần thử lại
        web_model   : Chế độ model trên web
                      WEB_MODEL_FREE     — không đổi model
                      WEB_MODEL_PRO      — tự động chọn Pro
                      WEB_MODEL_THINKING — tự động chọn Thinking (mặc định)
    """
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys

    for attempt in range(max_retries):
        try:
            driver = get_gemini_driver()
            wait = WebDriverWait(driver, 60)

            driver.get(LINK_GEMINI)
            time.sleep(3)

            # Bước 1: Chọn model
            if web_model == WEB_MODEL_THINKING:
                select_thinking_model(driver)
            elif web_model == WEB_MODEL_PRO:
                select_pro_model(driver)
            else:
                print(f"📌 Chế độ FREE — giữ nguyên model hiện tại")

            # Bước 2: Chọn cấp độ tư duy (nếu không phải 'off')
            if WEB_THINKING_LEVEL and WEB_THINKING_LEVEL != "off":
                select_thinking_level(driver, WEB_THINKING_LEVEL)

            # Selectors theo cấu trúc HTML mới (test.html):
            # <rich-textarea> → <div class="ql-editor ... new-input-ui" contenteditable="true"
            #   aria-label="Nhập câu lệnh cho Gemini" data-placeholder="Hỏi Gemini">
            input_selectors = [
                '.ql-editor.new-input-ui[contenteditable="true"]',  # Giao diện mới
                'rich-textarea div.ql-editor[contenteditable="true"]',
                'div.ql-editor[contenteditable="true"]',
                'div[contenteditable="true"][aria-label*="Gemini"]',
                'div[role="textbox"][contenteditable="true"]',
                'div[contenteditable="true"]',  # Fallback rộng nhất
            ]
            input_area = None
            for selector in input_selectors:
                try:
                    input_area = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if input_area:
                        break
                except:
                    continue

            if not input_area:
                raise NoSuchElementException("Không tìm thấy ô nhập liệu!")

            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", input_area
                )
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", input_area)
                driver.execute_script("arguments[0].focus();", input_area)
            except Exception as e:
                print(f"⚠️ Lỗi focus input: {e}")

            time.sleep(0.5)
            # Thay vì dùng pyperclip và phím tắt dán (chiếm OS clipboard), ta dùng js execCommand
            driver.execute_script(
                """
                const inputArea = arguments[0];
                const text = arguments[1];
                inputArea.focus();
                
                // Thử dùng insertText
                if (!document.execCommand('insertText', false, text)) {
                    // Fallback nếu sự kiện không hoạt động
                    const dt = new DataTransfer();
                    dt.setData('text/plain', text);
                    const evt = new ClipboardEvent('paste', {
                        clipboardData: dt,
                        bubbles: true,
                        cancelable: true
                    });
                    inputArea.dispatchEvent(evt);
                }
            """,
                input_area,
                prompt,
            )
            time.sleep(1)

            # Selectors theo cấu trúc HTML mới (test.html):
            # <gem-icon-button class="send-button ... has-input submit">
            #   <button aria-label="Gửi tin nhắn"> → icon arrow_upward
            # <div data-test-id="send-button-container">
            send_selectors = [
                # Giao diện mới: nút gửi trong send-button-container
                '[data-test-id="send-button-container"] button',
                "gem-icon-button.send-button button",
                'button[aria-label*="Gửi tin nhắn"]',
                'button[aria-label*="Gửi"]',
                'button[aria-label*="Send"]',
                # Fallback: tìm icon arrow_upward (icon mới thay cho send)
                'mat-icon[data-mat-icon-name="arrow_upward"]',
            ]
            send_button = None
            for selector in send_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        # Nếu tìm thấy mat-icon, leo lên ancestor button
                        if el.tag_name.lower() == "mat-icon":
                            try:
                                el = el.find_element(By.XPATH, "./ancestor::button")
                            except:
                                pass
                        if el.is_displayed() and el.is_enabled():
                            send_button = el
                            break
                    if send_button:
                        break
                except:
                    continue

            if send_button:
                driver.execute_script("arguments[0].click();", send_button)
            else:
                # Fallback cuối: dùng Enter key
                ActionChains(driver).send_keys(Keys.RETURN).perform()

            print(f"📤 Đã gửi prompt ({len(prompt)} ký tự). Đang chờ response...")
            time.sleep(5)

            max_wait = 1600
            min_response_length = 100
            start_time = time.time()
            last_text = ""
            stable_count = 0

            while time.time() - start_time < max_wait:
                # Selectors cho response — thử nhiều vì Gemini thay đổi thường xuyên
                response_selectors = [
                    "message-content .model-response-text",
                    ".model-response-text",
                    "message-content",
                    ".response-container-content",
                    ".markdown-main-container",
                    ".conversation-container message-content",
                ]
                current_text = ""
                for selector in response_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            current_text = elements[-1].text.strip()
                            if current_text:
                                break
                    except:
                        continue

                current_len = len(current_text) if current_text else 0
                last_len = len(last_text) if last_text else 0

                if current_len > last_len:
                    print(f"\r✍️ Đang nhận: {current_len} ký tự...", end="", flush=True)
                    stable_count = 0

                if current_text and current_text == last_text:
                    stable_count += 1
                    if stable_count >= 5 and current_len >= min_response_length:
                        print("\n✅ Streaming hoàn tất.")
                        final_text = copy_response_text(driver)
                        return final_text if final_text else current_text
                else:
                    stable_count = 0
                    last_text = current_text

                time.sleep(1)

            if last_text:
                return last_text
            raise TimeoutException("Timeout chờ response")

        except Exception as e:
            print(f"⚠️ Lỗi Selenium lần {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
                try:
                    driver.refresh()
                except:
                    pass
            else:
                raise ValueError(f"❌ Thất bại: {e}")


# ============================================================
# ★ CHATGPT SELENIUM DRIVER
# ============================================================
CHATGPT_PROFILE_PATH = os.path.join(USER_DATA_ROOT, "profiles", "chatgpt")

_chatgpt_driver = None


def _close_orphaned_chatgpt_profile_chrome():
    """Close Chrome processes that are still locking the ChatGPT Selenium profile."""
    if os.name != "nt":
        return

    env = os.environ.copy()
    env["CHATGPT_PROFILE_PATH_TO_CLOSE"] = CHATGPT_PROFILE_PATH
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
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        output = (result.stdout or "").strip().splitlines()
        closed_count = int(output[-1]) if output else 0
        if closed_count:
            print(
                f"Closed {closed_count} old ChatGPT Chrome process(es) using the Selenium profile."
            )
            time.sleep(2)
    except Exception:
        pass


def get_chatgpt_driver():
    """Lấy hoặc tạo driver cho ChatGPT web (giữ browser mở suốt phiên)."""
    global _chatgpt_driver
    if _chatgpt_driver is not None:
        try:
            _chatgpt_driver.current_url
            return _chatgpt_driver
        except:
            close_chatgpt_driver(close_orphans=True)

    print("🌐 Đang khởi động trình duyệt ChatGPT web...")
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-data-dir={CHATGPT_PROFILE_PATH}")
    apply_portable_chrome(options)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    for start_attempt in range(2):
        try:
            _chatgpt_driver = webdriver.Chrome(service=chrome_service(), options=options)
            break
        except SessionNotCreatedException:
            _chatgpt_driver = None
            if start_attempt == 0:
                _close_orphaned_chatgpt_profile_chrome()
                continue
            raise
    _chatgpt_driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        },
    )
    print("✅ Đã mở trình duyệt ChatGPT. Đảm bảo đã đăng nhập trong profile này!")
    return _chatgpt_driver


def close_chatgpt_driver(close_orphans=False):
    """Đóng driver ChatGPT khi kết thúc."""
    global _chatgpt_driver
    if _chatgpt_driver:
        try:
            _chatgpt_driver.quit()
        except:
            pass
        _chatgpt_driver = None
    if close_orphans:
        _close_orphaned_chatgpt_profile_chrome()


def setup_chatgpt_browser():
    """Mở browser để đăng nhập ChatGPT trước khi dịch."""
    print("\n" + "=" * 60)
    print("🔧 CHẾ ĐỘ CÀI ĐẶT CHATGPT")
    print("=" * 60)
    print("Trình duyệt sẽ mở ra để bạn:")
    print("  1. Đăng nhập tài khoản OpenAI/ChatGPT")
    print("  2. Chọn model (GPT-4o, o3, v.v.)")
    print("  3. Cài đặt khác (nếu cần)")
    print("=" * 60 + "\n")
    driver = get_chatgpt_driver()
    driver.get("https://chatgpt.com/")
    print("🌐 Trình duyệt đã mở tại: https://chatgpt.com/")
    print("\n🔔 Sau khi đăng nhập và cài đặt xong, nhấn ENTER để bắt đầu dịch...")
    if not (web_mode() and bool_option("skip_login_prompt", True)):
        input()
    print("✅ Đã sẵn sàng! Bắt đầu quá trình dịch...\n")


# ============================================================
# ★ CẤU HÌNH CHATGPT — chỉnh ở đây
# ============================================================
# Giá trị hỗ trợ cho CHATGPT_SELECT_THINKING:
#   "tức thì" / "instant"  = Nhanh nhất, không suy nghĩ
#   "vừa"     / "medium"   = Trung bình
#   "cao"     / "high"     = Cao (mặc định)
CHATGPT_SELECT_THINKING = str(option("chatgpt_thinking", "cao"))

# Giá trị hỗ trợ cho CHATGPT_SELECT_MODEL:
#   None / ""           = Không đổi model, dùng mặc định
#   "gpt-5.6 sol"       = GPT-5.6 Sol
#   "gpt-5.6"           = GPT-5.6 Sol (alias)
#   "gpt-5.5"           = GPT-5.5
#   "gpt-5.4"           = GPT-5.4
#   "gpt-5.3"           = GPT-5.3
#   "o3"                = o3
CHATGPT_SELECT_MODEL = str(option("chatgpt_model", "gpt-5.6 sol"))


def _open_chatgpt_pill_dropdown(driver):
    """
    Click vào pill chọn model/thinking trên ChatGPT.
    Trả về (pill_button, current_text) hoặc (None, None).

    HTML: <button class="__composer-pill __composer-pill--neutral">Cao</button>
    """
    pill_selectors = [
        "button.__composer-pill",
        'button[class*="composer-pill"]',
    ]
    pill_button = None
    for selector in pill_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if el.is_displayed():
                    pill_button = el
                    break
            if pill_button:
                break
        except:
            continue

    if not pill_button:
        print("⚠️ Không tìm thấy pill chọn model ChatGPT")
        return None, None

    current_text = pill_button.text.strip().lower()
    return pill_button, current_text


def select_chatgpt_thinking(driver, level=CHATGPT_SELECT_THINKING):
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
        "tức thì": ["tức thì", "instant", "tuc thi"],
        "instant": ["tức thì", "instant", "tuc thi"],
        "vừa": ["vừa", "medium", "vua"],
        "medium": ["vừa", "medium", "vua"],
        "cao": ["cao", "high"],
        "high": ["cao", "high"],
    }

    target_kws = level_keywords.get(level.strip().lower(), [level.strip().lower()])

    try:
        print(f"🧠 Đang chọn cấp độ thinking ChatGPT: {level}...")

        # Mở dropdown
        pill_button, current_text = _open_chatgpt_pill_dropdown(driver)
        if not pill_button:
            return False

        # Nếu pill đã hiển thị đúng level → không cần click
        if any(kw in current_text for kw in target_kws):
            print(f"✅ Đã ở cấp độ: {current_text}")
            return True

        # Click mở dropdown
        driver.execute_script("arguments[0].click();", pill_button)
        time.sleep(1.5)

        # Tìm menu items
        menu_items = driver.find_elements(
            By.CSS_SELECTOR, '[role="menuitemradio"], [role="menuitem"]'
        )
        target_item = None
        for item in menu_items:
            textContent = item.get_attribute("textContent")
            if textContent:
                text = textContent.strip().lower()
                if any(kw in text for kw in target_kws):
                    target_item = item
                    break

        if target_item:
            ActionChains(driver).move_to_element(target_item).click().perform()
            time.sleep(1)
            print(f"✅ Đã chọn cấp độ thinking: {level}")
            return True
        else:
            print(f"⚠️ Không tìm thấy option '{level}' trong menu")
            # Đóng menu
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return False

    except Exception as e:
        print(f"⚠️ Lỗi khi chọn thinking level ChatGPT: {e}")
        return False


def select_chatgpt_model(driver, model=CHATGPT_SELECT_MODEL):
    """
    Chọn model cụ thể trên ChatGPT (GPT-5.6 Sol, GPT-5.5, o3, v.v.).
    """
    if not model:
        return True

    target_model = model.strip().lower()

    try:
        print(f"📌 Đang chọn model ChatGPT: {model}...")

        # Mở dropdown
        pill_button, _ = _open_chatgpt_pill_dropdown(driver)
        if not pill_button:
            return False

        ActionChains(driver).move_to_element(pill_button).click().perform()
        time.sleep(1.5)

        # Tìm tất cả items
        all_items = driver.find_elements(
            By.CSS_SELECTOR, '[role="menuitem"], [role="menuitemradio"]'
        )

        # Xem có model trực tiếp không
        for item in all_items:
            textContent = item.get_attribute("textContent")
            if textContent and target_model in textContent.strip().lower():
                ActionChains(driver).move_to_element(item).click().perform()
                time.sleep(1)
                print(f"✅ Đã chọn model: {model}")
                return True

        # Bước 1: Tìm submenu trigger
        submenu_trigger = None
        for item in all_items:
            # Lấy element có popup hoặc không phải thinking level
            if (
                item.get_attribute("aria-haspopup")
                or item.get_attribute("role") == "menuitem"
            ):
                textContent = item.get_attribute("textContent")
                if textContent:
                    text = textContent.strip().lower()
                    if text and not any(
                        kw in text
                        for kw in ["tức thì", "vừa", "cao", "instant", "medium", "high"]
                    ):
                        submenu_trigger = item
                        break

        if not submenu_trigger:
            print(f"⚠️ Không tìm thấy submenu trigger hoặc model '{model}'")
            # Click escape or body to close
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return False

        # Click submenu trigger để mở danh sách model
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", submenu_trigger
        )
        time.sleep(0.5)
        ActionChains(driver).move_to_element(submenu_trigger).click().perform()
        time.sleep(1.5)

        # Bước 2: Tìm model trong submenu
        sub_items = driver.find_elements(By.CSS_SELECTOR, '[role="menuitemradio"]')
        target_item = None
        for item in sub_items:
            textContent = item.get_attribute("textContent")
            if textContent:
                text = textContent.strip().lower()
                if target_model in text:
                    target_item = item
                    break

        if target_item:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", target_item
            )
            time.sleep(0.5)
            ActionChains(driver).move_to_element(target_item).click().perform()
            time.sleep(1)
            print(f"✅ Đã chọn model: {model}")
            return True
        else:
            print(f"⚠️ Không tìm thấy model '{model}' trong submenu")
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return False

    except Exception as e:
        print(f"⚠️ Lỗi khi chọn model ChatGPT: {e}")
        return False


def generate_content_with_chatgpt(
    prompt,
    max_retries=3,
    chatgpt_model=CHATGPT_SELECT_MODEL,
    chatgpt_thinking=CHATGPT_SELECT_THINKING,
):
    """
    Gửi prompt đến ChatGPT web và lấy response.
    """
    import pyperclip
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys

    for attempt in range(max_retries):
        try:
            driver = get_chatgpt_driver()
            wait = WebDriverWait(driver, 60)

            driver.get("https://chatgpt.com/")
            time.sleep(3)

            # ── Bước 0: Chọn model và thinking level ──
            if chatgpt_model:
                select_chatgpt_model(driver, chatgpt_model)
            if chatgpt_thinking:
                select_chatgpt_thinking(driver, chatgpt_thinking)

            # ── Bước 1: Tìm ô nhập liệu ──
            input_selectors = [
                "#prompt-textarea",
                'div[contenteditable="true"][id="prompt-textarea"]',
                'div[contenteditable="true"][data-placeholder]',
                'div[role="textbox"][contenteditable="true"]',
                'textarea[id="prompt-textarea"]',
            ]
            input_area = None
            for selector in input_selectors:
                try:
                    input_area = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if input_area:
                        break
                except:
                    continue

            if not input_area:
                raise NoSuchElementException("Không tìm thấy ô nhập liệu ChatGPT!")

            # Focus vào ô nhập
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", input_area
                )
                time.sleep(0.5)
                ActionChains(driver).move_to_element(input_area).click().perform()
            except Exception as e:
                print(f"⚠️ Lỗi focus input: {e}")

            time.sleep(0.5)

            # ── Bước 2: Nhập prompt ──
            # ChatGPT dùng ProseMirror/contenteditable, dùng JS paste
            try:
                pyperclip.copy(prompt)
                time.sleep(0.5)
                # Dùng ActionChains Ctrl+V
                ActionChains(driver).key_down(Keys.CONTROL).send_keys("v").key_up(
                    Keys.CONTROL
                ).perform()
            except Exception as e:
                print(f"⚠️ Fallback paste bằng JS: {e}")
                # Fallback event
                driver.execute_script(
                    """
                    const dt = new DataTransfer();
                    dt.setData('text/plain', arguments[1]);
                    const evt = new ClipboardEvent('paste', {
                        clipboardData: dt, bubbles: true, cancelable: true
                    });
                    arguments[0].dispatchEvent(evt);
                """,
                    input_area,
                    prompt,
                )

            print("⏳ Đang đợi 30s để ChatGPT xử lý file text đính kèm...")
            time.sleep(30)

            # ── Bước 3: Nhấn nút gửi ──
            send_selectors = [
                'button[data-testid="send-button"]',
                'button[aria-label="Send prompt"]',
                'button[aria-label="Gửi tin nhắn"]',
                'button[aria-label="Send message"]',
                'form button[type="submit"]',
                "button.bottom-0",  # Fallback vị trí
            ]
            send_button = None
            for selector in send_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        if el.is_displayed() and el.is_enabled():
                            send_button = el
                            break
                    if send_button:
                        break
                except:
                    continue

            if send_button:
                driver.execute_script("arguments[0].click();", send_button)
            else:
                # Fallback: Ctrl+Enter hoặc Enter
                ActionChains(driver).key_down(Keys.CONTROL).send_keys(
                    Keys.RETURN
                ).key_up(Keys.CONTROL).perform()

            print(
                f"📤 Đã gửi prompt ({len(prompt)} ký tự). Đang chờ ChatGPT response..."
            )
            time.sleep(5)

            # ── Bước 4: Chờ response streaming hoàn tất ──
            max_wait = 1600
            min_response_length = 100
            start_time = time.time()
            last_text = ""
            stable_count = 0

            while time.time() - start_time < max_wait:
                response_selectors = [
                    # ChatGPT response markdown containers
                    'div[data-message-author-role="assistant"] div.markdown',
                    'div[data-message-author-role="assistant"]',
                    "div.agent-turn div.markdown",
                    "div.markdown.prose",
                    'div[class*="message"][class*="assistant"]',
                    "div.group\\/conversation-turn div.markdown",
                ]
                current_text = ""
                for selector in response_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            # Lấy response cuối cùng (mới nhất)
                            current_text = elements[-1].text.strip()
                            if current_text:
                                break
                    except:
                        continue

                current_len = len(current_text) if current_text else 0
                last_len = len(last_text) if last_text else 0

                if current_len > last_len:
                    print(f"\r✍️ Đang nhận: {current_len} ký tự...", end="", flush=True)
                    stable_count = 0

                if "###END###" in current_text:
                    print(
                        "\n✅ Streaming hoàn tất (phát hiện thấy ###END###, chốt ngay!)."
                    )
                    return current_text

                if current_text and current_text == last_text:
                    stable_count += 1

                    if stable_count == 30:
                        print(
                            "\n⚠️ AI đã dừng stream 30s nhưng chưa thấy ###END###. Bạn có thể bấm 'Continue generating' nếu cần. Script sẽ đợi tối đa 30 phút..."
                        )

                    # Nếu chưa thấy ###END###, đợi tối đa 30 phút (1800s)
                    elif stable_count >= 1800 and current_len >= min_response_length:
                        print(
                            "\n✅ Streaming hoàn tất (không thấy END, ngừng do đợi quá 30 phút)."
                        )
                        return current_text
                else:
                    stable_count = 0
                    last_text = current_text

                time.sleep(1)

            if last_text:
                return last_text
            raise TimeoutException("Timeout chờ ChatGPT response")

        except Exception as e:
            print(f"⚠️ Lỗi Selenium lần {attempt + 1}/{max_retries}: {e}")
            close_chatgpt_driver(close_orphans=True)
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise ValueError(f"❌ Thất bại: {e}")


# ==== FILE I/O (YAML — giữ nguyên) ====


def load_yaml(file_path=NOVEL_YAML):
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        if not data:
            raise ValueError("⚠️ File YAML rỗng hoặc sai định dạng!")
        return data


def save_yaml(data, file_path=NOVEL_YAML):
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


def _glossary_source_is_relevant(source, raw_text):
    searchable = (raw_text or "").casefold()
    source_folded = source.casefold()
    if source_folded in searchable:
        return True

    # Một tên ngắn trong raw vẫn kéo theo các mục tên mở rộng liên quan.
    # Ví dụ raw có "김" thì dùng cả "김" và "김철수" trong glossary.
    raw_cjk_terms = re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]+", searchable)
    if any(term in source_folded for term in raw_cjk_terms):
        return True

    # Với chữ Latin, so khớp theo cả từ để tránh một mẩu chữ ngắn khớp nhầm.
    source_words = set(re.findall(r"[^\W_]+", source_folded, flags=re.UNICODE))
    raw_words = set(re.findall(r"[^\W_]+", searchable, flags=re.UNICODE))
    return bool(source_words & raw_words)


def _filter_glossary(glossary_text, raw_text):
    """Keep glossary entries related to words found in the given chapters."""
    matched = []
    for line in str(glossary_text or "").splitlines():
        source, separator, _target = line.partition("=")
        source = source.strip()
        if not separator or not source:
            continue
        if _glossary_source_is_relevant(source, raw_text):
            matched.append(line.strip())
    return "\n".join(matched)


def find_glossary_targets(file_path=CONTEXT_YAML, raw_text="", pronouns_file=None):
    """Return translated glossary names related to the supplied raw chapters."""
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        ctx = yaml.safe_load(f) or {}

    targets = []
    for line in _filter_glossary(ctx.get("glossary", ""), raw_text).splitlines():
        _source, separator, target = line.partition("=")
        target = target.strip()
        if separator and target and target not in targets:
            targets.append(target)

    if pronouns_file:
        memory = load_pronouns(pronouns_file)
        character_names = [
            str(character)
            for data in memory.values()
            for character in data.get("characters", [])
            if character
        ]
        targets = [
            target
            for target in targets
            if any(
                _name_matches_glossary(character, target)
                for character in character_names
            )
        ]
    return targets


def load_context(file_path=CONTEXT_YAML, raw_text=None):
    if not os.path.exists(file_path):
        return ""
    with open(file_path, "r", encoding="utf-8") as f:
        ctx = yaml.safe_load(f) or {}
    parts = []
    if "glossary" in ctx:
        glossary = str(ctx["glossary"] or "")
        if raw_text is not None:
            glossary = _filter_glossary(glossary, raw_text)
        if glossary:
            parts.append("Thuật ngữ:\n" + glossary)
    if "style_notes" in ctx:
        parts.append("Ghi chú văn phong:\n" + ctx["style_notes"])
    if "previous_translations" in ctx:
        parts.append("Bản dịch tham khảo:\n" + "\n".join(ctx["previous_translations"]))
    return "\n\n".join(parts)


# ==== FILE I/O (MD — dùng cho dich_v3_md.py) ====

RAW_DIR = os.path.join(_project_dir, "raw")
TRANSLATED_DIR = os.path.join(_project_dir, "translated")


def _sort_key_md(filename):
    """Sort key cho tên file vx_cy_sz.md."""
    m = re.match(r"v(\d+)_c(\d+)_s(\d+)\.md$", os.path.basename(filename))
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (0, 0, 0)


def scan_md_dir(directory):
    """Trả về list đường dẫn đầy đủ *.md trong directory, sắp xếp theo vx_cy_sz."""
    if not os.path.exists(directory):
        return []
    files = [f for f in os.listdir(directory) if f.endswith(".md")]
    files.sort(key=_sort_key_md)
    return [os.path.join(directory, f) for f in files]


def is_translated(chapter_id, translated_dir=TRANSLATED_DIR):
    """Kiểm tra file vx_cy_sz.md có trong translated_dir và không rỗng."""
    path = os.path.join(translated_dir, f"{chapter_id}.md")
    return os.path.exists(path) and os.path.getsize(path) > 10


def load_md_chapter(filepath):
    """
    Đọc một file .md raw và trả về chapter dict tương thích với pipeline cũ:
      {id, title, content, title_translation, translation, _elements}

    _elements: list theo thứ tự xuất hiện trong file —
      {'type': 'text',  'content': str}
      {'type': 'image', 'content': '![image](...)'}

    content: chỉ chứa các đoạn text (join bằng \\n\\n), KHÔNG có ảnh.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    chapter_id = os.path.splitext(os.path.basename(filepath))[0]
    title = ""
    elements = []

    # Tách thành các block bằng dòng trống
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    title_found = False
    for block in blocks:
        if not title_found and block.startswith("# "):
            title = block[2:].strip()
            title_found = True
            continue  # tiêu đề không thêm vào elements
        if block.startswith("!["):
            elements.append({"type": "image", "content": block})
        else:
            elements.append({"type": "text", "content": block})

    text_content = "\n\n".join(e["content"] for e in elements if e["type"] == "text")

    return {
        "id": chapter_id,
        "title": title,
        "content": text_content,
        "title_translation": "",
        "translation": "",
        "_elements": elements,
    }


def save_translated_md(raw_filepath, translated_dir, title_vi, content_vi):
    """
    Ghi bản dịch Việt ra truyen/translated/vx_cy_sz.md.
    Placeholder ảnh được giữ nguyên đúng vị trí từ file raw.

    Trả về đường dẫn file đã lưu.
    """
    os.makedirs(translated_dir, exist_ok=True)

    # Re-parse raw để lấy structure elements (kể cả ảnh)
    with open(raw_filepath, "r", encoding="utf-8") as f:
        raw = f.read()
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    elements = []
    title_found = False
    for block in blocks:
        if not title_found and block.startswith("# "):
            title_found = True
            continue
        if block.startswith("!["):
            elements.append({"type": "image", "content": block})
        else:
            elements.append({"type": "text", "content": block})

    # Tách bản dịch thành từng đoạn (theo yêu cầu: mỗi dòng cách nhau 1 dòng)
    trans_paras = [p.strip() for p in content_vi.split("\n") if p.strip()]

    # Ghép lại: tiêu đề + elements theo thứ tự
    output_blocks = [f"# {title_vi}", ""]
    trans_idx = 0
    for elem in elements:
        if elem["type"] == "image":
            output_blocks.append(elem["content"])
            output_blocks.append("")
        else:
            if trans_idx < len(trans_paras):
                output_blocks.append(trans_paras[trans_idx])
                output_blocks.append("")
                trans_idx += 1

    # Nếu AI trả về nhiều đoạn hơn số text elements, append phần còn lại
    while trans_idx < len(trans_paras):
        output_blocks.append(trans_paras[trans_idx])
        output_blocks.append("")
        trans_idx += 1

    filename = os.path.basename(raw_filepath)
    out_path = os.path.join(translated_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_blocks))

    return out_path


def get_translated_title(chapter_id, translated_dir=TRANSLATED_DIR):
    """Lấy tiêu đề (dòng # đầu tiên) từ file translated. Trả về '' nếu không có."""
    path = os.path.join(translated_dir, f"{chapter_id}.md")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# "):
                return line[2:]
    return ""


def export_recent_translations_to_txt_md(
    raw_dir=RAW_DIR,
    translated_dir=TRANSLATED_DIR,
    txt_path=NOVEL_TXT,
    n=3,
    target_chapter_id=None,
):
    """
    Xuất n chương dịch gần nhất từ translated MD ra file txt làm ngữ cảnh.
    (Thay thế export_translations_to_txt khi dùng chế độ MD.)

    Nếu target_chapter_id được truyền (VD: 'v1_c100_s1'), chỉ lấy các chương
    đã dịch nằm TRƯỚC chương đó (theo thứ tự sort), rồi lấy n chương cuối.
    → Giúp lấy đúng ngữ cảnh khi dịch lại chương cũ.
    """
    raw_files = scan_md_dir(raw_dir)
    translated_files = scan_md_dir(translated_dir)

    print(f"📊 Tổng số chương raw: {len(raw_files)}")
    print(f"✅ Số chương đã dịch: {len(translated_files)}")

    # Nếu có target_chapter_id, chỉ giữ các chương trước chương đó
    if target_chapter_id and translated_files:
        target_key = _sort_key_md(target_chapter_id + ".md")
        translated_files = [
            f
            for f in translated_files
            if _sort_key_md(os.path.basename(f)) < target_key
        ]

    last_n = translated_files[-n:] if n and len(translated_files) >= n else (translated_files if n else [])
    if not last_n:
        print("⚠️ Không tìm thấy chương nào đã dịch!")
        return

    with open(txt_path, "w", encoding="utf-8") as out:
        for filepath in last_n:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            out.write(content + "\n\n\n\n\n")

    names = [os.path.basename(f) for f in last_n]
    print(
        f"📂 Đã xuất {len(last_n)} chương ngữ cảnh ra: {txt_path} ({', '.join(names)})"
    )


# ==== PHÁT HIỆN KÝ TỰ NƯỚC NGOÀI ====


def has_chinese(text):
    return bool(
        re.search(
            r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
            r"\U00020000-\U0002ebef\U00030000-\U000323af]",
            text,
        )
    )


def has_korean(text):
    return bool(re.search(r"[\uac00-\ud7af]", text))


def has_thai(text):
    return bool(re.search(r"[\u0e00-\u0e7f]", text))


def has_foreign(text):
    """Kiểm tra nếu có chữ Hán, Hàn hoặc Thái còn sót."""
    return has_chinese(text) or has_korean(text) or has_thai(text)


# ==== XƯNG HÔ ====


def load_pronouns(file_path=PRONOUNS_YAML):
    """Tải bộ nhớ xưng hô từ file."""
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_pronouns(data, file_path=PRONOUNS_YAML):
    """Lưu bộ nhớ xưng hô vào file."""
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


def extract_pronouns_from_translation(chapter_id, chapter_number, translation_text):
    """Dùng AI để trích xuất xưng hô từ bản dịch."""
    prompt = f"""Bạn là chuyên gia phân tích xưng hô trong văn bản tiếng Việt.

Hãy đọc đoạn văn bản sau và trích xuất TẤT CẢ các cặp xưng hô giữa các nhân vật:

---
{translation_text}
---

Xuất kết quả dưới dạng JSON với format:
{{
  "character_pairs": [
    {{
      "speaker": "Tên nhân vật A",
      "listener": "Tên nhân vật B",
      "speaker_self": "cách A tự xưng (ta/tôi/anh/em/...)",
      "speaker_to_listener": "cách A gọi B (ngươi/cậu/anh/em/...)",
      "relationship_status": "mô tả ngắn trạng thái mối quan hệ hiện tại",
      "emotional_tone": "giọng điệu cảm xúc (ấm áp/lạnh lùng/quan tâm/xa cách/...)"
    }}
  ]
}}

Lưu ý:
- Chỉ trích xuất các cặp xưng hô RÕ RÀNG xuất hiện trong đoạn văn
- Cả speaker và listener phải là NHÂN VẬT CỤ THỂ có tên hoặc biệt danh xác định
- Không dùng quốc gia, tổ chức, đám đông, công chúng hoặc nhóm người làm nhân vật
- CHÚ Ý ghi nhận thay đổi trong cảm xúc và xưng hô (nếu có)
- Bỏ qua những chỗ chỉ kể chuyện, không có đối thoại
- Nếu không tìm thấy xưng hô nào, trả về {{"character_pairs": []}}
- CHỈ trả về JSON, không giải thích thêm"""

    while True:
        raw_result_text = ""
        try:
            raw_result_text = call_gemini(
                prompt, model="gemini-3.1-flash-lite-preview", temperature=0.9
            ).strip()

            if not raw_result_text:
                print("⚠️ [DEBUG] API trả về dữ liệu rỗng! (bị mất text)")
                return {}

            clean_text = re.sub(r"```json\s*|\s*```", "", raw_result_text).strip()
            data = json.loads(clean_text)

            pronoun_records = {}
            for pair in data.get("character_pairs", []):
                speaker = pair.get("speaker", "").strip()
                listener = pair.get("listener", "").strip()
                if not speaker or not listener:
                    continue
                key = tuple(sorted([speaker, listener]))
                if key not in pronoun_records:
                    pronoun_records[key] = {"characters": list(key), "timeline": []}
                pronoun_records[key]["timeline"].append(
                    {
                        "chapter_id": chapter_id,
                        "chapter_number": chapter_number,
                        "speaker": speaker,
                        "listener": listener,
                        "speaker_self": pair.get("speaker_self", ""),
                        "speaker_to_listener": pair.get("speaker_to_listener", ""),
                        "relationship_status": pair.get("relationship_status", ""),
                        "emotional_tone": pair.get("emotional_tone", ""),
                    }
                )
            return pronoun_records

        except Exception as e:
            err = str(e)
            print(f"⚠️ Lỗi khi trích xuất xưng hô: {err}")
            print(f"🔍 [DEBUG] raw_result_text là: {repr(raw_result_text)}")
            if "Expecting value" in err:
                print("🔔 Bỏ qua lỗi JSON rỗng để chương trình đi tiếp...")
                return {}

            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                switch_api_key()
                print("🔔 Chờ 30s rồi thử lại...")
                time.sleep(30)
            elif any(code in err for code in ["500", "502", "503", "504"]):
                print("🔔 Lỗi 5xx, chờ 10s rồi thử lại...")
                time.sleep(10)
            else:
                print("🔔 Lỗi không mong đợi, chờ 15s rồi thử lại không bỏ cuộc...")
                time.sleep(15)


def update_pronoun_memory(
    chapter_id, chapter_number, translation_text, pronouns_file=PRONOUNS_YAML
):
    """Cập nhật bộ nhớ xưng hô với ưu tiên cho chương gần nhất."""
    memory = load_pronouns(pronouns_file)
    new_pronouns = extract_pronouns_from_translation(
        chapter_id, chapter_number, translation_text
    )
    updated_count = 0
    for key, data in new_pronouns.items():
        key_str = f"{key[0]}---{key[1]}"
        if key_str in memory and memory[key_str].get("locked"):
            print(f"🔒 Giữ quy tắc xưng hô đã khóa: {key_str}")
            continue
        if key_str not in memory:
            memory[key_str] = {"characters": data["characters"], "timeline": []}
        memory[key_str]["timeline"].extend(data["timeline"])
        memory[key_str]["timeline"] = sorted(
            memory[key_str]["timeline"],
            key=lambda x: x.get("chapter_number", 0),
        )[-25:]  # Giữ 25 chương gần nhất
        updated_count += 1
    save_pronouns(memory, pronouns_file)
    if updated_count:
        print(f"✅ Đã cập nhật {updated_count} cặp xưng hô từ chương {chapter_id}")


def _normalized_name_tokens(name):
    normalized = unicodedata.normalize("NFKC", str(name or "")).casefold()
    return re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)


def _name_matches_glossary(character_name, glossary_name):
    character_tokens = _normalized_name_tokens(character_name)
    glossary_tokens = _normalized_name_tokens(glossary_name)
    if not character_tokens or not glossary_tokens:
        return False
    if character_tokens == glossary_tokens:
        return True

    shorter, longer = sorted(
        (character_tokens, glossary_tokens), key=len
    )
    if len(shorter) < 2:
        return False
    width = len(shorter)
    return any(
        longer[index : index + width] == shorter
        for index in range(len(longer) - width + 1)
    )


def _pair_glossary_relevance(data, glossary_names):
    characters = [str(name) for name in data.get("characters", []) if name]
    return sum(
        any(_name_matches_glossary(character, glossary) for glossary in glossary_names)
        for character in characters[:2]
    )


def format_pronoun_context(
    current_chapter_number,
    pronouns_file=PRONOUNS_YAML,
    max_pairs=10,
    glossary_names=None,
):
    """Tạo context xưng hô chi tiết để inject vào prompt dịch."""
    memory = load_pronouns(pronouns_file)
    if not memory:
        return ""

    pair_scores = []
    for key_str, data in memory.items():
        timeline = data.get("timeline", [])
        relevant = [
            t for t in timeline if t.get("chapter_number", 0) < current_chapter_number
        ]
        if relevant:
            latest_chapter = max(t.get("chapter_number", 0) for t in relevant)
            relevance = _pair_glossary_relevance(data, glossary_names or [])
            pair_scores.append(
                (
                    key_str,
                    data,
                    latest_chapter,
                    relevant,
                    bool(data.get("locked")),
                    relevance,
                )
            )

    if glossary_names and any(item[5] for item in pair_scores):
        pair_scores = [item for item in pair_scores if item[5]]
    pair_scores.sort(key=lambda x: (x[5], x[4], x[2]), reverse=True)
    top_pairs = pair_scores[:max_pairs]
    if not top_pairs:
        return ""

    blocks = ["## 📌 Bộ nhớ xưng hô nhân vật (tham khảo để dịch có hồn)\n"]
    blocks.append(
        "💡 Lưu ý: Xưng hô phản ánh CẢM XÚC và MỐI QUAN HỆ. "
        "Hãy điều chỉnh linh hoạt theo diễn biến nội tâm nhân vật trong chương này.\n"
    )

    for key_str, data, latest_chap, relevant, locked, _relevance in top_pairs:
        last = relevant[-1]
        speaker = last["speaker"]
        listener = last["listener"]
        self_p = last.get("speaker_self") or "?"
        to_p = last.get("speaker_to_listener") or "?"
        rel_status = last.get("relationship_status", "")
        emo_tone = last.get("emotional_tone", "")
        last_chap_num = last.get("chapter_number", "?")

        change_note = ""
        if len(relevant) >= 2:
            prev = relevant[-2]
            prev_self = prev.get("speaker_self", "")
            prev_to = prev.get("speaker_to_listener", "")
            if prev_self != self_p or prev_to != to_p:
                change_note = (
                    f"  ↳ Trước đó (chương {prev.get('chapter_number', '?')}): "
                    f"{prev_self}/{prev_to} → "
                    f"đã thay đổi thành {self_p}/{to_p} "
                    f"(có thể do biến chuyển cảm xúc/quan hệ)"
                )

        reverse_info = ""
        for r in reversed(relevant):
            if r.get("speaker") == listener and r.get("listener") == speaker:
                r_self = r.get("speaker_self") or "?"
                r_to = r.get("speaker_to_listener") or "?"
                r_rel = r.get("relationship_status", "")
                r_emo = r.get("emotional_tone", "")
                reverse_info = (
                    f"  ← Chiều ngược ({listener}→{speaker}): "
                    f"tự xưng [{r_self}], gọi [{r_to}]"
                )
                if r_rel:
                    reverse_info += f" | quan hệ: {r_rel}"
                if r_emo:
                    reverse_info += f" | giọng điệu: {r_emo}"
                break

        line = f"▸ **{speaker} → {listener}** (chương {last_chap_num}):"
        if locked:
            line += "\n  🔒 QUY TẮC ĐÃ ĐƯỢC NGƯỜI DÙNG XÁC NHẬN — PHẢI ƯU TIÊN"
        line += f"\n  • Tự xưng: [{self_p}]  |  Gọi đối phương: [{to_p}]"
        if rel_status:
            line += f"\n  • Trạng thái quan hệ: {rel_status}"
        if emo_tone:
            line += f"\n  • Giọng điệu cảm xúc: {emo_tone}"
        if change_note:
            line += f"\n{change_note}"
        if reverse_info:
            line += f"\n{reverse_info}"
        blocks.append(line)

    return "\n\n".join(blocks)


# ==== PIPELINE HẬU DỊCH ====

# ── Helpers upload file qua Files API ──


def _upload_file_part(client, file_path, display_name, mime_type="text/plain"):
    """
    Upload mot file local len Gemini Files API.
    Tra ve types.Part neu thanh cong, None neu loi / file khong ton tai.
    """
    if not os.path.exists(file_path):
        print(f"[UPLOAD] Khong tim thay file: {file_path}")
        return None
    try:
        print(
            f"[UPLOAD] Uploading '{display_name}' ({os.path.getsize(file_path):,} bytes)..."
        )
        uploaded = client.files.upload(
            file=file_path,
            config={"mime_type": mime_type, "display_name": display_name},
        )
        print(f"[UPLOAD] Done: {uploaded.uri}")
        return types.Part(
            file_data=types.FileData(file_uri=uploaded.uri, mime_type=mime_type)
        )
    except Exception as e:
        print(f"[UPLOAD] Loi upload '{display_name}': {e}")
        return None


def _build_pronouns_snapshot(pronouns_file=PRONOUNS_YAML, n_chapters=50):
    """
    Loc pronouns.yaml: chi giu N chapter_number gan nhat.
    Ghi ra file tam va tra ve duong dan file tam do.
    Tra ve None neu memory rong.
    """
    memory = load_pronouns(pronouns_file)
    if not memory:
        return None

    all_chapters = set()
    for data in memory.values():
        for entry in data.get("timeline", []):
            ch = entry.get("chapter_number", 0)
            if ch:
                all_chapters.add(ch)

    if not all_chapters:
        return None

    recent_chapters = set(sorted(all_chapters, reverse=True)[:n_chapters])

    filtered = {}
    for key_str, data in memory.items():
        tl = [
            e
            for e in data.get("timeline", [])
            if e.get("chapter_number", 0) in recent_chapters
        ]
        if tl:
            filtered[key_str] = {
                "characters": data.get("characters", []),
                "timeline": tl,
                "locked": bool(data.get("locked", False)),
            }

    if not filtered:
        return None

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_pronouns_snapshot.yaml", encoding="utf-8", delete=False
    )
    yaml.dump(filtered, tmp, allow_unicode=True, sort_keys=False)
    tmp.close()
    print(
        f"[UPLOAD] Pronouns snapshot: {len(filtered)} cap, {n_chapters} chuong gan nhat -> {tmp.name}"
    )
    return tmp.name


def polish_translation(
    chapter,
    chapter_number,
    context_text="",
    pronoun_context="",
    characters_md_path=CHARACTERS_MD,
    pronouns_file=PRONOUNS_YAML,
):
    """
    Buoc 1 pipeline hau dich: Bien tap trau chuot van phong VA chinh xung ho cung luc.
    Dung gemini-3-flash-preview qua API.

    Upload qua Files API:
      - characters.md          -> ho so nhan vat day du
      - pronouns_snapshot.yaml -> fallback khi khong co context xung ho da loc

    Tra ve (title, content) da trau chuot.
    """
    chapter_id = chapter.get("id", f"chapter_{chapter_number}")
    raw_title = chapter.get("title", "")
    raw_content = chapter.get("content", "")
    title_cur = chapter.get("title_translation", "")
    content_cur = chapter.get("translation", "")

    if not content_cur.strip():
        return title_cur, content_cur

    print(
        f"[POLISH] Bien tap chuong {chapter_number} ({chapter_id}) voi {POLISH_MODEL}..."
    )

    tmp_pronouns = None
    try:
        tmp_pronouns = None
        if not pronoun_context.strip():
            tmp_pronouns = _build_pronouns_snapshot(pronouns_file, n_chapters=50)

        extra_parts = []
        current_upload_key_index = -1
        system_instruction = ""
        pronoun_reference = (
            "- Tra bo nho xung ho lien quan trong prompt de giu cach xung ho nhat quan"
            if pronoun_context
            else "- Tra pronouns_snapshot.yaml de biet cach xung ho da dung o cac chuong truoc"
        )

        prompt = f"""## Thuat ngu / Quy tac dich tham chieu:
{context_text}

## Van ban goc (Tham khao de khong sai nghia):
Tieu de goc: {raw_title}
Noi dung goc:
{raw_content}

## Bo nho xung ho lien quan den nhan vat trong chuong:
{pronoun_context if pronoun_context else "(Khong tim thay cap xung ho lien quan)"}

## Ban dich hien tai (Can bien tap):
Tieu de dich: {title_cur}
Noi dung dich:
{content_cur}

Hay bien tap trau chuot ban dich tieng Viet cho muot ma, cam xuc nhung PHAI dam bao dung nghia voi ban goc. Dong thoi chinh xung ho theo huong dan."""

        while True:
            try:
                # Kiem tra va upload file neu can (khi doi API key hoac lan dau)
                client = get_client()
                global current_key_index
                if current_upload_key_index != current_key_index:
                    extra_parts = []
                    chars_part = _upload_file_part(
                        client, characters_md_path, "characters.md"
                    )
                    if chars_part:
                        extra_parts.append(chars_part)

                    if tmp_pronouns:
                        pron_part = _upload_file_part(
                            client, tmp_pronouns, "pronouns_snapshot.yaml"
                        )
                        if pron_part:
                            extra_parts.append(pron_part)

                    current_upload_key_index = current_key_index

                    # Mo ta file dinh kem cho system prompt
                    attach_lines = []
                    if chars_part:
                        attach_lines.append(
                            "- characters.md (file dinh kem): Ho so day du cac nhan vat — dung de tra gioi tinh, tuoi tac, vai tro, biet danh."
                        )
                    if (
                        tmp_pronouns
                        and extra_parts
                        and len(extra_parts) > (1 if chars_part else 0)
                    ):
                        attach_lines.append(
                            "- pronouns_snapshot.yaml (file dinh kem): Lich su xung ho 50 chuong gan nhat — dung de chinh dai tu xung ho cho dung."
                        )
                    attach_block = (
                        "\n## Tai lieu tham chieu dinh kem:\n"
                        + "\n".join(attach_lines)
                        + "\n"
                        if attach_lines
                        else ""
                    )

                    system_instruction = f"""Ban la bien tap vien dich thuat chuyen nghiep tieu thuyet Han-Viet.
Nhiem vu la BIEN TAP LAI ban dich hien co theo hai muc tieu SONG SONG:
{attach_block}
1. TRAU CHUOT VAN PHONG:
   - Sua cac cau con dich sot ngon ngu goc.
   - Tranh dich sai nghia goc (hay tham khao ban goc de dam bao do nguyen ban)
   - Giu nguyen dau ngoac kep \u201c\u2026\u201d \u2018\u2026\u2019 danh dau hoi thoai
   - KHONG them markdown, KHONG them giai thich
   - Giu toan bo noi dung, KHONG cat bot hay them y moi

2. CHINH XUNG HO:
   - Tra characters.md de biet gioi tinh, tuoi tac, vai tro tung nhan vat
   {pronoun_reference}
   - Trong HOI THOAI: xung ho linh hoat theo cam xuc, khong cung nhac
   - Trong DAN TRUYEN: nhat quan theo bo nho xung ho
   - Uu tien ngu canh hien tai neu xung dot voi bo nho
   - Muc co locked: true la quy tac do nguoi dung xac nhan, PHAI uu tien va khong tu y thay doi

3. BIEN TAP TIEU DE:
   - Chi sua xung ho hoac van phong neu can, KHONG doi nghia
   - Giu dang Title Case (viet hoa chu cai dau moi tu)

Xuat ket qua DUNG THEO dinh dang sau (khong them bat ky text nao ngoai format):
###TITLE###
<tieu de da bien tap>

###CONTENT###
<noi dung da bien tap>
"""

                text = call_gemini(
                    prompt,
                    model=POLISH_MODEL,
                    temperature=0.7,
                    system_instruction=system_instruction,
                    as_chat_parts=True,
                    extra_parts=extra_parts if extra_parts else None,
                ).strip()

                if "###TITLE###" in text and "###CONTENT###" in text:
                    t_start = text.find("###TITLE###") + len("###TITLE###")
                    c_start = text.find("###CONTENT###")
                    title_out = text[t_start:c_start].strip()
                    content_out = text[c_start + len("###CONTENT###") :].strip()
                    print(
                        f"[POLISH] Da bien tap chuong {chapter_number} ({len(content_out)} ky tu)"
                    )
                    log_api_call(
                        chapter_id, "polish", POLISH_MODEL, prompt, text, ok=True
                    )
                    return title_out, content_out
                else:
                    print("[POLISH] Output sai format -- giu nguyen ban dich cu.")
                    log_api_call(
                        chapter_id, "polish", POLISH_MODEL, prompt, text, ok=False
                    )
                    return title_cur, content_cur

            except Exception as e:
                err = str(e)
                print(f"[POLISH] Loi: {err}")
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    switch_api_key()
                    print("[POLISH] Doi key, cho 30s roi thu lai...")
                    time.sleep(30)
                elif "403" in err or "PERMISSION_DENIED" in err:
                    # Co the file bi xoa hoac api key hien tai khong the truy cap file do, doi key luon
                    switch_api_key()
                    print(
                        "[POLISH] Loi quyen truy cap file, doi key, cho 15s roi thu lai..."
                    )
                    time.sleep(15)
                elif any(code in err for code in ["500", "502", "503", "504"]):
                    print("[POLISH] Loi server 5xx, cho 10s roi thu lai...")
                    time.sleep(10)
                else:
                    print("[POLISH] Loi khong xac dinh, cho 15s roi thu lai...")
                    time.sleep(15)

    finally:
        if tmp_pronouns and os.path.exists(tmp_pronouns):
            try:
                os.unlink(tmp_pronouns)
            except Exception:
                pass


def _run_background_review(
    chapter_id,
    chapter_number,
    title,
    content,
    context_text="",
    raw_content="",
    review_token=None,
):
    """
    Bước 4 pipeline (CHẠY NGẦM trong daemon thread):
    Review nhanh chất lượng bản dịch đã trau chuốt, lưu vào review.yaml.
    Dùng gemini-3.1-flash-lite-preview. Không block main flow.
    So sánh bản dịch với raw gốc để phát hiện thiếu/sai nội dung.
    """
    raw_section = ""
    if raw_content:
        raw_section = f"""## Nội dung gốc (raw tiếng Hàn — dùng để đối chiếu):
{raw_content}
"""

    prompt = f"""Bạn là reviewer dịch thuật tiểu thuyết Hàn-Việt. Review bản dịch tiếng Việt dưới đây, **đối chiếu với bản gốc tiếng Hàn**, và trả về JSON:

{{
  "chapter_id": "{chapter_id}",
  "overall_score": <1-10>,
  "issues": [
    {{"type": "thiếu nội dung|dịch sai|xưng hô|phong cách|thuật ngữ|logic",
      "severity": "nặng|trung bình|nhẹ",
      "original_kr": "đoạn gốc tiếng Hàn bị thiếu/dịch sai (nếu có)",
      "original_vi": "đoạn dịch bị lỗi (nếu có)",
      "suggestion": "gợi ý sửa"}}
  ],
  "summary": "nhận xét tổng quan 1-2 câu"
}}

## Yêu cầu kiểm tra:
1. **Thiếu nội dung**: So sánh từng đoạn bản dịch với bản gốc. Nếu có đoạn/câu trong bản gốc mà bản dịch bỏ sót, đánh dấu type = "thiếu nội dung", severity = "nặng".
2. **Dịch sai nội dung**: Nếu ý nghĩa bản dịch khác hẳn so với bản gốc (nhầm nhân vật, đổi ý, sai sự kiện), đánh dấu type = "dịch sai", severity = "nặng".
3. **Xưng hô**: Kiểm tra xưng hô có phù hợp ngữ cảnh và mối quan hệ nhân vật không.
4. **Phong cách & Thuật ngữ**: Kiểm tra theo glossary tham chiếu.

## Thuật ngữ tham chiếu:
{context_text}

{raw_section}## Tiêu đề dịch:
{title}

## Nội dung dịch:
{content}

Chỉ trả về JSON, không giải thích thêm."""

    try:
        text = call_gemini(prompt, model=REVIEW_BG_MODEL, temperature=0.6).strip()
        log_api_call(
            chapter_id, "review", REVIEW_BG_MODEL, prompt, text, ok=True
        )
        # Parse JSON — xử lý cả markdown code block
        clean = re.sub(r"```json\s*|\s*```", "", text).strip()
        start = clean.find("{")
        end = clean.rfind("}")
        review_parsed = {}
        if start != -1 and end != -1:
            try:
                review_parsed = json.loads(clean[start : end + 1])
            except Exception:
                review_parsed = {"raw": clean}
        else:
            review_parsed = {"raw": clean}

        # Lưu vào review.yaml (thread-safe)
        with _review_lock:
            if (
                review_token is not None
                and _latest_review_tokens.get(chapter_id) is not review_token
            ):
                print(
                    f"[REVIEW BG] Bỏ kết quả cũ của chương {chapter_id} "
                    "vì đã có bản hậu xử lý mới hơn."
                )
                return
            existing = {}
            if os.path.exists(REVIEW_YAML):
                try:
                    with open(REVIEW_YAML, "r", encoding="utf-8") as f:
                        existing = yaml.safe_load(f) or {}
                except Exception:
                    existing = {}
            existing[chapter_id] = {
                "chapter_number": chapter_number,
                "score": review_parsed.get("overall_score"),
                "issue_count": len(review_parsed.get("issues", [])),
                "issues": review_parsed.get("issues", []),
                "summary": str(
                    review_parsed.get("summary", review_parsed.get("raw", ""))
                )[:1500],
            }
            os.makedirs(os.path.dirname(os.path.abspath(REVIEW_YAML)), exist_ok=True)
            with open(REVIEW_YAML, "w", encoding="utf-8") as f:
                yaml.dump(existing, f, allow_unicode=True, sort_keys=False)
            if review_token is not None:
                _latest_review_tokens.pop(chapter_id, None)
        print(f"[REVIEW BG] ✅ Đã lưu review chương {chapter_id} vào {REVIEW_YAML}")

    except Exception as e:
        log_api_call(
            chapter_id, "review", REVIEW_BG_MODEL, prompt, str(e), ok=False
        )
        if review_token is not None:
            with _review_lock:
                if _latest_review_tokens.get(chapter_id) is review_token:
                    _latest_review_tokens.pop(chapter_id, None)
        print(f"[REVIEW BG] ⚠️ Lỗi review ngầm chương {chapter_id}: {e}")


def run_post_translation_pipeline(
    chapter,
    chapter_number,
    context_text="",
    pronoun_context="",
    pronouns_file=PRONOUNS_YAML,
):
    """
    Wrapper chạy toàn bộ pipeline hậu dịch.

    Bước 1 (tuần tự): polish_translation()     — gemini-3-flash  — biên tập + xưng hô
    Bước 2 (tuần tự): fix_translation()        — gemini-3-flash  — xét sót ngôn ngữ
    Bước 3 (tuần tự): update_pronoun_memory()  — flash-lite      — cập nhật pronouns.yaml
    Bước 4 (song song): _run_background_review() — flash-lite    — review ngầm → review.yaml

    Trả về (title, content) sau khi bước 1-3 hoàn tất.
    """
    chapter_id = chapter.get("id", f"chapter_{chapter_number}")
    print(f"\n{'─' * 55}")
    print(f"[PIPELINE] Bắt đầu hậu xử lý chương {chapter_number} ({chapter_id})")
    print(f"{'─' * 55}")

    # ── Bước 1: Biên tập trau chuốt + chỉnh xưng hô ──
    print(f"[PIPELINE] Bước 1 — Biên tập trau chuốt...")
    title_polished, content_polished = polish_translation(
        chapter,
        chapter_number,
        context_text,
        pronoun_context,
        pronouns_file=pronouns_file,
    )
    chapter["title_translation"] = title_polished
    chapter["translation"] = content_polished

    # ── Bước 2: Xét sót ngôn ngữ ──
    print(f"[PIPELINE] Bước 2 — Xét sót ngôn ngữ...")
    title_fixed, content_fixed = fix_translation(
        chapter, chapter_number, context_text, pronoun_context
    )
    chapter["title_translation"] = title_fixed
    chapter["translation"] = content_fixed

    # ── Bước 3: Cập nhật bộ nhớ xưng hô ──
    print(f"[PIPELINE] Bước 3 — Cập nhật bộ nhớ xưng hô...")
    update_pronoun_memory(chapter_id, chapter_number, content_fixed, pronouns_file)

    # ── Bước 4: Review ngầm (daemon thread, không block) ──
    print(f"[PIPELINE] Bước 4 — Khởi động review ngầm (gemini-3.1-flash-lite)...")
    raw_content = chapter.get("content", "")
    review_token = object()
    with _review_lock:
        _latest_review_tokens[chapter_id] = review_token
    t = threading.Thread(
        target=_run_background_review,
        args=(
            chapter_id,
            chapter_number,
            title_fixed,
            content_fixed,
            context_text,
            raw_content,
            review_token,
        ),
        daemon=True,
    )
    t.start()

    print(f"[PIPELINE] ✅ Hoàn tất hậu xử lý chương {chapter_number}")
    return title_fixed, content_fixed


# ==== TIỆN ÍCH ====


def save_manual_check_id(chapter_id, file_path="manual_check.yaml"):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f) or []
            except:
                data = []
    else:
        data = []
    if chapter_id not in data:
        data.append(chapter_id)
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)
    print(f"⚠️ Lưu chương '{chapter_id}' vào {file_path} để kiểm tra thủ công.")


def fix_translation(chapter, chapter_number, context_text="", pronoun_context=""):
    """Fix các chương còn sót ký tự nước ngoài bằng API."""
    attempt = 0
    while attempt < FIX_MAX_RETRY:
        title = chapter.get("title_translation", "")
        content = chapter.get("translation", "")
        if not has_foreign(title) and not has_foreign(content):
            return title, content

        print(
            f"⚠️ Phát hiện ký tự nước ngoài (lần {attempt + 1}/{FIX_MAX_RETRY}), đang dịch lại..."
        )
        prompt = f"""Bạn là dịch giả tiểu thuyết.
Bản dịch dưới đây vẫn còn sót chữ Hán/Hàn.
Hãy dịch lại thành bản hoàn chỉnh, giữ nguyên phong cách và nội dung, không được markdown.

{pronoun_context}

Ngữ cảnh:
{context_text}

Tiêu đề dịch hiện tại:
{title}

Nội dung dịch hiện tại:
{content}

⚠️ Xuất kết quả theo định dạng sau:

###TITLE###
<tiêu đề dịch hoàn chỉnh>

###CONTENT###
<nội dung dịch hoàn chỉnh>
"""
        try:
            chapter_id_fix = chapter.get("id", f"chapter_{chapter_number}")
            text = call_gemini(prompt, model=POLISH_MODEL, temperature=0.3).strip()
            if "###TITLE###" in text and "###CONTENT###" in text:
                parts = text.split("###CONTENT###")
                chapter["title_translation"] = (
                    parts[0].replace("###TITLE###", "").strip()
                )
                chapter["translation"] = parts[1].strip()
                log_api_call(chapter_id_fix, "fix", POLISH_MODEL, prompt, text, ok=True)
                attempt += 1
            else:
                print("⚠️ Output sai định dạng, thử lại sau 5s...")
                log_api_call(
                    chapter_id_fix, "fix", POLISH_MODEL, prompt, text, ok=False
                )
                attempt += 1
                time.sleep(5)
        except Exception as e:
            err = str(e)
            if "429" in err:
                switch_api_key()
                print("🔔 Chờ 30s rồi thử lại...")
                time.sleep(30)
            elif any(code in err for code in ["500", "502", "503", "504"]):
                print(f"⚠️ Lỗi 5xx từ server: {e}. Chờ 10s...")
                time.sleep(10)
            else:
                print(f"⚠️ Lỗi khi dịch lại: {e}")
                attempt += 1
                time.sleep(10)

    print(
        f"❌ Chương '{chapter.get('title', '')}' đã thử {FIX_MAX_RETRY} lần, cần kiểm tra thủ công."
    )
    save_manual_check_id(chapter.get("id", chapter.get("title", "UnknownID")))
    return chapter.get("title_translation", ""), chapter.get("translation", "")


def export_translations_to_txt(yaml_path=NOVEL_YAML, txt_path=NOVEL_TXT):
    """Xuất 5 chương dịch gần nhất ra file txt làm ngữ cảnh."""
    data = load_yaml(yaml_path)
    chapters = data.get("chapters", []) if isinstance(data, dict) else data
    translated_chapters = [ch for ch in chapters if ch.get("translation")]

    print(f"📊 Tổng số chương: {len(chapters)}")
    print(f"✅ Số chương đã dịch: {len(translated_chapters)}")

    last_5 = translated_chapters[-7:]
    if not last_5:
        print("⚠️ Không tìm thấy chương nào đã dịch!")
        return

    with open(txt_path, "w", encoding="utf-8") as f:
        for ch in last_5:
            title = ch.get("title_translation", "").strip()
            trans = ch.get("translation", "").strip()
            f.write(f"{title}\n")
            f.write(trans + "\n\n\n\n\n")
    print(f"📂 Đã xuất {len(last_5)} chương dịch cuối cùng ra: {txt_path}")


def manual_translate_via_file(prompt_text):
    """Fallback: Ghi prompt ra file prompt_to_translate.txt, đợi người dùng dán bản dịch vào file mới."""
    prompt_file = "prompt_to_translate.txt"
    file_path = "new_trans.txt"
    try:
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt_text)
        print(
            f"\n[INFO] Đã GHI prompt vào file '{prompt_file}'! ({len(prompt_text)} ký tự)"
        )
    except Exception as e:
        print(f"[ERROR] Không thể ghi prompt ra file: {e}")

    if web_mode():
        translated_content = str(option("manual_result", "")).strip()
        if not translated_content:
            raise ValueError(
                "Chưa có bản dịch thủ công. Hãy nhập kết quả AI trong biểu mẫu web."
            )
        return translated_content

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("")
    print(f"[ACTION] Mở '{prompt_file}' để xem nội dung nội dung prompt.")
    print(f"[ACTION] Hãy dán bản dịch vào file '{file_path}' và Lưu lại (Save).")

    while True:
        input(
            f" >> Sau khi đã lưu file '{file_path}', hãy nhấn ENTER tại đây để tiếp tục... "
        )
        if os.path.getsize(file_path) > 0:
            break
        print(
            f"[WARNING] File '{file_path}' vẫn đang trống! Vui lòng dán nội dung và lưu lại."
        )

    with open(file_path, "r", encoding="utf-8") as f:
        translated_content = f.read()
    print("[SUCCESS] Đã đọc bản dịch xong. Tiếp tục xử lý...")
    return translated_content
