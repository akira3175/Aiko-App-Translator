"""Stateful Gemini API runtime with persistent key rotation."""

import re
import time

from cores.gemini.api_client import generate_content
from cores.gemini.key_manager import GeminiKeyManager


def load_api_keys(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            keys = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        print("⚠️ Không tìm thấy data/apikeys.txt! Chỉ dùng Gemini Web.")
        return ["dummy_key"]
    if not keys:
        print("⚠️ Không có API key nào trong data/apikeys.txt! Chỉ dùng Gemini Web.")
        return ["dummy_key"]
    return keys


def _http_status(error):
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        match = re.search(r"(?<!\d)(429|5\d{2})(?!\d)", str(error))
        return int(match.group(1)) if match else None


class GeminiRuntime:
    def __init__(
        self,
        keys,
        state_file,
        client_factory,
        generate=generate_content,
        sleep=time.sleep,
    ):
        self.keys = list(keys)
        self.key_manager = GeminiKeyManager(self.keys, state_file, client_factory)
        self._generate = generate
        self._sleep = sleep

    @property
    def current_key_index(self):
        return self.key_manager.current_index

    @property
    def last_switch_time(self):
        return self.key_manager.last_switch_time

    @property
    def current_key(self):
        return self.key_manager.current_key

    def get_client(self):
        old_index = self.current_key_index
        client = self.key_manager.get_client()
        if self.current_key_index != old_index:
            print(f"🔄 Đã đổi API key sang key số {self.current_key_index + 1}")
        return client

    def switch(self):
        old_index, new_index = self.key_manager.switch()
        print(f"🔄 Lỗi 429! Đổi API key: {old_index + 1} → {new_index + 1}")
        return old_index, new_index

    def generate(
        self,
        prompt,
        model,
        max_output_tokens=None,
        system_instruction=None,
        as_chat_parts=False,
        extra_parts=None,
        character_document=None,
        pronoun_document=None,
        thinking_level=None,
    ):
        while True:
            try:
                return self._generate(
                    self.get_client(),
                    prompt,
                    model,
                    max_output_tokens=max_output_tokens,
                    system_instruction=system_instruction,
                    as_chat_parts=as_chat_parts,
                    extra_parts=extra_parts,
                    thinking_level=thinking_level,
                )
            except Exception as error:
                status = _http_status(error)
                if status == 429 or "RESOURCE_EXHAUSTED" in str(error):
                    print(error)
                    self.switch()
                    print("⏳ Thử lại sau 30 giây...")
                    self._sleep(30)
                elif status is not None and 500 <= status <= 599:
                    print(error)
                    print("⏳ Thử lại sau 15 giây...")
                    self._sleep(15)
                else:
                    raise
