"""Tạo glossary cho context.yaml bằng Gemini API."""

import os
import sys
import time

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from cores.context_workflow import run_context_generation
from cores.dich_utils import (
    CONTEXT_YAML,
    RAW_DIR,
    call_gemini,
    switch_api_key,
)
from cores.runtime_config import int_option, option
from cores.r19_translation import strip_r19_terms
from cores.translation_prompts import wrap_r19_prompt

CONTEXT_FILE = CONTEXT_YAML
BATCH_SIZE = int_option("batch_size", 30, minimum=1)
CONTEXT_MODEL = str(option("context_model", "gemini-3.5-flash"))
MAX_RETRIES = int_option("context_retries", 3, minimum=1)


def generate_glossary(chapters, old_glossary):
    content = strip_r19_terms("\n\n".join(
        f"{chapter.get('title', '')}\n{chapter.get('content', '')}"
        for chapter in chapters
        if chapter.get("content")
    ))
    old_glossary = strip_r19_terms(old_glossary)
    if not content.strip():
        print("⚠️ Batch này không có nội dung, bỏ qua.")
        return ""

    prompt = wrap_r19_prompt(f"""Bạn là chuyên gia xây dựng glossary cho bản dịch tiểu thuyết từ mọi ngôn ngữ nguồn sang tiếng Việt.
Văn bản có thể là tiếng Hàn, Trung, Nhật, Anh hoặc ngôn ngữ khác. Hãy tự nhận diện ngôn ngữ và thể loại từ nội dung, không mặc định đó là truyện fantasy.

Từ nội dung raw dưới đây, trích xuất thuật ngữ, danh hiệu, xưng hô, tên riêng
và địa danh cần giữ nhất quán. Bỏ qua từ phổ thông và vật dụng đời thường.
Giữ nguyên chính xác từ/cụm từ nguồn ở vế trái. Với tên ngoại lai được phiên âm
qua ngôn ngữ nguồn, chỉ khôi phục dạng La-tinh gốc khi có căn cứ chắc chắn.
Với tên bản địa, dùng cách đọc hoặc chuyển tự phù hợp với ngôn ngữ nguồn,
ưu tiên thống nhất với glossary cũ và không phỏng đoán khi không chắc chắn.
Thuật ngữ và danh hiệu dịch sang tiếng Việt hiện đại, đúng ngữ cảnh.

Glossary hiện có:
{old_glossary}

Nội dung raw:
{content}

Chỉ xuất mỗi dòng theo dạng:
Nguyên văn = Bản dịch

Bắt đầu bằng ###START### và kết thúc bằng ###END###.
Không thêm Markdown hoặc lời giải thích.""")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(
                f"📤 Gửi Gemini API bằng {CONTEXT_MODEL} "
                f"(lần {attempt}/{MAX_RETRIES})..."
            )
            response = call_gemini(
                prompt,
                model=CONTEXT_MODEL,
                temperature=0.2,
                max_output_tokens=16000,
            ).strip()
            if "###START###" in response and "###END###" in response:
                return response
            print("⚠️ Kết quả thiếu marker START/END.")
        except Exception as exc:
            print(f"⚠️ Lỗi Gemini API: {exc}")
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                switch_api_key()
        if attempt < MAX_RETRIES:
            time.sleep(5)

    raise ValueError(
        f"Gemini API không trả về glossary hợp lệ sau {MAX_RETRIES} lần thử"
    )


def main():
    if CONTEXT_MODEL.strip().lower() in {"", "none"}:
        print("Bỏ qua tạo context vì chưa cấu hình model Gemini API.")
        return
    return run_context_generation(
        engine_name="Gemini API",
        setup_browser=None,
        close_browser=None,
        generate_glossary=generate_glossary,
        raw_dir=RAW_DIR,
        context_file=CONTEXT_FILE,
        batch_size=BATCH_SIZE,
    )


if __name__ == "__main__":
    main()
