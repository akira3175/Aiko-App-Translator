"""Shared file-processing workflows for translation engines.

Engine modules own prompt construction and provider calls. This module owns the
common traversal, context preparation, post-processing, and output persistence.
"""

import os
import re
import time
from collections.abc import Callable

from cores.runtime_config import option

from cores.dich_utils import (
    export_recent_translations_to_txt_md,
    find_glossary_targets,
    format_pronoun_context,
    get_translated_title,
    is_translated,
    load_context,
    load_md_chapter,
    run_post_translation_pipeline,
    save_translated_md,
    scan_md_dir,
)

TranslateOne = Callable[[dict, int, str, str], tuple[str, str]]
TranslateBatch = Callable[[list[dict], int, str, str], list[tuple[str, str]]]


def _chapter_id(path):
    return os.path.splitext(os.path.basename(path))[0]


def _raw_text_for_glossary(paths):
    chapters = [load_md_chapter(path) for path in paths]
    return "\n".join(
        f"{chapter.get('title', '')}\n{chapter.get('content', '')}"
        for chapter in chapters
    )


def _filtered_context_and_names(
    context_path, raw_files, start_index, chapter_count=1
):
    """Use glossary terms found in the target chapter(s) or the next chapter."""
    stop_index = min(len(raw_files), start_index + chapter_count + 1)
    raw_text = _raw_text_for_glossary(raw_files[start_index:stop_index])
    pronouns_path = os.path.join(
        os.path.dirname(os.path.abspath(context_path)), "pronouns.yaml"
    )
    return (
        load_context(context_path, raw_text=raw_text),
        find_glossary_targets(context_path, raw_text, pronouns_path),
        pronouns_path,
    )


def translate_batch_with_web(
    batch,
    start_chapter_number,
    context_text,
    pronoun_context,
    *,
    novel_text_path,
    build_prompt,
    generate,
    reset_browser,
    engine_name,
    require_boundaries=False,
    max_retries=3,
):
    """Shared retry and response parser for browser-based batch engines."""
    chapter_count = len(batch)
    previous_chapters = ""
    if os.path.exists(novel_text_path):
        with open(novel_text_path, "r", encoding="utf-8") as file:
            previous_chapters = file.read().strip()

    prompt = build_prompt(batch, context_text, pronoun_context, previous_chapters)
    for attempt in range(max_retries):
        if attempt:
            print(f"🔄 Thử lại lần {attempt + 1}/{max_retries}...")
            reset_browser()
            time.sleep(3)

        end_chapter = start_chapter_number + chapter_count - 1
        print(
            f"✨ Đang dịch batch {chapter_count} chương "
            f"(từ Chương {start_chapter_number} đến Chương {end_chapter}) "
            f"qua {engine_name}..."
        )
        text = re.sub(r"\\\#\\\#\\\#", "###", generate(prompt) or "")

        if require_boundaries and (
            "###START###" not in text or "###END###" not in text
        ):
            print(
                f"⚠️ Response bị cắt ngang (thiếu START hoặc END) (lần {attempt + 1})."
            )
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            raise ValueError(
                f"AI không trả về đủ START và END sau {max_retries} lần thử"
            )

        missing = [
            f"###SECTION {index}###"
            for index in range(1, chapter_count + 1)
            if f"###SECTION {index}###" not in text
        ]
        if missing:
            print(f"⚠️ Response thiếu SECTION (lần {attempt + 1}). Thiếu: {missing}")
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            raise ValueError(f"Không thể dịch các chương sau {max_retries} lần thử")

        results = []
        has_placeholder = False
        for index in range(1, chapter_count + 1):
            start_marker = f"###SECTION {index}###"
            end_marker = (
                f"###SECTION {index + 1}###" if index < chapter_count else "###END###"
            )
            section_start = text.find(start_marker)
            section_end = text.find(end_marker)
            if section_end < 0:
                section_end = len(text)
            section = text[section_start:section_end]

            title = content = ""
            if "###TITLE###" in section and "###CONTENT###" in section:
                title_start = section.find("###TITLE###") + len("###TITLE###")
                content_start = section.find("###CONTENT###")
                title = section[title_start:content_start].strip()
                content = section[content_start + len("###CONTENT###") :].strip()

            if any(
                marker in title.lower()
                for marker in ("<tiêu đề dịch chương", "<tiêu đề")
            ):
                has_placeholder = True
            results.append((title, content))

        if has_placeholder:
            print(f"⚠️ AI trả về placeholder (lần {attempt + 1})")
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            raise ValueError(f"AI trả về placeholder sau {max_retries} lần thử")
        return results

    raise ValueError("Lỗi dịch hàng loạt")


def _context_with_previous_titles(
    context_text, raw_files, current_index, translated_dir, count, heading
):
    previous_titles = []
    for offset in range(1, count + 1):
        if current_index - offset < 0:
            break
        previous_id = _chapter_id(raw_files[current_index - offset])
        title = get_translated_title(previous_id, translated_dir)
        if title:
            previous_titles.append(title)

    if not previous_titles:
        return context_text
    return f"{context_text}\n\n{heading}\n- " + "\n- ".join(previous_titles)


def run_single_translation(
    translate: TranslateOne, raw_dir, translated_dir, context_path, postprocess=None
):
    """Translate and persist the first untranslated chapter."""
    raw_files = scan_md_dir(raw_dir)
    if not raw_files:
        print(f"[INFO] Không tìm thấy file .md nào trong {raw_dir}")
        return

    target_chapter = str(option("target_chapter", "") or "").strip()
    for index, raw_path in enumerate(raw_files):
        if target_chapter and os.path.basename(raw_path) != target_chapter:
            continue
        chapter_id = _chapter_id(raw_path)
        if is_translated(chapter_id, translated_dir):
            continue

        chapter_number = index + 1
        chapter = load_md_chapter(raw_path)
        context_text, glossary_names, pronouns_path = _filtered_context_and_names(
            context_path, raw_files, index
        )
        pronoun_context = format_pronoun_context(
            chapter_number,
            pronouns_file=pronouns_path,
            glossary_names=glossary_names,
        )
        previous_count = int(option("previous_context_chapters", 3))
        export_recent_translations_to_txt_md(target_chapter_id=chapter_id, n=previous_count)
        print(f"📖 Đang dịch Chương {chapter_number}: {chapter['id']}...")

        translation_context = _context_with_previous_titles(
            context_text,
            raw_files,
            index,
            translated_dir,
            count=previous_count,
            heading="Các tiêu đề trước đã dịch:",
        )
        result = translate(
            chapter, chapter_number, translation_context, pronoun_context
        )
        if result is None:
            return
        title, content = result
        chapter["title_translation"] = title
        chapter["translation"] = content

        if postprocess is None:
            title, content = run_post_translation_pipeline(
                chapter,
                chapter_number,
                context_text,
                pronoun_context,
                pronouns_file=pronouns_path,
            )
        else:
            title, content = postprocess(
                chapter, chapter_number, context_text, pronoun_context
            )
        chapter["title_translation"] = title
        chapter["translation"] = content

        output_path = save_translated_md(raw_path, translated_dir, title, content)
        print(f"✔ Đã lưu: {output_path}")
        return 1


def run_batch_translation(
    translate: TranslateBatch,
    batch_size,
    raw_dir,
    translated_dir,
    context_path,
):
    """Translate and persist the first consecutive untranslated batch."""
    raw_files = scan_md_dir(raw_dir)
    if not raw_files:
        print(f"[INFO] Không tìm thấy file .md nào trong {raw_dir}")
        return

    target_chapter = str(option("target_chapter", "") or "").strip()
    for index, raw_path in enumerate(raw_files):
        if target_chapter and os.path.basename(raw_path) != target_chapter:
            continue
        chapter_id = _chapter_id(raw_path)
        if is_translated(chapter_id, translated_dir):
            continue

        if target_chapter:
            batch_paths = [raw_path]
        else:
            batch_paths = []
            for path in raw_files[index : index + batch_size]:
                if is_translated(_chapter_id(path), translated_dir):
                    break
                batch_paths.append(path)

        if not batch_paths:
            continue

        batch = [load_md_chapter(path) for path in batch_paths]
        context_text, glossary_names, pronouns_path = _filtered_context_and_names(
            context_path, raw_files, index, chapter_count=len(batch_paths)
        )
        start_chapter_number = index + 1
        pronoun_context = format_pronoun_context(
            start_chapter_number,
            pronouns_file=pronouns_path,
            glossary_names=glossary_names,
        )
        previous_count = int(option("previous_context_chapters", 3))
        export_recent_translations_to_txt_md(target_chapter_id=chapter_id, n=previous_count)
        print(f"📖 Chuẩn bị dịch Batch {len(batch)} chương (từ {chapter_id})...")

        translation_context = _context_with_previous_titles(
            context_text,
            raw_files,
            index,
            translated_dir,
            count=previous_count,
            heading="Các tiêu đề trước đã dịch:",
        )
        results = translate(
            batch, start_chapter_number, translation_context, pronoun_context
        )

        for chapter, (title, content) in zip(batch, results):
            chapter["title_translation"] = title
            chapter["translation"] = content
            print(f"✔ Dịch sơ bộ xong: {chapter['id']} — {title}")

        print("\n🔧 Đang chạy pipeline hậu dịch cho từng chương trong batch...")
        for offset, (chapter, path) in enumerate(zip(batch, batch_paths)):
            chapter_number = start_chapter_number + offset
            (
                chapter_context,
                chapter_glossary_names,
                chapter_pronouns_path,
            ) = _filtered_context_and_names(
                context_path, raw_files, index + offset
            )
            current_pronouns = format_pronoun_context(
                chapter_number,
                pronouns_file=chapter_pronouns_path,
                glossary_names=chapter_glossary_names,
            )
            title, content = run_post_translation_pipeline(
                chapter,
                chapter_number,
                chapter_context,
                current_pronouns,
                pronouns_file=chapter_pronouns_path,
            )
            chapter["title_translation"] = title
            chapter["translation"] = content
            output_path = save_translated_md(path, translated_dir, title, content)
            print(f"✅ Đã lưu: {output_path}")

        print(f"✅ Hoàn tất Batch {len(batch)} chương!")
        return len(batch)
