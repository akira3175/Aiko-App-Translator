"""Persistent R19 source-to-translation mappings."""

from cores.storage.data_paths import R19_WORDS_FILE, ensure_user_data_migrated

ensure_user_data_migrated()


def _words_path(path=None):
    return path or R19_WORDS_FILE


def load_word_mappings(path=None):
    path = _words_path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
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


def load_terms(path=None):
    return load_word_mappings(path)[0]


def save_word_translation(source, translation, path=None):
    path = _words_path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
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
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)
