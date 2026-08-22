"""Own Gemini Web and ChatGPT Web browser sessions."""

from cores.chatgpt.web_session import ChatGPTWebSession
from cores.gemini.web_session import GeminiWebSession


class BrowserRuntime:
    def __init__(
        self,
        profile_path,
        service_factory,
        options_configurator,
        gemini_generate,
        chatgpt_generate,
        gemini_session_class=GeminiWebSession,
        chatgpt_session_class=ChatGPTWebSession,
    ):
        self._gemini_generate = gemini_generate
        self._chatgpt_generate = chatgpt_generate
        self.chatgpt = chatgpt_session_class(
            profile_path, service_factory, options_configurator
        )
        self.gemini = gemini_session_class(
            profile_path,
            service_factory,
            options_configurator,
            self.chatgpt.close_orphans,
        )

    def get_gemini_driver(self):
        return self.gemini.get_driver()

    def close_gemini(self):
        self.gemini.close()

    def setup_gemini(self, skip_login_prompt=False):
        self.gemini.setup(skip_login_prompt=skip_login_prompt)

    def generate_gemini(
        self, prompt, link, default_thinking, max_retries=3,
        web_model=None, thinking_level=None,
    ):
        return self._gemini_generate(
            prompt,
            get_driver=self.get_gemini_driver,
            link=link,
            default_thinking=default_thinking,
            max_retries=max_retries,
            web_model=web_model,
            thinking_level=thinking_level,
        )

    def close_chatgpt_orphans(self):
        self.chatgpt.close_orphans()

    def get_chatgpt_driver(self):
        return self.chatgpt.get_driver()

    def close_chatgpt(self, close_orphans=False):
        self.chatgpt.close(close_orphans=close_orphans)

    def setup_chatgpt(self, skip_login_prompt=False):
        self.chatgpt.setup(skip_login_prompt=skip_login_prompt)

    def generate_chatgpt(
        self,
        prompt,
        link,
        default_model,
        default_thinking,
        max_retries=3,
        chatgpt_model=None,
        chatgpt_thinking=None,
        chat_url=None,
    ):
        return self._chatgpt_generate(
            prompt,
            get_driver=self.get_chatgpt_driver,
            close_driver=self.close_chatgpt,
            link=link,
            default_model=default_model,
            default_thinking=default_thinking,
            max_retries=max_retries,
            chatgpt_model=chatgpt_model,
            chatgpt_thinking=chatgpt_thinking,
            chat_url=chat_url,
        )
