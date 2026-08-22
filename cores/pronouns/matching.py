"""Character-name matching used by glossary-aware pronoun selection."""

import re
import unicodedata


def _normalized_name_tokens(name):
    normalized = unicodedata.normalize("NFKC", str(name or "")).casefold()
    return re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)


def _name_matches_glossary(character_name, glossary_name):
    character_tokens = _normalized_name_tokens(character_name)
    glossary_tokens = _normalized_name_tokens(glossary_name)
    if not character_tokens or not glossary_tokens:
        return False
    if character_tokens == glossary_tokens:
        return True

    shorter, longer = sorted((character_tokens, glossary_tokens), key=len)
    if len(shorter) < 2:
        return False
    width = len(shorter)
    return any(
        longer[index : index + width] == shorter
        for index in range(len(longer) - width + 1)
    )


def pair_glossary_relevance(data, glossary_names):
    characters = [str(name) for name in data.get("characters", []) if name]
    return sum(
        any(_name_matches_glossary(character, glossary) for glossary in glossary_names)
        for character in characters[:2]
    )
