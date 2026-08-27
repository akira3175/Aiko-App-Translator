"""Send one prompt through Google AI Studio and return the new model turn."""

import time
from urllib.parse import urlencode
from uuid import uuid4

import pyperclip
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


AI_STUDIO_URL = "https://aistudio.google.com/prompts/new_chat"
DEFAULT_MODEL = "gemini-flash-latest"
DEFAULT_THINKING = "high"
THINKING_LEVELS = {"low", "medium", "high"}


def _prompt_url(model):
    selected_model = str(model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if selected_model.lower() == "current":
        selected_model = DEFAULT_MODEL
    return f"{AI_STUDIO_URL}?{urlencode({'model': selected_model})}"


def _visible(elements):
    for element in elements:
        try:
            if element.is_displayed():
                yield element
        except Exception:
            continue


def _model_turns(driver):
    return list(_visible(driver.find_elements(By.CSS_SELECTOR, "ms-chat-turn.text-chunk-host")))


def _turn_text(turn):
    nodes = list(_visible(turn.find_elements(By.CSS_SELECTOR, "ms-cmark-node.cmark-node")))
    texts = [(node.text or "").strip() for node in nodes]
    return (max(texts, key=len, default="") or (turn.text or "").strip()).strip()


def _is_ui_chrome(text):
    lines = {
        line.strip().lower()
        for line in str(text or "").splitlines()
        if line.strip()
    }
    return bool(lines) and lines <= {"thumb_up", "thumb_down"}


def _copy_response_as_markdown(driver, turn, clipboard=None):
    clipboard = clipboard or pyperclip
    original = None
    sentinel = f"aiko-ai-studio-{uuid4()}"
    try:
        original = clipboard.paste()
        clipboard.copy(sentinel)
        options_button = next(
            button
            for button in _visible(turn.find_elements(By.CSS_SELECTOR, "button"))
            if (button.get_attribute("aria-label") or "") == "Open options"
        )
        driver.execute_script("arguments[0].click();", options_button)

        def markdown_button(active_driver):
            for item in _visible(
                active_driver.find_elements(
                    By.CSS_SELECTOR, '[role="menuitem"], button.mat-mdc-menu-item'
                )
            ):
                if "copy as markdown" in (item.text or "").strip().lower():
                    return item
            return False

        copy_button = WebDriverWait(driver, 10).until(markdown_button)
        driver.execute_script("arguments[0].click();", copy_button)
        copied = WebDriverWait(driver, 10).until(
            lambda _driver: (
                value if (value := clipboard.paste()) != sentinel else False
            )
        )
        return str(copied or "").strip()
    except Exception:
        return ""
    finally:
        if original is not None:
            try:
                clipboard.copy(original)
            except Exception:
                pass


def _set_prompt(driver, input_area, prompt):
    # send_keys corrupts Vietnamese on some Windows/Selenium combinations.
    driver.execute_script(
        """
        const input = arguments[0], value = arguments[1];
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value'
        ).set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
        input.focus();
        """,
        input_area,
        prompt,
    )


def _paste_parts(input_area, parts, clipboard=None):
    """Paste prompt and references separately so AI Studio can create separate files."""
    clipboard = clipboard or pyperclip
    original = clipboard.paste()
    try:
        for part in parts:
            value = str(part or "")
            if not value.strip():
                continue
            clipboard.copy(value)
            input_area.send_keys(Keys.CONTROL, "v")
            time.sleep(0.5)
    finally:
        clipboard.copy(original)


def _run_button(driver):
    for button in _visible(driver.find_elements(By.CSS_SELECTOR, "button")):
        if (
            (button.text or "").strip().splitlines()[:1] == ["Run"]
            and button.is_enabled()
        ):
            return button
    return None


def _select_thinking_level(driver, level):
    selected_level = str(level or DEFAULT_THINKING).strip().lower()
    if selected_level == "current":
        selected_level = DEFAULT_THINKING
    if selected_level not in THINKING_LEVELS:
        raise ValueError(
            "Thinking level Google AI Studio phải là low, medium hoặc high"
        )
    wait = WebDriverWait(driver, 30)
    dropdown = wait.until(
        EC.visibility_of_element_located(
            (
                By.CSS_SELECTOR,
                'mat-select[aria-label="Thinking Level"], '
                '[role="combobox"][aria-label="Thinking Level"]',
            )
        )
    )
    if (dropdown.text or "").strip().lower() == selected_level:
        return
    driver.execute_script("arguments[0].click();", dropdown)

    def matching_option(active_driver):
        for option in _visible(
            active_driver.find_elements(By.CSS_SELECTOR, '[role="option"], mat-option')
        ):
            if (option.text or "").strip().lower() == selected_level:
                return option
        return False

    option = wait.until(matching_option)
    driver.execute_script("arguments[0].click();", option)
    wait.until(
        lambda _driver: (dropdown.text or "").strip().lower() == selected_level
    )


def generate_content(
    prompt,
    *,
    get_driver,
    max_retries=3,
    ai_studio_model=DEFAULT_MODEL,
    ai_studio_thinking=DEFAULT_THINKING,
    reference_documents=(),
):
    last_error = None
    for attempt in range(max_retries):
        try:
            driver = get_driver()
            driver.get(_prompt_url(ai_studio_model))
            wait = WebDriverWait(driver, 60)
            input_area = wait.until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, 'textarea[aria-label="Enter a prompt"]')
                )
            )
            _select_thinking_level(driver, ai_studio_thinking)
            old_count = len(_model_turns(driver))
            reference_parts = [
                f"\n\n## Reference file: {item['name']}\n\n{item['content']}"
                for item in reference_documents
            ]
            _paste_parts(input_area, [prompt, *reference_parts])
            run_button = WebDriverWait(driver, 15).until(
                lambda active_driver: _run_button(active_driver)
            )
            driver.execute_script("arguments[0].click();", run_button)

            deadline = time.time() + 1600
            last_text = ""
            stable_count = 0
            while time.time() < deadline:
                turns = _model_turns(driver)
                if len(turns) > old_count:
                    turn = turns[-1]
                    turn_body = (turn.text or "").lower()
                    if "internal error" in turn_body:
                        raise RuntimeError("Google AI Studio báo lỗi nội bộ")
                    current_text = _turn_text(turn)
                    running = any(
                        (button.text or "").strip().splitlines()[:1] == ["Stop"]
                        for button in _visible(driver.find_elements(By.CSS_SELECTOR, "button"))
                    )
                    if current_text and current_text == last_text and not running:
                        stable_count += 1
                        if stable_count >= 2:
                            markdown = _copy_response_as_markdown(driver, turn)
                            result = markdown or current_text
                            if _is_ui_chrome(result):
                                raise RuntimeError(
                                    "Google AI Studio chỉ trả về nút giao diện, không có nội dung"
                                )
                            return result
                    else:
                        stable_count = 0
                        last_text = current_text
                time.sleep(1)
            raise TimeoutException("Quá thời gian chờ Google AI Studio trả lời")
        except Exception as error:
            last_error = error
            if attempt + 1 < max_retries:
                time.sleep(3)
    raise ValueError(f"Google AI Studio Web thất bại: {last_error}")
