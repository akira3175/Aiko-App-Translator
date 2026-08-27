"""Configured browser transport for Gemini Web and ChatGPT Web."""

from cores.browser.chrome import apply_portable_chrome, create_chrome_service
from cores.browser.runtime import BrowserRuntime
from cores.chatgpt.web_client import generate_content as generate_chatgpt_content
from cores.config import (
    CHATGPT_SELECT_MODEL,
    CHATGPT_SELECT_THINKING,
    LINK_CHATGPT,
    LINK_GEMINI,
    PORTABLE_CHROME,
    PORTABLE_CHROMEDRIVER,
    SELECT_MODEL,
    SELENIUM_PROFILE_PATH,
    WEB_THINKING_LEVEL,
)
from cores.gemini.web_client import generate_content as generate_gemini_content
from cores.google_ai_studio.web_client import generate_content as generate_ai_studio_content
from cores.config.runtime import bool_option, option, web_mode


def _chatgpt_link():
    return str(option("link_chatgpt", "https://chatgpt.com/")).strip()


def _service():
    return create_chrome_service(PORTABLE_CHROMEDRIVER)


def _configure(options):
    return apply_portable_chrome(options, PORTABLE_CHROME)


browser_runtime = BrowserRuntime(
    SELENIUM_PROFILE_PATH,
    _service,
    _configure,
    generate_gemini_content,
    generate_chatgpt_content,
)


def get_gemini_driver():
    return browser_runtime.get_gemini_driver()


def close_gemini_driver():
    browser_runtime.close_gemini()


def setup_gemini_browser():
    browser_runtime.setup_gemini(
        skip_login_prompt=web_mode() and bool_option("skip_login_prompt", True)
    )


def generate_content_with_selenium(
    prompt, max_retries=3, web_model=SELECT_MODEL, thinking_level=None
):
    return browser_runtime.generate_gemini(
        prompt,
        link=LINK_GEMINI,
        default_thinking=WEB_THINKING_LEVEL,
        max_retries=max_retries,
        web_model=web_model,
        thinking_level=thinking_level,
    )


def get_chatgpt_driver():
    return browser_runtime.get_chatgpt_driver()


def close_chatgpt_driver(close_orphans=False):
    browser_runtime.close_chatgpt(close_orphans=close_orphans)


def close_orphaned_chatgpt_chrome():
    browser_runtime.close_chatgpt_orphans()


def setup_chatgpt_browser():
    browser_runtime.setup_chatgpt(
        skip_login_prompt=web_mode() and bool_option("skip_login_prompt", True),
        link=_chatgpt_link(),
    )


def generate_content_with_chatgpt(
    prompt,
    max_retries=3,
    chatgpt_model=CHATGPT_SELECT_MODEL,
    chatgpt_thinking=CHATGPT_SELECT_THINKING,
    chat_url=None,
):
    return browser_runtime.generate_chatgpt(
        prompt,
        link=_chatgpt_link(),
        default_model=CHATGPT_SELECT_MODEL,
        default_thinking=CHATGPT_SELECT_THINKING,
        max_retries=max_retries,
        chatgpt_model=chatgpt_model,
        chatgpt_thinking=chatgpt_thinking,
        chat_url=chat_url,
    )


def setup_ai_studio_browser():
    browser_runtime.get_chatgpt_driver().get(
        "https://aistudio.google.com/prompts/new_chat"
    )


def close_ai_studio_driver():
    browser_runtime.close_chatgpt()


def generate_content_with_ai_studio(
    prompt, max_retries=3, ai_studio_model="gemini-flash-latest",
    ai_studio_thinking="high", ai_studio_references=(),
):
    return generate_ai_studio_content(
        prompt,
        get_driver=browser_runtime.get_chatgpt_driver,
        max_retries=max_retries,
        ai_studio_model=ai_studio_model,
        ai_studio_thinking=ai_studio_thinking,
        reference_documents=ai_studio_references,
    )
