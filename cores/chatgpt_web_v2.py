"""Batch post-translation stages executed in separate ChatGPT Web chats."""

import json
import os
import re
from copy import deepcopy

import yaml

from cores.dich_utils import (
    build_translation_review_prompt,
    generate_content_with_chatgpt,
    load_pronouns,
    project_polish_prompt,
    save_pronouns,
)
from cores.runtime_config import bool_option, option
from cores.r19_translation import (
    mask_postprocess_contexts,
    prepare_postprocess_chapter,
    restore_results,
)

NEW_CHAT_URL = "https://chatgpt.com/"


def stage_chatgpt_options(stage):
    model = str(
        option(f"gpt_v2_{stage}_model", "")
        or option("chatgpt_model", "gpt-5.6 sol")
    ).strip()
    thinking = str(
        option(f"gpt_v2_{stage}_thinking", "")
        or option("chatgpt_thinking", "cao")
    ).strip()
    return model, thinking


def _new_chat(prompt, stage):
    model, thinking = stage_chatgpt_options(stage)
    return generate_content_with_chatgpt(
        prompt,
        chat_url=NEW_CHAT_URL,
        chatgpt_model=model,
        chatgpt_thinking=thinking,
    )


def _run_stage(prompt, consume, stage, attempts=3):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return consume(_new_chat(prompt, stage))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            last_error = error
            print(
                f"[CHATGPT V2] Phản hồi sai format "
                f"({attempt}/{attempts}): {error}"
            )
    raise ValueError(f"ChatGPT Web V2 sai format sau {attempts} lần: {last_error}")


def _chapter_block(chapter, index, include_raw=True):
    raw = ""
    if include_raw:
        raw = f"""###RAW_TITLE###
{chapter.get('title', '')}
###RAW_CONTENT###
{chapter.get('content', '')}
"""
    return f"""###SECTION {index}###
###CHAPTER_ID###
{chapter.get('id', '')}
{raw}###TITLE###
{chapter.get('title_translation', '')}
###CONTENT###
{chapter.get('translation', '')}
"""


def build_polish_batch_prompt(chapters, context_text="", pronoun_context=""):
    role, task = project_polish_prompt()
    sections = "\n".join(
        _chapter_block(chapter, index)
        for index, chapter in enumerate(chapters, 1)
    )
    return f"""# Vai trò hiệu đính
{role}

# Nhiệm vụ
{task}

Hiệu đính toàn bộ {len(chapters)} chương dưới đây. Đối chiếu nguyên tác, giữ đủ nội dung, Markdown và thứ tự. Không giải thích.

## Thuật ngữ và quy tắc
{context_text}

## Bộ nhớ xưng hô
{pronoun_context}

RAW_TITLE và RAW_CONTENT chỉ là nguyên tác để đối chiếu, tuyệt đối không chép lại hai phần này trong phản hồi.
Chỉ trả về từ START đến END. Mỗi chương chỉ gồm đúng các marker SECTION, TITLE và CONTENT.
Không trả về CHAPTER_ID, RAW_TITLE hoặc RAW_CONTENT.

Mẫu phản hồi bắt buộc:
###START###
###SECTION 1###
###TITLE###
Tiêu đề đã hiệu đính
###CONTENT###
Nội dung đã hiệu đính
###END###

# Dữ liệu đầu vào

###START###
{sections}
###END###"""


def parse_polish_batch(text, expected_count):
    text = re.sub(r"\\#\\#\\#", "###", text or "")
    if "###START###" not in text or "###END###" not in text:
        raise ValueError("Kết quả hiệu đính thiếu START/END")
    results = []
    for index in range(1, expected_count + 1):
        marker = f"###SECTION {index}###"
        next_marker = (
            f"###SECTION {index + 1}###"
            if index < expected_count
            else "###END###"
        )
        start = text.find(marker)
        end = text.find(next_marker, start + len(marker))
        if start < 0 or end < 0:
            raise ValueError(f"Kết quả hiệu đính thiếu SECTION {index}")
        section = text[start:end]
        title_at = section.find("###TITLE###")
        content_at = section.find("###CONTENT###")
        if title_at < 0 or content_at < title_at:
            raise ValueError(f"SECTION {index} sai format")
        title = section[title_at + len("###TITLE###") : content_at].strip()
        content = section[content_at + len("###CONTENT###") :].strip()
        if not title or not content:
            raise ValueError(f"SECTION {index} trống")
        results.append((title, content))
    return results


def build_pronoun_batch_prompt(chapters):
    sections = "\n".join(
        _chapter_block(chapter, index, include_raw=False)
        for index, chapter in enumerate(chapters, 1)
    )
    return f"""Phân tích xưng hô trong batch bản dịch sau. Chỉ ghi nhận cặp nhân vật cụ thể và cách xưng hô xuất hiện rõ ràng.

Chỉ trả JSON hợp lệ:
{{"character_pairs":[{{"chapter_id":"v1_c1_s1","speaker":"A","listener":"B","speaker_self":"tôi","speaker_to_listener":"cậu","relationship_status":"...","emotional_tone":"..."}}]}}
Nếu không có, trả {{"character_pairs":[]}}. Không Markdown, không giải thích.
Sau JSON, thêm một dòng ###END### để đánh dấu đã trả xong.

{sections}

Nhắc lại: kết thúc phản hồi bằng ###END###"""


def _json_object(text):
    clean = re.sub(r"```json\s*|\s*```", "", text or "").strip()
    start, end = clean.find("{"), clean.rfind("}")
    if start < 0 or end < start:
        raise ValueError("ChatGPT không trả JSON hợp lệ")
    return json.loads(clean[start : end + 1])


def _prepare_polish_batch(chapters, context_text, pronoun_context):
    """Use one shared R19 map so placeholders stay unique across the batch."""
    if not bool_option("r19_mode", False):
        return chapters, context_text, pronoun_context, [], {}
    separator = "\n__CHATGPT_V2_CHAPTER_BOUNDARY__\n"
    combined = {
        field: separator.join(str(chapter.get(field, "")) for chapter in chapters)
        for field in ("title", "content", "title_translation", "translation")
    }
    masked, entries, translations = prepare_postprocess_chapter(combined)
    masked_chapters = [deepcopy(chapter) for chapter in chapters]
    for field in combined:
        values = masked[field].split(separator)
        if len(values) != len(chapters):
            raise ValueError("Không thể chia batch R19 sau khi tạo placeholder")
        for chapter, value in zip(masked_chapters, values):
            chapter[field] = value
    masked_context, masked_pronouns = mask_postprocess_contexts(
        [context_text, pronoun_context], translations
    )
    return masked_chapters, masked_context, masked_pronouns, entries, translations


def apply_pronoun_batch(text, chapters, start_chapter_number, pronouns_file):
    data = _json_object(text)
    chapter_numbers = {
        str(chapter.get("id", "")): number
        for number, chapter in enumerate(chapters, start_chapter_number)
    }
    memory = load_pronouns(pronouns_file)
    updated = 0
    for pair in data.get("character_pairs", []):
        chapter_id = str(pair.get("chapter_id", "")).strip()
        speaker = str(pair.get("speaker", "")).strip()
        listener = str(pair.get("listener", "")).strip()
        if chapter_id not in chapter_numbers or not speaker or not listener:
            continue
        names = sorted([speaker, listener])
        key = f"{names[0]}---{names[1]}"
        if memory.get(key, {}).get("locked"):
            continue
        record = memory.setdefault(key, {"characters": names, "timeline": []})
        record["timeline"].append(
            {
                "chapter_id": chapter_id,
                "chapter_number": chapter_numbers[chapter_id],
                "speaker": speaker,
                "listener": listener,
                "speaker_self": pair.get("speaker_self", ""),
                "speaker_to_listener": pair.get("speaker_to_listener", ""),
                "relationship_status": pair.get("relationship_status", ""),
                "emotional_tone": pair.get("emotional_tone", ""),
            }
        )
        record["timeline"] = sorted(
            record["timeline"], key=lambda item: item.get("chapter_number", 0)
        )[-25:]
        updated += 1
    save_pronouns(memory, pronouns_file)
    return updated


def build_review_batch_prompt(chapters, start_chapter_number, context_text=""):
    prompts = []
    for offset, chapter in enumerate(chapters):
        prompts.append(
            build_translation_review_prompt(
                chapter.get("id", ""),
                start_chapter_number + offset,
                chapter.get("title", ""),
                chapter.get("content", ""),
                chapter.get("title_translation", ""),
                chapter.get("translation", ""),
                context_text,
            )
        )
    return (
        """Review từng chương sau. Tuân theo tiêu chí và schema trong từng mục, nhưng trả một JSON hợp lệ dạng {"reviews":[<kết quả từng chương>]}. Không Markdown, không giải thích.\n\n"""
        + "\n\n===== CHƯƠNG TIẾP THEO =====\n\n".join(prompts)
        + "\n\nSau JSON, bắt buộc thêm một dòng ###END### để đánh dấu đã review xong."
    )


def save_review_batch(text, chapters, start_chapter_number, review_file):
    data = _json_object(text)
    expected = {str(chapter.get("id", "")) for chapter in chapters}
    reviews = data.get("reviews", [])
    returned = {str(item.get("chapter_id", "")) for item in reviews}
    if returned != expected:
        raise ValueError("Kết quả review không đủ đúng các chương trong batch")
    existing = {}
    if os.path.exists(review_file):
        with open(review_file, "r", encoding="utf-8") as handle:
            existing = yaml.safe_load(handle) or {}
    numbers = {
        str(chapter.get("id", "")): start_chapter_number + offset
        for offset, chapter in enumerate(chapters)
    }
    for item in reviews:
        chapter_id = str(item["chapter_id"])
        issues = item.get("issues", [])
        existing[chapter_id] = {
            "chapter_number": numbers[chapter_id],
            "score": item.get("overall_score"),
            "issue_count": len(issues),
            "issues": issues,
            "summary": str(item.get("summary", ""))[:1500],
        }
    with open(review_file, "w", encoding="utf-8") as handle:
        yaml.dump(existing, handle, allow_unicode=True, sort_keys=False)


def run_chatgpt_v2_batch(
    chapters,
    start_chapter_number,
    context_text,
    pronoun_context,
    pronouns_file,
    checkpoint=None,
):
    """Run enabled stages; every call to _new_chat starts a separate chat."""
    results = [
        (chapter.get("title_translation", ""), chapter.get("translation", ""))
        for chapter in chapters
    ]
    if bool_option("gpt_v2_polish", True):
        print(f"[CHATGPT V2] Hiệu đính batch {len(chapters)} chương trong chat mới...")
        (
            polish_chapters,
            polish_context,
            polish_pronouns,
            r19_entries,
            r19_translations,
        ) = _prepare_polish_batch(chapters, context_text, pronoun_context)
        results = _run_stage(
            build_polish_batch_prompt(
                polish_chapters, polish_context, polish_pronouns
            ),
            lambda text: parse_polish_batch(text, len(chapters)),
            "polish",
        )
        if r19_entries:
            results = restore_results(results, r19_entries, r19_translations)
        for chapter, (title, content) in zip(chapters, results):
            chapter["title_translation"] = title
            chapter["translation"] = content
        if checkpoint:
            checkpoint(results)
    else:
        print("[CHATGPT V2] Bỏ qua hiệu đính.")

    if bool_option("gpt_v2_pronouns", True):
        print(f"[CHATGPT V2] Xuất xưng hô batch {len(chapters)} chương trong chat mới...")
        _run_stage(
            build_pronoun_batch_prompt(chapters),
            lambda text: apply_pronoun_batch(
                text, chapters, start_chapter_number, pronouns_file
            ),
            "pronouns",
        )
    else:
        print("[CHATGPT V2] Bỏ qua xuất xưng hô.")

    if bool_option("gpt_v2_review", True):
        print(f"[CHATGPT V2] Review batch {len(chapters)} chương trong chat mới...")
        review_file = os.path.join(os.path.dirname(pronouns_file), "review.yaml")
        _run_stage(
            build_review_batch_prompt(chapters, start_chapter_number, context_text),
            lambda text: save_review_batch(
                text, chapters, start_chapter_number, review_file
            ),
            "review",
        )
    else:
        print("[CHATGPT V2] Bỏ qua review.")
    return results
