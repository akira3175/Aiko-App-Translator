"""Mask and remove configured R19 terms."""

import re
from copy import deepcopy

from cores.r19 import storage
from cores.config.runtime import bool_option


def enabled():
    return bool_option("r19_mode", False)


def _matcher(terms):
    return re.compile("|".join(re.escape(term) for term in terms), re.IGNORECASE)


def prepare_chapters(chapters):
    copies = deepcopy(chapters)
    if not enabled():
        return copies, []
    terms = storage.load_terms()
    if not terms:
        raise ValueError("Đã bật Dịch R19 nhưng r19_words.txt chưa có từ hoặc cụm từ nào.")
    matcher = _matcher(terms)
    entries, tokens_by_term = [], {}

    def mask(text):
        def replace(match):
            original = match.group(0)
            key = original.casefold()
            if key not in tokens_by_term:
                tokens_by_term[key] = f"__20AGE_{len(entries) + 1:04d}__"
                entries.append({"token": tokens_by_term[key], "source": original})
            return tokens_by_term[key]
        return matcher.sub(replace, str(text or ""))

    for chapter in copies:
        chapter["title"] = mask(chapter.get("title", ""))
        chapter["content"] = mask(chapter.get("content", ""))
    return copies, entries


def mask_contexts(texts, entries):
    values = [str(text or "") for text in texts]
    if not enabled():
        return values
    terms = storage.load_terms()
    if not terms:
        return values
    matcher = _matcher(terms)
    target_tokens = {item["source"].casefold(): item["token"] for item in entries}
    context_tokens = {}

    def replace(match):
        key = match.group(0).casefold()
        if key in target_tokens:
            return target_tokens[key]
        if key not in context_tokens:
            context_tokens[key] = f"__20AGE_CTX_{len(context_tokens) + 1:04d}__"
        return context_tokens[key]
    return [matcher.sub(replace, value) for value in values]


def strip_r19_terms(text):
    value = str(text or "")
    if not enabled():
        return value
    terms, translations = storage.load_word_mappings()
    blocked = terms + [item for item in translations.values() if item]
    if not blocked:
        return value
    return _matcher(sorted(set(blocked), key=len, reverse=True)).sub("", value)


def strip_previous_context(text):
    return strip_r19_terms(text)


def prepare_postprocess_chapter(chapter):
    copy = deepcopy(chapter)
    if not enabled():
        return copy, [], {}
    terms, translations = storage.load_word_mappings()
    replacements = {}
    for source in terms:
        translated = translations.get(source.casefold())
        if translated:
            replacements[source.casefold()] = translated
            replacements[translated.casefold()] = translated
    if not replacements:
        return copy, [], {}
    matcher = _matcher(sorted(replacements, key=len, reverse=True))
    entries, restore_map, tokens_by_translation = [], {}, {}

    def replace(match):
        translated = replacements[match.group(0).casefold()]
        key = translated.casefold()
        if key not in tokens_by_translation:
            token = f"__20AGE_PP_{len(entries) + 1:04d}__"
            tokens_by_translation[key] = token
            entries.append({"token": token, "source": match.group(0)})
            restore_map[token] = translated
        return tokens_by_translation[key]

    for field in ("title", "content", "title_translation", "translation"):
        copy[field] = matcher.sub(replace, str(copy.get(field, "")))
    return copy, entries, restore_map


def mask_postprocess_contexts(texts, restore_map):
    values = [str(text or "") for text in texts]
    if not enabled() or not restore_map:
        return values
    terms, translations = storage.load_word_mappings()
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
    matcher = _matcher(sorted(replacements, key=len, reverse=True))
    return [matcher.sub(lambda match: replacements[match.group(0).casefold()], value) for value in values]
