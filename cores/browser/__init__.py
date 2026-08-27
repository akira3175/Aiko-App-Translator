"""Shared Chrome and web-session runtime."""

from cores.browser.chrome import apply_portable_chrome, create_chrome_service
from cores.browser.runtime import BrowserRuntime
from cores.browser.content import (
    browser_runtime,
    close_ai_studio_driver,
    close_chatgpt_driver,
    close_gemini_driver,
    close_orphaned_chatgpt_chrome,
    generate_content_with_chatgpt,
    generate_content_with_ai_studio,
    generate_content_with_selenium,
    get_chatgpt_driver,
    get_gemini_driver,
    setup_chatgpt_browser,
    setup_ai_studio_browser,
    setup_gemini_browser,
)


__all__ = [
    "BrowserRuntime", "apply_portable_chrome", "browser_runtime",
    "close_ai_studio_driver", "close_chatgpt_driver", "close_gemini_driver", "close_orphaned_chatgpt_chrome",
    "create_chrome_service", "generate_content_with_ai_studio", "generate_content_with_chatgpt",
    "generate_content_with_selenium", "get_chatgpt_driver", "get_gemini_driver",
    "setup_ai_studio_browser", "setup_chatgpt_browser", "setup_gemini_browser",
]
