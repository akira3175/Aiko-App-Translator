"""Send prompts through Gemini Web and wait for the matching response."""

import time

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from cores.gemini.web_controls import (
    select_flash_model,
    select_pro_model,
    select_thinking_level,
    select_thinking_model,
)
from cores.gemini.web_response import (
    copy_response_text,
    find_new_response as _find_new_gemini_response,
    response_text as _gemini_response_text,
    snapshot_conversation as _snapshot_gemini_conversation,
)
from cores.json_output import parse_complete_json_object
from cores.config.runtime import option


# Prompt dài hơn ngưỡng này (ký tự) sẽ được gửi dưới dạng file .md đính kèm.
# Đặt gemini_web_upload_threshold = 0 để tắt tính năng upload.
DEFAULT_UPLOAD_THRESHOLD = 15000
UPLOAD_FILE_NAME = "prompt.md"
UPLOAD_INSTRUCTION = (
    "Đọc toàn bộ file prompt.md đính kèm và thực hiện CHÍNH XÁC mọi yêu cầu "
    "trong đó. Chỉ xuất kết quả đúng định dạng file yêu cầu, không giải thích thêm."
)
ATTACHMENT_SELECTORS = (
    "uploader-file-preview",
    "uploader-file-preview-container",
    '[data-test-id="file-preview"]',
    ".file-preview-container",
    ".attachment-preview-wrapper",
    "file-preview",
)
PASTE_FILE_SCRIPT = r"""
const inputArea = arguments[0];
const content = arguments[1];
const name = arguments[2];
inputArea.focus();
const file = new File([content], name, {type: 'text/markdown'});
const dt = new DataTransfer();
dt.items.add(file);
const evt = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
inputArea.dispatchEvent(evt);
return true;
"""


def _upload_instruction():
    value = str(option("gemini_web_upload_instruction", "") or "").strip()
    return value or UPLOAD_INSTRUCTION


def _upload_threshold():
    try:
        return int(option("gemini_web_upload_threshold", DEFAULT_UPLOAD_THRESHOLD) or 0)
    except (TypeError, ValueError):
        return DEFAULT_UPLOAD_THRESHOLD


def _attachment_count(driver):
    total = 0
    for selector in ATTACHMENT_SELECTORS:
        try:
            total = max(total, len(driver.find_elements(By.CSS_SELECTOR, selector)))
        except Exception:
            continue
    return total


def _upload_prompt_file(driver, input_area, content, timeout=60):
    """Dán prompt như một file .md vào ô chat. Trả về True nếu thấy file đã gắn."""
    before = _attachment_count(driver)
    driver.execute_script(PASTE_FILE_SCRIPT, input_area, content, UPLOAD_FILE_NAME)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _attachment_count(driver) > before:
            # Đợi thêm để Gemini tải file lên server xong.
            time.sleep(3)
            return True
        time.sleep(0.5)
    return False


def _insert_text(driver, input_area, text):
    driver.execute_script(
        """
        const inputArea = arguments[0];
        const text = arguments[1];
        inputArea.focus();
        if (!document.execCommand('insertText', false, text)) {
            const dt = new DataTransfer();
            dt.setData('text/plain', text);
            const evt = new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true
            });
            inputArea.dispatchEvent(evt);
        }
        """,
        input_area,
        text,
    )


def _is_known_structured_response(text):
    parsed = parse_complete_json_object(text)
    if parsed is None:
        return False
    if isinstance(parsed.get("character_pairs"), list):
        return True
    return isinstance(parsed.get("overall_score"), (int, float)) and isinstance(
        parsed.get("issues"), list
    )


def _has_end_marker(text):
    return "###END###" in text or "###CHAR_END###" in text


def normalize_web_model(value):
    model = str(value or "").strip().lower()
    aliases = {
        "fast": "flash",
        "gemini flash": "flash",
        "gemini 3 flash": "flash",
        "3 flash": "flash",
        "3.8 flash": "flash",
        "3.1 pro": "pro",
        "argon": "thinking",
        "4 argon": "thinking",
        "gemini argon": "thinking",
    }
    return aliases.get(model, model)


def generate_content(
    prompt,
    *,
    get_driver,
    link,
    default_thinking,
    max_retries=3,
    web_model="pro",
    thinking_level=None,
):
    """
    Gửi prompt đến Gemini web và lấy response.

    Args:
        prompt      : Nội dung gửi đi
        max_retries : Số lần thử lại
        web_model   : Chế độ model trên web
                      WEB_MODEL_FREE     — không đổi model
                      "pro"      — tự động chọn Pro
                      "thinking" — tự động chọn Thinking (mặc định)
    """
    for attempt in range(max_retries):
        try:
            driver = get_driver()
            wait = WebDriverWait(driver, 60)

            driver.get(link)
            time.sleep(3)

            # Bước 1: Chọn model
            selected_model = normalize_web_model(web_model)
            if selected_model == "thinking":
                select_thinking_model(driver)
            elif selected_model == "pro":
                select_pro_model(driver)
            elif selected_model == "flash":
                select_flash_model(driver)
            else:
                print(
                    f"⚠️ Model Gemini Web không hỗ trợ: {web_model!r}; "
                    "giữ nguyên model hiện tại"
                )

            # Bước 2: Chọn cấp độ tư duy (nếu không phải 'off')
            effective_thinking = default_thinking if thinking_level is None else str(thinking_level).strip().lower()
            if effective_thinking and effective_thinking != "off":
                select_thinking_level(driver, effective_thinking)

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
            threshold = _upload_threshold()
            uploaded = False
            if threshold and len(prompt) > threshold:
                print(f"📎 Prompt dài {len(prompt)} ký tự → gửi dưới dạng {UPLOAD_FILE_NAME}...")
                try:
                    uploaded = _upload_prompt_file(driver, input_area, prompt)
                except Exception as e:
                    print(f"⚠️ Upload file lỗi: {e}")
                if not uploaded:
                    print("⚠️ Không xác nhận được file đã gắn, quay về dán text.")
            # Thay vì dùng pyperclip và phím tắt dán (chiếm OS clipboard), ta dùng js execCommand
            _insert_text(driver, input_area, _upload_instruction() if uploaded else prompt)
            time.sleep(1)

            # Đánh dấu lịch sử ngay trước khi gửi để không nhận lại câu trả lời
            # cuối của lần dịch trước trong cùng cuộc chat Gemini.
            response_token = f"novel-{time.time_ns()}"
            old_response_count = _snapshot_gemini_conversation(
                driver, response_token
            )

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

            max_wait = 1800
            min_response_length = 100
            start_time = time.time()
            last_text = ""
            stable_count = 0
            response_root = None
            require_end = "###END###" in prompt or "###CHAR_END###" in prompt

            while time.time() - start_time < max_wait:
                current_text = ""
                try:
                    if response_root is None:
                        response_root = _find_new_gemini_response(
                            driver, response_token, old_response_count
                        )
                    if response_root is not None:
                        current_text = _gemini_response_text(response_root)
                except StaleElementReferenceException:
                    response_root = None
                    continue

                current_len = len(current_text) if current_text else 0
                last_len = len(last_text) if last_text else 0

                if current_len > last_len:
                    print(f"\r✍️ Đang nhận: {current_len} ký tự...", end="", flush=True)
                    stable_count = 0

                # 1. Nếu đã thấy marker kết thúc, đợi ổn định 3s rồi trả kết quả
                if _has_end_marker(current_text):
                    print(
                        "\n⏳ Đã thấy ###END###, đợi thêm 3 giây để response ổn định..."
                    )
                    time.sleep(3)
                    try:
                        if response_root is not None:
                            current_text = _gemini_response_text(response_root)
                    except StaleElementReferenceException:
                        response_root = _find_new_gemini_response(
                            driver, response_token, old_response_count
                        )
                        if response_root is not None:
                            current_text = _gemini_response_text(response_root)
                    final_text = copy_response_text(driver)
                    result = final_text if final_text else current_text
                    print("✅ Streaming hoàn tất.")
                    return result

                # 2. Nếu prompt không yêu cầu ###END### nhưng đã có JSON hợp lệ
                if not require_end and _is_known_structured_response(current_text):
                    print(
                        "\n⏳ Đã nhận đủ JSON, đợi thêm 3 giây để response ổn định..."
                    )
                    time.sleep(3)
                    try:
                        if response_root is not None:
                            current_text = _gemini_response_text(response_root)
                    except StaleElementReferenceException:
                        response_root = _find_new_gemini_response(
                            driver, response_token, old_response_count
                        )
                        if response_root is not None:
                            current_text = _gemini_response_text(response_root)
                    if _is_known_structured_response(current_text):
                        final_text = copy_response_text(driver)
                        result = final_text if final_text else current_text
                        print("✅ Streaming hoàn tất, JSON hợp lệ.")
                        return result

                # 3. Quản lý trạng thái dừng khi text không đổi
                if current_text and current_text == last_text:
                    stable_count += 1
                    if require_end:
                        if stable_count % 30 == 0:
                            print(
                                f"\n⏳ Đang đợi ###END### (đã nhận {current_len} ký tự, tạm dừng {stable_count}s)...",
                                flush=True,
                            )
                        if stable_count >= 1800 and current_len >= min_response_length:
                            print(
                                "\n⚠️ Đã đợi 30 phút nhưng không thấy ###END###, kết thúc streaming."
                            )
                            final_text = copy_response_text(driver)
                            return final_text if final_text else current_text
                    else:
                        if stable_count >= 20 and current_len >= min_response_length:
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
