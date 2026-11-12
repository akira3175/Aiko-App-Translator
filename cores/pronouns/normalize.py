"""Normalization helpers shared by pronoun extraction, prompt context and editing.

Pronoun memory stores both directions of a character pair (A → B and B → A) in
one timeline. Every consumer must therefore group records by direction before
looking at "latest" or "previous" values, otherwise the two directions are
compared with each other and look like a pronoun change.
"""

import os
import re
import unicodedata

NARRATOR_NAME = "Nhân vật chính (Tôi)"

_PLACEHOLDER_RE = re.compile(
    r"^(?:"
    r"|\?+|-+|—+|…+|\.+"
    r"|none|null|n/?a|unknown"
    r"|không|không rõ.*|không xác định.*|không tự xưng.*|không gọi.*|không có.*"
    r"|không dùng.*|không xưng.*|chưa rõ.*|chưa xác định.*|ngầm định.*"
    r"|tỉnh lược.*|lược bỏ.*|bỏ trống.*|trống"
    r")$"
)

_NARRATOR_ALIASES = {
    "tôi",
    "nhân vật chính",
    "nvc",
    "mc",
    "main",
    "người kể chuyện",
    "người kể",
    "narrator",
    "protagonist",
}

_GROUP_NAMES = {
    "mọi người",
    "tất cả",
    "tất cả mọi người",
    "đám đông",
    "đám người",
    "công chúng",
    "cả lớp",
    "cả nhóm",
    "khán giả",
    "dân chúng",
    "binh lính",
}

_ALIAS_FIELD_RE = re.compile(
    r"(?im)^\s*[-*+] \*\*(?:Tên gốc|Ten goc|Biệt danh / Danh hiệu|Biet danh / Danh hieu"
    r"|Biệt danh|Danh hiệu|Tên khác|Bí danh)\*\*\s*:\s*(.+)$"
)
_HEADER_RE = re.compile(r"(?m)^## (?!#)(.+?)\s*$")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]")


def fold(value):
    """Case-insensitive, whitespace-normalized comparison key."""
    text = unicodedata.normalize("NFC", str(value or "")).strip().casefold()
    return re.sub(r"\s+", " ", text)


def _tidy(value):
    text = unicodedata.normalize("NFC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip(" \t\"'“”‘’[]")


def is_placeholder(value):
    return bool(_PLACEHOLDER_RE.match(fold(_tidy(value))))


def clean_pronoun(value):
    """Drop placeholder values such as "không rõ" while keeping real alternatives."""
    text = _tidy(value)
    if not text:
        return ""
    parts = [_tidy(part) for part in re.split(r"\s*/\s*", text)]
    kept = []
    seen = set()
    for part in parts:
        if not part or is_placeholder(part):
            continue
        key = fold(part)
        if key not in seen:
            seen.add(key)
            kept.append(part)
    return " / ".join(kept)


def _name_variants(name):
    text = _tidy(name)
    variants = [text]
    outside = re.sub(r"\([^()]*\)", "", text).strip()
    if outside and outside != text:
        variants.append(outside)
    variants.extend(item.strip() for item in re.findall(r"\(([^()]+)\)", text))
    return [item for item in variants if item]


def is_narrator_name(name):
    return any(fold(variant) in _NARRATOR_ALIASES for variant in _name_variants(name))


def is_group_name(name):
    return fold(name) in _GROUP_NAMES


def default_characters_file(pronouns_file):
    if not pronouns_file:
        return None
    return os.path.join(os.path.dirname(os.path.abspath(pronouns_file)), "characters.md")


def _usable_alias(alias):
    text = _tidy(alias).strip(" -")
    if not text or is_placeholder(text):
        return ""
    if len(text) < 2 and not _CJK_RE.search(text):
        return ""
    return text


def parse_character_roster(markdown):
    """Return [(canonical_name, [aliases...])] from characters.md content."""
    matches = list(_HEADER_RE.finditer(markdown or ""))
    roster = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        header = match.group(1).strip()
        block = markdown[match.start() : end]
        header_parts = [part.strip() for part in re.split(r"\s+/\s+", header) if part.strip()]
        if not header_parts:
            continue
        canonical = header_parts[0]
        aliases = list(header_parts[1:])
        for value in _ALIAS_FIELD_RE.findall(block):
            for part in re.split(r"\s*/\s*|\s*,\s*|\s*;\s*", value):
                aliases.extend(_name_variants(part))
        cleaned = []
        for alias in aliases:
            alias = _usable_alias(alias)
            if alias and fold(alias) != fold(canonical) and alias not in cleaned:
                cleaned.append(alias)
        roster.append((canonical, cleaned))
    return roster


def load_character_roster(characters_file):
    if not characters_file or not os.path.exists(characters_file):
        return []
    try:
        with open(characters_file, "r", encoding="utf-8") as file:
            return parse_character_roster(file.read())
    except OSError:
        return []


class NameResolver:
    """Map nicknames, titles and narrator aliases to one canonical character name."""

    def __init__(self, roster=()):
        self.roster = list(roster or ())
        mapping = {}
        ambiguous = set()
        for canonical, aliases in self.roster:
            for alias in [canonical, *aliases]:
                key = fold(alias)
                if not key:
                    continue
                if key in mapping and mapping[key] != canonical:
                    ambiguous.add(key)
                else:
                    mapping[key] = canonical
        for key in ambiguous:
            mapping.pop(key, None)
        self._mapping = mapping
        self.narrator = next(
            (
                canonical
                for canonical, aliases in self.roster
                if any(is_narrator_name(alias) for alias in [canonical, *aliases])
            ),
            None,
        )

    def canonical(self, name):
        text = _tidy(name)
        if not text:
            return ""
        for variant in _name_variants(text):
            canonical = self._mapping.get(fold(variant))
            if canonical:
                return canonical
        if is_narrator_name(text):
            return self.narrator or NARRATOR_NAME
        return text

    def aliases(self, name):
        """Return canonical name plus known aliases, used for glossary matching."""
        canonical = self.canonical(name)
        names = [canonical, *(_name_variants(name))]
        for roster_name, aliases in self.roster:
            if roster_name == canonical:
                names.extend(aliases)
                break
        return list(dict.fromkeys(item for item in names if item))

    def names(self):
        return [canonical for canonical, _aliases in self.roster]


def _record_sort_key(entry):
    order, record = entry
    try:
        chapter = float(record.get("chapter_number", 0) or 0)
    except (TypeError, ValueError):
        chapter = 0
    manual = 1 if record.get("source") == "manual" else 0
    return chapter, manual, order


def sorted_records(records):
    """Sort by chapter; inside one chapter manual edits win over AI records."""
    return [record for _order, record in sorted(enumerate(records), key=_record_sort_key)]


def direction_key(record):
    return (_tidy(record.get("speaker", "")), _tidy(record.get("listener", "")))


def group_directions(records):
    """Group records by (speaker, listener), each group sorted chronologically."""
    groups = {}
    for record in sorted_records(records):
        groups.setdefault(direction_key(record), []).append(record)
    return groups


def resolve_direction(records):
    """Collapse one direction's history into its effective, stable state.

    Empty or placeholder values inherit the last known value instead of erasing
    it, so a chapter where a character omits the subject does not reset memory.
    """
    records = sorted_records(records)
    current = {"speaker_self": "", "speaker_to_listener": ""}
    chapters = []  # [(chapter_number, state_after_chapter)]
    since = None
    relationship = ""
    for record in records:
        speaker_self = clean_pronoun(record.get("speaker_self"))
        to_listener = clean_pronoun(record.get("speaker_to_listener"))
        updated = {
            "speaker_self": speaker_self or current["speaker_self"],
            "speaker_to_listener": to_listener or current["speaker_to_listener"],
        }
        chapter = record.get("chapter_number", 0)
        if updated != current:
            since = chapter
        current = updated
        if chapters and chapters[-1][0] == chapter:
            chapters[-1] = (chapter, dict(current))
        else:
            chapters.append((chapter, dict(current)))
        if str(record.get("relationship_status") or "").strip():
            relationship = str(record["relationship_status"]).strip()

    latest = records[-1] if records else {}
    # `previous` is the most recent complete state that differs from the
    # current one; `changed` means that switch happened in the latest chapter.
    previous = None
    changed = False
    for index in range(len(chapters) - 1, 0, -1):
        before_chapter, before = chapters[index - 1]
        after = chapters[index][1]
        if before != after and before["speaker_self"] and before["speaker_to_listener"]:
            previous = {**before, "chapter_number": before_chapter}
            changed = index == len(chapters) - 1
            break

    return {
        "speaker": latest.get("speaker", ""),
        "listener": latest.get("listener", ""),
        "speaker_self": current["speaker_self"],
        "speaker_to_listener": current["speaker_to_listener"],
        "chapter_number": latest.get("chapter_number", 0),
        "since_chapter": since,
        "previous": previous,
        "changed": changed,
        "relationship_status": relationship,
        "emotional_tone": str(latest.get("emotional_tone") or "").strip(),
        "temporary_address": clean_pronoun(latest.get("temporary_address")),
        "record": latest,
    }


def trim_timeline(timeline, per_direction=15):
    """Keep recent records plus older state changes needed for inheritance.

    State-changing records are retained as anchors, preserving original chapter
    numbers and manual provenance without fabricating values in AI records.
    """
    groups = {}
    for entry in sorted(enumerate(timeline), key=_record_sort_key):
        groups.setdefault(direction_key(entry[1]), []).append(entry)
    keep = set()
    for entries in groups.values():
        keep.update(order for order, _record in entries[-per_direction:])
        current = {"speaker_self": "", "speaker_to_listener": ""}
        relationship_anchor = None
        for order, record in entries[:-per_direction]:
            updated = {
                field: clean_pronoun(record.get(field)) or value
                for field, value in current.items()
            }
            if updated != current or record.get("source") == "manual":
                keep.add(order)
            current = updated
            if str(record.get("relationship_status") or "").strip():
                relationship_anchor = order
        if relationship_anchor is not None:
            keep.add(relationship_anchor)
    return [
        record
        for order, record in sorted(enumerate(timeline), key=_record_sort_key)
        if order in keep
    ]
