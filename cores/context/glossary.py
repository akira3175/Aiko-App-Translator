"""Parse and filter glossary.txt entries against source text."""

import re


def glossary_source_is_relevant(source, raw_text):
    searchable = (raw_text or "").casefold()
    source_folded = source.casefold()
    if source_folded in searchable:
        return True

    raw_cjk_terms = re.findall(
        r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]+", searchable
    )
    if any(term in source_folded for term in raw_cjk_terms):
        return True

    source_words = set(re.findall(r"[^\W_]+", source_folded, flags=re.UNICODE))
    raw_words = set(re.findall(r"[^\W_]+", searchable, flags=re.UNICODE))
    return bool(source_words & raw_words)


def filter_glossary(glossary_text, raw_text):
    """Keep glossary entries related to words found in the given chapters."""
    matched = []
    for line in str(glossary_text or "").splitlines():
        source, separator, _target = line.partition("=")
        source = source.strip()
        if separator and source and glossary_source_is_relevant(source, raw_text):
            matched.append(line.strip())
    return "\n".join(matched)
