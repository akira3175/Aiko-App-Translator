"""Browser URLs, models, and reasoning defaults."""

from cores.platform.browser_profile import APP_BROWSER_PROFILE_PATH
from cores.config.runtime import option


SELENIUM_PROFILE_PATH = str(APP_BROWSER_PROFILE_PATH)
LINK_GEMINI = str(
    option("link_gemini", "https://gemini.google.com/gem/fdec65ac9c69")
)
LINK_CHATGPT = str(option("link_chatgpt", "https://chatgpt.com/"))

WEB_MODEL_FREE = "free"
WEB_MODEL_PRO = "pro"
WEB_MODEL_THINKING = "thinking"
SELECT_MODEL = str(option("gemini_web_model", WEB_MODEL_PRO))
WEB_THINKING_LEVEL = str(option("gemini_thinking", "extended"))

CHATGPT_SELECT_THINKING = str(option("chatgpt_thinking", "cao"))
CHATGPT_SELECT_MODEL = str(option("chatgpt_model", "gpt-5.6 sol"))
