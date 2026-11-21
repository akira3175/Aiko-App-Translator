"""Send prompts through Gemini Web and wait for the matching response."""

import time
from cores.web_errors import RetryableWebError, WebQuotaError, WebTaskStopped, WebSubmissionUncertain, check_quota, retryable_transport

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
    select_custom_model,
    select_flash_lite_model,
    select_flash_model,
    select_pro_model,
    select_task_mode,
    select_thinking_level,
    select_thinking_model,
)
from cores.gemini.web_response import (
    copy_response_text,
    find_new_response as _find_new_gemini_response,
    response_text as _gemini_response_text,
    response_finished as _gemini_response_finished,
    submission_state as _gemini_submission_state,
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


def _task_mode_enabled(task_mode=None):
    if task_mode is not None:
        if isinstance(task_mode, bool):
            return task_mode
        return str(task_mode).strip().lower() in {"on", "true", "1", "task", "spark"}
    value = str(option("gemini_web_task_mode", "off") or "off").strip().lower()
    return value in {"on", "true", "1", "task", "spark"}


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
        check_quota(driver)
        if _attachment_count(driver) > before:
            # Đợi thêm để Gemini tải file lên server xong.
            time.sleep(3)
            check_quota(driver)
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


def _wait_for_submission(driver, token, old_response_count, timeout=30, processing_timeout=90):
    started = time.monotonic()
    seen_pending = False
    while True:
        check_quota(driver)
        state = _gemini_submission_state(driver, token, old_response_count)
        if state == 'processing':
            return
        if state == 'pending' and not seen_pending:
            print(f"[INFO] Đã thấy lượt tin nhắn; chờ Gemini bắt đầu xử lý (tối đa {processing_timeout} giây từ lúc gửi).")
            seen_pending = True
        elapsed = time.monotonic() - started
        if elapsed >= (processing_timeout if seen_pending else timeout):
            state = _gemini_submission_state(driver, token, old_response_count)
            if state == 'processing':
                return
            if state == 'pending' and not seen_pending:
                seen_pending = True
                continue
            if seen_pending:
                raise WebSubmissionUncertain(
                    f"Đã thấy tin nhắn nhưng chưa xác nhận Gemini xử lý sau {processing_timeout} giây. "
                    "Dừng để tránh gửi trùng; hãy kiểm tra lượt tin nhắn trong Chrome trước khi chạy lại."
                )
            raise RetryableWebError(
                f"Chưa xác nhận Gemini nhận prompt sau {timeout} giây; thử gửi lại đầy đủ prompt/file."
            )
        time.sleep(0.5)


def _validate_answer(text, prompt):
    if '###TITLE###' in prompt and '###CONTENT###' in prompt:
        from cores.stages.outputs import parse_title_content

        title = text.find('###TITLE###')
        content = text.find('###CONTENT###')
        end = text.find('###END###')
        if not (0 <= title < content < end):
            raise ValueError('Gemini trả sai thứ tự hoặc thiếu TITLE/CONTENT/END; thử lại bước hiện tại.')
        parse_title_content(text, 'Gemini Web')
    return text


def normalize_web_model(value):
    model = str(value or "").strip().lower()
    aliases = {
        "fast": "flash",
        "gemini flash": "flash",
        "gemini 3 flash": "flash",
        "3 flash": "flash",
        "3.8 flash": "flash",
        "trợ giúp toàn diện": "flash",
        "flash-lite": "flash-lite",
        "3.5 flash-lite": "flash-lite",
        "lite": "flash-lite",
        "quick answers": "flash-lite",
        "3.1 pro": "pro",
        "detailed research": "pro",
        "argon": "thinking",
        "4 argon": "thinking",
        "gemini argon": "thinking",
        "code & analysis": "thinking",
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
    task_mode=None,
    force_upload=False,
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
            check_quota(driver)

            # Selectors theo cấu trúc HTML mới (test.html):
            # <rich-textarea> → <div class="ql-editor ... new-input-ui" contenteditable="true"
            #   aria-label="Nhập câu lệnh cho Gemini" data-placeholder="Hỏi Gemini" | "Mô tả tác vụ">
            input_selectors = [
                '.ql-editor.new-input-ui[contenteditable="true"]',  # Giao diện mới
                'rich-textarea div.ql-editor[contenteditable="true"]',
                'div.ql-editor[contenteditable="true"]',
                'div[contenteditable="true"][aria-label*="Gemini"]',
                'div[role="textbox"][contenteditable="true"]',
                'div[contenteditable="true"]',  # Fallback rộng nhất
            ]

            def _locate_input_area(timeout_sec=60):
                local_wait = WebDriverWait(driver, timeout_sec)
                for selector in input_selectors:
                    try:
                        def input_or_quota(active_driver):
                            check_quota(active_driver)
                            return EC.presence_of_element_located((By.CSS_SELECTOR, selector))(active_driver)

                        found = local_wait.until(input_or_quota)
                        if found:
                            return found
                    except WebQuotaError:
                        raise
                    except Exception:
                        continue
                return None

            # Đợi giao diện Gemini Web tải xong trước khi thao tác chọn chế độ/model
            if not _locate_input_area(timeout_sec=60):
                raise NoSuchElementException("Không tìm thấy ô nhập liệu!")

            # Bước 0: Chọn chế độ Nhiệm vụ / Cuộc trò chuyện (nếu có trên giao diện)
            select_task_mode(driver, _task_mode_enabled(task_mode))

            # Bước 1: Chọn model
            selected_model = normalize_web_model(web_model)
            if selected_model == "thinking":
                select_thinking_model(driver)
            elif selected_model == "pro":
                select_pro_model(driver)
            elif selected_model == "flash":
                select_flash_model(driver)
            elif selected_model == "flash-lite":
                select_flash_lite_model(driver)
            elif selected_model in {"", "free", "default", "auto"}:
                pass
            elif not select_custom_model(driver, web_model):
                print(
                    f"⚠️ Model Gemini Web không tìm thấy: {web_model!r}; "
                    "giữ nguyên model hiện tại"
                )

            # Bước 2: Chọn cấp độ tư duy (nếu không phải 'off')
            effective_thinking = default_thinking if thinking_level is None else str(thinking_level).strip().lower()
            if effective_thinking and effective_thinking != "off":
                select_thinking_level(driver, effective_thinking)

            # Lấy lại ô nhập liệu sau khi đổi chế độ/model để tránh StaleElementReferenceException
            input_area = _locate_input_area(timeout_sec=15)
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
            if force_upload or (threshold and len(prompt) > threshold):
                print(f"📎 Prompt dài {len(prompt)} ký tự → gửi dưới dạng {UPLOAD_FILE_NAME}...")
                try:
                    uploaded = _upload_prompt_file(driver, input_area, prompt)
                except WebQuotaError:
                    raise
                except Exception as e:
                    print(f"⚠️ Upload file lỗi: {e}")
                if not uploaded:
                    raise RetryableWebError(
                        "Không đính kèm được toàn bộ file prompt.md; chưa gửi yêu cầu cho Gemini."
                    )
            # Thay vì dùng pyperclip và phím tắt dán (chiếm OS clipboard), ta dùng js execCommand
            _insert_text(driver, input_area, _upload_instruction() if uploaded else prompt)
            time.sleep(1)
            check_quota(driver)

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

            print("[INFO] Đang xác nhận Gemini đã nhận prompt (tối đa 30 giây)...")
            _wait_for_submission(driver, response_token, old_response_count)
            print(f"📤 Đã xác nhận Gemini xử lý prompt ({len(prompt)} ký tự). Đang chờ response...")
            time.sleep(5)

            max_wait = 1800
            min_response_length = 100
            start_time = time.monotonic()
            last_text = ""
            stable_count = 0
            response_root = None
            require_end = "###END###" in prompt or "###CHAR_END###" in prompt

            while time.monotonic() - start_time < max_wait:
                check_quota(driver)
                current_text = ""
                try:
                    latest_root = _find_new_gemini_response(
                        driver, response_token, old_response_count
                    )
                    if latest_root is not None:
                        response_root = latest_root
                    if response_root is not None:
                        current_text = _gemini_response_text(response_root)
                    finished = _gemini_response_finished(response_root)
                except StaleElementReferenceException:
                    response_root = None
                    continue

                if not finished:
                    last_text = current_text
                    time.sleep(1)
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
                    if not _gemini_response_finished(response_root):
                        last_text = current_text
                        continue
                    final_text = copy_response_text(
                        driver, response_root, token=response_token
                    )
                    result = (
                        final_text
                        if final_text and _has_end_marker(final_text)
                        else current_text
                    )
                    if not _has_end_marker(result):
                        raise ValueError("Gemini mất dấu kết thúc sau khi đọc lại phản hồi.")
                    print("✅ Streaming hoàn tất.")
                    return _validate_answer(result, prompt)

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
                    if _gemini_response_finished(response_root) and _is_known_structured_response(current_text):
                        final_text = copy_response_text(
                            driver, response_root, token=response_token
                        )
                        result = (
                            final_text
                            if final_text and _is_known_structured_response(final_text)
                            else current_text
                        )
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
                    else:
                        if stable_count >= 20 and current_len >= min_response_length:
                            print("\n✅ Streaming hoàn tất.")
                            final_text = copy_response_text(
                                driver, response_root, token=response_token
                            )
                            return final_text if final_text else current_text
                else:
                    stable_count = 0
                    last_text = current_text

                time.sleep(1)

            if require_end:
                if last_text:
                    raise ValueError("Gemini trả về nội dung thiếu ###END### hoặc ###CHAR_END###.")
                raise TimeoutException("Gemini chưa hoàn tất sau 30 phút: thiếu ###END### hoặc ###CHAR_END###.")
            raise TimeoutException("Timeout chờ response")

        except Exception as e:
            if isinstance(e, (WebQuotaError, WebTaskStopped)):
                raise
            print(f"⚠️ Lỗi Selenium lần {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                print(f"[THỬ LẠI] Tải lại trang và gửi lại đầy đủ prompt (lần {attempt + 2}/{max_retries}).")
                time.sleep(5)
                try:
                    driver.refresh()
                except:
                    pass
            else:
                if retryable_transport(e):
                    raise RetryableWebError(str(e)) from e
                raise ValueError(f"❌ Thất bại: {e}")
