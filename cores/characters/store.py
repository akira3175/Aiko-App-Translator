"""Structured character profiles.

``characters.json`` is the single editable source of truth. ``characters.md`` is
a one-way read-only export for humans; per-chapter Markdown snapshots are
rendered for AI translation, polish, and review stages.

Every attribute stores a list of entries. Each entry may carry the chapter id
(``v1_c2_s1.md``) where the information was established; entries without a
chapter come from legacy data or manual edits and are treated as "undated".
"""

import json
import re
import shutil
import unicodedata
import uuid
from pathlib import Path

from cores.pronouns.storage import _write_lock
from cores.storage.project import load_json, save_json

SCHEMA_VERSION = 1
JSON_NAME = "characters.json"
MD_NAME = "characters.md"
LEGACY_BACKUP_NAME = "characters.legacy.md"
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_VALUE_LENGTH = 2000
MAX_NOTE_LENGTH = 4000
MAX_UNCLASSIFIED_LENGTH = 100_000
SNAPSHOT_DATED_NOTE_LIMIT = 12
PROMPT_RECENT_NOTE_LIMIT = 4

FIELDS = (
    ("original_name", "Tên gốc"),
    ("aliases", "Biệt danh / Danh hiệu"),
    ("gender", "Giới tính"),
    ("age", "Tuổi / Độ tuổi"),
    ("origin", "Chủng tộc / Xuất thân"),
    ("status", "Địa vị / Chức vụ"),
    ("faction", "Phe / Tổ chức"),
    ("special_state", "Trạng thái đặc biệt (cơ thể / thân phận)"),
    ("voice", "Giọng điệu / Khẩu khí"),
    ("narration_pronoun", "Đại từ dẫn truyện (ngôi thứ ba)"),
    ("self_reference", "Tự xưng thường dùng"),
    ("address", "Xưng hô với nhân vật quan trọng"),
)
FIELD_KEYS = tuple(key for key, _label in FIELDS)
FIELD_LABELS = dict(FIELDS)
ALIAS_FIELDS = ("original_name", "aliases")
# Cumulative fields accumulate multiple active values across chapters
# (a character can hold several aliases or address relationships simultaneously).
CUMULATIVE_FIELDS = ("aliases", "address")
SOURCES = ("ai", "user", "legacy")

_CHAPTER_RE = re.compile(r"^v(\d+)_c(\d+)_s(\d+)(?:\.md)?$", re.IGNORECASE)
_FIELD_LINE_RE = re.compile(r"^\s*[-*+]\s+\*\*(.+?)\*\*\s*:\s*(.*)$")
_HEADER_RE = re.compile(r"(?m)^## (?!#)(.+?)\s*$")
_INLINE_CHAPTER_RE = re.compile(r"^\[(v\d+_c\d+_s\d+(?:\.md)?)\]\s*(.+)$", re.IGNORECASE)

# Prefixes of folded (accent-free) legacy labels -> field key.
_LEGACY_LABELS = (
    ("ten goc", "original_name"),
    ("biet danh", "aliases"),
    ("danh hieu", "aliases"),
    ("bi danh", "aliases"),
    ("ten khac", "aliases"),
    ("gioi tinh", "gender"),
    ("tuoi", "age"),
    ("do tuoi", "age"),
    ("chung toc", "origin"),
    ("xuat than", "origin"),
    ("dia vi", "status"),
    ("chuc vu", "status"),
    ("phe", "faction"),
    ("to chuc", "faction"),
    ("trang thai", "special_state"),
    ("giong dieu", "voice"),
    ("khau khi", "voice"),
    ("dai tu dan truyen", "narration_pronoun"),
    ("tu xung", "self_reference"),
    ("xung ho voi", "address"),
)
_KNOWN_SECTIONS = {"thong tin co ban", "thong tin theo chuong", "xung ho", "ghi chu dich thuat"}
_NOTE_SECTIONS = {"ghi chu dich thuat", "dien bien", "dien bien theo chuong"}


# --------------------------------------------------------------------------- helpers


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def fold(value):
    text = unicodedata.normalize("NFC", str(value or "")).strip().casefold()
    return re.sub(r"\s+", " ", text)


def _ascii_fold(value):
    text = unicodedata.normalize("NFD", str(value or "")).replace("đ", "d").replace("Đ", "D")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"\([^()]*\)", " ", text.casefold())
    return re.sub(r"\s+", " ", text).strip()


def chapter_key(chapter_id):
    match = _CHAPTER_RE.match(str(chapter_id or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def normalize_chapter(value):
    """Return canonical ``v1_c2_s1.md`` for valid ids, ``None`` for blank; raise for junk."""
    text = str(value or "").strip()
    if not text:
        return None
    parts = chapter_key(text)
    if not parts:
        raise ValueError(f"Mã chương không hợp lệ: “{text}” (cần dạng v1_c2_s1.md)")
    return f"v{parts[0]}_c{parts[1]}_s{parts[2]}.md"


def format_chapter_code(value):
    """Best-effort display code: ``v1_c2_s1.md`` if valid, else stripped raw value."""
    text = str(value or "").strip()
    if not text:
        return ""
    parts = chapter_key(text)
    return f"v{parts[0]}_c{parts[1]}_s{parts[2]}.md" if parts else text


def empty_document():
    return {"schema_version": SCHEMA_VERSION, "revision": 0, "characters": []}


def _entry_sort_key(entry):
    key = chapter_key(entry.get("chapter"))
    return (0, (0, 0, 0)) if key is None else (1, key)


def split_names(value):
    parts = []
    for part in re.split(r"\s*/\s*|\s*,\s*|\s*;\s*|\s*、\s*", str(value or "")):
        part = part.strip(" -")
        if not part:
            continue
        parts.append(part)
        parts.extend(item.strip() for item in re.findall(r"\(([^()]+)\)", part))
        outside = re.sub(r"\([^()]+\)", "", part).strip()
        if outside and outside != part:
            parts.append(outside)
    return [part for part in dict.fromkeys(parts) if part]


def character_names(character, *, until_key=None):
    """Return canonical name plus aliases (optionally limited to ``<= until_key``)."""
    names = [character.get("name", "")]
    for field in ALIAS_FIELDS:
        for entry in character.get("fields", {}).get(field, []):
            entry_key = chapter_key(entry.get("chapter"))
            if until_key is not None and entry_key is not None and entry_key > until_key:
                continue
            names.extend(split_names(entry.get("value")))
    return [name for name in dict.fromkeys(names) if name and name.strip()]


# --------------------------------------------------------------------------- validation


def _clean_text(value, limit, what):
    text = str(value if value is not None else "").replace("\r\n", "\n").replace("\x00", "").strip()
    if len(text) > limit:
        raise ValueError(f"{what} dài quá {limit} ký tự")
    return text


def _clean_bool(value):
    return value is True or str(value).lower() in {"1", "true", "yes", "on"}


def validate_document(data):
    """Return a normalized copy of ``data`` or raise ``ValueError``."""
    if not isinstance(data, dict):
        raise ValueError("Hồ sơ nhân vật phải là object JSON")
    characters = data.get("characters", [])
    if not isinstance(characters, list):
        raise ValueError("Trường characters phải là danh sách")
    cleaned = []
    seen_names = {}
    seen_ids = set()
    for position, raw in enumerate(characters, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Nhân vật thứ {position} không hợp lệ")
        name = _clean_text(raw.get("name"), 200, f"Tên nhân vật thứ {position}")
        if not name:
            raise ValueError(f"Nhân vật thứ {position} chưa có tên chuẩn")
        if fold(name) in seen_names:
            raise ValueError(f"Tên nhân vật bị trùng: “{name}”")
        seen_names[fold(name)] = True
        character_id = str(raw.get("id") or "").strip() or new_id("ch")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", character_id) or character_id in seen_ids:
            character_id = new_id("ch")
        seen_ids.add(character_id)

        raw_fields = raw.get("fields") or {}
        if not isinstance(raw_fields, dict):
            raise ValueError(f"Thông tin của “{name}” không hợp lệ")
        unknown = [key for key in raw_fields if key not in FIELD_KEYS]
        if unknown:
            raise ValueError(f"“{name}” có trường không hỗ trợ: {', '.join(unknown)}")
        fields = {}
        for key in FIELD_KEYS:
            entries = raw_fields.get(key) or []
            if not isinstance(entries, list):
                raise ValueError(f"“{name}” · {FIELD_LABELS[key]} phải là danh sách mốc")
            fields[key] = [
                item
                for item in (
                    _clean_entry(entry, "value", MAX_VALUE_LENGTH, f"“{name}” · {FIELD_LABELS[key]}")
                    for entry in entries
                )
                if item
            ]
            fields[key].sort(key=_entry_sort_key)
        notes_raw = raw.get("notes") or []
        if not isinstance(notes_raw, list):
            raise ValueError(f"Diễn biến của “{name}” phải là danh sách")
        notes = [
            item
            for item in (
                _clean_entry(entry, "text", MAX_NOTE_LENGTH, f"“{name}” · Diễn biến")
                for entry in notes_raw
            )
            if item
        ]
        notes.sort(key=_entry_sort_key)
        cleaned.append(
            {
                "id": character_id,
                "name": name,
                "fields": {key: value for key, value in fields.items() if value},
                "notes": notes,
                "unclassified": _clean_text(
                    raw.get("unclassified"),
                    MAX_UNCLASSIFIED_LENGTH,
                    f"Ghi chú chưa phân loại của “{name}”",
                ),
            }
        )
    cleaned.sort(key=lambda item: fold(item["name"]))
    try:
        revision = max(0, int(data.get("revision") or 0))
    except (TypeError, ValueError):
        revision = 0
    document = {"schema_version": SCHEMA_VERSION, "revision": revision, "characters": cleaned}
    if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ValueError("Hồ sơ nhân vật vượt quá 5 MB")
    return document


def _clean_entry(entry, text_key, limit, what):
    if not isinstance(entry, dict):
        raise ValueError(f"{what}: mốc không hợp lệ")
    text = _clean_text(entry.get(text_key), limit, what)
    if not text:
        return None  # Blank rows from the editor are dropped.
    try:
        chapter = normalize_chapter(entry.get("chapter"))
    except ValueError as error:
        raise ValueError(f"{what}: {error}") from None
    source = str(entry.get("source") or "user")
    entry_id = str(entry.get("id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", entry_id):
        entry_id = new_id("e")
    return {
        "id": entry_id,
        text_key: text,
        "chapter": chapter,
        "confirmed": _clean_bool(entry.get("confirmed")),
        "source": source if source in SOURCES else "user",
    }


# --------------------------------------------------------------------------- legacy migration


def _legacy_field(label):
    folded = _ascii_fold(label)
    for prefix, key in _LEGACY_LABELS:
        if folded == prefix or folded.startswith(prefix + " ") or folded.startswith(prefix + "/"):
            return key
    return None


def parse_legacy_markdown(markdown):
    """Convert legacy ``characters.md`` into a document without dropping text.

    Unknown fields, headings, or freeform text are preserved in ``unclassified``.
    Chapter milestones are never guessed; undated entries keep ``chapter: None``.
    """
    text = str(markdown or "").replace("\r\n", "\n")
    matches = list(_HEADER_RE.finditer(text))
    characters = []
    used = set()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        header = match.group(1).strip()
        parts = [part.strip() for part in re.split(r"\s+/\s+", header) if part.strip()]
        if not parts:
            continue
        name = parts[0]
        base, suffix = name, 2
        while fold(name) in used:
            name = f"{base} ({suffix})"
            suffix += 1
        used.add(fold(name))
        fields = {}
        notes = []
        unclassified = []

        def add_field(key, value):
            value = value.strip()
            if not value:
                return
            chapter = None
            inline = _INLINE_CHAPTER_RE.match(value)
            if inline:
                chapter = normalize_chapter(inline.group(1))
                value = inline.group(2).strip()
            if not value:
                return
            entries = fields.setdefault(key, [])
            if any(item.get("chapter") == chapter and fold(item["value"]) == fold(value) for item in entries):
                return
            entries.append(
                {
                    "id": new_id("e"),
                    "value": value,
                    "chapter": chapter,
                    "confirmed": False,
                    "source": "legacy",
                }
            )

        if len(parts) > 1:
            add_field("aliases", " / ".join(parts[1:]))
        section = ""
        pending_heading = ""
        for line in text[match.end() : end].split("\n"):
            stripped = line.strip()
            if not stripped or re.fullmatch(r"-{3,}|\*{3,}", stripped):
                continue
            heading = re.match(r"^#{3,6}\s+(.+)$", stripped)
            if heading:
                section = _ascii_fold(heading.group(1))
                pending_heading = (
                    ""
                    if section in _KNOWN_SECTIONS or section in _NOTE_SECTIONS
                    else stripped
                )
                continue
            field = _FIELD_LINE_RE.match(line)
            if field:
                key = _legacy_field(field.group(1))
                if key:
                    add_field(key, field.group(2))
                    continue
            bullet = re.match(r"^\s*[-*+]\s+(.+)$", line)
            if bullet and section in _NOTE_SECTIONS and not field:
                raw_note = bullet.group(1).strip()
                chapter = None
                inline = _INLINE_CHAPTER_RE.match(raw_note)
                if inline:
                    chapter = normalize_chapter(inline.group(1))
                    raw_note = inline.group(2).strip()
                if raw_note:
                    notes.append(
                        {
                            "id": new_id("e"),
                            "text": raw_note,
                            "chapter": chapter,
                            "confirmed": False,
                            "source": "legacy",
                        }
                    )
                continue
            if pending_heading:
                unclassified.append(pending_heading)
                pending_heading = ""
            unclassified.append(stripped)
        characters.append(
            {
                "id": new_id("ch"),
                "name": name,
                "fields": fields,
                "notes": notes,
                "unclassified": "\n".join(unclassified),
            }
        )
    return validate_document({"characters": characters})


# --------------------------------------------------------------------------- persistence


def project_paths(project_dir):
    project = Path(project_dir)
    return project / JSON_NAME, project / MD_NAME, project / LEGACY_BACKUP_NAME


def load_document(project_dir, *, migrate=True):
    """Load characters.json, migrating a legacy characters.md once if needed."""
    if migrate:
        with _write_lock(Path(project_dir) / JSON_NAME):
            return _load_document(project_dir, migrate=True)
    return _load_document(project_dir, migrate=False)


def _load_document(project_dir, *, migrate):
    json_path, md_path, legacy_path = project_paths(project_dir)
    if json_path.exists():
        return validate_document(load_json(json_path, {}))
    if not md_path.exists():
        return empty_document()
    document = parse_legacy_markdown(md_path.read_text(encoding="utf-8"))
    if migrate and Path(project_dir).is_dir():
        if not legacy_path.exists():
            shutil.copy2(md_path, legacy_path)
        document["revision"] = 1
        save_json(json_path, document)
        _write_export(md_path, document)
        print(f"[CHARACTERS] Đã chuyển {md_path.name} sang {json_path.name} (bản gốc: {legacy_path.name})")
    return document


def save_document(project_dir, data, *, expected_revision=None, allow_empty=False):
    with _write_lock(Path(project_dir) / JSON_NAME):
        return _save_document(project_dir, data, expected_revision=expected_revision, allow_empty=allow_empty)


def commit_ai_updates(project_dir, payload, chapters):
    with _write_lock(Path(project_dir) / JSON_NAME):
        current = _load_document(project_dir, migrate=True)
        document, stats = merge_ai_updates(current, payload, chapters)
        return _save_document(project_dir, document, allow_empty=True), stats


def _save_document(project_dir, data, *, expected_revision=None, allow_empty=False):
    json_path, md_path, _legacy = project_paths(project_dir)
    current = load_document(project_dir, migrate=False)
    if expected_revision is not None and int(expected_revision) != int(current.get("revision", 0)):
        raise ValueError(
            "Hồ sơ nhân vật vừa được cập nhật ở nơi khác (ví dụ tác vụ AI). Hãy tải lại trước khi lưu."
        )
    document = validate_document(data)
    if current["characters"] and not document["characters"] and not allow_empty:
        raise ValueError("Không thể vô tình xóa sạch hồ sơ nhân vật")
    document["revision"] = int(current.get("revision", 0)) + 1
    save_json(json_path, document, backup=json_path.exists())
    _write_export(md_path, document)
    return document


def restore_backup(project_dir):
    """Restore ``characters.json`` from ``characters.json.bak`` safely."""
    json_path, md_path, _legacy = project_paths(project_dir)
    with _write_lock(json_path):
        return _restore_backup(project_dir, json_path, md_path)


def _restore_backup(project_dir, json_path, md_path):
    backup_path = json_path.with_name(json_path.name + ".bak")
    if not backup_path.exists():
        raise ValueError("Không có bản sao lưu characters.json.bak để khôi phục")
    restored = validate_document(load_json(backup_path, {}))
    preserve_current = json_path.exists()
    try:
        current = load_document(project_dir, migrate=False)
    except (UnicodeError, ValueError):
        shutil.copy2(json_path, json_path.with_suffix(f".{uuid.uuid4().hex}.corrupt"))
        current = {}
        preserve_current = False
    restored["revision"] = max(int(current.get("revision", 0)), int(restored.get("revision", 0))) + 1
    save_json(json_path, restored, backup=preserve_current)
    _write_export(md_path, restored)
    return restored


def _write_export(md_path, document):
    md_path = Path(md_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = md_path.with_name(md_path.name + ".tmp")
    temporary.write_text(render_markdown(document), encoding="utf-8")
    temporary.replace(md_path)


# --------------------------------------------------------------------------- rendering


def _format_entry(entry, *, text_key="value", show_chapter=True):
    label = entry.get("chapter") or "chưa rõ mốc"
    lock = " 🔒" if entry.get("confirmed") else ""
    return f"[{label}] {entry[text_key]}{lock}" if show_chapter else f"{entry[text_key]}{lock}"


def render_markdown(document):
    """Full one-way read-only export containing every entry."""
    lines = [
        "# Hồ Sơ Nhân Vật",
        "",
        "> File xuất một chiều từ `characters.json`. Hãy chỉnh trực tiếp trên giao diện app; "
        "sửa file này sẽ bị ghi đè ở lần lưu sau.",
        "",
    ]
    blocks = []
    for character in document.get("characters", []):
        block = [f"## {character['name']}", ""]
        fields = character.get("fields", {})
        if fields:
            block.append("### Thông tin theo chương")
            for key in FIELD_KEYS:
                entries = fields.get(key) or []
                if not entries:
                    continue
                if key in ALIAS_FIELDS:
                    names = " / ".join(dict.fromkeys(entry["value"] for entry in entries))
                    block.append(f"- **{FIELD_LABELS[key]}**: {names}")
                    if any(entry.get("chapter") for entry in entries):
                        block.append(f"  - Mốc: {'; '.join(_format_entry(entry) for entry in entries)}")
                elif len(entries) == 1:
                    block.append(f"- **{FIELD_LABELS[key]}**: {_format_entry(entries[0])}")
                else:
                    block.append(f"- **{FIELD_LABELS[key]}**:")
                    block.extend(f"  - {_format_entry(entry)}" for entry in entries)
            block.append("")
        if character.get("notes"):
            block.append("### Diễn biến theo chương")
            block.extend(f"- {_format_entry(note, text_key='text')}" for note in character["notes"])
            block.append("")
        if character.get("unclassified"):
            block.extend(["### Ghi chú chưa phân loại", character["unclassified"], ""])
        blocks.append("\n".join(block).rstrip())
    return "\n".join(lines) + ("\n" + "\n\n---\n\n".join(blocks) if blocks else "") + "\n"


def _visible(entry, current_key):
    if current_key is None:
        return True
    key = chapter_key(entry.get("chapter"))
    return key is None or key < current_key


def _address_parts(text):
    """Split ``Listener → relation`` into ``(folded_listener, raw_listener, relation)``."""
    raw = str(text or "").strip()
    parts = re.split(r"\s*(?:→|->|[:：])\s*", raw, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        listener = parts[0].strip()
        return fold(listener), listener, parts[1].strip()
    return None, "", raw


def _format_state_entries(entries, current_key, *, value_getter=lambda entry: entry["value"]):
    dated = [entry for entry in entries if chapter_key(entry.get("chapter"))]
    undated = [entry for entry in entries if not chapter_key(entry.get("chapter"))]
    if dated:
        latest = dated[-1]
        latest_val = value_getter(latest)
        text = f"{latest_val}{' 🔒' if latest.get('confirmed') else ''} (từ {latest['chapter']}"
        previous = []
        for entry in reversed(dated[:-1]):
            val = value_getter(entry)
            if fold(val) != fold(latest_val) and val not in previous:
                previous.append(val)
            if len(previous) == 2:
                break
        if previous:
            text += "; trước đó: " + " → ".join(reversed(previous))
        text += ")"
        others = [
            value_getter(entry)
            for entry in undated
            if fold(value_getter(entry)) != fold(latest_val)
        ]
        if others:
            text += " · chưa rõ mốc: " + " / ".join(dict.fromkeys(others))
        return text
    text = " / ".join(
        dict.fromkeys(
            f"{value_getter(entry)}{' 🔒' if entry.get('confirmed') else ''}" for entry in undated
        )
    )
    if current_key is not None:
        text += " (chưa rõ mốc)"
    return text


def _field_lines(key, label, entries, current_key):
    visible = [entry for entry in entries if _visible(entry, current_key)]
    if not visible:
        return []

    if key == "aliases":
        dated = [entry for entry in visible if chapter_key(entry.get("chapter"))]
        undated = [entry for entry in visible if not chapter_key(entry.get("chapter"))]
        ordered = undated + dated
        parts = []
        seen = set()
        for entry in ordered:
            if fold(entry["value"]) in seen:
                continue
            seen.add(fold(entry["value"]))
            lock = " 🔒" if entry.get("confirmed") else ""
            if entry.get("chapter"):
                parts.append(f"{entry['value']}{lock} (từ {entry['chapter']})")
            elif current_key is not None:
                parts.append(f"{entry['value']}{lock} (chưa rõ mốc)")
            else:
                parts.append(f"{entry['value']}{lock}")
        return [f"- **{label}**: {' / '.join(parts)}"] if parts else []

    if key == "address":
        # Group by target listener so each relationship resolves to its latest state < current_key.
        grouped = {}
        order = []
        freeform = []
        for entry in visible:
            listener_key, raw_listener, relation = _address_parts(entry["value"])
            if listener_key is None:
                freeform.append(entry)
                continue
            if listener_key not in grouped:
                grouped[listener_key] = {"listener": raw_listener, "entries": []}
                order.append(listener_key)
            else:
                grouped[listener_key]["listener"] = raw_listener
            grouped[listener_key]["entries"].append((entry, relation))

        rendered = []
        for listener_key in order:
            group = grouped[listener_key]
            pair_entries = [item[0] for item in group["entries"]]
            relation_by_id = {id(item[0]): item[1] for item in group["entries"]}
            summary = _format_state_entries(
                pair_entries,
                current_key,
                value_getter=lambda entry, mapping=relation_by_id: mapping[id(entry)],
            )
            rendered.append(f"{group['listener']} → {summary}")
        for entry in freeform:
            rendered.append(_format_entry(entry))
        if not rendered:
            return []
        if len(rendered) == 1:
            return [f"- **{label}**: {rendered[0]}"]
        return [f"- **{label}**:", *(f"  - {line}" for line in rendered)]

    return [f"- **{label}**: {_format_state_entries(visible, current_key)}"]


def _in_range_changes(character, start_key, end_key):
    """Entries dated in ``[start_key, end_key)`` grouped by chapter for batch mode."""
    by_chapter = {}
    for key in FIELD_KEYS:
        for entry in character.get("fields", {}).get(key, []):
            ekey = chapter_key(entry.get("chapter"))
            if ekey is not None and start_key <= ekey < end_key:
                lock = " 🔒" if entry.get("confirmed") else ""
                by_chapter.setdefault(entry["chapter"], []).append(
                    f"{FIELD_LABELS[key]}: {entry['value']}{lock}"
                )
    for note in character.get("notes", []):
        nkey = chapter_key(note.get("chapter"))
        if nkey is not None and start_key <= nkey < end_key:
            lock = " 🔒" if note.get("confirmed") else ""
            by_chapter.setdefault(note["chapter"], []).append(f"Diễn biến: {note['text']}{lock}")
    return [
        (chapter, by_chapter[chapter])
        for chapter in sorted(by_chapter, key=lambda cid: chapter_key(cid) or (0, 0, 0))
    ]


def render_character_snapshot(character, current_key, *, batch_end_key=None):
    lines = []
    for key in FIELD_KEYS:
        lines.extend(_field_lines(key, FIELD_LABELS[key], character.get("fields", {}).get(key) or [], current_key))
    notes = [note for note in character.get("notes", []) if _visible(note, current_key)]
    dated = [note for note in notes if chapter_key(note.get("chapter"))][-SNAPSHOT_DATED_NOTE_LIMIT:]
    undated = [note for note in notes if not chapter_key(note.get("chapter"))]
    unclassified = character.get("unclassified", "")
    batch_updates = (
        _in_range_changes(character, current_key, batch_end_key)
        if current_key is not None and batch_end_key is not None and batch_end_key > current_key
        else []
    )
    if not lines and not dated and not undated and not unclassified and not batch_updates:
        return ""
    block = [f"## {character['name']}"]
    if lines:
        block += ["", "### Thông tin đã xác lập", *lines]
    if dated or undated:
        block += ["", "### Diễn biến đã biết"]
        block += [f"- {_format_entry(note, text_key='text')}" for note in undated + dated]
    if batch_updates:
        block += ["", "### Thay đổi theo mốc trong batch (chỉ áp dụng từ chương ghi nhận trở đi)"]
        for chapter, items in batch_updates:
            for item in items:
                block.append(f"- [{chapter}] {item}")
    if unclassified:
        block += ["", "### Ghi chú chưa phân loại (chưa rõ mốc)", unclassified]
    return "\n".join(block)


def _alias_score(alias, searchable):
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", alias).casefold().strip())
    if not normalized:
        return 0
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]", normalized):
        return searchable.count(normalized)
    return len(re.findall(rf"(?<!\w){re.escape(normalized)}(?!\w)", searchable))


def render_snapshot(document, chapter_id=None, relevant_text=None, max_characters=20):
    """Markdown with the state established *before* ``chapter_id``.

    Entries dated at or after ``chapter_id`` are excluded. When ``relevant_text``
    is provided, only characters mentioned in it are included (ranked by hits).
    """
    current_key = chapter_key(chapter_id)
    searchable = None
    if relevant_text is not None:
        searchable = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", relevant_text or "").casefold())
    ranked = []
    for order, character in enumerate(document.get("characters", [])):
        block = render_character_snapshot(character, current_key)
        if not block:
            continue
        score = 1
        if searchable is not None:
            names = character_names(character, until_key=current_key)
            score = sum(min(_alias_score(alias, searchable), 5) for alias in names)
            if not score:
                continue
        ranked.append((score, -order, block))
    if not ranked:
        return ""
    ranked.sort(reverse=True)
    selected = sorted(ranked[: max(1, int(max_characters))], key=lambda item: -item[1])
    if current_key is not None:
        chapter = normalize_chapter(chapter_id)
        intro = (
            f"> Trạng thái đã xác lập TRƯỚC chương {chapter}. Thay đổi xảy ra trong chính chương này "
            "không có ở đây — hãy áp dụng theo đúng vị trí biến cố trong nguyên tác. "
            "Mục “chưa rõ mốc” là dữ liệu chưa xác định thời điểm, chỉ dùng khi phù hợp với nguyên tác. "
            "🔒 = người dùng đã xác nhận."
        )
    else:
        intro = "> 🔒 = người dùng đã xác nhận. Mục “chưa rõ mốc” chỉ dùng khi phù hợp với nguyên tác."
    return "# Hồ Sơ Nhân Vật Liên Quan\n\n" + intro + "\n\n" + "\n\n---\n\n".join(
        item[2] for item in selected
    ) + "\n"


def render_batch_snapshot(document, chapter_ids, relevant_text=None, max_characters=20):
    """Markdown for a multi-chapter batch: baseline before first chapter + per-chapter updates."""
    valid = [(chapter_key(cid), normalize_chapter(cid)) for cid in (chapter_ids or []) if chapter_key(cid)]
    if not valid:
        return render_snapshot(document, None, relevant_text, max_characters)
    valid.sort()
    first_key, first_chapter = valid[0]
    last_key, last_chapter = valid[-1]
    if first_key == last_key:
        return render_snapshot(document, first_chapter, relevant_text, max_characters)

    searchable = None
    if relevant_text is not None:
        searchable = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", relevant_text or "").casefold())
    ranked = []
    for order, character in enumerate(document.get("characters", [])):
        block = render_character_snapshot(character, first_key, batch_end_key=last_key)
        if not block:
            continue
        score = 1
        if searchable is not None:
            names = character_names(character, until_key=last_key)
            score = sum(min(_alias_score(alias, searchable), 5) for alias in names)
            if not score:
                continue
        ranked.append((score, -order, block))
    if not ranked:
        return ""
    ranked.sort(reverse=True)
    selected = sorted(ranked[: max(1, int(max_characters))], key=lambda item: -item[1])
    intro = (
        f"> Trạng thái nền đã xác lập TRƯỚC chương {first_chapter} (batch {first_chapter} → {last_chapter}). "
        "Các mục trong phần “Thay đổi theo mốc trong batch” chỉ áp dụng từ đúng chương ghi nhận trở đi, "
        "tuyệt đối không dùng ngược cho chương trước đó. 🔒 = người dùng đã xác nhận."
    )
    return "# Hồ Sơ Nhân Vật Liên Quan\n\n" + intro + "\n\n" + "\n\n---\n\n".join(
        item[2] for item in selected
    ) + "\n"


def summarize_document_for_prompt(document):
    """Compact summary of existing characters sent to AI during profile analysis."""
    characters = (document or {}).get("characters") or []
    if not characters:
        return "(Chưa có dữ liệu nhân vật)"
    blocks = []
    for character in characters:
        lines = [f"## {character['name']} (id: {character['id']})"]
        for key in FIELD_KEYS:
            entries = character.get("fields", {}).get(key) or []
            if not entries:
                continue
            if key in CUMULATIVE_FIELDS:
                summary = "; ".join(_format_entry(entry) for entry in entries)
                lines.append(f"- {key} ({FIELD_LABELS[key]}): {summary}")
            else:
                latest = entries[-1]
                lines.append(f"- {key} ({FIELD_LABELS[key]}): {_format_entry(latest)}")
        notes = character.get("notes") or []
        if notes:
            recent = notes[-PROMPT_RECENT_NOTE_LIMIT:]
            lines.append("- events gần nhất:")
            lines.extend(f"  - {_format_entry(note, text_key='text')}" for note in recent)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def roster(document):
    """Return ``[(canonical_name, [aliases...])]`` for name resolution."""
    result = []
    for character in document.get("characters", []):
        names = character_names(character)
        canonical = character["name"]
        aliases = [name for name in names if fold(name) != fold(canonical)]
        result.append((canonical, aliases))
    return result


def roster_for_characters_file(characters_file):
    """Roster from a sibling characters.json, or ``None`` when it does not exist."""
    if not characters_file:
        return None
    json_path = Path(characters_file).with_name(JSON_NAME)
    if not json_path.exists():
        return None
    try:
        return roster(validate_document(load_json(json_path, {})))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------- AI merge


def find_character(document, name="", character_id=""):
    if character_id:
        for character in document["characters"]:
            if character["id"] == character_id:
                return character
    wanted = fold(name)
    if not wanted:
        return None
    for character in document["characters"]:
        if fold(character["name"]) == wanted:
            return character
    for character in document["characters"]:
        if any(fold(alias) == wanted for alias in character_names(character)):
            return character
    return None


def _normalize_allowed_chapters(allowed_chapters):
    allowed = {}
    for item in allowed_chapters or ():
        raw = str(item or "").strip()
        if not raw:
            continue
        if chapter_key(raw):
            norm = normalize_chapter(raw)
            allowed[norm] = norm
            allowed[norm[:-3]] = norm
        else:
            allowed[raw.lower()] = raw
    return allowed


def _ai_chapter(value, allowed_map):
    raw = str(value or "").strip()
    if not raw:
        return False, None
    key = raw.lower()
    if chapter_key(raw):
        norm = normalize_chapter(raw)
        if norm in allowed_map:
            return True, allowed_map[norm]
        if norm[:-3] in allowed_map:
            return True, allowed_map[norm[:-3]]
        return False, None
    if key in allowed_map:
        mapped = allowed_map[key]
        return True, (mapped if chapter_key(mapped) else None)
    return False, None


def merge_ai_updates(document, payload, allowed_chapters):
    """Append AI findings without overwriting history or user-confirmed data.

    Returns ``(document, stats)``. Entries whose chapter is not in
    ``allowed_chapters`` are rejected instead of guessed.
    """
    allowed_map = _normalize_allowed_chapters(allowed_chapters)
    stats = {"added_characters": 0, "added_entries": 0, "added_notes": 0, "skipped": 0, "rejected": 0}
    items = payload.get("characters") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("JSON hồ sơ nhân vật thiếu danh sách characters")
    for item in items:
        if not isinstance(item, dict):
            stats["rejected"] += 1
            continue
        name = _clean_text(item.get("name"), 200, "Tên nhân vật")
        character = find_character(document, name, str(item.get("id") or "").strip())
        if character is None:
            if not name:
                stats["rejected"] += 1
                continue
            character = {"id": new_id("ch"), "name": name, "fields": {}, "notes": [], "unclassified": ""}
            document["characters"].append(character)
            stats["added_characters"] += 1
        for update in item.get("updates") or []:
            if not isinstance(update, dict):
                stats["rejected"] += 1
                continue
            field = str(update.get("field") or "").strip()
            value = str(update.get("value") or "").strip()[:MAX_VALUE_LENGTH]
            ok, chapter = _ai_chapter(update.get("chapter"), allowed_map)
            if field not in FIELD_KEYS or not value or not ok:
                stats["rejected"] += 1
                continue
            if _append_field(character, field, value, chapter):
                stats["added_entries"] += 1
            else:
                stats["skipped"] += 1
        for event in item.get("events") or []:
            if not isinstance(event, dict):
                stats["rejected"] += 1
                continue
            text = str(event.get("text") or "").strip()[:MAX_NOTE_LENGTH]
            ok, chapter = _ai_chapter(event.get("chapter"), allowed_map)
            if not text or not ok:
                stats["rejected"] += 1
                continue
            notes = character.setdefault("notes", [])
            if any(note.get("chapter") == chapter and fold(note["text"]) == fold(text) for note in notes):
                stats["skipped"] += 1
                continue
            notes.append(
                {"id": new_id("e"), "text": text, "chapter": chapter, "confirmed": False, "source": "ai"}
            )
            stats["added_notes"] += 1
    return validate_document(document), stats


def _append_field(character, field, value, chapter):
    entries = character.setdefault("fields", {}).setdefault(field, [])
    new_key = chapter_key(chapter)

    # Exact duplicate at same chapter (or same folded value already present).
    for entry in entries:
        if entry.get("chapter") == chapter and fold(entry["value"]) == fold(value):
            return False

    confirmed = [entry for entry in entries if entry.get("confirmed")]
    if field == "address":
        target, _raw, relation = _address_parts(value)
        for entry in confirmed:
            if entry.get("chapter") in (None, chapter):
                locked, _lraw, _lrel = _address_parts(entry["value"])
                if not locked or not target or locked == target:
                    return False
        if target is not None and new_key is not None:
            same_listener = [
                (entry, _address_parts(entry["value"])[2])
                for entry in entries
                if _address_parts(entry["value"])[0] == target
            ]
            effective = [
                (entry, rel)
                for entry, rel in same_listener
                if chapter_key(entry.get("chapter")) and chapter_key(entry["chapter"]) <= new_key
            ]
            if effective and fold(sorted(effective, key=lambda item: _entry_sort_key(item[0]))[-1][1]) == fold(relation):
                return False
            if not effective and any(
                not chapter_key(entry.get("chapter")) and fold(rel) == fold(relation)
                for entry, rel in same_listener
            ):
                return False
    if field == "aliases" or (field == "address" and target is None):
        # Cumulative fields: skip if value already exists at or before new_key (or undated).
        for entry in entries:
            ekey = chapter_key(entry.get("chapter"))
            if fold(entry["value"]) == fold(value) and (
                ekey is None or new_key is None or ekey <= new_key
            ):
                return False
    elif field not in CUMULATIVE_FIELDS:
        # State fields: protect confirmed entries from AI overwrite at the same chapter,
        # and protect undated confirmed user rules from AI replacement.
        for entry in confirmed:
            ekey = chapter_key(entry.get("chapter"))
            if ekey is None or new_key is None or ekey == new_key:
                return False
        # Skip if the value effective at this chapter is already identical.
        if new_key is not None:
            effective = [
                entry
                for entry in entries
                if chapter_key(entry.get("chapter")) and chapter_key(entry["chapter"]) <= new_key
            ]
            if effective and fold(sorted(effective, key=_entry_sort_key)[-1]["value"]) == fold(value):
                return False
            if not effective and any(
                not chapter_key(entry.get("chapter")) and fold(entry["value"]) == fold(value)
                for entry in entries
            ):
                return False
        elif any(fold(entry["value"]) == fold(value) for entry in entries):
            return False

    entries.append(
        {"id": new_id("e"), "value": value, "chapter": chapter, "confirmed": False, "source": "ai"}
    )
    entries.sort(key=_entry_sort_key)
    return True
