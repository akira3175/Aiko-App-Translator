"""Send prompts through ChatGPT Web and wait for the matching response."""

import time

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from cores.chatgpt.web_controls import select_chatgpt_model, select_chatgpt_thinking
from cores.chatgpt.web_response import (
    find_new_response as _find_new_chatgpt_response,
    ready_send_button as _ready_chatgpt_send_button,
    response_text as _chatgpt_response_text,
    snapshot_conversation as _snapshot_chatgpt_conversation,
)
from cores.json_output import parse_complete_json_object


END_MARKER_SETTLE_SECONDS = 3


def _is_known_structured_response(text):
    parsed = parse_complete_json_object(text)
    if parsed is None:
        return False
    if isinstance(parsed.get("character_pairs"), list):
        return True
    return isinstance(parsed.get("overall_score"), (int, float)) and isinstance(
        parsed.get("issues"), list
    )


def _settle_end_marker_response(
    driver, response_turn, response_token, old_assistant_count, current_text
):
    """Give the rendered response time to finish updating after its end marker."""
    time.sleep(END_MARKER_SETTLE_SECONDS)
    try:
        refreshed = _chatgpt_response_text(response_turn)
    except StaleElementReferenceException:
        response_turn = _find_new_chatgpt_response(
            driver, response_token, old_assistant_count
        )
        refreshed = (
            _chatgpt_response_text(response_turn) if response_turn is not None else ""
        )
    return refreshed if len(refreshed or "") >= len(current_text) else current_text


def generate_content(
    prompt,
    *,
    get_driver,
    close_driver,
    link,
    default_model,
    default_thinking,
    max_retries=3,
    chatgpt_model=None,
    chatgpt_thinking=None,
    chat_url=None,
):
    """
    Gửi prompt đến ChatGPT web và lấy response.
    """
    import pyperclip
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys

    if chatgpt_model is None:
        chatgpt_model = default_model
    if chatgpt_thinking is None:
        chatgpt_thinking = default_thinking

    for attempt in range(max_retries):
        try:
            driver = get_driver()
            wait = WebDriverWait(driver, 60)

            driver.get(chat_url or link)
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

            print("⏳ Đang chờ ChatGPT nạp xong prompt...")
            send_button = WebDriverWait(driver, 300, poll_frequency=0.25).until(
                _ready_chatgpt_send_button
            )
            print("✅ Prompt đã sẵn sàng, nút Gửi đã được bật.")

            # Ghi dấu toàn bộ hội thoại cũ ngay trước lúc gửi. Không được lấy
            # response cuối trang vì nó có thể là bản dịch của lần chạy trước.
            response_token = f"novel-{time.time_ns()}"
            old_assistant_count = _snapshot_chatgpt_conversation(
                driver, response_token
            )

            # ── Bước 3: Nhấn nút gửi ──
            driver.execute_script("arguments[0].click();", send_button)

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
            response_turn = None

            while time.time() - start_time < max_wait:
                current_text = ""
                try:
                    if response_turn is None:
                        response_turn = _find_new_chatgpt_response(
                            driver, response_token, old_assistant_count
                        )
                    if response_turn is not None:
                        current_text = _chatgpt_response_text(response_turn)
                except StaleElementReferenceException:
                    # React thay node lúc stream: tìm lại đúng turn sau prompt mới.
                    response_turn = None
                    continue

                current_len = len(current_text) if current_text else 0
                last_len = len(last_text) if last_text else 0

                if current_len > last_len:
                    print(f"\r✍️ Đang nhận: {current_len} ký tự...", end="", flush=True)
                    stable_count = 0

                if "###END###" in current_text:
                    print(
                        "\n⏳ Đã thấy ###END###, đợi thêm 3 giây để response ổn định..."
                    )
                    final_text = _settle_end_marker_response(
                        driver,
                        response_turn,
                        response_token,
                        old_assistant_count,
                        current_text,
                    )
                    print("✅ Streaming hoàn tất, đã đọc lại response cuối.")
                    return final_text

                if _is_known_structured_response(current_text):
                    print(
                        "\n⏳ Đã nhận đủ JSON, đợi thêm 3 giây để response ổn định..."
                    )
                    final_text = _settle_end_marker_response(
                        driver,
                        response_turn,
                        response_token,
                        old_assistant_count,
                        current_text,
                    )
                    if _is_known_structured_response(final_text):
                        print("✅ Streaming hoàn tất, JSON hợp lệ.")
                        return final_text

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
            close_driver(close_orphans=True)
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise ValueError(f"❌ Thất bại: {e}")
