"""Persistent R19 source-to-translation mappings."""

from cores.storage.data_paths import R19_WORDS_FILE, ensure_user_data_migrated

ensure_user_data_migrated()


def load_word_mappings():
    try:
        lines = R19_WORDS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], {}
    terms, translations, seen = [], {}, set()
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


def save_word_translation(source, translation):
    try:
        lines = R19_WORDS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    key = source.casefold()
    for index, line in enumerate(lines):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        existing_source = value.partition("=")[0].strip()
        if existing_source.casefold() == key:
            lines[index] = f"{existing_source} = {translation}"
            break
    else:
        lines.append(f"{source} = {translation}")
    temporary = R19_WORDS_FILE.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(R19_WORDS_FILE)
