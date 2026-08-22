"""Translate uncached R19 fragments through an injected stage transport."""

import json
import re

from cores.r19 import storage

TOKEN_PATTERN = re.compile(r"__20AGE_\d{4}__")


def fragment_prompt(source):
    return f"""Dịch từ hoặc cụm từ sau sang tiếng Việt.
Không có ngữ cảnh bổ sung. Chỉ trả về một JSON object hợp lệ theo mẫu:
{{"translation": "bản dịch ngắn"}}
Không thêm Markdown hoặc giải thích.

Từ/cụm từ: {json.dumps(source, ensure_ascii=False)}"""


def parse_fragment_translation(text):
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1)
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("Engine trả sai JSON khi dịch riêng cụm R19.") from error
    if not isinstance(payload, dict):
        raise ValueError("Kết quả dịch cụm R19 phải là JSON object.")
    value = str(payload.get("translation", "")).strip()
    if not value or "\n" in value or TOKEN_PATTERN.search(value):
        raise ValueError("Engine chưa trả bản dịch R19 hợp lệ.")
    return value


def _log_r19_call(token, model, prompt, response, ok):
    from cores.api_logging import log_project_api_call
    try:
        log_project_api_call(f"r19:{token}", "r19_word", model, prompt, response, ok=ok)
    except OSError as error:
        print(f"Không thể ghi log request R19: {error}")


def _is_4xx_error(error):
    code = getattr(error, "code", None) or getattr(error, "status_code", None)
    return (isinstance(code, int) and 400 <= code <= 499) or bool(
        re.search(r"(?<!\d)4\d\d(?!\d)", str(error))
    )


def request_word_translation(
    source, token, model, *, generate=None, logger=None, switcher=None, key_count=None
):
    if generate is None:
        raise ValueError("Chưa truyền engine để dịch cụm R19.")
    logger = logger or (
        lambda prompt, response, ok: _log_r19_call(token, model, prompt, response, ok)
    )
    switcher = switcher or (lambda: None)
    attempts = max(1, int(key_count or 1))
    prompt = fragment_prompt(source)
    for attempt in range(attempts):
        response = ""
        try:
            response = generate(prompt) or ""
            translation = parse_fragment_translation(response)
        except Exception as error:
            logger(prompt, response, False)
            if _is_4xx_error(error) and attempt < attempts - 1:
                switcher()
                print(f"Dịch R19: đổi API key và thử lại ({attempt + 2}/{attempts})...")
                continue
            raise
        logger(prompt, response, True)
        return translation
    raise ValueError("Không thể dịch cụm R19 sau khi đã thử tất cả API key")


def translate_fragments(
    entries,
    generate=None,
    *,
    provider="",
    model="",
    switcher=None,
    key_count=1,
):
    if not entries:
        return {}
    engine_label = f"{provider}:{model}".strip(":") or "engine đã chọn"
    _terms, cached = storage.load_word_mappings()
    translations, missing = {}, 0
    for item in entries:
        source = item["source"]
        translation = cached.get(source.casefold())
        if translation:
            translations[item["token"]] = translation
            continue
        if generate is None:
            raise ValueError("Chưa truyền engine để dịch các cụm R19 chưa có cache.")
        missing += 1
        print(f"Đang dịch riêng cụm R19 {item['token']} bằng {engine_label}...")
        translation = request_word_translation(
            source,
            item["token"],
            engine_label,
            generate=generate,
            switcher=switcher,
            key_count=key_count,
        )
        translations[item["token"]] = translation
        cached[source.casefold()] = translation
        storage.save_word_translation(source, translation)
    print(f"Dịch R19: dùng lại {len(entries) - missing} cụm, gọi API cho {missing} cụm mới.")
    return translations
