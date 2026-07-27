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

CONTEXT_FILE = CONTEXT_YAML
BATCH_SIZE = int_option("batch_size", 30, minimum=1)
CONTEXT_MODEL = str(option("context_model", "gemini-3.5-flash"))
MAX_RETRIES = int_option("context_retries", 3, minimum=1)


def generate_glossary(chapters, old_glossary):
    content = "\n\n".join(
        f"{chapter.get('title', '')}\n{chapter.get('content', '')}"
        for chapter in chapters
        if chapter.get("content")
    )
    if not content.strip():
        print("⚠️ Batch này không có nội dung, bỏ qua.")
        return ""

    prompt = f"""Bạn là công cụ xây dựng glossary cho bản dịch tiểu thuyết.

Từ nội dung raw dưới đây, trích xuất thuật ngữ, danh hiệu, xưng hô, tên riêng
và địa danh cần giữ nhất quán. Bỏ qua từ phổ thông và vật dụng đời thường.
Tên riêng ngoại lai phải chuyển về dạng La-tinh gốc nếu nhận diện được.
Thuật ngữ và danh hiệu dịch sang tiếng Việt hiện đại, đúng ngữ cảnh.

Glossary hiện có:
{old_glossary}

Nội dung raw:
{content}

Chỉ xuất mỗi dòng theo dạng:
Nguyên văn = Bản dịch

Bắt đầu bằng ###START### và kết thúc bằng ###END###.
Không thêm Markdown hoặc lời giải thích."""

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
