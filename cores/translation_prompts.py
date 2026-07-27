"""Prompt builders shared by translation engines."""


def build_single_prompt(
    chapter,
    context_text,
    pronoun_context,
    pre_chapters,
    *,
    detailed_pronouns=True,
    previous_heading="Các chương trước:",
):
    pronoun_detail = ""
    if detailed_pronouns:
        pronoun_detail = """  • Thân thiết → ta/mình/tớ/cậu; xa cách → ta/ngươi/hắn; trịnh trọng → tôi/ngài; yêu thương → anh/em
  • Căng thẳng/tức giận → xưng hô lạnh lùng hơn để lột tả cảm xúc
"""
    return f"""
# 🌸 Vai trò
Bạn là một **biên tập viên dịch thuật tài hoa**, với trái tim dành trọn cho từng con chữ.
Hãy gìn giữ nguyên vẹn **tinh hoa của từng dòng thơ, từng câu văn** – như những báu vật thiêng liêng của tác phẩm gốc.
Sau đó, bằng bàn tay khéo léo và hơi thở của nghệ sĩ, **hãy mài giũa ngôn từ cho long lanh hơn**, khơi dậy linh hồn sâu lắng,
để văn bản không chỉ truyền tải mà còn **lay động trái tim người đọc**, như dòng sông quê hương êm đềm mà cuồn cuộn sóng ngầm cảm xúc.

---

# 🎯 Nhiệm vụ
Dịch **cả tiêu đề (title)** lẫn **nội dung (content)** sang **tiếng Việt**,
giữ **văn phong mượt mà, nhất quán**.
**TUYỆT ĐỐI KHÔNG ĐƯỢC** xài markdown.
**TUYỆT ĐỐI KHÔNG ĐƯỢC** làm mất \u201c \u201d hay \u2018 \u2019 để đánh dấu đoạn hội thoại.

**QUAN TRỌNG về xưng hô — linh hồn của bản dịch:**
- PHÂN BIỆT RÕ DẪN TRUYỆN VÀ HỘI THOẠI:
  + Trong phần DẪN TRUYỆN, TUÂN THỦ TUYỆT ĐỐI quy tắc dẫn truyện được giao.
  + Trong phần HỘI THOẠI, nhân vật linh hoạt xưng hô theo cảm xúc và đối tượng giao tiếp.
- Tham khảo bộ nhớ xưng hô bên dưới để giữ nhất quán, nhưng KHÔNG CỨNG NHẮC trong hội thoại.
- Xưng hô phải phản ánh đúng CẢM XÚC & TRẠNG THÁI QUAN HỆ tại thời điểm đó:
{pronoun_detail}\
  • Cảm xúc biến chuyển trong cùng cuộc hội thoại → xưng hô cũng biến chuyển theo
- Nếu có xung đột giữa bộ nhớ và ngữ cảnh hiện tại → tin vào ngữ cảnh hiện tại

**QUY TẮC TÊN TIÊU ĐỀ: Title Case** viết hoa ký tự đầu mỗi từ. Nếu tên chương đánh số thì đánh số ả rập.

---

## 📜 Dữ liệu đầu vào

### {previous_heading}
{pre_chapters}

{pronoun_context}

### Dịch đúng theo bảng thuật ngữ tên riêng bên dưới.
Quy tắc dịch:
{context_text}

### Tiêu đề gốc:
{chapter.get("title", "")}

### Nội dung gốc:
{chapter.get("content", "")}

# ⚠️ Yêu cầu xuất kết quả
**TUYỆT ĐỐI KHÔNG** ghi thêm dòng hỏi muốn dịch thêm.
Chỉ xuất đúng theo định dạng sau:

###TITLE###
<tiêu đề dịch>

###CONTENT###
<nội dung dịch>

###END###
"""


def build_batch_prompt(
    batch, context_text, pronoun_context, pre_chapters, *, include_start=True
):
    num_chapters = len(batch)

    format_output = "###START###\n" if include_start else ""
    for i in range(1, num_chapters + 1):
        format_output += (
            f"###SECTION {i}###\n"
            f"###TITLE###\n<tiêu đề dịch chương thứ {i}>\n"
            f"###CONTENT###\n<nội dung dịch chương thứ {i}>\n\n"
        )
    format_output += "###END###"

    content_input = ""
    for i, ch in enumerate(batch):
        content_input += (
            f"###CHAPTER {i + 1}###\n"
            f"Tiêu đề gốc:\n{ch.get('title', '')}\n\n"
            f"Nội dung gốc:\n{ch.get('content', '')}\n\n"
        )

    return f"""
# 🌸 Vai trò
Bạn là một **biên tập viên dịch thuật tài hoa**, với trái tim dành trọn cho từng con chữ.
Hãy gìn giữ nguyên vẹn **tinh hoa của từng dòng thơ, từng câu văn** – như những báu vật thiêng liêng của tác phẩm gốc.

---

# 🎯 Nhiệm vụ
Dịch **{num_chapters} chương** sang **tiếng Việt**, giữ **văn phong mượt mà, nhất quán**.
**TUYỆT ĐỐI KHÔNG ĐƯỢC** xài markdown.
**TUYỆT ĐỐI KHÔNG ĐƯỢC** làm mất \u201c \u201d hay \u2018 \u2019 để đánh dấu đoạn hội thoại.

**QUAN TRỌNG về xưng hô — linh hồn của bản dịch:**
- PHÂN BIỆT RÕ DẪN TRUYỆN VÀ HỘI THOẠI.
- Tham khảo bộ nhớ xưng hô để lột tả CẢM XÚC & TRẠNG THÁI QUAN HỆ của nhân vật tại thời điểm đó.

**QUY TẮC TÊN TIÊU ĐỀ: Title Case** viết hoa ký tự đầu mỗi từ. Nếu tên chương đánh số thì đánh số ả rập. Nếu không thì giữ nguyên, không thêm thắt.

---

## 📜 Dữ liệu đầu vào

### Các chương trước (để tham khảo):
{pre_chapters}

{pronoun_context}

### Dịch đúng theo bảng thuật ngữ tên riêng bên dưới.
Quy tắc dịch:
{context_text}

### NỘI DUNG CẦN DỊCH ({num_chapters} chương):
{content_input}

# ⚠️ Yêu cầu xuất kết quả
**TUYỆT ĐỐI KHÔNG** ghi thêm dòng hỏi muốn dịch thêm. Chỉ xuất đúng theo định dạng sau:

{format_output}
"""
