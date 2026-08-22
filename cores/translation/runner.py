"""Run and persist one translation chapter."""

import os
from collections.abc import Callable

from cores.chapters.files import (
    export_recent_translations,
    is_translated,
    load_md_chapter,
    save_translated_md,
    scan_md_dir,
)
from cores.config import NOVEL_TXT, RAW_DIR, TRANSLATED_DIR
from cores.postprocess import enqueue_background_review, run_post_translation_pipeline
from cores.pronouns import format_pronoun_context
from cores.r19 import (
    mask_postprocess_contexts,
    prepare_postprocess_chapter,
    restore_results,
)
from cores.config.runtime import bool_option, option
from cores.translation.context import (
    chapter_id,
    filtered_context_and_names,
    with_previous_titles,
)

TranslateOne = Callable[[dict, int, str, str], tuple[str, str]]


def _export_recent_translations(target_chapter_id, count):
    return export_recent_translations(
        RAW_DIR,
        TRANSLATED_DIR,
        NOVEL_TXT,
        n=count,
        target_chapter_id=target_chapter_id,
    )


def run_single_translation(
    translate: TranslateOne, raw_dir, translated_dir, context_path, postprocess=None
):
    """Translate and persist the first untranslated chapter."""
    raw_files = scan_md_dir(raw_dir)
    if not raw_files:
        print(f"[INFO] Khong tim thay file .md nao trong {raw_dir}")
        return

    target_chapter = str(option("target_chapter", "") or "").strip()
    for index, raw_path in enumerate(raw_files):
        if target_chapter and os.path.basename(raw_path) != target_chapter:
            continue
        current_chapter_id = chapter_id(raw_path)
        if is_translated(current_chapter_id, translated_dir):
            continue

        chapter_number = index + 1
        chapter = load_md_chapter(raw_path)
        context_text, glossary_names, pronouns_path = filtered_context_and_names(
            context_path, raw_files, index
        )
        pronoun_context = format_pronoun_context(
            chapter_number,
            pronouns_file=pronouns_path,
            glossary_names=glossary_names,
        )
        previous_count = int(option("previous_context_chapters", 3))
        _export_recent_translations(current_chapter_id, previous_count)
        print(f"Dang dich Chuong {chapter_number}: {chapter['id']}...")

        translation_context = with_previous_titles(
            context_text,
            raw_files,
            index,
            translated_dir,
            count=previous_count,
            heading="Cac tieu de truoc da dich:",
        )
        result = translate(chapter, chapter_number, translation_context, pronoun_context)
        if result is None:
            return
        title, content = result
        chapter["title_translation"] = title
        chapter["translation"] = content

        postprocess_entries = []
        postprocess_translations = {}
        pipeline_context = context_text
        pipeline_pronouns = pronoun_context
        if bool_option("r19_mode", False):
            chapter, postprocess_entries, postprocess_translations = (
                prepare_postprocess_chapter(chapter)
            )
            pipeline_context, pipeline_pronouns = mask_postprocess_contexts(
                [context_text, pronoun_context], postprocess_translations
            )
        if postprocess is None:
            title, content = run_post_translation_pipeline(
                chapter,
                chapter_number,
                pipeline_context,
                pipeline_pronouns,
                pronouns_file=pronouns_path,
            )
        else:
            title, content = postprocess(
                chapter, chapter_number, pipeline_context, pipeline_pronouns
            )
        if postprocess_entries:
            title, content = restore_results(
                [(title, content)], postprocess_entries, postprocess_translations
            )[0]
        chapter["title_translation"] = title
        chapter["translation"] = content

        output_path = save_translated_md(raw_path, translated_dir, title, content)
        print(f"Da luu: {output_path}")
        enqueue_background_review(chapter, chapter_number, pipeline_context)
        return 1
