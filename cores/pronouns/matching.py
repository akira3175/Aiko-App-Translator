"""Character-name matching used by glossary-aware pronoun selection."""

import re
import unicodedata

# Common words that must not make two different names match on their own.
_GENERIC_TOKENS = {
    "anh", "chị", "em", "cô", "chú", "bác", "ông", "bà", "cậu", "mẹ", "cha", "bố",
    "con", "ngài", "nàng", "hắn", "gã", "tôi", "ta", "người", "nhân", "vật", "chính",
    "của", "và", "the", "of", "lady", "lord", "sir", "miss", "mr", "mrs", "ms",
    "công", "chúa", "hoàng", "tử", "đế", "vương", "tiểu", "thư", "thiếu", "gia",
    "đại", "tiên", "sinh", "sư", "phụ", "huynh", "đệ", "tỷ", "muội",
}


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
    if len(shorter) == 1:
        # Single-token names ("Shironia" vs "Công chúa Shironia") are common in
        # light novels; accept them when the token is distinctive enough.
        token = shorter[0]
        if token in _GENERIC_TOKENS or (len(token) < 3 and token.isascii()):
            return False
        return token in longer
    width = len(shorter)
    return any(
        longer[index : index + width] == shorter
        for index in range(len(longer) - width + 1)
    )


def name_matches_any(names, glossary_names):
    return any(
        _name_matches_glossary(name, glossary)
        for name in names
        for glossary in glossary_names
    )


def pair_glossary_relevance(data, glossary_names, resolver=None):
    characters = [str(name) for name in data.get("characters", []) if name]
    score = 0
    for character in characters[:2]:
        names = resolver.aliases(character) if resolver else [character]
        if name_matches_any(names, glossary_names):
            score += 1
    return score
