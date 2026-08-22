"""Translate a short source-text selection into Vietnamese."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SourceTranslationService:
    opener: object = urlopen

    @staticmethod
    def source_language(text: str):
        if re.search(r"[\uac00-\ud7a3]", text):
            return "ko"
        if re.search(r"[\u3040-\u30ff]", text):
            return "ja"
        if re.search(r"[\u3400-\u9fff]", text):
            return "zh-CN"
        if re.search(r"[A-Za-z]", text):
            return "en"
        return "auto"

    def translate_details(self, text: str):
        text = text.strip()
        if not text:
            raise ValueError("Chưa chọn nội dung cần dịch")
        if len(text) > 5000:
            raise ValueError("Đoạn được chọn quá dài; tối đa 5.000 ký tự")
        body = urlencode(
            [
                ("client", "gtx"),
                ("sl", self.source_language(text)),
                ("tl", "vi"),
                ("dt", "t"),
                ("q", text),
            ]
        ).encode("utf-8")
        request = Request(
            "https://translate.googleapis.com/translate_a/single",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0",
            },
        )
        with self.opener(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        translated = "".join(
            part[0] for part in (data[0] if data else []) if part and part[0]
        ).strip()
        if not translated:
            raise ValueError("Google Translate không trả về bản dịch")
        detected = str(data[2] or "") if len(data) > 2 else ""
        return {"translated": translated, "detected_language": detected}

    def translate(self, text: str):
        return self.translate_details(text)["translated"]
