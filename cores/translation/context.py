"""Prepare glossary and previous-chapter context for translation."""

import os

from cores.chapters.files import get_translated_title, load_md_chapter
from cores.context import find_glossary_targets, load_context_text
from cores.r19 import strip_r19_terms


def chapter_id(path):
    return os.path.splitext(os.path.basename(path))[0]


def filtered_context_and_names(context_path, raw_files, start_index, chapter_count=1):
    """Return context and names found in the target chapters or next chapter."""
    stop_index = min(len(raw_files), start_index + chapter_count + 1)
    chapters = [load_md_chapter(path) for path in raw_files[start_index:stop_index]]
    raw_text = "\n".join(
        f"{chapter.get('title', '')}\n{chapter.get('content', '')}"
        for chapter in chapters
    )
    pronouns_path = os.path.join(
        os.path.dirname(os.path.abspath(context_path)), "pronouns.json"
    )
    return (
        load_context_text(context_path, raw_text=raw_text),
        find_glossary_targets(context_path, raw_text, pronouns_path),
        pronouns_path,
    )


def with_previous_titles(
    context_text, raw_files, current_index, translated_dir, count, heading
):
    previous_titles = []
    for offset in range(1, count + 1):
        if current_index - offset < 0:
            break
        previous_id = chapter_id(raw_files[current_index - offset])
        title = strip_r19_terms(get_translated_title(previous_id, translated_dir))
        if title:
            previous_titles.append(title)

    if not previous_titles:
        return context_text
    return f"{context_text}\n\n{heading}\n- " + "\n- ".join(previous_titles)
