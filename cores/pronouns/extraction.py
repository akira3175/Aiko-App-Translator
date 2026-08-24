"""AI extraction and timeline updates for pronoun memory."""

import json
import time

from cores.pronouns.storage import load_pronouns, save_pronouns
from cores.json_output import parse_complete_json_object


def extract_pronouns_from_translation(
    chapter_id, chapter_number, translation_text, model, generate,
    switch_key=None, sleep=time.sleep,
):
    """Dùng AI để trích xuất xưng hô từ bản dịch."""
    if str(model).strip().lower() in {"", "none"}:
        print("Bỏ qua cập nhật xưng hô vì chưa cấu hình model.")
        return {}

    prompt = f"""Bạn là chuyên gia phân tích xưng hô trong văn bản tiếng Việt.

Hãy đọc đoạn văn bản sau và trích xuất TẤT CẢ các cặp xưng hô giữa các nhân vật:

---
{translation_text}
---

Xuất kết quả dưới dạng JSON với format:
{{
  "character_pairs": [
    {{
      "speaker": "Tên nhân vật A",
      "listener": "Tên nhân vật B",
      "speaker_self": "cách A tự xưng (ta/tôi/anh/em/...)",
      "speaker_to_listener": "cách A gọi B (ngươi/cậu/anh/em/...)",
      "relationship_status": "mô tả ngắn trạng thái mối quan hệ hiện tại",
      "emotional_tone": "giọng điệu cảm xúc (ấm áp/lạnh lùng/quan tâm/xa cách/...)"
    }}
  ]
}}

Lưu ý:
- Chỉ trích xuất các cặp xưng hô RÕ RÀNG xuất hiện trong đoạn văn
- Cả speaker và listener phải là NHÂN VẬT CỤ THỂ có tên hoặc biệt danh xác định
- Không dùng quốc gia, tổ chức, đám đông, công chúng hoặc nhóm người làm nhân vật
- CHÚ Ý ghi nhận thay đổi trong cảm xúc và xưng hô (nếu có)
- Bỏ qua những chỗ chỉ kể chuyện, không có đối thoại
- Nếu không tìm thấy xưng hô nào, trả về {{"character_pairs": []}}
- CHỈ trả về JSON, không giải thích thêm"""

    while True:
        raw_result_text = ""
        try:
            raw_result_text = generate(prompt).strip()
            if not raw_result_text:
                print("⚠️ [DEBUG] API trả về dữ liệu rỗng! (bị mất text)")
                return {}

            data = parse_complete_json_object(raw_result_text)
            if data is None:
                raise json.JSONDecodeError("Không tìm thấy JSON object hoàn chỉnh", raw_result_text, 0)
            pronoun_records = {}
            for pair in data.get("character_pairs", []):
                speaker = pair.get("speaker", "").strip()
                listener = pair.get("listener", "").strip()
                if not speaker or not listener:
                    continue
                key = tuple(sorted([speaker, listener]))
                if key not in pronoun_records:
                    pronoun_records[key] = {"characters": list(key), "timeline": []}
                pronoun_records[key]["timeline"].append(
                    {
                        "chapter_id": chapter_id,
                        "chapter_number": chapter_number,
                        "speaker": speaker,
                        "listener": listener,
                        "speaker_self": pair.get("speaker_self", ""),
                        "speaker_to_listener": pair.get("speaker_to_listener", ""),
                        "relationship_status": pair.get("relationship_status", ""),
                        "emotional_tone": pair.get("emotional_tone", ""),
                    }
                )
            return pronoun_records
        except Exception as error:
            message = str(error)
            print(f"⚠️ Lỗi khi trích xuất xưng hô: {message}")
            print(f"🔍 [DEBUG] raw_result_text là: {raw_result_text!r}")
            if "Expecting value" in message:
                print("🔔 Bỏ qua lỗi JSON rỗng để chương trình đi tiếp...")
                return {}
            if "429" in message or "RESOURCE_EXHAUSTED" in message:
                if switch_key is not None:
                    switch_key()
                print("🔔 Chờ 30s rồi thử lại...")
                sleep(30)
            elif any(code in message for code in ["500", "502", "503", "504"]):
                print("🔔 Lỗi 5xx, chờ 10s rồi thử lại...")
                sleep(10)
            else:
                print("🔔 Lỗi không mong đợi, chờ 15s rồi thử lại không bỏ cuộc...")
                sleep(15)


def update_pronoun_memory(
    chapter_id, chapter_number, translation_text, pronouns_file, model, generate,
    switch_key=None, sleep=time.sleep,
):
    """Cập nhật bộ nhớ xưng hô với ưu tiên cho chương gần nhất."""
    memory = load_pronouns(pronouns_file)
    new_pronouns = extract_pronouns_from_translation(
        chapter_id, chapter_number, translation_text, model=model, generate=generate,
        switch_key=switch_key, sleep=sleep,
    )
    updated_count = 0
    for key, data in new_pronouns.items():
        key_str = f"{key[0]}---{key[1]}"
        if key_str in memory and memory[key_str].get("locked"):
            print(f"🔒 Giữ quy tắc xưng hô đã khóa: {key_str}")
            continue
        if key_str not in memory:
            memory[key_str] = {"characters": data["characters"], "timeline": []}
        memory[key_str]["timeline"].extend(data["timeline"])
        memory[key_str]["timeline"] = sorted(
            memory[key_str]["timeline"],
            key=lambda item: item.get("chapter_number", 0),
        )[-25:]
        updated_count += 1
    save_pronouns(memory, pronouns_file)
    if updated_count:
        print(f"✅ Đã cập nhật {updated_count} cặp xưng hô từ chương {chapter_id}")
