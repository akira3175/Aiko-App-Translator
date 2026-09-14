"""Foreign-character checks and manual-review persistence."""

import os
import time

from cores.storage.project import load_json, save_json
from cores.stages.outputs import parse_title_content
from cores.chapters.images import IMAGE_INSTRUCTION, validate_image_markers


def save_manual_check_id(chapter_id, file_path):
    data = load_json(file_path, []) if os.path.exists(file_path) else []
    if not isinstance(data, list):
        data = []
    if chapter_id not in data:
        data.append(chapter_id)
        save_json(file_path, data, backup=True)
    print(f"⚠️ Lưu chương '{chapter_id}' vào {file_path} để kiểm tra thủ công.")


def fix_translation(runtime, chapter, chapter_number, context_text="", pronoun_context="", model=None, thinking_level=None):
    """Fix các chương còn sót ký tự nước ngoài bằng API."""
    attempt = 0
    effective_model = str(model or runtime.model_and_thinking("polish")[0])
    while attempt < runtime.FIX_MAX_RETRY:
        title = chapter.get("title_translation", "")
        content = chapter.get("translation", "")
        if not runtime.has_foreign(title) and not runtime.has_foreign(content):
            return title, content

        print(
            f"⚠️ Phát hiện ký tự nước ngoài (lần {attempt + 1}/{runtime.FIX_MAX_RETRY}), đang dịch lại..."
        )
        prompt = runtime.wrap_r19_prompt(f"""Bạn là dịch giả tiểu thuyết.
Bản dịch dưới đây vẫn còn sót chữ Hán/Hàn.
Hãy dịch lại thành bản hoàn chỉnh, giữ nguyên phong cách và nội dung, không được markdown.

{runtime._r19_placeholder_instruction()}

{pronoun_context}

Ngữ cảnh:
{context_text}

Tiêu đề dịch hiện tại:
{title}

Nội dung dịch hiện tại:
{content}

⚠️ Xuất kết quả theo định dạng sau:

###TITLE###
<tiêu đề dịch hoàn chỉnh>

###CONTENT###
<nội dung dịch hoàn chỉnh>

###END###
""")
        if "_image_markers" in chapter:
            prompt = IMAGE_INSTRUCTION + "\n\n" + prompt
        try:
            chapter_id_fix = chapter.get("id", f"chapter_{chapter_number}")
            text, provider, effective_model = runtime.generate("polish", prompt)
            if "###END###" in text:
                title_out, content_out = parse_title_content(text, "Dịch lại")
                if "_image_markers" in chapter:
                    validate_image_markers(content_out, chapter["_image_markers"], title_out)
                chapter["title_translation"] = title_out
                chapter["translation"] = content_out
                runtime.log_api_call(chapter_id_fix, "fix", f"{provider}:{effective_model}", prompt, text, ok=True)
                attempt += 1
            else:
                print("⚠️ Output sai định dạng, thử lại sau 5s...")
                runtime.log_api_call(
                    chapter_id_fix, "fix", f"{provider}:{effective_model}", prompt, text, ok=False
                )
                attempt += 1
                time.sleep(5)
        except Exception as e:
            err = str(e)
            if "429" in err and runtime.provider("polish") == "gemini-api":
                runtime.switch_key_for("polish")
                print("🔔 Chờ 30s rồi thử lại...")
                time.sleep(30)
            elif any(code in err for code in ["500", "502", "503", "504"]):
                print(f"⚠️ Lỗi 5xx từ server: {e}. Chờ 10s...")
                time.sleep(10)
            else:
                print(f"⚠️ Lỗi khi dịch lại: {e}")
                attempt += 1
                time.sleep(10)

    print(
        f"❌ Chương '{chapter.get('title', '')}' đã thử {runtime.FIX_MAX_RETRY} lần, cần kiểm tra thủ công."
    )
    save_manual_check_id(
        chapter.get("id", chapter.get("title", "UnknownID")),
        runtime.MANUAL_CHECK_JSON,
    )
    return chapter.get("title_translation", ""), chapter.get("translation", "")
