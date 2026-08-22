"""Restore R19 placeholders in translated results."""

import re


def _uppercase_first_letter(value):
    return re.sub(r"[^\W\d_]", lambda match: match.group(0).upper(), value, count=1)


def _title_case_translation(value):
    result, at_word_start = [], True
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
        line = previous[:-1].rsplit("\n", 1)[-1].strip()
        return not line or re.fullmatch(r"(?:[-*+>]|\d+[.)])", line) is not None
    return False


def normalize_placeholder_variants(text, entries):
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


def restore_text(text, entries, translations, *, is_title=False):
    result = normalize_placeholder_variants(text, entries)
    for item in entries:
        token, translation = item["token"], translations[item["token"]]

        def replace(match):
            if is_title:
                return _title_case_translation(translation)
            return _uppercase_first_letter(translation) if _is_sentence_start(result[:match.start()]) else translation

        result = re.sub(re.escape(token), replace, result)
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
