"""Prompt context built from pronoun history."""

from cores.config.runtime import int_option
from cores.pronouns.matching import name_matches_any
from cores.pronouns.normalize import (
    NameResolver,
    default_characters_file,
    is_narrator_name,
    load_character_roster,
    resolve_direction,
    sorted_records,
)
from cores.pronouns.storage import load_pronouns

PRONOUN_CONTEXT_HEADER = """## 📌 Bộ nhớ xưng hô nhân vật
Cách áp dụng:
- Mục 🔒 ĐÃ KHÓA là quy tắc người dùng đã xác nhận: BẮT BUỘC tuân theo.
- Cặp tự xưng/gọi bên dưới là XƯNG HÔ NỀN đã ghi nhận: giữ nguyên để bản dịch nhất quán.
- Khi dịch lại một chương, áp dụng cả chỉnh sửa thủ công của người dùng ở chính chương đó.
- Chỉ đổi xưng hô nền khi chương hiện tại có biến cố quan hệ rõ ràng trong nguyên tác (lộ thân phận, thổ lộ, trở mặt, kết nghĩa, giả trang trước người khác...).
- Cảm xúc nhất thời (giận, đùa, mỉa mai, hoảng hốt) thể hiện bằng giọng điệu, từ ngữ và tiểu từ cuối câu; KHÔNG tự ý đổi hệ đại từ.
- "Cách gọi tạm thời" chỉ là ghi chú ngữ cảnh, chỉ dùng khi nguyên tác thật sự có cách gọi tương tự."""


def collect_directions(memory, resolver, before_chapter=None):
    """Group every record by canonical (speaker, listener) across all stored pairs.

    Canonicalizing at read time also repairs legacy data where one character
    was stored under several names ("Egi" / "Eginaya", "Tôi" / "Nhân vật chính").
    """
    directions = {}
    for data in memory.values():
        if not isinstance(data, dict):
            continue
        locked = bool(data.get("locked"))
        for record in data.get("timeline", []) or []:
            if not isinstance(record, dict):
                continue
            chapter = record.get("chapter_number", 0) or 0
            if before_chapter is not None:
                if chapter > before_chapter:
                    continue
                if chapter == before_chapter and record.get("source") != "manual":
                    continue
            speaker = resolver.canonical(record.get("speaker", ""))
            listener = resolver.canonical(record.get("listener", ""))
            if not speaker or not listener or speaker == listener:
                continue
            directions.setdefault((speaker, listener), []).append(
                {**record, "speaker": speaker, "listener": listener, "_locked": locked}
            )
    return {
        key: sorted_records(
            [record for record in records if record.get("_locked")] or records
        )
        for key, records in directions.items()
    }


def build_pair_states(directions):
    pairs = {}
    for (speaker, listener), records in directions.items():
        key = tuple(sorted((speaker, listener)))
        state = resolve_direction(records)
        state["speaker"], state["listener"] = speaker, listener
        entry = pairs.setdefault(key, {"characters": list(key), "directions": [], "locked": False})
        entry["directions"].append(state)
        entry["locked"] = entry["locked"] or any(item.get("_locked") for item in records)
    for entry in pairs.values():
        entry["directions"].sort(key=lambda item: (item["speaker"], item["listener"]))
        entry["latest_chapter"] = max(
            (item.get("chapter_number", 0) or 0 for item in entry["directions"]), default=0
        )
    return pairs


def _relevance(entry, glossary_names, resolver):
    if not glossary_names:
        return 0
    return sum(
        name_matches_any(resolver.aliases(name), glossary_names)
        for name in entry["characters"]
    )


def _direction_line(state):
    self_pronoun = state["speaker_self"] or "?"
    listener_pronoun = state["speaker_to_listener"] or "?"
    line = (
        f"  • {state['speaker']} → {state['listener']}: "
        f"tự xưng [{self_pronoun}] | gọi đối phương [{listener_pronoun}]"
    )
    since = state.get("since_chapter")
    if since not in (None, "", 0) and since != state.get("chapter_number"):
        line += f" (ổn định từ chương {since})"
    previous = state.get("previous")
    if previous:
        verb = "vừa đổi" if state.get("changed") else "đã đổi"
        line += (
            f"\n    ↳ {verb} so với chương {previous.get('chapter_number', '?')}: "
            f"{previous['speaker_self']}/{previous['speaker_to_listener']} → "
            f"{self_pronoun}/{listener_pronoun}"
        )
    if state.get("temporary_address"):
        line += (
            f"\n    ↳ Cách gọi tạm thời gần nhất: \"{state['temporary_address']}\" "
            "(cảm xúc nhất thời, không phải xưng hô nền)"
        )
    return line


def format_pronoun_context(
    current_chapter_number, pronouns_file, max_pairs=None, glossary_names=None,
    characters_file=None,
):
    """Tạo context xưng hô chi tiết để inject vào prompt dịch."""
    if max_pairs is None:
        max_pairs = min(50, int_option("pronoun_context_pairs", 10, minimum=1))
    memory = load_pronouns(pronouns_file)
    if not memory:
        return ""
    if characters_file is None:
        characters_file = default_characters_file(pronouns_file)
    resolver = NameResolver(load_character_roster(characters_file))
    pairs = build_pair_states(
        collect_directions(memory, resolver, before_chapter=current_chapter_number)
    )
    glossary_names = list(glossary_names or [])

    scored = []
    for entry in pairs.values():
        if not any(
            state["speaker_self"] or state["speaker_to_listener"]
            for state in entry["directions"]
        ):
            continue
        relevance = _relevance(entry, glossary_names, resolver)
        narrator = any(is_narrator_name(name) or name == resolver.narrator for name in entry["characters"])
        scored.append((relevance, entry["locked"], narrator, entry["latest_chapter"], entry))

    if glossary_names:
        # Locking controls authority, not relevance. Known characters with no
        # matching history must not pull unrelated rules into this chapter.
        scored = [item for item in scored if item[0]]
        scored.sort(key=lambda item: item[:4], reverse=True)
        locked_pairs = [item for item in scored if item[1]]
        other_pairs = [item for item in scored if not item[1]]
        selected = locked_pairs + other_pairs[:max(0, max_pairs - len(locked_pairs))]
    else:
        # Without identified characters, use a bounded recent-history fallback.
        scored.sort(key=lambda item: (item[3], item[1], item[2]), reverse=True)
        selected = scored[:max(0, max_pairs)]
    if not selected:
        return ""

    blocks = [PRONOUN_CONTEXT_HEADER]
    for _relevance_score, locked, _narrator, latest_chapter, entry in selected:
        first, second = entry["characters"]
        lines = [f"▸ **{first} ↔ {second}** (cập nhật chương {latest_chapter}):"]
        if locked:
            lines.append("  🔒 QUY TẮC ĐÃ ĐƯỢC NGƯỜI DÙNG XÁC NHẬN — PHẢI ƯU TIÊN")
        for state in entry["directions"]:
            if state["speaker_self"] or state["speaker_to_listener"]:
                lines.append(_direction_line(state))
        newest = max(
            entry["directions"], key=lambda item: item.get("chapter_number", 0) or 0
        )
        relationship = next(
            (
                state["relationship_status"]
                for state in sorted(
                    entry["directions"],
                    key=lambda item: item.get("chapter_number", 0) or 0,
                    reverse=True,
                )
                if state["relationship_status"]
            ),
            "",
        )
        if relationship:
            lines.append(f"  • Trạng thái quan hệ: {relationship}")
        if newest.get("emotional_tone"):
            lines.append(f"  • Giọng điệu gần nhất: {newest['emotional_tone']}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
