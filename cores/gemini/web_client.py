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


def normalize_web_model(value):
    model = str(value or "").strip().lower()
    aliases = {
        "fast": "flash",
        "gemini flash": "flash",
        "gemini 3 flash": "flash",
        "3 flash": "flash",
    }
    return aliases.get(model, model)
from cores.gemini.web_response import (
    copy_response_text,
    find_new_response as _find_new_gemini_response,
    response_text as _gemini_response_text,
    snapshot_conversation as _snapshot_gemini_conversation,
)


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

            max_wait = 1600
            min_response_length = 100
            start_time = time.time()
            last_text = ""
            stable_count = 0
            response_root = None

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
