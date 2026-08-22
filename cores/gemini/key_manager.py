"""Persistent Gemini API-key selection and rotation."""

import hashlib
import json
import os
import time
from pathlib import Path


class GeminiKeyManager:
    def __init__(self, keys, state_file, client_factory, clock=time.time):
        self.keys = list(keys) or ["dummy_key"]
        self.state_file = Path(state_file)
        self.client_factory = client_factory
        self.clock = clock
        self.current_index = self._load_index()
        self.last_switch_time = self.clock()

    @staticmethod
    def fingerprint(key):
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    @property
    def current_key(self):
        return self.keys[self.current_index]

    def _load_index(self):
        try:
            fingerprint = json.loads(
                self.state_file.read_text(encoding="utf-8")
            ).get("current_key_fingerprint", "")
        except (OSError, json.JSONDecodeError, AttributeError):
            return 0
        return next(
            (
                index
                for index, key in enumerate(self.keys)
                if self.fingerprint(key) == fingerprint
            ),
            0,
        )

    def _save_index(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"current_key_fingerprint": self.fingerprint(self.current_key)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.state_file)

    def _advance(self):
        old_index = self.current_index
        self.current_index = (self.current_index + 1) % len(self.keys)
        self.last_switch_time = self.clock()
        self._save_index()
        return old_index, self.current_index

    def get_client(self, rotation_seconds=3600):
        if self.clock() - self.last_switch_time >= rotation_seconds:
            self._advance()
        return self.client_factory(api_key=self.current_key)

    def switch(self):
        return self._advance()
