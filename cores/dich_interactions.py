"""V1 translation using the Gemini Interactions API with SSE streaming (Beta)."""

import os
import json
import re
import sys
import time

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

from cores import dich_utils, dich_v1
from cores.gemini_interactions import stream_interaction
from cores.runtime_config import bool_option, option, stop_requested, web_mode


_stage = None
_chapter = None
_stream_text = ""
_polish_original_lines = []
_polish_emitted = {}
_original_translate = dich_v1.translate_chapter
_original_polish = dich_utils.polish_translation


def _emit(event_type, **payload):
    if not _chapter:
        return
    event = {"type": event_type, "chapter": f"{_chapter}.md", **payload}
    print(
        "@@NOVEL_STREAM@@" + json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        flush=True,
    )


def _parsed_stream(text):
    text = re.sub(r"\\\#\\\#\\\#", "###", text or "")
    if "###TITLE###" not in text or "###CONTENT###" not in text:
        return None
    title_block, content = text.split("###CONTENT###", 1)
    title = title_block.split("###TITLE###", 1)[1].strip()
    complete = "###END###" in content
    if complete:
        content = content.split("###END###", 1)[0]
    content = content.lstrip("\r\n")
    markdown = f"# {title}\n\n{content}"
    return markdown, complete


def _stream_to_workspace(delta):
    global _stream_text
    if _stage not in {"translation", "polish"}:
        return
    _stream_text += delta
    parsed = _parsed_stream(_stream_text)
    if not parsed:
        return
    markdown, complete = parsed
    if _stage == "translation":
        _emit("translation_snapshot", text=markdown.rstrip() if complete else markdown)
    else:
        _emit_polish_lines(markdown, complete=complete)


def _emit_polish_lines(markdown, complete=False):
    lines = markdown.splitlines()
    ready = len(lines) if complete or markdown.endswith("\n") else max(2, len(lines) - 1)
    for index in range(ready):
        current = lines[index]
        original = _polish_original_lines[index] if index < len(_polish_original_lines) else ""
        if current != original and _polish_emitted.get(index) != current:
            _polish_emitted[index] = current
            _emit("polish_line", line=index, text=current)


def _finish_workspace_stream(text):
    parsed = _parsed_stream(text)
    if not parsed:
        return
    markdown, _ = parsed
    markdown = markdown.rstrip() + "\n"
    if _stage == "translation":
        _emit("translation_snapshot", text=markdown)
    elif _stage == "polish":
        _emit_polish_lines(markdown, complete=True)
        _emit("polish_complete", text=markdown)


def _configured_generation(temperature):
    config = {}
    configured_temperature = option("gemini_api_temperature", "")
    config["temperature"] = float(configured_temperature) if configured_temperature not in (None, "") else temperature
    thinking = str(option("gemini_api_thinking", "high")).strip().lower()
    if thinking == "off":
        config["thinking_level"] = "minimal"
    elif thinking != "auto":
        config["thinking_level"] = thinking
    for setting, field, converter in (
        ("gemini_api_top_p", "top_p", float),
        ("gemini_api_top_k", "top_k", int),
        ("gemini_api_max_output_tokens", "max_output_tokens", int),
    ):
        value = option(setting, "")
        if value not in (None, ""):
            config[field] = converter(value)
    return config


def call_interactions(
    prompt, model, temperature=0.5, system_instruction=None, **_kwargs
):
    global _stream_text
    if _stage in {"translation", "polish"}:
        _stream_text = ""
    api_key = dich_utils.API_KEYS[dich_utils.current_key_index]
    print(f"[INTERACTIONS BETA] Streaming từ {model}...")
    text = stream_interaction(
        api_key=api_key,
        model=model,
        prompt=prompt,
        generation_config=_configured_generation(temperature),
        system_instruction=system_instruction,
        on_text=_stream_to_workspace,
        stop_requested=stop_requested,
    )
    _finish_workspace_stream(text)
    return text


def translate_interactions(chapter, chapter_number, context_text="", pronoun_context=""):
    global _stage, _chapter, _stream_text
    _chapter = chapter.get("id", f"chapter_{chapter_number}")
    _stage = "translation"
    _stream_text = ""
    try:
        return _original_translate(
            chapter, chapter_number, context_text, pronoun_context
        )
    finally:
        _stage = None


def polish_interactions(*args, **kwargs):
    global _stage, _chapter, _stream_text, _polish_original_lines, _polish_emitted
    chapter = args[0] if args else kwargs.get("chapter", {})
    chapter_number = args[1] if len(args) > 1 else kwargs.get("chapter_number", 0)
    _chapter = chapter.get("id", f"chapter_{chapter_number}")
    original_markdown = (
        f"# {chapter.get('title_translation', '')}\n\n"
        f"{chapter.get('translation', '')}"
    )
    _polish_original_lines = original_markdown.splitlines()
    _polish_emitted = {}
    _stream_text = ""
    _stage = "polish"
    try:
        return _original_polish(*args, **kwargs)
    finally:
        _stage = None


def main():
    dich_v1.call_gemini = call_interactions
    dich_v1.translate_chapter = translate_interactions
    dich_utils.call_gemini = call_interactions
    dich_utils.polish_translation = polish_interactions
    print("Gemini Interactions Streaming — V1 (Beta)")
    print(f"Model dịch chính: {dich_v1.TRANSLATE_MODEL}")
    while True:
        if stop_requested():
            break
        dich_v1.run_translation()
        raw_files = dich_utils.scan_md_dir(dich_utils.RAW_DIR)
        if all(
            dich_utils.is_translated(
                os.path.splitext(os.path.basename(path))[0],
                dich_utils.TRANSLATED_DIR,
            )
            for path in raw_files
        ):
            print("Đã dịch hết tất cả các chương.")
            break
        if web_mode() and not bool_option("run_until_complete", False):
            print("Đã xử lý một chương bằng Interactions API Beta.")
            break
        time.sleep(1)


if __name__ == "__main__":
    main()
