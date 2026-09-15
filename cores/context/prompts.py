"""Editable glossary instructions and the required output format."""

from cores.r19 import strip_r19_terms
from cores.translation.prompts import wrap_r19_prompt

DEFAULT_CONTEXT_INSTRUCTIONS = """Bạn là chuyên gia xây dựng glossary cho bản dịch tiểu thuyết từ mọi ngôn ngữ nguồn sang tiếng Việt.
Tự nhận diện ngôn ngữ và thể loại từ nội dung; không mặc định truyện thuộc thể loại fantasy.

Trích xuất thuật ngữ, danh hiệu, xưng hô, tên riêng và địa danh cần giữ nhất quán.
- Bỏ qua từ phổ thông và vật dụng đời thường.
- Giữ nguyên chính xác từ/cụm từ nguồn ở vế trái.
- Chỉ khôi phục tên La-tinh gốc khi có căn cứ chắc chắn.
- Dịch thuật ngữ và danh hiệu sang tiếng Việt tự nhiên, thống nhất với glossary cũ.
- Tên riêng viết hoa từng âm tiết; danh từ và chức vị thông thường viết thường."""


def context_instructions(value):
    if value is None or value == '':
        return DEFAULT_CONTEXT_INSTRUCTIONS
    if not isinstance(value, str) or not value.strip() or len(value) > 20000:
        raise ValueError('Hướng dẫn tạo Context phải có từ 1 đến 20.000 ký tự')
    return value.strip()


def build_glossary_prompt(chapters, old_glossary, instructions=None):
    content = strip_r19_terms('\n\n'.join(
        f"{chapter.get('title', '')}\n{chapter.get('content', '')}"
        for chapter in chapters if chapter.get('content')
    ))
    if not content.strip():
        return ''
    return wrap_r19_prompt(f"""{context_instructions(instructions)}

Glossary hiện có:
{strip_r19_terms(old_glossary)}

Nội dung raw:
{content}

Chỉ xuất mỗi dòng theo dạng:
Nguyên văn = Bản dịch

Bắt đầu bằng ###START### và kết thúc bằng ###END###.
Không thêm Markdown hoặc lời giải thích.""")
