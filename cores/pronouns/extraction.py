"""AI extraction and timeline updates for pronoun memory."""

import json
import time

from cores.json_output import parse_complete_json_object
from cores.pronouns.normalize import (
    NARRATOR_NAME,
    NameResolver,
    clean_pronoun,
    default_characters_file,
    fold,
    is_group_name,
    load_character_roster,
    trim_timeline,
)
from cores.pronouns.storage import edit_pronouns

MAX_SOURCE_CHARS = 15000
MAX_ROSTER_NAMES = 80
MAX_ATTEMPTS = 6
RECORDS_PER_DIRECTION = 15


def build_pronoun_instructions(resolver=None):
    """Shared schema and extraction rules for polish and the fallback model."""
    resolver = resolver or NameResolver()
    roster_lines = []
    for canonical, aliases in resolver.roster[:MAX_ROSTER_NAMES]:
        alias_text = f" (còn gọi: {', '.join(aliases[:6])})" if aliases else ""
        roster_lines.append(f"- {canonical}{alias_text}")
    narrator = resolver.narrator or NARRATOR_NAME
    roster_block = (
        "\n".join(roster_lines)
        if roster_lines
        else "(Chưa có hồ sơ nhân vật — dùng tên đầy đủ nhất xuất hiện trong văn bản)"
    )
    return f"""## Danh sách nhân vật chuẩn
{roster_block}

Trích xuất các cặp xưng hô TRONG HỘI THOẠI giữa các nhân vật, xuất JSON đúng format:
{{
  "character_pairs": [
    {{
      "speaker": "Tên chuẩn của người nói",
      "listener": "Tên chuẩn của người nghe",
      "speaker_self": "đại từ người nói tự xưng (tôi/ta/anh/em/tớ/con/...) hoặc \\"\\"",
      "speaker_to_listener": "đại từ/danh xưng người nói gọi người nghe (cậu/anh/ngươi/mẹ/tiểu thư/...) hoặc \\"\\"",
      "temporary_address": "cách gọi nhất thời theo cảm xúc (lời mắng, biệt danh trêu chọc) hoặc \\"\\"",
      "relationship_status": "mô tả ngắn quan hệ hiện tại",
      "emotional_tone": "giọng điệu cảm xúc"
    }}
  ]
}}

Quy tắc bắt buộc:
- speaker/listener PHẢI dùng đúng tên trong "Danh sách nhân vật chuẩn" nếu nhân vật có trong danh sách; quy đổi mọi biệt danh, danh hiệu, tên tắt về tên chuẩn.
- Người kể chuyện ngôi thứ nhất ("tôi") dùng tên "{narrator}".
- Cả speaker và listener phải là nhân vật cụ thể; không dùng quốc gia, tổ chức, đám đông, nhóm người.
- speaker_self và speaker_to_listener chỉ ghi XƯNG HÔ NỀN (đại từ hoặc danh xưng ổn định). Nếu trong chương người nói không tự xưng hoặc không gọi trực tiếp thì để chuỗi rỗng "" — TUYỆT ĐỐI không ghi "không rõ", "không xác định", "?".
- Lời mắng, biệt danh trêu chọc, cách gọi chỉ xuất hiện do cảm xúc nhất thời thì ghi vào temporary_address, KHÔNG ghi vào speaker_to_listener.
- Mỗi chiều người nói → người nghe chỉ xuất MỘT mục. Nếu trong chương dùng nhiều cách, ghi cách chủ đạo trước, tối đa 3 cách, ngăn cách bằng " / ".
- A → B và B → A là hai mục riêng.
- Bỏ qua phần chỉ kể chuyện, không có đối thoại.
- Nếu không tìm thấy, trả về {{"character_pairs": []}}"""


def build_extraction_prompt(translation_text, source_text="", resolver=None):
    source_block = ""
    source_text = str(source_text or "").strip()
    if source_text:
        if len(source_text) > MAX_SOURCE_CHARS:
            source_text = source_text[:MAX_SOURCE_CHARS] + "\n[...đã cắt bớt...]"
        source_block = f"""
## Nguyên tác (dùng để xác định đúng AI nói với AI và mức kính ngữ)
---
{source_text}
---
"""
    return f"""Bạn là chuyên gia phân tích xưng hô trong bản dịch tiểu thuyết tiếng Việt.
{source_block}
## Bản dịch tiếng Việt cần phân tích
---
{translation_text}
---

{build_pronoun_instructions(resolver)}
- CHỈ trả về JSON, không giải thích thêm"""


def validate_pronoun_payload(data):
    """Reject malformed output before it can replace a chapter's history."""
    pairs = data.get("character_pairs") if isinstance(data, dict) else None
    if not isinstance(pairs, list) or any(
        not isinstance(pair, dict)
        or any(
            not isinstance(pair.get(field), str) or not pair[field].strip()
            for field in ("speaker", "listener")
        )
        or any(
            pair.get(field) is not None and not isinstance(pair[field], str)
            for field in (
                "speaker_self", "speaker_to_listener", "temporary_address",
                "relationship_status", "emotional_tone",
            )
        )
        for pair in pairs
    ):
        raise ValueError("character_pairs không đúng cấu trúc")
    return pairs


def _merge_value(current, incoming):
    """Combine distinct alternatives in order of appearance."""
    current = clean_pronoun(current)
    incoming = clean_pronoun(incoming)
    if not incoming:
        return current
    if not current:
        return incoming
    combined = clean_pronoun(f"{current} / {incoming}")
    parts = combined.split(" / ")
    return " / ".join(parts[:3])


def extract_pronouns_from_translation(
    chapter_id, chapter_number, translation_text, model, generate,
    switch_key=None, sleep=time.sleep, source_text="", resolver=None,
):
    """Return extracted pairs (possibly empty), or None on failure/skip."""
    if str(model).strip().lower() in {"", "none"}:
        print("Bỏ qua cập nhật xưng hô vì chưa cấu hình model.")
        return None

    resolver = resolver or NameResolver()
    prompt = build_extraction_prompt(translation_text, source_text, resolver)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw_result_text = ""
        try:
            raw_result_text = generate(prompt).strip()
            if not raw_result_text:
                print("⚠️ [DEBUG] API trả về dữ liệu rỗng! (bị mất text)")
                return None

            data = parse_complete_json_object(raw_result_text)
            if data is None:
                raise json.JSONDecodeError("Không tìm thấy JSON object hoàn chỉnh", raw_result_text, 0)
            pairs = validate_pronoun_payload(data)
            return _records_from_pairs(pairs, chapter_id, chapter_number, resolver)
        except Exception as error:
            message = str(error)
            print(f"⚠️ Lỗi khi trích xuất xưng hô (lần {attempt}/{MAX_ATTEMPTS}): {message}")
            print(f"🔍 [DEBUG] raw_result_text là: {raw_result_text!r}")
            if isinstance(error, ValueError) or "Expecting value" in message:
                if attempt >= 2:
                    print("🔔 AI trả JSON lỗi nhiều lần, bỏ qua để chương trình đi tiếp...")
                    return None
                print("🔔 JSON lỗi, thử lại một lần...")
                continue
            if attempt >= MAX_ATTEMPTS:
                print("🔔 Hết số lần thử, bỏ qua cập nhật xưng hô cho chương này.")
                return None
            if "429" in message or "RESOURCE_EXHAUSTED" in message:
                if switch_key is not None:
                    switch_key()
                print("🔔 Chờ 30s rồi thử lại...")
                sleep(30)
            elif any(code in message for code in ["500", "502", "503", "504"]):
                print("🔔 Lỗi 5xx, chờ 10s rồi thử lại...")
                sleep(10)
            else:
                print("🔔 Lỗi không mong đợi, chờ 15s rồi thử lại...")
                sleep(15)
    return None


def _records_from_pairs(pairs, chapter_id, chapter_number, resolver):
    merged = {}
    for pair in pairs if isinstance(pairs, list) else []:
        if not isinstance(pair, dict):
            continue
        speaker = resolver.canonical(pair.get("speaker", ""))
        listener = resolver.canonical(pair.get("listener", ""))
        if not speaker or not listener or speaker == listener:
            continue
        if is_group_name(speaker) or is_group_name(listener):
            continue
        direction = (speaker, listener)
        record = merged.get(direction)
        if record is None:
            record = merged[direction] = {
                "chapter_id": chapter_id,
                "chapter_number": chapter_number,
                "speaker": speaker,
                "listener": listener,
                "speaker_self": "",
                "speaker_to_listener": "",
                "temporary_address": "",
                "relationship_status": "",
                "emotional_tone": "",
            }
        for field in ("speaker_self", "speaker_to_listener", "temporary_address"):
            record[field] = _merge_value(record[field], pair.get(field, ""))
        for field in ("relationship_status", "emotional_tone"):
            value = str(pair.get(field) or "").strip()
            if value and not record[field]:
                record[field] = value

    pronoun_records = {}
    for record in merged.values():
        key = tuple(sorted([record["speaker"], record["listener"]]))
        if not record["temporary_address"]:
            record.pop("temporary_address")
        pronoun_records.setdefault(key, {"characters": list(key), "timeline": []})
        pronoun_records[key]["timeline"].append(record)
    return pronoun_records


def _find_pair_key(memory, characters, resolver=None):
    resolver = resolver or NameResolver()
    wanted = {fold(resolver.canonical(name)) for name in characters}
    direct = f"{characters[0]}---{characters[1]}"
    matches = []
    for key, data in memory.items():
        if not isinstance(data, dict):
            continue
        stored = {
            fold(resolver.canonical(name))
            for name in data.get("characters", [])[:2]
        }
        if stored == wanted:
            if data.get("locked"):
                return key
            matches.append(key)
    return direct if direct in matches else next(iter(matches), direct)


def update_pronoun_memory(
    chapter_id, chapter_number, translation_text, pronouns_file, model, generate,
    switch_key=None, sleep=time.sleep, source_text="", characters_file=None,
):
    """Cập nhật bộ nhớ xưng hô với ưu tiên cho chương gần nhất."""
    if characters_file is None:
        characters_file = default_characters_file(pronouns_file)
    resolver = NameResolver(load_character_roster(characters_file))
    new_pronouns = extract_pronouns_from_translation(
        chapter_id, chapter_number, translation_text, model=model, generate=generate,
        switch_key=switch_key, sleep=sleep, source_text=source_text, resolver=resolver,
    )
    if new_pronouns is None:
        return 0
    return _merge_pronoun_memory(chapter_id, new_pronouns, pronouns_file, resolver)


def apply_pronoun_payload(
    chapter_id, chapter_number, payload, pronouns_file, characters_file=None,
):
    """Normalize validated polish output and use the same protected merge as AI."""
    pairs = validate_pronoun_payload(payload)
    if characters_file is None:
        characters_file = default_characters_file(pronouns_file)
    resolver = NameResolver(load_character_roster(characters_file))
    records = _records_from_pairs(pairs, chapter_id, chapter_number, resolver)
    return _merge_pronoun_memory(chapter_id, records, pronouns_file, resolver)


def _merge_pronoun_memory(chapter_id, new_pronouns, pronouns_file, resolver):
    updated_keys = set()
    # AI generation stays outside the lock so users can edit while it runs.
    # Reload inside the transaction to honor edits/locks made during that wait.
    with edit_pronouns(pronouns_file) as memory:
        for key_str, data in list(memory.items()):
            if not isinstance(data, dict) or data.get("locked"):
                continue
            characters = data.get("characters", [])
            if len(characters) == 2:
                matching_key = _find_pair_key(memory, characters, resolver)
                if memory.get(matching_key, {}).get("locked"):
                    continue
            timeline = data.get("timeline", [])
            remaining = [
                item for item in timeline
                if not isinstance(item, dict)
                or item.get("chapter_id") != chapter_id
                or item.get("source") == "manual"
            ]
            if len(remaining) != len(timeline):
                updated_keys.add(key_str)
                data["timeline"] = remaining

        for data in new_pronouns.values():
            key_str = _find_pair_key(memory, data["characters"], resolver)
            if key_str in memory and memory[key_str].get("locked"):
                print(f"🔒 Giữ quy tắc xưng hô đã khóa: {key_str}")
                continue
            if key_str not in memory:
                memory[key_str] = {"characters": data["characters"], "timeline": []}
            timeline = [
                item for item in memory[key_str].get("timeline", [])
                if isinstance(item, dict)
            ]
            timeline.extend(data["timeline"])
            memory[key_str]["timeline"] = trim_timeline(timeline, RECORDS_PER_DIRECTION)
            updated_keys.add(key_str)
        # Reuse existing keys/metadata when a pair reappears in this rerun.
        # Only remove empty pairs after their replacement records are merged.
        for key_str in updated_keys:
            if not memory[key_str].get("timeline"):
                del memory[key_str]
    updated_count = len(updated_keys)
    if updated_count:
        print(f"✅ Đã cập nhật {updated_count} cặp xưng hô từ chương {chapter_id}")
    return updated_count
