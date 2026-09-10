"""Send one prompt through Google AI Studio and return the new model turn."""

import re
import time
from urllib.parse import urlencode
from uuid import uuid4

import pyperclip
from cores.json_output import parse_complete_json_object
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


AI_STUDIO_URL = "https://aistudio.google.com/prompts/new_chat"
DEFAULT_MODEL = "gemini-flash-latest"
DEFAULT_THINKING = "high"
THINKING_LEVELS = {"low", "medium", "high"}

_UI_ONLY_LINES = {
    "thinking",
    "expand to view model thoughts",
    "collapse model thoughts",
    "chevron_right",
    "chevron_left",
    "expand_more",
    "expand_less",
    "thumb_up",
    "thumb_down",
    "more_vert",
    "content_copy",
}
_MODEL_TIME_RE = re.compile(
    r"^model(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?)?$",
    flags=re.IGNORECASE,
)


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


def _strip_ui_chrome(text):
    lines = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if line.lower() in _UI_ONLY_LINES or _MODEL_TIME_RE.fullmatch(line):
            continue
        lines.append(raw_line.rstrip())
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip()


def _is_ui_chrome(text):
    return not bool(_strip_ui_chrome(text))


def _structured_score(text):
    value = str(text or "")
    score = 0
    if "###TITLE###" in value:
        score += 10
    if "###CONTENT###" in value:
        score += 10
    if "###END###" in value:
        score += 3
    if "###START###" in value or "###CHAR_START###" in value:
        score += 10
    if value.lstrip().startswith(("{", "[")):
        score += 2
    return score


def _is_complete_response(text, stage):
    value = _strip_ui_chrome(text)
    if not value:
        return False
    stage = str(stage or "").strip().lower()
    if stage in {"translate", "polish"}:
        return all(
            marker in value
            for marker in ("###TITLE###", "###CONTENT###", "###END###")
        )
    if stage in {"context", "glossary"}:
        return "###START###" in value and "###END###" in value
    if stage == "characters":
        has_start = "###START###" in value or "###CHAR_START###" in value
        has_end = "###END###" in value or "###CHAR_END###" in value
        return has_start and has_end and "## " in value
    parsed = parse_complete_json_object(value, strict=False)
    if stage == "pronouns":
        return isinstance(parsed, dict) and isinstance(
            parsed.get("character_pairs"), list
        )
    if stage == "review":
        return (
            isinstance(parsed, dict)
            and isinstance(parsed.get("overall_score"), (int, float))
            and isinstance(parsed.get("issues"), list)
        )
    return True


def _turn_text(turn):
    candidates = []
    for node in _visible(turn.find_elements(By.CSS_SELECTOR, "ms-cmark-node.cmark-node")):
        cleaned = _strip_ui_chrome(node.text or "")
        if cleaned:
            candidates.append(cleaned)
    if candidates:
        return max(
            candidates,
            key=lambda value: (_structured_score(value), len(value)),
        ).strip()
    return _strip_ui_chrome(turn.text or "")


def _copy_response_as_markdown(driver, turn, clipboard=None):
    clipboard = clipboard or pyperclip
    original = None
    sentinel = f"aiko-ai-studio-{uuid4()}"
    try:
        original = clipboard.paste()
        clipboard.copy(sentinel)
        ActionChains(driver).move_to_element(turn).perform()

        def options_ready(_driver):
            return next(
                (
                    button
                    for button in _visible(turn.find_elements(By.CSS_SELECTOR, "button"))
                    if (button.get_attribute("aria-label") or "") == "Open options"
                    and button.is_enabled()
                ),
                False,
            )

        options_button = WebDriverWait(driver, 10).until(options_ready)
        options_button.click()

        def markdown_button(active_driver):
            for item in _visible(
                active_driver.find_elements(
                    By.CSS_SELECTOR, '[role="menuitem"], button.mat-mdc-menu-item'
                )
            ):
                if (
                    "copy as markdown" in (item.text or "").strip().lower()
                    and item.is_enabled()
                ):
                    return item
            return False

        copy_button = WebDriverWait(driver, 10).until(markdown_button)
        copy_button.click()
        copied = WebDriverWait(driver, 10).until(
            lambda _driver: (
                value if (value := clipboard.paste()) != sentinel else False
            )
        )
        return _strip_ui_chrome(str(copied or ""))
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


def _generation_running(driver):
    for button in _visible(driver.find_elements(By.CSS_SELECTOR, "button")):
        parts = [
            (button.text or "").strip(),
            (button.get_attribute("aria-label") or "").strip(),
            (button.get_attribute("title") or "").strip(),
        ]
        label = " ".join(part for part in parts if part).lower()
        if label == "stop" or label.startswith("stop ") or "stop generating" in label:
            return True
    return False


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
    stage="",
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
                    running = _generation_running(driver)
                    if not current_text or _is_ui_chrome(current_text):
                        stable_count = 0
                        last_text = ""
                        time.sleep(1)
                        continue
                    if current_text == last_text and not running:
                        stable_count += 1
                        if stable_count >= 3:
                            markdown = _copy_response_as_markdown(driver, turn)
                            result = _strip_ui_chrome(markdown or current_text)
                            if not _is_complete_response(result, stage):
                                stable_count = 0
                                time.sleep(1)
                                continue
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
