"""Prompt context built from pronoun history."""

from cores.pronouns.matching import pair_glossary_relevance
from cores.pronouns.storage import load_pronouns


def format_pronoun_context(
    current_chapter_number, pronouns_file, max_pairs=10, glossary_names=None,
):
    """Tạo context xưng hô chi tiết để inject vào prompt dịch."""
    memory = load_pronouns(pronouns_file)
    if not memory:
        return ""

    pair_scores = []
    for key_str, data in memory.items():
        relevant = [
            item for item in data.get("timeline", [])
            if item.get("chapter_number", 0) < current_chapter_number
        ]
        if relevant:
            latest_chapter = max(item.get("chapter_number", 0) for item in relevant)
            relevance = pair_glossary_relevance(data, glossary_names or [])
            pair_scores.append(
                (key_str, data, latest_chapter, relevant, bool(data.get("locked")), relevance)
            )

    if glossary_names and any(item[5] for item in pair_scores):
        pair_scores = [item for item in pair_scores if item[5]]
    pair_scores.sort(key=lambda item: (item[5], item[4], item[2]), reverse=True)
    top_pairs = pair_scores[:max_pairs]
    if not top_pairs:
        return ""

    blocks = ["## 📌 Bộ nhớ xưng hô nhân vật (tham khảo để dịch có hồn)\n"]
    blocks.append(
        "💡 Lưu ý: Xưng hô phản ánh CẢM XÚC và MỐI QUAN HỆ. "
        "Hãy điều chỉnh linh hoạt theo diễn biến nội tâm nhân vật trong chương này.\n"
    )
    for _key, data, _latest, relevant, locked, _relevance in top_pairs:
        last = relevant[-1]
        speaker = last["speaker"]
        listener = last["listener"]
        self_pronoun = last.get("speaker_self") or "?"
        listener_pronoun = last.get("speaker_to_listener") or "?"
        relationship = last.get("relationship_status", "")
        emotion = last.get("emotional_tone", "")
        chapter_number = last.get("chapter_number", "?")

        change_note = ""
        if len(relevant) >= 2:
            previous = relevant[-2]
            previous_self = previous.get("speaker_self", "")
            previous_listener = previous.get("speaker_to_listener", "")
            if previous_self != self_pronoun or previous_listener != listener_pronoun:
                change_note = (
                    f"  ↳ Trước đó (chương {previous.get('chapter_number', '?')}): "
                    f"{previous_self}/{previous_listener} → đã thay đổi thành "
                    f"{self_pronoun}/{listener_pronoun} "
                    f"(có thể do biến chuyển cảm xúc/quan hệ)"
                )

        reverse_info = ""
        for record in reversed(relevant):
            if record.get("speaker") == listener and record.get("listener") == speaker:
                reverse_info = (
                    f"  ← Chiều ngược ({listener}→{speaker}): "
                    f"tự xưng [{record.get('speaker_self') or '?'}], "
                    f"gọi [{record.get('speaker_to_listener') or '?'}]"
                )
                if record.get("relationship_status"):
                    reverse_info += f" | quan hệ: {record['relationship_status']}"
                if record.get("emotional_tone"):
                    reverse_info += f" | giọng điệu: {record['emotional_tone']}"
                break

        line = f"▸ **{speaker} → {listener}** (chương {chapter_number}):"
        if locked:
            line += "\n  🔒 QUY TẮC ĐÃ ĐƯỢC NGƯỜI DÙNG XÁC NHẬN — PHẢI ƯU TIÊN"
        line += f"\n  • Tự xưng: [{self_pronoun}]  |  Gọi đối phương: [{listener_pronoun}]"
        if relationship:
            line += f"\n  • Trạng thái quan hệ: {relationship}"
        if emotion:
            line += f"\n  • Giọng điệu cảm xúc: {emotion}"
        if change_note:
            line += f"\n{change_note}"
        if reverse_info:
            line += f"\n{reverse_info}"
        blocks.append(line)

    return "\n\n".join(blocks)
