"""Polish translated chapters with provider-neutral reference snapshots."""

import os
import time
from pathlib import Path

from cores.postprocess.snapshots import build_characters_snapshot
from cores.chapters.images import IMAGE_INSTRUCTION, validate_image_markers


def polish_translation(
    runtime,
    chapter,
    chapter_number,
    context_text,
    pronoun_context,
    characters_md_path,
    pronouns_file,
    model=None,
    thinking_level=None,
):
    """Polish one translated chapter through the configured polish provider."""
    chapter_id = chapter.get("id", f"chapter_{chapter_number}")
    raw_title = chapter.get("title", "")
    raw_content = chapter.get("content", "")
    title_cur = chapter.get("title_translation", "")
    content_cur = chapter.get("translation", "")
    configured_model, _thinking = runtime.model_and_thinking("polish")
    effective_model = str(model or configured_model)
    if not content_cur.strip():
        return title_cur, content_cur

    provider = runtime.provider("polish")
    print(
        f"[POLISH] Biên tập chương {chapter_number} ({chapter_id}) "
        f"với {provider}:{effective_model}..."
    )
    tmp_characters = None
    try:
        relevant_text = "\n".join(
            [raw_title, raw_content, title_cur, content_cur, pronoun_context]
        )
        tmp_characters = build_characters_snapshot(
            characters_md_path,
            relevant_text,
            max_characters=min(
                runtime.int_option("character_snapshot_limit", 20, minimum=1), 50
            ),
        )
        attachments = []
        if tmp_characters:
            attachments.append(
                {
                    "name": "characters.md",
                    "mime_type": "text/markdown",
                    "content": Path(tmp_characters).read_text(encoding="utf-8"),
                }
            )
        role, task = runtime.project_polish_prompt()
        prompt = runtime.wrap_r19_prompt(f"""# Vai trò hiệu đính
{role}

# Nhiệm vụ hiệu đính
{task}

Giữ nguyên đầy đủ nội dung, Markdown ảnh và dấu hội thoại. Không giải thích thay đổi.
{runtime._r19_placeholder_instruction()}

## Thuật ngữ và quy tắc
{context_text}

## Bộ nhớ xưng hô
{pronoun_context}

## Nguyên tác
Tiêu đề: {raw_title}
{raw_content}

## Bản dịch cần hiệu đính
Tiêu đề: {title_cur}
{content_cur}

Chỉ trả về:
###TITLE###
<tiêu đề hoàn chỉnh>
###CONTENT###
<nội dung hoàn chỉnh>
###END###""")
        if tmp_characters:
            prompt = runtime.with_character_document_instruction(prompt)
        if "_image_markers" in chapter:
            prompt = IMAGE_INSTRUCTION + "\n\n" + prompt

        while True:
            try:
                text, provider, effective_model = runtime.generate(
                    "polish", prompt, attachments
                )
                if "###TITLE###" not in text or "###CONTENT###" not in text:
                    print("[POLISH] Output sai format -- giữ nguyên bản dịch cũ.")
                    runtime.log_api_call(
                        chapter_id,
                        "polish",
                        f"{provider}:{effective_model}",
                        prompt,
                        text,
                        ok=False,
                        attachments=attachments,
                    )
                    return title_cur, content_cur
                title_marker = text.find("###TITLE###") + len("###TITLE###")
                content_marker = text.find("###CONTENT###")
                title_out = text[title_marker:content_marker].strip()
                content_out = text[content_marker + len("###CONTENT###") :].strip()
                if content_out.endswith("###END###"):
                    content_out = content_out[: -len("###END###")].rstrip()
                if "_image_markers" in chapter:
                    validate_image_markers(content_out, chapter["_image_markers"], title_out)
                runtime.log_api_call(
                    chapter_id,
                    "polish",
                    f"{provider}:{effective_model}",
                    prompt,
                    text,
                    ok=True,
                    attachments=attachments,
                )
                print(
                    f"[POLISH] Đã biên tập chương {chapter_number} "
                    f"({len(content_out)} ký tự)"
                )
                return title_out, content_out
            except Exception as error:
                message = str(error)
                print(f"[POLISH] Lỗi: {message}")
                if provider == "gemini-api" and (
                    "429" in message
                    or "RESOURCE_EXHAUSTED" in message
                    or "403" in message
                    or "PERMISSION_DENIED" in message
                ):
                    runtime.switch_key_for("polish")
                    delay = 30 if "429" in message or "RESOURCE_EXHAUSTED" in message else 15
                elif any(code in message for code in ("500", "502", "503", "504")):
                    delay = 10
                else:
                    delay = 15
                print(f"[POLISH] Chờ {delay}s rồi thử lại...")
                time.sleep(delay)
    finally:
        for path in (tmp_characters,):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass
