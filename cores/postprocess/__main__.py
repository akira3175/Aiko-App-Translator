"""Polish one existing translated chapter without running other stages."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cores.chapters.files import load_md_chapter, save_translated_md, scan_md_dir
from cores.chapters.images import uses_image_markers
from cores.config import CONTEXT_JSON, RAW_DIR, TRANSLATED_DIR
from cores.config.runtime import option, task_config
from cores.postprocess import runtime
from cores.pronouns import format_pronoun_context
from cores.translation.context import filtered_context_and_names
from providers.registry import pipeline_config


def main():
    config = pipeline_config(task_config())
    os.environ["NOVEL_WEB_CONFIG"] = json.dumps(config, ensure_ascii=False)
    task_config.cache_clear()
    target = Path(str(option("target_chapter", "") or "")).name
    raw_files = scan_md_dir(RAW_DIR)
    raw_path = next((path for path in raw_files if Path(path).name == target), None)
    translated_path = Path(TRANSLATED_DIR) / target
    if not raw_path or not translated_path.is_file():
        raise RuntimeError("Không tìm thấy chương đã dịch cần hiệu đính")

    chapter_index = raw_files.index(raw_path)
    marker_mode = uses_image_markers(translated_path)
    chapter = load_md_chapter(raw_path, image_markers=marker_mode)
    translated = load_md_chapter(translated_path, image_markers=marker_mode)
    if marker_mode:
        chapter["_image_markers"] = translated["_image_markers"]
    chapter["title_translation"] = translated["title"]
    chapter["translation"] = translated["content"]
    context_text, glossary_names, pronouns_path = filtered_context_and_names(
        CONTEXT_JSON, raw_files, chapter_index
    )
    pronoun_context = format_pronoun_context(
        chapter_index + 1,
        pronouns_file=pronouns_path,
        glossary_names=glossary_names,
    )
    provider = runtime.provider("polish")
    if provider == "off":
        raise RuntimeError("Công đoạn Hiệu đính đang tắt trong Cài đặt")
    runtime.setup_browser(provider)
    try:
        print(f"Đang hiệu đính {target} bằng {provider}...")
        title, content = runtime.polish_translation(
            chapter,
            chapter_index + 1,
            context_text,
            pronoun_context,
            pronouns_file=pronouns_path,
        )
        chapter["title_translation"] = title
        chapter["translation"] = content
        title, content = runtime.fix_translation(
            chapter, chapter_index + 1, context_text, pronoun_context
        )
        output = save_translated_md(
            raw_path, TRANSLATED_DIR, title, content,
            image_markers=chapter.get("_image_markers"),
        )
        print(f"Đã lưu bản hiệu đính: {output}")
    finally:
        runtime.close_browsers()


if __name__ == "__main__":
    main()
