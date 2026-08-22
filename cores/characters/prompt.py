"""Prompt construction for character analysis."""

from cores.r19 import strip_r19_terms
from cores.translation.prompts import wrap_r19_prompt


def build_character_prompt(chapters: list, existing_md: str, glossary: str = "") -> str:
    content_blocks = [
        f"### {chapter.get('title', '')}\n{chapter.get('content', '')}"
        for chapter in chapters
        if chapter.get("content")
    ]
    full_text = strip_r19_terms("\n\n".join(content_blocks))
    glossary = strip_r19_terms(glossary)
    existing_md = strip_r19_terms(existing_md)
    return wrap_r19_prompt(f"""
# Vai trò
Bạn là trợ lý biên tập chuyên phân tích nhân vật trong tiểu thuyết.

# Nhiệm vụ
Đọc văn bản gốc, sau đó trích xuất hoặc cập nhật thông tin nhân vật bằng tiếng Việt.

# Văn bản gốc
{full_text}

# Glossary tên nhân vật và thuật ngữ
{glossary if glossary else "(Chưa có glossary)"}

# Dữ liệu nhân vật hiện có
{existing_md if existing_md else "(Chưa có dữ liệu nhân vật)"}

# Yêu cầu
1. Trích xuất nhân vật quan trọng có thoại, hành động hoặc tác động đến cốt truyện.
2. Bỏ qua NPC phụ không đáng kể, chỉ xuất hiện một lần.
3. Nếu nhân vật đã có, chỉ hợp nhất và bổ sung, không xóa dữ liệu cũ.
4. Header `## Tên nhân vật` phải dùng tên đầy đủ theo glossary.
5. Nếu nhân vật đã có, giữ nguyên tên header hiện tại.
6. Không dùng biệt danh, danh hiệu hoặc tên tắt làm header.

# Template bắt buộc
```
## [Tên nhân vật]

### Thông tin cơ bản
- **Tên gốc**:
- **Biệt danh / Danh hiệu**:
- **Giới tính**: Nam / Nữ / Không xác định
- **Tuổi / Độ tuổi ước lượng**:
- **Chủng tộc / Xuất thân**:
- **Địa vị / Chức vụ**:
- **Phe / Tổ chức**:

### Ghi chú dịch thuật
- (Tên gốc, cách dịch đặc biệt, lưu ý khi dịch thoại...)
```

Bắt đầu bằng `###CHAR_START###` và kết thúc bằng `###CHAR_END###`.
Không thêm giải thích hoặc nội dung ngoài hai marker.
""")
