"""Send prompts through ChatGPT Web and wait for the matching response."""

import time
from pathlib import Path

from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from cores.chatgpt.web_controls import (
    select_chatgpt_mode,
    select_chatgpt_model,
    select_chatgpt_thinking,
)
from cores.config.runtime import option
from cores.chatgpt.web_response import (
    copy_response_markdown,
    find_new_response as _find_new_chatgpt_response,
    ready_send_button as _ready_chatgpt_send_button,
    response_text as _chatgpt_response_text,
    snapshot_conversation as _snapshot_chatgpt_conversation,
)
from cores.json_output import parse_complete_json_object


END_MARKER_SETTLE_SECONDS = 3
RESPONSE_TIMEOUT_SECONDS = 1800
INCOMPLETE_RESPONSE_DIR = Path(__file__).resolve().parents[2] / ".runtime" / "chatgpt-incomplete"


def _save_incomplete_response(text, attempt):
    """Keep diagnostic text separate from accepted translation output."""
    if not text:
        return
    try:
        INCOMPLETE_RESPONSE_DIR.mkdir(parents=True, exist_ok=True)
        path = INCOMPLETE_RESPONSE_DIR / f"{time.time_ns()}-attempt-{attempt}.txt"
        path.write_text(text, encoding="utf-8")
        print(f"[ChatGPT] Phản hồi chưa hoàn tất đã lưu tại: {path}")
    except OSError as error:
        print(f"[ChatGPT] Không lưu được phản hồi dang dở: {error}")

INPUT_SELECTORS = (
    '#pending-home-input', '#prompt-textarea',
    'div.ProseMirror[contenteditable="true"][data-composer-markdown]',
    'div[contenteditable="true"][data-placeholder]',
    'div[role="textbox"][contenteditable="true"]',
)


class ChatGPTComposerError(ValueError):
    """Stop before sending when the requested configuration cannot be verified."""


def _ready_input(driver):
    for selector in INPUT_SELECTORS:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            try:
                if element.is_displayed() and element.is_enabled():
                    return element
            except StaleElementReferenceException:
                continue
    return False


def _paste_prompt(driver, input_area, prompt, clipboard):
    from selenium.webdriver.common.keys import Keys

    original = clipboard.paste()
    try:
        input_area.click()
        input_area.send_keys(Keys.CONTROL, 'a')
        clipboard.copy(prompt)
        input_area.send_keys(Keys.CONTROL, 'v')
    finally:
        if clipboard.paste() == prompt:
            clipboard.copy(original)


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
    return copy_response_markdown(
        driver, response_token, old_assistant_count,
        require_end='###END###' in current_text or '###END###' in refreshed,
    )


def _resolve_chatgpt_mode(chatgpt_mode=None):
    if chatgpt_mode is not None:
        if isinstance(chatgpt_mode, bool):
            return "work" if chatgpt_mode else "chat"
        value = str(chatgpt_mode).strip().lower()
    else:
        value = str(option("chatgpt_mode", "chat") or "chat").strip().lower()
    if value in {"work", "cong viec", "công việc", "on", "true", "1", "task", "nhiem vu", "nhiệm vụ"}:
        return "work"
    return "chat"


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
    chatgpt_mode=None,
    chat_url=None,
):
    """
    Gửi prompt đến ChatGPT web và lấy response.
    """
    import pyperclip

    if chatgpt_model is None:
        chatgpt_model = default_model
    if chatgpt_thinking is None:
        chatgpt_thinking = default_thinking
    effective_mode = _resolve_chatgpt_mode(chatgpt_mode)

    for attempt in range(max_retries):
        partial_text = ""
        try:
            driver = get_driver()
            wait = WebDriverWait(driver, 60)

            driver.get(chat_url or link)
            time.sleep(3)

            input_area = wait.until(_ready_input)
            if not select_chatgpt_mode(driver, effective_mode):
                print(
                    f"⚠️ Không chuyển được chế độ ChatGPT '{effective_mode}'. "
                    "Tiếp tục với chế độ hiện tại trên ChatGPT."
                )
            if chatgpt_model and not select_chatgpt_model(driver, chatgpt_model):
                print(
                    f"⚠️ Không chọn được model ChatGPT '{chatgpt_model}'. "
                    "Tiếp tục với model hiện tại trên ChatGPT."
                )
            if chatgpt_thinking and not select_chatgpt_thinking(driver, chatgpt_thinking):
                print(
                    f"⚠️ Không chọn được mức suy luận '{chatgpt_thinking}'. "
                    "Tiếp tục với mức suy luận hiện tại trên ChatGPT."
                )
            input_area = wait.until(_ready_input)
            _paste_prompt(driver, input_area, prompt, pyperclip)
            print(f"📋 Đã thực hiện dán prompt ({len(prompt)} ký tự nguồn).")

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
            send_button.click()

            print(
                f"📤 Đã nhấn Gửi ({len(prompt)} ký tự nguồn). Đang chờ ChatGPT response..."
            )
            time.sleep(5)

            # ── Bước 4: Chờ response streaming hoàn tất ──
            start_time = time.monotonic()
            last_text = ""
            stable_count = 0
            response_turn = None

            while time.monotonic() - start_time < RESPONSE_TIMEOUT_SECONDS:
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
                if current_text:
                    partial_text = current_text
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

                else:
                    stable_count = 0
                    last_text = current_text

                time.sleep(1)

            if last_text:
                raise TimeoutException("ChatGPT chưa hoàn tất sau 30 phút: thiếu ###END### hoặc JSON hợp lệ.")
            raise TimeoutException("Timeout chờ ChatGPT response hoàn tất sau 30 phút")

        except ChatGPTComposerError:
            # Keep the browser open for inspection; do not retry a UI mismatch.
            raise
        except Exception as e:
            _save_incomplete_response(partial_text, attempt + 1)
            print(f"⚠️ Lỗi Selenium lần {attempt + 1}/{max_retries}: {e}")
            close_driver(close_orphans=True)
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise ValueError(f"❌ Thất bại: {e}")
