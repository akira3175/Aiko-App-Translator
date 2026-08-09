"""Translate one Markdown chapter, then polish it, using GPT API only."""

import msvcrt
import os
import re
import sys
import time

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from cores.dich_utils import (
    CONTEXT_YAML,
    NOVEL_TXT,
    PRONOUNS_YAML,
    RAW_DIR,
    TRANSLATED_DIR,
    is_translated,
    scan_md_dir,
    update_pronoun_memory,
)
from cores.gpt_api_client import call_gpt_api
from cores.runtime_config import chapter_limit, option, stop_requested, web_mode
from cores.translation_prompts import build_single_prompt, project_polish_prompt
from cores.translation_workflows import run_single_translation

TRANSLATE_MODEL = str(option("gpt_api_translate_model", "gpt-5.6-luna"))
POLISH_MODEL = str(option("gpt_api_polish_model", "gpt-5.6-terra"))
PRONOUN_MODEL = str(option("gpt_api_pronoun_model", "gpt-5.6-terra"))


def _parse_result(text, stage):
    text = re.sub(r"\\###", "###", text or "")
    if "###TITLE###" not in text or "###CONTENT###" not in text:
        raise ValueError(f"GPT API trả sai định dạng ở bước {stage}.")
    title_start = text.find("###TITLE###") + len("###TITLE###")
    content_start = text.find("###CONTENT###")
    title = text[title_start:content_start].strip()
    raw_content = text[content_start + len("###CONTENT###") :]
    end = raw_content.find("###END###")
    content = (raw_content[:end] if end >= 0 else raw_content).strip()
    placeholders = {"tiêu đề dịch", "nội dung dịch", "translated title", "translated content"}
    if not title or not content or title.strip("<>").lower() in placeholders or content.strip("<>").lower() in placeholders:
        raise ValueError(f"GPT API trả placeholder hoặc nội dung trống ở bước {stage}.")
    return title, content


def translate_chapter(chapter, chapter_number, context_text="", pronoun_context=""):
    previous = ""
    if os.path.exists(NOVEL_TXT):
        with open(NOVEL_TXT, "r", encoding="utf-8") as file:
            previous = file.read().strip()
    prompt = build_single_prompt(chapter, context_text, pronoun_context, previous)
    print(f"[GPT API] Dịch chương {chapter_number} bằng {TRANSLATE_MODEL}...")
    text = call_gpt_api(
        prompt,
        model=TRANSLATE_MODEL,
        reasoning_effort=option("gpt_api_translate_effort", "medium"),
        stage="dịch",
    )
    return _parse_result(text, "dịch")


def polish_chapter(chapter, chapter_number, context_text="", pronoun_context=""):
    if POLISH_MODEL.strip().lower() in {"", "none"}:
        print("[GPT API] Bỏ qua hiệu đính vì chưa cấu hình model.")
        return chapter.get("title_translation", ""), chapter.get("translation", "")
    polish_role, polish_task = project_polish_prompt()
    prompt = f"""# Vai trò hiệu đính
{polish_role}

# Nhiệm vụ hiệu đính
{polish_task}

Các quy tắc kỹ thuật bắt buộc: giữ nguyên đầy đủ nội dung, dấu hội thoại, Markdown ảnh và ký hiệu cần thiết. Không giải thích thay đổi. Các mục xưng hô có locked: true phải được ưu tiên.

## Thuật ngữ và quy tắc
{context_text}

## Bộ nhớ xưng hô
{pronoun_context}

## Nguyên tác
Tiêu đề: {chapter.get('title', '')}
{chapter.get('content', '')}

## Bản dịch cần hiệu đính
Tiêu đề: {chapter.get('title_translation', '')}
{chapter.get('translation', '')}

Chỉ trả về:
###TITLE###
<tiêu đề hoàn chỉnh>
###CONTENT###
<nội dung hoàn chỉnh>
###END###"""
    print(f"[GPT API] Hiệu đính chương {chapter_number} bằng {POLISH_MODEL}...")
    text = call_gpt_api(
        prompt,
        model=POLISH_MODEL,
        reasoning_effort=option("gpt_api_polish_effort", "high"),
        stage="hiệu đính",
    )
    return _parse_result(text, "hiệu đính")


def postprocess_chapter(chapter, chapter_number, context_text="", pronoun_context=""):
    title, content = polish_chapter(
        chapter, chapter_number, context_text, pronoun_context
    )
    chapter["title_translation"] = title
    chapter["translation"] = content

    if PRONOUN_MODEL.strip().lower() in {"", "none"}:
        print("[GPT API] Bỏ qua cập nhật xưng hô vì chưa cấu hình model.")
        return title, content

    def generate_pronouns(prompt):
        return call_gpt_api(
            prompt,
            model=PRONOUN_MODEL,
            reasoning_effort=option("gpt_api_polish_effort", "high"),
            stage="cập nhật xưng hô",
        )

    update_pronoun_memory(
        chapter.get("id", f"chapter_{chapter_number}"),
        chapter_number,
        content,
        PRONOUNS_YAML,
        model=PRONOUN_MODEL,
        generate=generate_pronouns,
    )
    return title, content


def run_translation():
    return run_single_translation(
        translate_chapter,
        RAW_DIR,
        TRANSLATED_DIR,
        CONTEXT_YAML,
        postprocess=postprocess_chapter,
    )


if __name__ == "__main__":
    print("GPT API — dịch và hiệu đính bằng API")
    print(f"Model dịch: {TRANSLATE_MODEL} | Model hiệu đính: {POLISH_MODEL}")
    limit = chapter_limit()
    processed = 0
    while True:
        if stop_requested():
            break
        try:
            processed += run_translation() or 0
        except Exception as exc:
            print(f"[GPT API] Lỗi: {exc}")
            if web_mode():
                raise
            time.sleep(15)
            continue
        raw_files = scan_md_dir(RAW_DIR)
        if all(is_translated(os.path.splitext(os.path.basename(path))[0], TRANSLATED_DIR) for path in raw_files):
            print("Đã dịch hết tất cả các chương.")
            break
        if web_mode() and limit is not None and processed >= limit:
            break
        print("Nhấn Enter để dừng, phím bất kỳ để tiếp tục.")
        while not msvcrt.kbhit():
            time.sleep(0.1)
        if msvcrt.getch() == b"\r":
            break
