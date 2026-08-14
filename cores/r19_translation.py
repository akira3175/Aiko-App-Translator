"""Mask configured R19 terms during the main translation request."""

import json
import re
from copy import deepcopy
from pathlib import Path

from cores.data_paths import R19_WORDS_FILE, ensure_user_data_migrated

from cores.runtime_config import bool_option, option


ensure_user_data_migrated()
TOKEN_PATTERN = re.compile(r"__20AGE_\d{4}__")


def enabled():
    return bool_option("r19_mode", False)


def load_word_mappings():
    try:
        lines = R19_WORDS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], {}
    terms, translations = [], {}
    seen = set()
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        source, separator, translation = value.partition("=")
        source = source.strip()
        translation = translation.strip() if separator else ""
        if not source:
            continue
        key = source.casefold()
        if key not in seen:
            seen.add(key)
            terms.append(source)
        if translation:
            translations[key] = translation
    return sorted(terms, key=len, reverse=True), translations


def load_terms():
    return load_word_mappings()[0]


def prepare_chapters(chapters):
    copies = deepcopy(chapters)
    if not enabled():
        return copies, []
    terms = load_terms()
    if not terms:
        raise ValueError("Đã bật Dịch R19 nhưng r19_words.txt chưa có từ hoặc cụm từ nào.")
    matcher = re.compile("|".join(re.escape(term) for term in terms), re.IGNORECASE)
    entries = []
    tokens_by_term = {}

    def mask(text):
        source = str(text or "")

        def replace(match):
            original = match.group(0)
            key = original.casefold()
            token = tokens_by_term.get(key)
            if token is None:
                token = f"__20AGE_{len(entries) + 1:04d}__"
                tokens_by_term[key] = token
                entries.append({
                    "token": token,
                    "source": original,
                })
            return token

        return matcher.sub(replace, source)

    for chapter in copies:
        chapter["title"] = mask(chapter.get("title", ""))
        chapter["content"] = mask(chapter.get("content", ""))
    return copies, entries


def mask_contexts(texts, entries):
    """Mask R19 terms in reference-only prompt blocks without requiring restoration."""
    values = [str(text or "") for text in texts]
    if not enabled():
        return values
    terms = load_terms()
    if not terms:
        return values
    matcher = re.compile("|".join(re.escape(term) for term in terms), re.IGNORECASE)
    target_tokens = {item["source"].casefold(): item["token"] for item in entries}
    context_tokens = {}

    def mask(text):
        def replace(match):
            key = match.group(0).casefold()
            if key in target_tokens:
                return target_tokens[key]
            if key not in context_tokens:
                context_tokens[key] = f"__20AGE_CTX_{len(context_tokens) + 1:04d}__"
            return context_tokens[key]

        return matcher.sub(replace, text)

    return [mask(value) for value in values]


def strip_r19_terms(text):
    """Remove source and translated R19 terms when R19 mode is enabled."""
    value = str(text or "")
    if not enabled():
        return value
    terms, translations = load_word_mappings()
    blocked = terms + [item for item in translations.values() if item]
    if not blocked:
        return value
    matcher = re.compile(
        "|".join(re.escape(term) for term in sorted(set(blocked), key=len, reverse=True)),
        re.IGNORECASE,
    )
    return matcher.sub("", value)


def strip_previous_context(text):
    return strip_r19_terms(text)


def prepare_postprocess_chapter(chapter):
    """Mask R19 source/translated terms until the entire post pipeline finishes."""
    copy = deepcopy(chapter)
    if not enabled():
        return copy, [], {}
    terms, translations = load_word_mappings()
    replacements = {}
    for source in terms:
        translated = translations.get(source.casefold())
        if translated:
            replacements[source.casefold()] = translated
            replacements[translated.casefold()] = translated
    if not replacements:
        return copy, [], {}
    matcher = re.compile(
        "|".join(
            re.escape(term) for term in sorted(replacements, key=len, reverse=True)
        ),
        re.IGNORECASE,
    )
    entries = []
    restore_map = {}
    tokens_by_translation = {}

    def mask(text):
        def replace(match):
            key = match.group(0).casefold()
            translated = replacements[key]
            translation_key = translated.casefold()
            token = tokens_by_translation.get(translation_key)
            if token is None:
                token = f"__20AGE_PP_{len(entries) + 1:04d}__"
                tokens_by_translation[translation_key] = token
                entries.append({"token": token, "source": match.group(0)})
                restore_map[token] = translated
            return token

        return matcher.sub(replace, str(text or ""))

    for field in ("title", "content", "title_translation", "translation"):
        copy[field] = mask(copy.get(field, ""))
    return copy, entries, restore_map


def mask_postprocess_contexts(texts, restore_map):
    """Mask source and translated R19 terms in post-pipeline reference blocks."""
    values = [str(text or "") for text in texts]
    if not enabled() or not restore_map:
        return values
    terms, translations = load_word_mappings()
    token_by_translation = {
        translation.casefold(): token for token, translation in restore_map.items()
    }
    replacements = {}
    for source in terms:
        translated = translations.get(source.casefold())
        if translated and translated.casefold() in token_by_translation:
            token = token_by_translation[translated.casefold()]
            replacements[source.casefold()] = token
            replacements[translated.casefold()] = token
    if not replacements:
        return values
    matcher = re.compile(
        "|".join(
            re.escape(term) for term in sorted(replacements, key=len, reverse=True)
        ),
        re.IGNORECASE,
    )
    return [
        matcher.sub(lambda match: replacements[match.group(0).casefold()], value)
        for value in values
    ]


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
            raw = raw[start:end + 1]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Gemini API trả sai JSON khi dịch riêng cụm R19.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Kết quả dịch cụm R19 phải là JSON object.")
    value = str(payload.get("translation", "")).strip()
    if not value or "\n" in value or TOKEN_PATTERN.search(value):
        raise ValueError("Gemini API chưa trả bản dịch R19 hợp lệ.")
    return value


def save_word_translation(source, translation):
    try:
        lines = R19_WORDS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    key = source.casefold()
    updated = False
    for index, line in enumerate(lines):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        existing_source = value.partition("=")[0].strip()
        if existing_source.casefold() == key:
            lines[index] = f"{existing_source} = {translation}"
            updated = True
            break
    if not updated:
        lines.append(f"{source} = {translation}")
    temporary = R19_WORDS_FILE.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(R19_WORDS_FILE)


def _gemini_generate(prompt, model):
    from cores.dich_utils import call_gemini

    return call_gemini(prompt, model=model)


def _log_r19_call(token, model, prompt, response, ok):
    from cores.dich_utils import log_api_call

    try:
        log_api_call(f"r19:{token}", "r19_word", model, prompt, response, ok=ok)
    except OSError as exc:
        print(f"Không thể ghi log request R19: {exc}")


def _is_4xx_error(exc):
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int) and 400 <= code <= 499:
        return True
    return bool(re.search(r"(?<!\d)4\d\d(?!\d)", str(exc)))


def request_word_translation(
    source,
    token,
    model,
    *,
    generate=None,
    logger=None,
    switcher=None,
    key_count=None,
):
    from cores import dich_utils

    generate = generate or (lambda prompt: _gemini_generate(prompt, model))
    logger = logger or (
        lambda prompt, response, ok: _log_r19_call(
            token, model, prompt, response, ok
        )
    )
    switcher = switcher or dich_utils.switch_api_key
    attempts = max(1, int(key_count or len(dich_utils.API_KEYS)))
    prompt = fragment_prompt(source)
    for attempt in range(attempts):
        response = ""
        try:
            response = generate(prompt) or ""
            translation = parse_fragment_translation(response)
        except Exception as exc:
            logger(prompt, response, False)
            if _is_4xx_error(exc) and attempt < attempts - 1:
                switcher()
                print(f"Dịch R19: đổi API key và thử lại ({attempt + 2}/{attempts})...")
                continue
            raise
        logger(prompt, response, True)
        return translation
    raise ValueError("Không thể dịch cụm R19 sau khi đã thử tất cả API key")


def translate_fragments(entries, generate=None):
    if not entries:
        return {}
    model = str(option("r19_model", "gemini-3.5-flash"))
    _terms, cached_translations = load_word_mappings()
    translations = {}
    missing = 0
    for item in entries:
        source = item["source"]
        cached = cached_translations.get(source.casefold())
        if cached:
            translations[item["token"]] = cached
            continue
        missing += 1
        print(f"Đang dịch riêng cụm R19 {item['token']} bằng Gemini API...")
        translation = request_word_translation(
            source,
            item["token"],
            model,
            generate=generate,
        )
        translations[item["token"]] = translation
        cached_translations[source.casefold()] = translation
        save_word_translation(source, translation)
    print(f"Dịch R19: dùng lại {len(entries) - missing} cụm, gọi API cho {missing} cụm mới.")
    return translations


def _uppercase_first_letter(value):
    return re.sub(r"[^\W\d_]", lambda match: match.group(0).upper(), value, count=1)


def _title_case_translation(value):
    result = []
    at_word_start = True
    for character in str(value or ""):
        if character.isalpha():
            result.append(character.upper() if at_word_start else character)
            at_word_start = False
        else:
            result.append(character)
            at_word_start = not character.isdigit()
    return "".join(result)


def _is_sentence_start(prefix):
    trailing_space = re.search(r"\s*$", prefix).group(0)
    previous = prefix[: len(prefix) - len(trailing_space)].rstrip()
    if not previous or "\n" in trailing_space:
        return True
    if previous[-1] in ".?!;…。？！；“\"([{‘":
        return True
    if re.search(r"[.?!…。？！][\"”’]$", previous):
        return True
    if previous[-1] in "—–-":
        line_before_dash = previous[:-1].rsplit("\n", 1)[-1].strip()
        return not line_before_dash or re.fullmatch(r"(?:[-*+>]|\d+[.)])", line_before_dash) is not None
    return False


def restore_text(text, entries, translations, *, is_title=False):
    result = normalize_placeholder_variants(text, entries)
    for item in entries:
        token = item["token"]
        translation = translations[token]

        def replace(match):
            if is_title:
                return _title_case_translation(translation)
            prefix = result[:match.start()]
            return _uppercase_first_letter(translation) if _is_sentence_start(prefix) else translation

        result = re.sub(re.escape(token), replace, result)
    return result


def normalize_placeholder_variants(text, entries):
    """Canonicalize placeholder forms rewritten by Markdown-capable models."""
    result = str(text or "").replace("\\_", "_")
    for item in entries:
        token = item["token"]
        core = token.strip("_")
        pattern = re.compile(
            rf"(?<![A-Za-z0-9])(?:\*\*|__)?{re.escape(core)}(?:\*\*|__)?(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        result = pattern.sub(token, result)
    return result


def restore_results(results, entries, translations):
    normalized = [
        tuple(normalize_placeholder_variants(value, entries) for value in result)
        for result in results
    ]
    combined = "\n".join(value for result in normalized for value in result)
    missing = [item["token"] for item in entries if item["token"] not in combined]
    if missing:
        raise ValueError("AI làm mất mã giữ chỗ R19: " + ", ".join(missing))
    return [
        (
            restore_text(title, entries, translations, is_title=True),
            restore_text(content, entries, translations),
        )
        for title, content in normalized
    ]
