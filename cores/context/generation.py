"""Provider-independent glossary generation."""

import time

from cores.gemini import switch_api_key
from cores.r19 import strip_r19_terms
from cores.config.runtime import int_option, option
from cores.stages import (
    browser_lifecycle as stage_browser_lifecycle,
    generate_stage,
    stage_model_and_thinking,
    stage_provider,
    stage_transports,
)
from cores.translation.prompts import wrap_r19_prompt


TRANSPORT_OVERRIDES = {}


def context_provider():
    return stage_provider("context", get_option=option)


def context_model_and_thinking(provider):
    return stage_model_and_thinking("context", provider, get_option=option)


def context_transports():
    return stage_transports(TRANSPORT_OVERRIDES)


def browser_lifecycle(provider):
    return stage_browser_lifecycle(provider)


def build_glossary_prompt(chapters, old_glossary):
    content = strip_r19_terms("\n\n".join(
        f"{chapter.get('title', '')}\n{chapter.get('content', '')}"
        for chapter in chapters
        if chapter.get("content")
    ))
    if not content.strip():
        return ""
    old_glossary = strip_r19_terms(old_glossary)
    return wrap_r19_prompt(f"""Bạn là chuyên gia xây dựng glossary cho bản dịch tiểu thuyết từ mọi ngôn ngữ nguồn sang tiếng Việt.
Tự nhận diện ngôn ngữ và thể loại từ nội dung; không mặc định truyện thuộc thể loại fantasy.

Trích xuất thuật ngữ, danh hiệu, xưng hô, tên riêng và địa danh cần giữ nhất quán.
- Bỏ qua từ phổ thông và vật dụng đời thường.
- Giữ nguyên chính xác từ/cụm từ nguồn ở vế trái.
- Chỉ khôi phục tên La-tinh gốc khi có căn cứ chắc chắn.
- Dịch thuật ngữ và danh hiệu sang tiếng Việt tự nhiên, thống nhất với glossary cũ.
- Tên riêng viết hoa từng âm tiết; danh từ và chức vị thông thường viết thường.

Glossary hiện có:
{old_glossary}

Nội dung raw:
{content}

Chỉ xuất mỗi dòng theo dạng:
Nguyên văn = Bản dịch

Bắt đầu bằng ###START### và kết thúc bằng ###END###.
Không thêm Markdown hoặc lời giải thích.""")


def generate_glossary(chapters, old_glossary):
    prompt = build_glossary_prompt(chapters, old_glossary)
    if not prompt:
        print("⚠️ Batch này không có nội dung, bỏ qua.")
        return ""
    provider = context_provider()
    model, thinking = context_model_and_thinking(provider)
    retries = int_option("context_retries", 3, minimum=1)
    for attempt in range(1, retries + 1):
        try:
            print(f"📤 Gửi {provider} bằng {model} (lần {attempt}/{retries})...")
            response = generate_stage(
                "context",
                prompt,
                provider=provider,
                get_option=option,
                overrides=TRANSPORT_OVERRIDES,
            )[0].text.strip()
            if "###START###" in response and "###END###" in response:
                return response
            print("⚠️ Kết quả thiếu marker START/END.")
        except Exception as error:
            print(f"⚠️ Lỗi tạo Context qua {provider}: {error}")
            if provider == "gemini-api" and (
                "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error)
            ):
                switch_api_key()
        if attempt < retries:
            time.sleep(5)
    raise ValueError(f"{provider} không trả về glossary hợp lệ sau {retries} lần thử")
