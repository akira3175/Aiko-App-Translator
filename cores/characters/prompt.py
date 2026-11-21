"""Prompt construction for chapter-aware structured character analysis."""

from cores.characters.store import (
    FIELDS,
    format_chapter_code,
    summarize_document_for_prompt,
)
from cores.r19 import strip_r19_terms
from cores.translation.prompts import wrap_r19_prompt


def _format_existing(existing):
    if isinstance(existing, dict):
        return summarize_document_for_prompt(existing)
    text = str(existing or "").strip()
    return text if text else "(Chưa có dữ liệu nhân vật)"


def build_character_prompt(chapters: list, existing, glossary: str = "") -> str:
    content_blocks = []
    chapter_codes = []
    for chapter in chapters:
        content = chapter.get("content", "")
        if not content:
            continue
        code = format_chapter_code(chapter.get("id", ""))
        if code:
            chapter_codes.append(code)
            heading = f"### [{code}] {chapter.get('title', '')}".strip()
        else:
            heading = f"### {chapter.get('title', '')}".strip()
        content_blocks.append(f"{heading}\n{content}")

    full_text = strip_r19_terms("\n\n".join(content_blocks))
    glossary = strip_r19_terms(glossary)
    existing_summary = strip_r19_terms(_format_existing(existing))
    field_guide = "\n".join(f"- `{key}`: {label}" for key, label in FIELDS)
    allowed_list = ", ".join(chapter_codes) if chapter_codes else "(không có)"

    return wrap_r19_prompt(
        f"""
# Vai trò
Bạn là trợ lý biên tập chuyên phân tích nhân vật trong tiểu thuyết để phục vụ dịch thuật chính xác theo tiến độ từng chương.

# Nhiệm vụ
Đọc văn bản gốc của các chương bên dưới, sau đó xuất **chỉ những thông tin mới hoặc thay đổi mới** phát hiện được trong batch chương này dưới dạng JSON hợp lệ bằng tiếng Việt.

# Danh sách mã chương hợp lệ trong batch này
{allowed_list}

# Văn bản gốc
{full_text}

# Glossary tên nhân vật và thuật ngữ
{glossary if glossary else "(Chưa có glossary)"}

# Hồ sơ nhân vật hiện có (tóm tắt)
{existing_summary}

# Danh sách `field` hợp lệ
{field_guide}

# Quy tắc bắt buộc
1. Chỉ trích xuất nhân vật quan trọng có thoại, hành động hoặc tác động đến cốt truyện; bỏ qua NPC phụ thoáng qua.
2. Nếu nhân vật đã có trong "Hồ sơ nhân vật hiện có", điền đúng `id` và `name` hiện tại. Nếu là nhân vật mới, để `"id": ""` và dùng tên đầy đủ theo glossary cho `name` (không dùng biệt danh hay danh hiệu làm `name`).
3. **Chỉ ghi thông tin mới hoặc thay đổi thực sự phát sinh** trong batch này; KHÔNG chép lại các thuộc tính đã có sẵn mà không thay đổi.
4. Mọi mục trong `updates` và `events` **bắt buộc** có `chapter` lấy chính xác từ danh sách mã chương hợp lệ ở trên (ví dụ `"v7_c11_s1.md"`).
5. `chapter` là **chương tiết lộ hoặc xác lập thông tin đó trong nguyên tác**. Nếu chương sau mới tiết lộ quá khứ của chương trước, vẫn gắn mã chương hiện tại đang tiết lộ (KHÔNG tự suy ngược về chương cũ).
6. Không tự ghi đè hay bác bỏ các mục đã gắn `🔒` (do người dùng xác nhận), trừ khi có biến cố thay đổi mới ở chương về sau.
7. `events` chỉ ghi biến cố/thông tin thực sự có ích cho việc dịch (lộ thân phận, đổi phe, bái sư, đổi xưng hô, biến đổi cơ thể/giới tính, bí mật quan trọng), ngắn gọn 1 câu; không viết tóm tắt nhật ký vụn vặt.
8. Các mục `voice`, `narration_pronoun`, `self_reference`, `address` chỉ điền khi văn bản có căn cứ rõ ràng, không phỏng đoán.
9. Nếu batch này không có cập nhật nhân vật đáng kể nào, trả về `{{"characters": []}}`.

# Định dạng JSON bắt buộc
Bọc duy nhất một đối tượng JSON giữa `###START###` và `###END###` (trong code block `json`), không thêm giải thích bên ngoài:
```json
###START###
{{
  "characters": [
    {{
      "id": "ch_xxxxxxxxxx hoặc để trống nếu nhân vật mới",
      "name": "Tên đầy đủ theo glossary",
      "updates": [
        {{"field": "status", "value": "Giá trị mới", "chapter": "v7_c11_s1.md"}}
      ],
      "events": [
        {{"chapter": "v7_c11_s1.md", "text": "Biến cố hoặc lưu ý dịch thuật quan trọng"}}
      ]
    }}
  ]
}}
###END###
```
"""
    )
