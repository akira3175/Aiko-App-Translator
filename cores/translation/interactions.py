"""Gemini Interactions streaming transport for the translation pipeline."""

import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from cores.config import CONTEXT_JSON, PRONOUNS_JSON, RAW_DIR, TRANSLATED_DIR
from cores.gemini.interactions import stream_interaction
from cores.gemini import current_gemini_api_key
from cores.config.runtime import chapter_limit, option, stop_requested, web_mode
from cores.postprocess import run_post_translation_pipeline
from cores.translation.runner import run_single_translation
from cores.translation import stage as translation_stage


_stage = None
_chapter = None
_stream_text = ""
_polish_original_lines = []
_polish_emitted = {}


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
    return f"# {title}\n\n{content}", complete


def _emit_polish_lines(markdown, complete=False):
    lines = markdown.splitlines()
    ready = len(lines) if complete or markdown.endswith("\n") else max(2, len(lines) - 1)
    for index in range(ready):
        current = lines[index]
        original = _polish_original_lines[index] if index < len(_polish_original_lines) else ""
        if current != original and _polish_emitted.get(index) != current:
            _polish_emitted[index] = current
            _emit("polish_line", line=index, text=current)


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


def _configured_generation():
    config = {}
    thinking = str(option("gemini_api_thinking", "high")).strip().lower()
    if thinking == "off":
        config["thinking_level"] = "minimal"
    elif thinking != "auto":
        config["thinking_level"] = thinking
    value = option("gemini_api_max_output_tokens", "")
    if value not in (None, ""):
        config["max_output_tokens"] = int(value)
    return config


def call_interactions(
    prompt,
    model,
    system_instruction=None,
    character_document=None,
    pronoun_document=None,
    **_kwargs,
):
    global _stream_text
    if _stage in {"translation", "polish"}:
        _stream_text = ""
    print(f"[INTERACTIONS BETA] Streaming từ {model}...")
    text = stream_interaction(
        api_key=current_gemini_api_key(),
        model=model,
        prompt=prompt,
        generation_config=_configured_generation(),
        system_instruction=system_instruction,
        documents=[
            item
            for item in (
                {"name": "characters.md", "mime_type": "text/markdown", "content": character_document}
                if character_document else None,
                {"name": "pronouns_snapshot.json", "mime_type": "application/json", "content": pronoun_document}
                if pronoun_document else None,
            )
            if item
        ],
        on_text=_stream_to_workspace,
        stop_requested=stop_requested,
    )
    _finish_workspace_stream(text)
    return text


def translate_interactions(chapter, chapter_number, context_text="", pronoun_context=""):
    global _stage, _chapter, _stream_text
    _chapter = chapter.get("id", f"chapter_{chapter_number}")
    _stage, _stream_text = "translation", ""
    try:
        return translation_stage.translate_chapter(
            chapter, chapter_number, context_text, pronoun_context
        )
    finally:
        _stage = None


def postprocess_interactions(chapter, chapter_number, context_text="", pronoun_context=""):
    global _stage, _chapter, _stream_text, _polish_original_lines, _polish_emitted
    _chapter = chapter.get("id", f"chapter_{chapter_number}")
    original = f"# {chapter.get('title_translation', '')}\n\n{chapter.get('translation', '')}"
    _polish_original_lines = original.splitlines()
    _polish_emitted, _stream_text, _stage = {}, "", "polish"
    try:
        return run_post_translation_pipeline(
            chapter,
            chapter_number,
            context_text,
            pronoun_context,
            PRONOUNS_JSON,
        )
    finally:
        _stage = None


def _run_translation_with_retry():
    try:
        return run_single_translation(
            translate_interactions,
            RAW_DIR,
            TRANSLATED_DIR,
            CONTEXT_JSON,
            postprocess=postprocess_interactions,
        ) or 0
    except Exception as exc:
        print(f"⚠️ Lỗi khi dịch: {exc}")
        print("⏳ Gemini đang bận hoặc gặp lỗi; chờ 15s rồi thử lại...")
        for _ in range(15):
            if stop_requested():
                return 0
            time.sleep(1)
        return 0


def main():
    translation_stage.TRANSPORT_OVERRIDES["gemini-api"] = call_interactions
    print("Gemini Interactions Streaming — Pipeline 1.0 (Beta)")
    limit, processed = chapter_limit(), 0
    while not stop_requested():
        count = _run_translation_with_retry()
        processed += count
        if not count or (web_mode() and limit is not None and processed >= limit):
            break
        time.sleep(1)


if __name__ == "__main__":
    main()
