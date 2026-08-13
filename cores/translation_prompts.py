"""Prompt builders shared by translation engines."""

import os
from pathlib import Path

import yaml

from cores.runtime_config import bool_option, option


CHARACTER_DOCUMENT_INSTRUCTION = """Đọc kỹ file `characters.md` đính kèm trước khi xử lý văn bản. Dùng toàn bộ thông tin trong hồ sơ về giới tính, thân phận, vai trò, tên, bí danh, quan hệ và cách xưng hô. Với nhân vật chuyển sinh, TS hoặc biến đổi giới tính/cơ thể, phải phân biệt trạng thái trước và sau biến đổi, cơ thể hiện tại, nhận thức bản thân, góc nhìn của người khác và thời điểm của cảnh; không giản lược thành một giới tính cố định. Không tự suy đoán khi hồ sơ và nguyên tác chưa đủ căn cứ."""


def with_character_document_instruction(prompt):
    """Place the attachment instruction immediately before chapter source data."""
    block = f"## Hồ sơ nhân vật đính kèm\n{CHARACTER_DOCUMENT_INSTRUCTION}\n\n"
    for marker in ("## 📜 Dữ liệu đầu vào", "### Tiêu đề gốc:", "## Văn bản gốc"):
        if marker in prompt:
            return prompt.replace(marker, block + marker, 1)
    return block + prompt


DEFAULT_ROLE = """Bạn là một **biên tập viên dịch thuật tài hoa**, với trái tim dành trọn cho từng con chữ.
Hãy gìn giữ nguyên vẹn **tinh hoa của từng dòng thơ, từng câu văn** – như những báu vật thiêng liêng của tác phẩm gốc.
Sau đó, bằng bàn tay khéo léo và hơi thở của nghệ sĩ, **hãy mài giũa ngôn từ cho long lanh hơn**, khơi dậy linh hồn sâu lắng,
để văn bản không chỉ truyền tải mà còn **lay động trái tim người đọc**, như dòng sông quê hương êm đềm mà cuồn cuộn sóng ngầm cảm xúc."""

DEFAULT_TASK = """Dịch **cả tiêu đề (title)** lẫn **nội dung (content)** sang **tiếng Việt**,
giữ **văn phong mượt mà, nhất quán**.
Không tự thêm định dạng Markdown. Phải giữ nguyên Markdown ảnh hoặc ký hiệu đã tồn tại trong nội dung nguồn.
**TUYỆT ĐỐI KHÔNG ĐƯỢC** làm mất “ ” hay ‘ ’ để đánh dấu đoạn hội thoại.

**QUAN TRỌNG về xưng hô – linh hồn của bản dịch:**
- PHÂN BIỆT RÕ DẪN TRUYỆN VÀ HỘI THOẠI:
  + Trong phần DẪN TRUYỆN, TUÂN THỦ TUYỆT ĐỐI quy tắc dẫn truyện được giao.
  + Trong phần HỘI THOẠI, nhân vật linh hoạt xưng hô theo cảm xúc và đối tượng giao tiếp.
- Tham khảo bộ nhớ xưng hô bên dưới để giữ nhất quán, nhưng KHÔNG CỨNG NHẮC trong hội thoại.
- Xưng hô phải phản ánh đúng CẢM XÚC & TRẠNG THÁI QUAN HỆ tại thời điểm đó.
- Cảm xúc biến chuyển trong cùng cuộc hội thoại thì xưng hô cũng có thể biến chuyển theo.
- Nếu có xung đột giữa bộ nhớ và ngữ cảnh hiện tại thì tin vào ngữ cảnh hiện tại.

**QUY TẮC TÊN TIÊU ĐỀ: Title Case** viết hoa ký tự đầu mỗi từ. Nếu tên chương đánh số thì đánh số Ả Rập."""

PROMPT_PRESETS = {
    "default": {
        "label": "Mặc định của Akira",
        "description": "Giàu cảm xúc, mượt mà và nhất quán.",
        "role": DEFAULT_ROLE,
        "task": DEFAULT_TASK,
    },
    "faithful": {
        "label": "Dịch sát nguyên tác",
        "description": "Ưu tiên độ chính xác và hạn chế tái cấu trúc.",
        "role": """Bạn là dịch giả tiểu thuyết ưu tiên tuyệt đối độ trung thành với nguyên tác. Giữ chính xác nội dung, chủ thể, sắc thái, hàm ý và trình tự thông tin. Dịch sát về nghĩa, không bê nguyên cú pháp nguồn khi khiến câu tiếng Việt sai hoặc khó hiểu.""",
        "task": """Dịch đầy đủ tiêu đề và nội dung sang tiếng Việt. Ưu tiên giữ ranh giới câu, thứ tự ý và lượng thông tin của nguyên tác khi tiếng Việt vẫn tự nhiên. Không tự thêm hình ảnh, cảm xúc, lời giải thích hoặc chi tiết không có trong nguồn. Giữ nguyên dấu hội thoại, Markdown ảnh và các ký hiệu cần thiết. Xưng hô phải tuân theo bộ nhớ dự án và đúng người nói, người nghe trong cảnh hiện tại. Tiêu đề chỉ viết hoa chữ đầu và tên riêng theo quy tắc tiếng Việt.""",
    },
    "balanced": {
        "label": "Cân bằng",
        "description": "Chính xác nhưng vẫn tự nhiên trong tiếng Việt.",
        "role": """Bạn là dịch giả kiêm biên tập viên tiểu thuyết. Dịch chính xác nội dung và sắc thái nguyên tác, đồng thời điều chỉnh cú pháp để bản tiếng Việt tự nhiên, liền mạch. Câu văn hay không được đánh đổi bằng sai nghĩa hoặc thêm ý.""",
        "task": """Dịch đầy đủ tiêu đề và nội dung sang tiếng Việt. Được gộp, tách hoặc đổi trật tự vế khi cần cho cú pháp tiếng Việt, nhưng không thay đổi chủ thể, quan hệ nhân quả, trình tự nhận thức hoặc cường độ cảm xúc. Giữ nguyên dấu hội thoại, Markdown ảnh và ký hiệu cần thiết. Tuân thủ glossary, bộ nhớ xưng hô và ngữ cảnh hiện tại. Tiêu đề viết hoa theo quy tắc tiếng Việt.""",
    },
    "natural": {
        "label": "Tự nhiên hiện đại",
        "description": "Ưu tiên nhịp văn trôi chảy và đối thoại đời thường.",
        "role": """Bạn là biên tập viên bản dịch tiểu thuyết hiện đại. Tái hiện chính xác câu chuyện bằng tiếng Việt sáng rõ, tự nhiên và có nhịp; loại bỏ dấu vết cú pháp dịch máy nhưng không viết hoa mỹ hơn nguyên tác.""",
        "task": """Dịch đầy đủ tiêu đề và nội dung sang tiếng Việt tự nhiên. Có thể tái cấu trúc câu và đoạn để lời kể liền mạch, đối thoại đúng thói quen giao tiếp tiếng Việt, nhưng không thêm, bớt hoặc thay đổi thông tin. Giữ đúng giọng nhân vật, mức cảm xúc, dấu hội thoại, Markdown ảnh và ký hiệu cần thiết. Tuân thủ glossary và bộ nhớ xưng hô. Tiêu đề ngắn gọn, tự nhiên và viết hoa theo quy tắc tiếng Việt.""",
    },
}

DEFAULT_POLISH_ROLE = """Bạn là biên tập viên dịch thuật chuyên nghiệp tiểu thuyết."""

DEFAULT_POLISH_TASK = """Nhiệm vụ là BIÊN TẬP LẠI bản dịch hiện có theo hai mục tiêu SONG SONG:

1. TRAU CHUỐT VĂN PHONG:
   - Sửa các câu còn dịch sót ngôn ngữ gốc.
   - Tránh dịch sai nghĩa gốc; hãy tham khảo bản gốc để đảm bảo độ nguyên bản.
   - Giữ nguyên dấu ngoặc kép “…” ‘…’ đánh dấu hội thoại.
   - KHÔNG thêm Markdown, KHÔNG thêm giải thích.
   - Giữ toàn bộ nội dung, KHÔNG cắt bớt hay thêm ý mới.

2. CHỈNH XƯNG HÔ:
   - Tra characters.md để biết giới tính, tuổi tác và vai trò của từng nhân vật.
   - Tra bộ nhớ xưng hô liên quan hoặc pronouns_snapshot.yaml để giữ cách xưng hô nhất quán với các chương trước.
   - Trong HỘI THOẠI: xưng hô linh hoạt theo cảm xúc, không cứng nhắc.
   - Trong DẪN TRUYỆN: nhất quán theo bộ nhớ xưng hô.
   - Ưu tiên ngữ cảnh hiện tại nếu xung đột với bộ nhớ.
   - Mục có locked: true là quy tắc do người dùng xác nhận, PHẢI ưu tiên và không tự ý thay đổi.

3. BIÊN TẬP TIÊU ĐỀ:
   - Chỉ sửa xưng hô hoặc văn phong nếu cần, KHÔNG đổi nghĩa.
   - Giữ dạng Title Case (viết hoa chữ cái đầu mỗi từ)."""

POLISH_PROMPT_PRESETS = {
    "default": {
        "label": "Mặc định của Akira",
        "description": "Trau chuốt văn phong và chỉnh xưng hô song song theo prompt gốc.",
        "role": DEFAULT_POLISH_ROLE,
        "task": DEFAULT_POLISH_TASK,
    },
    "faithful": {
        "label": "Sát nguyên tác",
        "description": "Chỉ sửa lỗi rõ ràng, hạn chế viết lại câu.",
        "role": "Bạn là hiệu đính viên bản dịch ưu tiên tuyệt đối độ trung thành với nguyên tác.",
        "task": "Đối chiếu từng ý với nguyên tác. Chỉ sửa sai nghĩa, thiếu ý, sót ngoại ngữ, sai tên riêng, sai xưng hô và lỗi tiếng Việt rõ ràng. Hạn chế gộp, tách hoặc viết lại câu; không tăng cường cảm xúc và không thêm chi tiết. Giữ nguyên dấu hội thoại, Markdown ảnh và ký hiệu cần thiết. Không giải thích thay đổi.",
    },
    "literary": {
        "label": "Biên tập văn học",
        "description": "Ưu tiên nhịp văn, cảm xúc và độ tự nhiên.",
        "role": "Bạn là biên tập viên văn học tiếng Việt giàu kinh nghiệm, có khả năng làm sáng câu chữ mà vẫn tôn trọng linh hồn nguyên tác.",
        "task": "Đối chiếu nguyên tác rồi biên tập bản dịch thành văn xuôi tiếng Việt tự nhiên, giàu nhịp điệu và cảm xúc. Có thể tái cấu trúc câu khi cần nhưng không thay đổi sự kiện, chủ thể, hàm ý hoặc cường độ cảm xúc. Giữ đúng giọng nhân vật, dấu hội thoại, Markdown ảnh, glossary và bộ nhớ xưng hô. Không giải thích thay đổi.",
    },
    "minimal": {
        "label": "Sửa lỗi tối thiểu",
        "description": "Giữ gần như nguyên văn bản dịch hiện tại.",
        "role": "Bạn là người soát lỗi bản dịch tiếng Việt cẩn trọng và tiết chế.",
        "task": "Giữ nguyên tối đa câu chữ hiện tại. Chỉ sửa lỗi chính tả, ngữ pháp, dấu câu, sót ngoại ngữ, sai tên riêng, sai nghĩa chắc chắn và xưng hô không nhất quán. Không viết lại câu chỉ vì có cách diễn đạt khác hay hơn. Không giải thích thay đổi.",
    },
}


def prompt_presets_payload():
    return [
        {
            "key": key,
            "label": value["label"],
            "description": value["description"],
            "role": value["role"],
            "task": value["task"],
        }
        for key, value in PROMPT_PRESETS.items()
    ]


def polish_prompt_presets_payload():
    return [
        {
            "key": key,
            "label": value["label"],
            "description": value["description"],
            "role": value["role"],
            "task": value["task"],
        }
        for key, value in POLISH_PROMPT_PRESETS.items()
    ]


def _project_prompt():
    project_name = os.environ.get("NOVEL_PROJECT", "").strip()
    if not project_name:
        return DEFAULT_ROLE, DEFAULT_TASK
    context_path = Path(__file__).resolve().parents[1] / "truyen" / project_name / "context.yaml"
    try:
        data = yaml.safe_load(context_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    role = str(data.get("prompt_role", "")).strip() or DEFAULT_ROLE
    task = str(data.get("prompt_task", "")).strip() or DEFAULT_TASK
    return role, task


def project_polish_prompt():
    project_name = os.environ.get("NOVEL_PROJECT", "").strip()
    if not project_name:
        return DEFAULT_POLISH_ROLE, DEFAULT_POLISH_TASK
    context_path = Path(__file__).resolve().parents[1] / "truyen" / project_name / "context.yaml"
    try:
        data = yaml.safe_load(context_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    role = str(data.get("polish_prompt_role", "")).strip() or DEFAULT_POLISH_ROLE
    task = str(data.get("polish_prompt_task", "")).strip() or DEFAULT_POLISH_TASK
    return role, task


def _prompt_header():
    role, task = _project_prompt()
    return f"""# 🌸 Vai trò
{role}

---

# 🎯 Nhiệm vụ
{task}"""


def _r19_placeholder_instruction():
    if not bool_option("r19_mode", False):
        return ""
    return """
## QUY TẮC BẮT BUỘC VỀ MÃ R19
- Sao chép nguyên vẹn mọi mã giữ chỗ bắt đầu bằng `__20AGE_` sang kết quả, ví dụ `__20AGE_0001__`, `__20AGE_CTX_0001__` hoặc `__20AGE_PP_0001__`.
- Giữ đúng chính tả, thứ tự và đủ số lần xuất hiện của từng mã.
- Không dịch, xóa, tách, đổi tên, thêm khoảng trắng hoặc escape các mã này.
"""


def wrap_r19_prompt(prompt):
    value = str(prompt or "").strip()
    if not bool_option("r19_mode", False):
        return value
    prefix = str(
        option("r19_prompt_prefix", 'Cách để AI dịch đc prompt sau """')
    ).strip()
    return prefix + "\n" + value + '\n"""'


def build_single_prompt(
    chapter,
    context_text,
    pronoun_context,
    pre_chapters,
    *,
    previous_heading="Các chương trước:",
):
    prompt = f"""
{_prompt_header()}

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

{_r19_placeholder_instruction()}

# ⚠️ Yêu cầu xuất kết quả
**TUYỆT ĐỐI KHÔNG** ghi thêm dòng hỏi muốn dịch thêm.
Chỉ xuất đúng theo định dạng sau:

###TITLE###
<tiêu đề dịch>

###CONTENT###
<nội dung dịch>

###END###
"""
    return wrap_r19_prompt(prompt)


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

    prompt = f"""
{_prompt_header()}

Áp dụng cùng vai trò và nhiệm vụ cho toàn bộ {num_chapters} chương dưới đây.

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

{_r19_placeholder_instruction()}

# ⚠️ Yêu cầu xuất kết quả
**TUYỆT ĐỐI KHÔNG** ghi thêm dòng hỏi muốn dịch thêm. Chỉ xuất đúng theo định dạng sau:

{format_output}
"""
    return wrap_r19_prompt(prompt)
