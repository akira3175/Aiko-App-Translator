"""Background translation review and shared review prompt."""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from cores.job_events import emit_job_event
from cores.storage.project import load_json, save_json


def build_reference_documents(*args, **kwargs):
    """Import lazily so clean context entrypoints do not cycle through postprocess."""
    from cores.stages.references import build_reference_documents as build

    return build(*args, **kwargs)


def build_translation_review_prompt(
    chapter_id,
    chapter_number,
    raw_title,
    raw_content,
    title,
    content,
    context_text="",
    criteria="",
):
    """Prompt review dùng chung cho review nền và Review toàn bộ."""
    return f"""Bạn là reviewer dịch thuật tiểu thuyết từ ngôn ngữ nguồn bất kỳ sang tiếng Việt. Review bản dịch tiếng Việt dưới đây, đối chiếu với bản gốc và trả về JSON.

## Tiêu chí review:
{criteria}

## Thuật ngữ tham chiếu:
{context_text}

## Thông tin chương:
- ID: {chapter_id}
- Số chương: {chapter_number}

## Bản gốc:
### Tiêu đề gốc:
{raw_title}

### Nội dung gốc:
{raw_content}

## Bản dịch tiếng Việt:
### Tiêu đề dịch:
{title}

### Nội dung dịch:
{content}

## Định dạng JSON:
{{
  "chapter_id": "{chapter_id}",
  "overall_score": <1-10>,
  "issues": [
    {{"type": "thiếu nội dung|thêm nội dung|dịch sai|giới tính|xưng hô|thuật ngữ|phong cách|logic|ngoại ngữ",
      "severity": "nặng|trung bình|nhẹ",
      "original": "trích đoạn có thật trong bản gốc",
      "original_vi": "trích đoạn có thật trong bản dịch",
      "suggestion": "gợi ý sửa"}}
  ],
  "gender_ok": true/false,
  "address_ok": true/false,
  "summary": "nhận xét tổng quan 1-2 câu"
}}

Chỉ trả về JSON, không Markdown hoặc giải thích thêm."""


def run_background_review(
    runtime,
    chapter_id,
    chapter_number,
    title,
    content,
    context_text="",
    raw_content="",
    review_token=None,
    raw_title="",
):
    """
    Bước 4 pipeline (CHẠY NGẦM trong daemon thread):
    Review nhanh chất lượng bản dịch đã trau chuốt, lưu vào review.json.
    Dùng provider Review đã chọn. API chạy nền; web chạy tuần tự để giữ ổn định trình duyệt.
    So sánh bản dịch với raw gốc để phát hiện thiếu/sai nội dung.
    """
    prompt = build_translation_review_prompt(
        chapter_id, chapter_number, raw_title, raw_content, title, content,
        context_text, runtime.REVIEW_BG_CRITERIA,
    )
    documents = build_reference_documents(
        {
            "title": raw_title,
            "content": raw_content,
            "title_translation": title,
            "translation": content,
        },
        include_translation=True,
    )
    if any(item["name"] == "characters.md" for item in documents):
        prompt = runtime.with_character_document_instruction(prompt)
    provider = runtime.provider("review")
    model, _thinking = runtime.model_and_thinking("review")

    try:
        while True:
            try:
                text, provider, model = runtime.generate("review", prompt, documents)
                break
            except Exception as exc:
                error = str(exc)
                if "408" in error or any(code in error for code in ["500", "502", "503", "504"]):
                    print(f"[REVIEW BG] Lỗi API tạm thời, giữ key và thử lại: {error}")
                    time.sleep(10)
                    continue
                if "429" in error or "RESOURCE_EXHAUSTED" in error:
                    if provider == "gemini-api":
                        runtime.switch_key_for("review")
                        print(f"[REVIEW BG] Hết quota, đổi key và thử lại: {error}")
                    else:
                        print(f"[REVIEW BG] Bị giới hạn tần suất, thử lại: {error}")
                    time.sleep(30)
                    continue
                if provider == "gemini-api" and (
                    re.search(r"\b4\d\d\b", error)
                    or any(code in error for code in ["PERMISSION_DENIED", "UNAUTHENTICATED"])
                ):
                    print(f"[REVIEW BG] Lỗi API 4xx, đổi key và thử lại: {error}")
                    runtime.switch_key_for("review")
                    time.sleep(15)
                    continue
                raise
        runtime.log_api_call(
            chapter_id, "review", f"{provider}:{model}", prompt, text, ok=True,
            attachments=list(documents),
        )
        # Parse JSON — xử lý cả markdown code block
        clean = re.sub(r"```json\s*|\s*```", "", text).strip()
        start = clean.find("{")
        end = clean.rfind("}")
        review_parsed = {}
        if start != -1 and end != -1:
            try:
                review_parsed = json.loads(clean[start : end + 1])
            except Exception:
                review_parsed = {"raw": clean}
        else:
            review_parsed = {"raw": clean}

        # Lưu vào review.json (thread-safe)
        with runtime._review_lock:
            if (
                review_token is not None
                and runtime._latest_review_tokens.get(chapter_id) is not review_token
            ):
                print(
                    f"[REVIEW BG] Bỏ kết quả cũ của chương {chapter_id} "
                    "vì đã có bản hậu xử lý mới hơn."
                )
                return
            existing = {}
            if os.path.exists(runtime.REVIEW_JSON):
                try:
                    existing = load_json(runtime.REVIEW_JSON, {})
                except Exception:
                    existing = {}
            existing[chapter_id] = {
                "chapter_number": chapter_number,
                "score": review_parsed.get("overall_score"),
                "issue_count": len(review_parsed.get("issues", [])),
                "issues": review_parsed.get("issues", []),
                "summary": str(
                    review_parsed.get("summary", review_parsed.get("raw", ""))
                )[:1500],
            }
            save_json(runtime.REVIEW_JSON, existing, backup=True)
            if review_token is not None:
                runtime._latest_review_tokens.pop(chapter_id, None)
        print(f"[REVIEW BG] ✅ Đã lưu review chương {chapter_id} vào {runtime.REVIEW_JSON}")
        emit_job_event("review_saved", chapter=chapter_id)

    except Exception as e:
        runtime.log_api_call(
            chapter_id, "review", f"{provider}:{model}", prompt, str(e), ok=False,
            attachments=list(documents),
        )
        if review_token is not None:
            with runtime._review_lock:
                if runtime._latest_review_tokens.get(chapter_id) is review_token:
                    runtime._latest_review_tokens.pop(chapter_id, None)
        print(f"[REVIEW BG] ⚠️ Lỗi review ngầm chương {chapter_id}: {e}")


def enqueue_background_review(runtime, chapter, chapter_number, context_text=""):
    """Xếp review vào một worker riêng; các chương được review tuần tự."""
    if not runtime.enabled("review"):
        print("[PIPELINE] Bỏ qua review nền vì công đoạn đã tắt hoặc chưa có model.")
        return None
    chapter_id = chapter.get("id", f"chapter_{chapter_number}")
    review_token = object()
    with runtime._review_lock:
        runtime._latest_review_tokens[chapter_id] = review_token
    provider = runtime.provider("review")
    model, _thinking = runtime.model_and_thinking("review")
    print(f"[PIPELINE] Đã xếp review nền {chapter_id} ({provider}:{model}).")
    if provider in {"gemini-web", "chatgpt-web", "google-ai-studio-web"}:
        run_background_review(
            runtime,
            chapter_id,
            chapter_number,
            chapter.get("title_translation", ""),
            chapter.get("translation", ""),
            context_text,
            chapter.get("content", ""),
            review_token,
            chapter.get("title", ""),
        )
        return None
    if runtime._review_executor is None:
        runtime._review_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="review-bg"
        )
    return runtime._review_executor.submit(
        run_background_review,
        runtime,
        chapter_id,
        chapter_number,
        chapter.get("title_translation", ""),
        chapter.get("translation", ""),
        context_text,
        chapter.get("content", ""),
        review_token,
        chapter.get("title", ""),
    )
