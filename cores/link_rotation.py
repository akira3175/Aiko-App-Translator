"""Rotate configured browser links only at persisted chapter boundaries."""

import time
from contextvars import ContextVar
from functools import wraps
from threading import RLock
from urllib.parse import urlsplit

from cores.config.runtime import option
from cores.web_errors import RetryableWebError, WebLinksExhausted

HOSTS = {"gemini_web": "gemini.google.com", "ai_studio": "aistudio.google.com"}


def parse_links(value, provider):
    links = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    for link in links:
        url = urlsplit(link)
        if (url.scheme != "https" or url.netloc != HOSTS[provider]
                or any(char.isspace() for char in link)):
            raise ValueError(f"Mỗi link phải bắt đầu bằng https://{HOSTS[provider]}/")
    return links


class LinkRotation:
    def __init__(self):
        self.states = {}
        self.lock = RLock()
        self.can_advance = True
        self.chapter = ContextVar("browser_rotation_chapter", default=None)

    def link(self, provider, fallback):
        if not any(option(f"{provider}_rotation_{suffix}", "off") == "on" for suffix in ("enabled", "on_error")):
            return fallback
        links = parse_links(option(f"{provider}_rotation_links", ""), provider)
        if not links:
            raise ValueError("Hãy nhập ít nhất một link trước khi bật tự chuyển link.")
        with self.lock:
            state = self.states.get(provider)
            if state is None or state["links"] != links:
                state = dict(links=links, index=0, started=time.monotonic(), count=0)
                self.states[provider] = state
            chapter = self.chapter.get()
            if chapter is not None:
                chapter.add(provider)
            return links[state["index"]]

    def advance(self):
        with self.lock:
            for provider, state in self.states.items():
                if option(f"{provider}_rotation_enabled", "off") != "on":
                    continue
                if not state["count"]:
                    continue
                minutes = int(option(f"{provider}_rotation_minutes", 0) or 0)
                chapters = int(option(f"{provider}_rotation_chapters", 0) or 0)
                due = ((minutes > 0 and time.monotonic() - state["started"] >= minutes * 60)
                       or (chapters > 0 and state["count"] >= chapters))
                if not due:
                    continue
                index = state["index"] + 1
                if index >= len(state["links"]):
                    if option(f"{provider}_rotation_loop", "on") != "on":
                        continue
                    index = 0
                state.update(index=index, count=0, started=time.monotonic())
                print(f"[INFO] {provider}: chuyển sang link {index + 1}/{len(state['links'])}.")

    def run(self, provider, link, generate):
        """Retry only this request; each distinct URL is visited once per failure chain."""
        visited = set()
        while True:
            visited.add(link)
            try:
                return generate(link)
            except RetryableWebError as error:
                if option(f"{provider}_rotation_on_error", "off") != "on":
                    raise
                with self.lock:
                    state = self.states.get(provider)
                    if state is None:
                        raise
                    links = state["links"]
                    next_index = next((
                        (state["index"] + offset) % len(links)
                        for offset in range(1, len(links) + 1)
                        if links[(state["index"] + offset) % len(links)] not in visited
                    ), None)
                    if next_index is None:
                        raise WebLinksExhausted(
                            f"{provider}: đã thử hết {len(visited)} link cho bước hiện tại. Lỗi cuối: {error}"
                        ) from error
                    state.update(index=next_index, count=0, started=time.monotonic())
                    link = links[next_index]
                    print(f"[THỬ LẠI] {provider}: lỗi usage/upload/kết nối; chuyển sang link {next_index + 1}/{len(links)}, gửi lại bước hiện tại.")

    def chapter_task(self, function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if self.can_advance:
                self.advance()
            self.can_advance = False
            used = set()
            token = self.chapter.set(used)
            try:
                result = function(*args, **kwargs)
                if result:
                    self.can_advance = True
                    with self.lock:
                        for provider in used:
                            self.states[provider]["count"] += 1
                return result
            finally:
                self.chapter.reset(token)
        return wrapped


rotation = LinkRotation()
