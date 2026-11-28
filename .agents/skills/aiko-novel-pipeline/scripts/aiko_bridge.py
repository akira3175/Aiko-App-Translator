#!/usr/bin/env python3
"""Direct Antigravity <-> Aiko App Translator bridge reusing 100% of optimized `cores/*` logic."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys


APP_ROOT = Path(__file__).resolve().parents[4]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _extract_project_arg(argv: list[str]) -> str:
    for idx, token in enumerate(argv):
        if token == "--project" and idx + 1 < len(argv):
            return argv[idx + 1].strip()
        if token.startswith("--project="):
            return token.split("=", 1)[1].strip()
    return ""


# Must run BEFORE importing `cores.*` because `cores.config.project_paths` binds NOVEL_PROJECT on import.
_initial_project = _extract_project_arg(sys.argv[1:])
if _initial_project:
    os.environ["NOVEL_PROJECT"] = _initial_project
os.chdir(APP_ROOT)


def _require_project_dir(project: str) -> Path:
    if not project:
        raise SystemExit("Thiếu tham số --project <Tên truyện>.")
    project_dir = APP_ROOT / "truyen" / project
    if not project_dir.is_dir():
        available = sorted(
            p.name for p in (APP_ROOT / "truyen").iterdir() if p.is_dir()
        ) if (APP_ROOT / "truyen").is_dir() else []
        hint = ", ".join(available) if available else "(chưa có truyện nào trong truyen/)"
        raise SystemExit(f"Không tìm thấy truyện '{project}'. Các truyện hiện có: {hint}")
    return project_dir


def _foreign_lines(text: str) -> list[str]:
    from cores.chapters.files import has_foreign

    bad: list[str] = []
    for line_no, line in enumerate(str(text or "").splitlines(), start=1):
        if has_foreign(line):
            bad.append(f"L{line_no}: {line.strip()[:140]}")
    return bad


def _resolve_chapter_index(raw_files: list[str], chapter_arg: str | None, translated_dir: Path, *, require_translated: bool = False) -> int:
    from cores.chapters.files import is_translated
    from cores.translation.context import chapter_id

    if chapter_arg:
        normalized = chapter_arg if chapter_arg.endswith(".md") else f"{chapter_arg}.md"
        names = [os.path.basename(p) for p in raw_files]
        if normalized not in names:
            raise SystemExit(f"Không tìm thấy chương '{normalized}' trong raw/.")
        idx = names.index(normalized)
        cid = chapter_id(raw_files[idx])
        if require_translated and not is_translated(cid, str(translated_dir)):
            raise SystemExit(f"Chương '{normalized}' chưa có bản dịch trong translated/.")
        return idx

    for idx, raw_path in enumerate(raw_files):
        cid = chapter_id(raw_path)
        has_trans = is_translated(cid, str(translated_dir))
        if require_translated and has_trans:
            return idx
        if not require_translated and not has_trans:
            return idx
    raise SystemExit(
        "Không tìm thấy chương đã dịch phù hợp."
        if require_translated
        else "Tất cả các chương trong truyện này đều đã có bản dịch!"
    )


def cmd_status(args: argparse.Namespace) -> None:
    truyen_root = APP_ROOT / "truyen"
    if not args.project:
        projects = []
        if truyen_root.is_dir():
            for p in sorted(truyen_root.iterdir()):
                if not p.is_dir() or not (p / "raw").is_dir():
                    continue
                raw_count = len(list((p / "raw").glob("*.md")))
                trans_count = len(list((p / "translated").glob("*.md"))) if (p / "translated").is_dir() else 0
                projects.append({"project": p.name, "raw": raw_count, "translated": trans_count})
        print(json.dumps({"projects": projects}, ensure_ascii=False, indent=2))
        return

    project_dir = _require_project_dir(args.project)
    from cores.chapters.files import is_translated, scan_md_dir
    from cores.characters.storage import load_index as load_char_index
    from cores.characters.store import load_document as load_char_doc
    from cores.config.runtime import bool_option
    from cores.full_review.storage import load_manual_check, load_review
    from cores.r19 import enabled as r19_enabled
    from cores.storage.project import load_context, load_json
    from cores.translation.context import chapter_id

    raw_dir = project_dir / "raw"
    trans_dir = project_dir / "translated"
    raw_files = scan_md_dir(str(raw_dir)) if raw_dir.is_dir() else []
    translated_flags = [is_translated(chapter_id(p), str(trans_dir)) for p in raw_files]
    next_untranslated = next(
        (
            {"index_1based": i + 1, "chapter": os.path.basename(p)}
            for i, (p, done) in enumerate(zip(raw_files, translated_flags))
            if not done
        ),
        None,
    )
    ctx = load_context(project_dir)
    glossary_lines = [
        ln for ln in str(ctx.get("glossary", "")).splitlines() if "=" in ln
    ]
    char_doc = load_char_doc(project_dir, migrate=False)
    char_index = load_char_index(str(project_dir / "project_state.json"))
    pronouns = load_json(project_dir / "pronouns.json", {})
    reviews = load_review(str(project_dir / "review.json"))
    manual_checks = load_manual_check(str(project_dir / "manual_check.json"))

    payload = {
        "project": args.project,
        "total_raw": len(raw_files),
        "total_translated": sum(1 for x in translated_flags if x),
        "next_untranslated": next_untranslated,
        "glossary_processed_index": ctx.get("index", 0),
        "glossary_terms_count": len(glossary_lines),
        "characters_processed_index": char_index,
        "characters_count": len(char_doc.get("characters", [])),
        "pronoun_pairs_count": len(pronouns) if isinstance(pronouns, dict) else 0,
        "reviewed_chapters_count": len(reviews) if isinstance(reviews, dict) else 0,
        "manual_check_count": len(manual_checks),
        "image_markers": bool_option("image_markers", False),
        "r19_enabled": r19_enabled(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_glossary_prepare(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    from cores.chapters.files import load_md_chapter, scan_md_dir
    from cores.context.prompts import build_glossary_prompt
    from cores.storage.project import load_context

    raw_files = scan_md_dir(str(project_dir / "raw"))
    if not raw_files:
        raise SystemExit("Không có chương raw nào.")
    ctx = load_context(project_dir)
    start_idx = (args.start - 1) if args.start is not None else int(ctx.get("index", 0))
    start_idx = max(0, start_idx)
    if start_idx >= len(raw_files):
        raise SystemExit(f"Đã xử lý hết {len(raw_files)} chương (start={start_idx + 1}).")

    end_idx = min(len(raw_files), start_idx + args.count)
    batch_paths = raw_files[start_idx:end_idx]
    batch = [load_md_chapter(p) for p in batch_paths]
    old_glossary = "" if args.no_existing else str(ctx.get("glossary", ""))
    prompt = build_glossary_prompt(
        batch,
        old_glossary,
        instructions=ctx.get("context_instructions"),
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "prompt.md"
    meta_path = out_dir / "meta.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    meta = {
        "project": args.project,
        "stage": "glossary",
        "start_1based": start_idx + 1,
        "end_1based": end_idx,
        "new_index": end_idx,
        "chapter_count": len(batch),
        "chapters": [os.path.basename(p) for p in batch_paths],
        "prompt_chars": len(prompt),
        "prompt_file": str(prompt_path.resolve()),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


def _incremental_glossary_merge(old_glossary: str, incoming_texts: list[str]) -> str:
    from cores.context.merge import parse_glossary

    ordered_keys: list[str] = []
    mapping: dict[str, str] = {}

    for raw_line in str(old_glossary or "").splitlines():
        if "=" not in raw_line:
            continue
        src, _, dst = raw_line.partition("=")
        src, dst = src.strip(), dst.strip()
        if src and dst:
            if src not in mapping:
                ordered_keys.append(src)
            mapping[src] = dst

    for block in incoming_texts:
        cleaned = parse_glossary(block)
        for raw_line in cleaned.splitlines():
            if "=" not in raw_line:
                continue
            src, _, dst = raw_line.partition("=")
            src, dst = src.strip(), dst.strip()
            if src and dst:
                if src not in mapping:
                    ordered_keys.append(src)
                mapping[src] = dst

    return "\n".join(f"{k} = {mapping[k]}" for k in ordered_keys)


def cmd_glossary_commit(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    from cores.api_logging import log_project_api_call
    from cores.context.merge import merge_context
    from cores.storage.project import load_context, save_context

    in_files = [Path(p) for p in args.inputs]
    texts = [p.read_text(encoding="utf-8") for p in in_files]
    latest = load_context(project_dir)

    if args.incremental or len(texts) > 1:
        merged_str = _incremental_glossary_merge(latest.get("glossary", ""), texts)
        wrapped = f"###START###\n{merged_str}\n###END###"
        updated = merge_context(latest, wrapped)
    else:
        updated = merge_context(latest, texts[0])

    if args.new_index is not None:
        updated["index"] = max(int(latest.get("index", 0)), int(args.new_index))
    elif args.bundle:
        meta_file = Path(args.bundle) / "meta.json"
        if meta_file.is_file():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if "new_index" in meta:
                updated["index"] = int(meta["new_index"])

    save_context(project_dir, updated, backup=True)
    term_count = len([ln for ln in updated.get("glossary", "").splitlines() if "=" in ln])
    log_project_api_call(
        f"glossary_idx_{updated.get('index', 0)}",
        "glossary",
        "antigravity:direct",
        f"Committed {len(texts)} glossary slice(s)",
        updated.get("glossary", ""),
        ok=True,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "index": updated.get("index", 0),
                "glossary_terms_count": term_count,
                "context_json": str((project_dir / "context.json").resolve()),
                "glossary_txt": str((project_dir / "glossary.txt").resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_characters_prepare(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    from cores.chapters.files import load_md_chapter, scan_md_dir
    from cores.characters.prompt import build_character_prompt
    from cores.characters.storage import load_glossary, load_index
    from cores.characters.store import format_chapter_code, load_document

    raw_files = scan_md_dir(str(project_dir / "raw"))
    if not raw_files:
        raise SystemExit("Không có chương raw nào.")
    state_path = project_dir / "project_state.json"
    saved_index = load_index(str(state_path))
    start_idx = (args.start - 1) if args.start is not None else saved_index
    start_idx = max(0, start_idx)
    if start_idx >= len(raw_files):
        raise SystemExit(f"Đã phân tích nhân vật hết {len(raw_files)} chương.")

    end_idx = min(len(raw_files), start_idx + args.count)
    batch_paths = raw_files[start_idx:end_idx]
    batch = [load_md_chapter(p) for p in batch_paths]
    allowed_chapters = [format_chapter_code(ch.get("id", "")) for ch in batch]
    document = load_document(project_dir, migrate=True)
    glossary = load_glossary(str(project_dir / "context.json"))
    prompt = build_character_prompt(batch, document, glossary)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "prompt.md"
    meta_path = out_dir / "meta.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    meta = {
        "project": args.project,
        "stage": "characters",
        "start_1based": start_idx + 1,
        "end_1based": end_idx,
        "new_index": end_idx,
        "allowed_chapters": allowed_chapters,
        "chapters": [os.path.basename(p) for p in batch_paths],
        "prompt_chars": len(prompt),
        "prompt_file": str(prompt_path.resolve()),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


def cmd_characters_commit(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    from cores.api_logging import log_project_api_call
    from cores.characters.parser import extract_character_payload
    from cores.characters.storage import load_index, save_index
    from cores.characters.store import commit_ai_updates

    bundle_dir = Path(args.bundle)
    meta = json.loads((bundle_dir / "meta.json").read_text(encoding="utf-8"))
    allowed = meta.get("allowed_chapters") or []
    raw_response = Path(args.input).read_text(encoding="utf-8")
    payload, error_msg = extract_character_payload(raw_response, allowed_chapters=allowed)
    if payload is None:
        raise SystemExit(f"JSON nhân vật không hợp lệ: {error_msg}")

    _doc, stats = commit_ai_updates(project_dir, payload, allowed)
    state_path = str(project_dir / "project_state.json")
    saved_idx = load_index(state_path)
    new_idx = max(saved_idx, int(meta.get("new_index", saved_idx)))
    save_index(new_idx, state_path)
    log_project_api_call(
        f"chars_{meta.get('start_1based')}_{meta.get('end_1based')}",
        "characters",
        "antigravity:direct",
        f"Batch {allowed[0] if allowed else ''}..{allowed[-1] if allowed else ''}",
        raw_response,
        ok=True,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "new_index": new_idx,
                "stats": stats,
                "characters_json": str((project_dir / "characters.json").resolve()),
                "characters_md": str((project_dir / "characters.md").resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_translate_prepare(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    from cores.chapters.files import export_recent_translations, load_md_chapter, scan_md_dir
    from cores.config import CONTEXT_JSON, NOVEL_TXT, RAW_DIR, TRANSLATED_DIR
    from cores.config.runtime import bool_option, option
    from cores.pronouns import format_pronoun_context
    from cores.r19 import load_word_mappings, mask_contexts, prepare_chapters, strip_previous_context
    from cores.stages import build_reference_documents
    from cores.translation.context import chapter_id, filtered_context_and_names, with_previous_titles
    from cores.translation.prompts import build_single_prompt, with_character_document_instruction

    raw_files = scan_md_dir(str(RAW_DIR))
    if not raw_files:
        raise SystemExit("Không tìm thấy chương raw nào.")
    idx = _resolve_chapter_index(raw_files, args.chapter, Path(TRANSLATED_DIR), require_translated=False)
    raw_path = raw_files[idx]
    cid = chapter_id(raw_path)
    chapter_number = idx + 1

    use_image_markers = bool_option("image_markers", False)
    chapter = load_md_chapter(raw_path, image_markers=use_image_markers)
    context_text, glossary_names, pronouns_path = filtered_context_and_names(
        str(CONTEXT_JSON), raw_files, idx
    )
    pronoun_context = format_pronoun_context(
        chapter_number,
        pronouns_file=pronouns_path,
        glossary_names=glossary_names,
    )
    previous_count = int(option("previous_context_chapters", 3))
    export_recent_translations(
        str(RAW_DIR),
        str(TRANSLATED_DIR),
        str(NOVEL_TXT),
        n=previous_count,
        target_chapter_id=cid,
    )
    previous = Path(NOVEL_TXT).read_text(encoding="utf-8").strip() if Path(NOVEL_TXT).is_file() else ""
    translation_context = with_previous_titles(
        context_text,
        raw_files,
        idx,
        str(TRANSLATED_DIR),
        count=previous_count,
        heading="Cac tieu de truoc da dich:",
    )

    masked_chapters, r19_entries = prepare_chapters([chapter])
    masked_context, masked_pronouns = mask_contexts(
        [translation_context, pronoun_context], r19_entries
    )
    prompt = build_single_prompt(
        masked_chapters[0],
        masked_context,
        masked_pronouns,
        strip_previous_context(previous),
    )
    documents = build_reference_documents(chapter, pronoun_context)
    if any(item["name"] == "characters.md" for item in documents):
        prompt = with_character_document_instruction(prompt)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    saved_docs = []
    for doc in documents:
        doc_path = out_dir / doc["name"]
        doc_path.write_text(doc["content"], encoding="utf-8")
        saved_docs.append(str(doc_path.resolve()))

    known_r19 = load_word_mappings() if r19_entries else {}
    untranslated_r19 = [
        {"token": item["token"], "source": item["source"]}
        for item in r19_entries
        if item["source"].casefold() not in known_r19
    ]

    meta = {
        "project": args.project,
        "stage": "translate",
        "chapter": os.path.basename(raw_path),
        "chapter_id": cid,
        "chapter_number": chapter_number,
        "raw_path": str(Path(raw_path).resolve()),
        "image_markers": chapter.get("_image_markers"),
        "r19_entries": r19_entries,
        "untranslated_r19": untranslated_r19,
        "prompt_file": str(prompt_path.resolve()),
        "reference_files": saved_docs,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


def cmd_translate_commit(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    from cores.api_logging import log_project_api_call
    from cores.chapters.files import save_translated_md
    from cores.chapters.images import validate_image_markers
    from cores.r19 import load_word_mappings, restore_results, save_word_translation
    from cores.stages import parse_title_content

    bundle_dir = Path(args.bundle)
    meta = json.loads((bundle_dir / "meta.json").read_text(encoding="utf-8"))
    raw_response = Path(args.input).read_text(encoding="utf-8")
    title, content = parse_title_content(raw_response, "Dịch")

    r19_entries = meta.get("r19_entries") or []
    if r19_entries:
        word_map = load_word_mappings()
        extra_map = {}
        if args.r19_map:
            extra_map = json.loads(Path(args.r19_map).read_text(encoding="utf-8"))
        token_translations = {}
        for item in r19_entries:
            token = item["token"]
            source = item["source"]
            if token in extra_map:
                vi = str(extra_map[token]).strip()
                save_word_translation(source, vi)
                token_translations[token] = vi
            elif source in extra_map:
                vi = str(extra_map[source]).strip()
                save_word_translation(source, vi)
                token_translations[token] = vi
            elif source.casefold() in word_map:
                token_translations[token] = word_map[source.casefold()]
            else:
                raise SystemExit(
                    f"Thiếu bản dịch cho cụm R19 {token} ({source!r}). Hãy truyền --r19-map <json>."
                )
        title, content = restore_results([(title, content)], r19_entries, token_translations)[0]

    image_markers = meta.get("image_markers")
    if image_markers is not None:
        validate_image_markers(content, image_markers, title)

    foreign = _foreign_lines(f"{title}\n{content}")
    if foreign and not args.allow_foreign:
        preview = "\n".join(foreign[:10])
        raise SystemExit(
            f"Bản dịch còn sót {len(foreign)} dòng chứa ký tự ngoại ngữ (hãy dịch sạch rồi commit lại, hoặc dùng --allow-foreign nếu cố ý):\n{preview}"
        )

    out_path = save_translated_md(
        meta["raw_path"],
        str(project_dir / "translated"),
        title,
        content,
        image_markers=image_markers,
    )
    prompt_text = (bundle_dir / "prompt.md").read_text(encoding="utf-8") if (bundle_dir / "prompt.md").is_file() else ""
    log_project_api_call(
        meta["chapter_id"],
        "translate",
        "antigravity:direct",
        prompt_text,
        raw_response,
        ok=True,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "chapter": meta["chapter"],
                "title": title,
                "saved_path": str(Path(out_path).resolve()),
                "foreign_lines_remaining": len(foreign),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_polish_prepare(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    from cores.chapters.files import load_md_chapter, scan_md_dir
    from cores.chapters.images import IMAGE_INSTRUCTION, uses_image_markers
    from cores.characters.store import format_chapter_code
    from cores.config import CHARACTERS_MD, CONTEXT_JSON, PRONOUNS_JSON, RAW_DIR, TRANSLATED_DIR
    from cores.config.runtime import bool_option, int_option
    from cores.postprocess.snapshots import build_characters_snapshot
    from cores.pronouns import format_pronoun_context
    from cores.pronouns.extraction import build_pronoun_instructions
    from cores.pronouns.normalize import NameResolver, default_characters_file, load_character_roster
    from cores.r19 import mask_postprocess_contexts, prepare_postprocess_chapter
    from cores.translation.context import chapter_id, filtered_context_and_names
    from cores.translation.prompts import (
        NEUTRAL_REFERENCE_RULE,
        _r19_placeholder_instruction,
        project_polish_prompt,
        with_character_document_instruction,
        wrap_r19_prompt,
    )

    raw_files = scan_md_dir(str(RAW_DIR))
    idx = _resolve_chapter_index(raw_files, args.chapter, Path(TRANSLATED_DIR), require_translated=True)
    raw_path = raw_files[idx]
    cid = chapter_id(raw_path)
    chapter_number = idx + 1

    trans_path = Path(TRANSLATED_DIR) / f"{cid}.md"
    marker_mode = uses_image_markers(trans_path)
    raw_chap = load_md_chapter(raw_path, image_markers=marker_mode)
    trans_chap = load_md_chapter(str(trans_path), image_markers=marker_mode)

    chapter = {
        **raw_chap,
        "title_translation": trans_chap.get("title", ""),
        "translation": trans_chap.get("content", ""),
    }
    if marker_mode and "_image_markers" in trans_chap:
        chapter["_image_markers"] = trans_chap["_image_markers"]
    context_text, glossary_names, pronouns_path = filtered_context_and_names(
        str(CONTEXT_JSON), raw_files, idx
    )
    pronoun_context = format_pronoun_context(
        chapter_number,
        pronouns_file=pronouns_path,
        glossary_names=glossary_names,
    )

    post_entries = []
    post_translations = {}
    if bool_option("r19_mode", False):
        chapter, post_entries, post_translations = prepare_postprocess_chapter(chapter)
        context_text, pronoun_context = mask_postprocess_contexts(
            [context_text, pronoun_context], post_translations
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    relevant_text = "\n".join([
        chapter.get("title", ""),
        chapter.get("content", ""),
        chapter.get("title_translation", ""),
        chapter.get("translation", ""),
        pronoun_context,
    ])
    tmp_chars = build_characters_snapshot(
        str(CHARACTERS_MD),
        relevant_text,
        max_characters=min(int_option("character_snapshot_limit", 20, minimum=1), 50),
        chapter_id=cid,
    )
    ref_files = []
    try:
        if tmp_chars:
            char_dest = out_dir / "characters.md"
            char_dest.write_text(Path(tmp_chars).read_text(encoding="utf-8"), encoding="utf-8")
            ref_files.append(str(char_dest.resolve()))
    finally:
        if tmp_chars and os.path.exists(tmp_chars):
            try:
                os.remove(tmp_chars)
            except OSError:
                pass

    role, task = project_polish_prompt()
    pronoun_instructions = ""
    pronoun_format = ""
    if args.with_pronouns:
        roster_path = default_characters_file(str(PRONOUNS_JSON))
        resolver = NameResolver(load_character_roster(roster_path))
        pronoun_instructions = f"""
## Xuất xưng hô sau hiệu đính
Sau khi hiệu đính, trích xuất xưng hô thực tế trong bản hoàn chỉnh ở ###CONTENT###.
Không sao chép các cặp chỉ có trong bộ nhớ nhưng không xuất hiện trong hội thoại chương này.
Đặt toàn bộ JSON vào mục ###PRONOUNS### riêng, không đưa vào nội dung truyện.
{build_pronoun_instructions(resolver)}
"""
        pronoun_format = '\n###PRONOUNS###\n<JSON object có "character_pairs" theo cấu trúc trên>'

    prompt = wrap_r19_prompt(f"""# Vai trò hiệu đính
{role}

# Nhiệm vụ hiệu đính
{task}

{NEUTRAL_REFERENCE_RULE}
Đối chiếu nguyên tác và sửa những chỗ bản dịch đã tự thêm giới tính hoặc chủ ngữ.

Giữ nguyên đầy đủ nội dung, Markdown ảnh và dấu hội thoại. Không giải thích thay đổi.
{_r19_placeholder_instruction()}

## Thuật ngữ và quy tắc
{context_text}

## Bộ nhớ xưng hô
{pronoun_context}

## Nguyên tác
Mã chương: {format_chapter_code(cid)}
Tiêu đề: {chapter.get('title', '')}
{chapter.get('content', '')}

## Bản dịch cần hiệu đính
Tiêu đề: {chapter.get('title_translation', '')}
{chapter.get('translation', '')}
{pronoun_instructions}

Chỉ trả về:
###TITLE###
<tiêu đề hoàn chỉnh>
###CONTENT###
<nội dung hoàn chỉnh>{pronoun_format}
###END###""")
    if ref_files:
        prompt = with_character_document_instruction(prompt)
    if "_image_markers" in chapter:
        prompt = IMAGE_INSTRUCTION + "\n\n" + prompt

    prompt_path = out_dir / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    meta = {
        "project": args.project,
        "stage": "polish",
        "chapter": f"{cid}.md",
        "chapter_id": cid,
        "chapter_number": chapter_number,
        "raw_path": str(Path(raw_path).resolve()),
        "translated_path": str(trans_path.resolve()),
        "image_markers": chapter.get("_image_markers"),
        "postprocess_entries": post_entries,
        "postprocess_translations": post_translations,
        "with_pronouns": bool(args.with_pronouns),
        "prompt_file": str(prompt_path.resolve()),
        "reference_files": ref_files,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


def cmd_polish_commit(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    import tempfile
    from cores.api_logging import log_project_api_call
    from cores.chapters.files import save_translated_md
    from cores.chapters.images import validate_image_markers
    from cores.postprocess.outputs import parse_polish_output
    from cores.pronouns.extraction import apply_pronoun_payload
    from cores.r19 import restore_results
    from services.polish_review import create_review

    bundle_dir = Path(args.bundle)
    meta = json.loads((bundle_dir / "meta.json").read_text(encoding="utf-8"))
    raw_response = Path(args.input).read_text(encoding="utf-8")
    title_out, content_out, pronoun_payload = parse_polish_output(raw_response)

    post_entries = meta.get("postprocess_entries") or []
    post_translations = meta.get("postprocess_translations") or {}
    if post_entries:
        title_out, content_out = restore_results(
            [(title_out, content_out)], post_entries, post_translations
        )[0]

    image_markers = meta.get("image_markers")
    if image_markers is not None:
        validate_image_markers(content_out, image_markers, title_out)

    foreign = _foreign_lines(f"{title_out}\n{content_out}")
    if foreign and not args.allow_foreign:
        preview = "\n".join(foreign[:10])
        raise SystemExit(
            f"Bản hiệu đính còn sót {len(foreign)} dòng chứa ký tự ngoại ngữ:\n{preview}"
        )

    trans_path = Path(meta["translated_path"])
    pronouns_updated = 0
    if args.pending:
        original_md = trans_path.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as folder:
            proposal = save_translated_md(
                meta["raw_path"],
                folder,
                title_out,
                content_out,
                image_markers=image_markers,
            )
            create_review(trans_path, original_md, Path(proposal).read_text(encoding="utf-8"))
        save_mode = "pending_review"
    else:
        save_translated_md(
            meta["raw_path"],
            str(project_dir / "translated"),
            title_out,
            content_out,
            image_markers=image_markers,
        )
        save_mode = "saved_direct"
        if pronoun_payload is not None:
            pronouns_updated = apply_pronoun_payload(
                meta["chapter_id"],
                int(meta["chapter_number"]),
                pronoun_payload,
                str(project_dir / "pronouns.json"),
            )

    prompt_text = (bundle_dir / "prompt.md").read_text(encoding="utf-8") if (bundle_dir / "prompt.md").is_file() else ""
    log_project_api_call(
        meta["chapter_id"],
        "polish",
        "antigravity:direct",
        prompt_text,
        raw_response,
        ok=True,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "chapter": meta["chapter"],
                "mode": save_mode,
                "pronouns_updated": pronouns_updated,
                "translated_path": str(trans_path.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_pronouns_prepare(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    from cores.chapters.files import load_md_chapter, scan_md_dir
    from cores.config import PRONOUNS_JSON, RAW_DIR, TRANSLATED_DIR
    from cores.pronouns.extraction import build_extraction_prompt
    from cores.pronouns.normalize import NameResolver, default_characters_file, load_character_roster
    from cores.translation.context import chapter_id

    raw_files = scan_md_dir(str(RAW_DIR))
    idx = _resolve_chapter_index(raw_files, args.chapter, Path(TRANSLATED_DIR), require_translated=True)
    raw_path = raw_files[idx]
    cid = chapter_id(raw_path)
    chapter_number = idx + 1

    raw_chap = load_md_chapter(raw_path)
    trans_chap = load_md_chapter(str(Path(TRANSLATED_DIR) / f"{cid}.md"))
    resolver = NameResolver(load_character_roster(default_characters_file(str(PRONOUNS_JSON))))
    prompt = build_extraction_prompt(
        f"{trans_chap.get('title', '')}\n\n{trans_chap.get('content', '')}",
        source_text=f"{raw_chap.get('title', '')}\n\n{raw_chap.get('content', '')}",
        resolver=resolver,
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    meta = {
        "project": args.project,
        "stage": "pronouns",
        "chapter": f"{cid}.md",
        "chapter_id": cid,
        "chapter_number": chapter_number,
        "prompt_file": str(prompt_path.resolve()),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


def cmd_pronouns_commit(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    from cores.json_output import parse_complete_json_object
    from cores.pronouns.extraction import apply_pronoun_payload

    bundle_dir = Path(args.bundle)
    meta = json.loads((bundle_dir / "meta.json").read_text(encoding="utf-8"))
    raw_response = Path(args.input).read_text(encoding="utf-8")
    parsed = parse_complete_json_object(raw_response, strict=False)
    if parsed is None:
        raise SystemExit("Không tìm thấy JSON xưng hô hợp lệ trong file kết quả.")

    updated = apply_pronoun_payload(
        meta["chapter_id"],
        int(meta["chapter_number"]),
        parsed,
        str(project_dir / "pronouns.json"),
    )
    print(
        json.dumps(
            {
                "ok": True,
                "chapter": meta["chapter"],
                "pronouns_updated": updated,
                "pronouns_json": str((project_dir / "pronouns.json").resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_review_prepare(args: argparse.Namespace) -> None:
    _require_project_dir(args.project)
    from cores.chapters.files import load_md_chapter, scan_md_dir
    from cores.config import CONTEXT_JSON, RAW_DIR, TRANSLATED_DIR
    from cores.full_review.service import build_review_prompt
    from cores.stages import build_reference_documents
    from cores.translation.context import chapter_id, filtered_context_and_names
    from cores.translation.prompts import with_character_document_instruction

    raw_files = scan_md_dir(str(RAW_DIR))
    idx = _resolve_chapter_index(raw_files, args.chapter, Path(TRANSLATED_DIR), require_translated=True)
    raw_path = raw_files[idx]
    cid = chapter_id(raw_path)
    chapter_number = idx + 1

    raw_chap = load_md_chapter(raw_path)
    trans_chap = load_md_chapter(str(Path(TRANSLATED_DIR) / f"{cid}.md"))
    context_text, _names, _pronouns_path = filtered_context_and_names(
        str(CONTEXT_JSON), raw_files, idx
    )
    prompt = build_review_prompt(
        cid,
        chapter_number,
        raw_chap.get("title", ""),
        raw_chap.get("content", ""),
        trans_chap.get("title", ""),
        trans_chap.get("content", ""),
        context_text=context_text,
    )
    documents = build_reference_documents(
        {
            "title": raw_chap.get("title", ""),
            "content": raw_chap.get("content", ""),
            "title_translation": trans_chap.get("title", ""),
            "translation": trans_chap.get("content", ""),
        },
        include_translation=True,
        chapter_id=cid,
    )
    if any(doc["name"] == "characters.md" for doc in documents):
        prompt = with_character_document_instruction(prompt)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    saved_docs = []
    for doc in documents:
        doc_path = out_dir / doc["name"]
        doc_path.write_text(doc["content"], encoding="utf-8")
        saved_docs.append(str(doc_path.resolve()))

    meta = {
        "project": args.project,
        "stage": "review",
        "chapter": f"{cid}.md",
        "chapter_id": cid,
        "chapter_number": chapter_number,
        "prompt_file": str(prompt_path.resolve()),
        "reference_files": saved_docs,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


def cmd_review_commit(args: argparse.Namespace) -> None:
    project_dir = _require_project_dir(args.project)
    from cores.api_logging import log_project_api_call
    from cores.full_review.service import parse_review_json, process_review_result
    from cores.full_review.storage import (
        load_manual_check,
        load_review,
        save_manual_check,
        save_review,
    )

    bundle_dir = Path(args.bundle)
    meta = json.loads((bundle_dir / "meta.json").read_text(encoding="utf-8"))
    raw_response = Path(args.input).read_text(encoding="utf-8")
    review_data = parse_review_json(raw_response)

    review_path = str(project_dir / "review.json")
    manual_path = str(project_dir / "manual_check.json")
    review_store = load_review(review_path)
    manual_list = load_manual_check(manual_path)
    process_review_result(
        meta["chapter_id"],
        int(meta["chapter_number"]),
        review_data,
        review_store,
        manual_list,
    )
    save_review(review_store, review_path)
    save_manual_check(manual_list, manual_path)
    prompt_text = (bundle_dir / "prompt.md").read_text(encoding="utf-8") if (bundle_dir / "prompt.md").is_file() else ""
    log_project_api_call(
        meta["chapter_id"],
        "review",
        "antigravity:direct",
        prompt_text,
        raw_response,
        ok=True,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "chapter": meta["chapter"],
                "score": review_data.get("overall_score"),
                "issue_count": len(review_data.get("issues", [])),
                "review_json": str(Path(review_path).resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aiko Novel Pipeline Bridge for direct Antigravity orchestration."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="List projects or inspect a project's pipeline status.")
    p_status.add_argument("--project", default="", help="Project folder name inside truyen/")
    p_status.set_defaults(func=cmd_status)

    p_gp = sub.add_parser("glossary-prepare", help="Prepare an exact glossary batch prompt.")
    p_gp.add_argument("--project", required=True)
    p_gp.add_argument("--start", type=int, default=None, help="1-based chapter index (default: context.json index + 1)")
    p_gp.add_argument("--count", type=int, default=12, help="Chapters in this batch (recommended: 10-15)")
    p_gp.add_argument("--no-existing", action="store_true", help="Omit existing glossary for parallel slice extraction")
    p_gp.add_argument("--out", required=True, help="Output bundle directory")
    p_gp.set_defaults(func=cmd_glossary_prepare)

    p_gc = sub.add_parser("glossary-commit", help="Validate and save glossary output into context.json & glossary.txt.")
    p_gc.add_argument("--project", required=True)
    p_gc.add_argument("--in", dest="inputs", action="append", required=True, help="Response file(s) with ###START###...###END###")
    p_gc.add_argument("--bundle", default="", help="Optional bundle directory to read new_index from")
    p_gc.add_argument("--new-index", type=int, default=None, help="Explicit new chapter index")
    p_gc.add_argument("--incremental", action="store_true", help="Merge new Raw = Dịch lines onto existing glossary")
    p_gc.set_defaults(func=cmd_glossary_commit)

    p_cp = sub.add_parser("characters-prepare", help="Prepare structured character profile batch prompt.")
    p_cp.add_argument("--project", required=True)
    p_cp.add_argument("--start", type=int, default=None, help="1-based start chapter")
    p_cp.add_argument("--count", type=int, default=10, help="Chapters per batch")
    p_cp.add_argument("--out", required=True, help="Output bundle directory")
    p_cp.set_defaults(func=cmd_characters_prepare)

    p_cc = sub.add_parser("characters-commit", help="Validate and commit character JSON updates.")
    p_cc.add_argument("--project", required=True)
    p_cc.add_argument("--bundle", required=True)
    p_cc.add_argument("--in", dest="input", required=True)
    p_cc.set_defaults(func=cmd_characters_commit)

    p_tp = sub.add_parser("translate-prepare", help="Prepare exact chapter translation bundle (prompt + snapshots + R19/image metadata).")
    p_tp.add_argument("--project", required=True)
    p_tp.add_argument("--chapter", default=None, help="e.g. v1_c1_s1.md (default: next untranslated)")
    p_tp.add_argument("--out", required=True)
    p_tp.set_defaults(func=cmd_translate_prepare)

    p_tc = sub.add_parser("translate-commit", help="Validate and save chapter translation.")
    p_tc.add_argument("--project", required=True)
    p_tc.add_argument("--bundle", required=True)
    p_tc.add_argument("--in", dest="input", required=True)
    p_tc.add_argument("--r19-map", default=None, help="Optional JSON mapping for new R19 tokens")
    p_tc.add_argument("--allow-foreign", action="store_true")
    p_tc.set_defaults(func=cmd_translate_commit)

    p_pp = sub.add_parser("polish-prepare", help="Prepare chapter polish (+ optional pronoun extraction) bundle.")
    p_pp.add_argument("--project", required=True)
    p_pp.add_argument("--chapter", required=True)
    p_pp.add_argument("--with-pronouns", action="store_true")
    p_pp.add_argument("--out", required=True)
    p_pp.set_defaults(func=cmd_polish_prepare)

    p_pc = sub.add_parser("polish-commit", help="Validate and save polished chapter (+ optional pronouns).")
    p_pc.add_argument("--project", required=True)
    p_pc.add_argument("--bundle", required=True)
    p_pc.add_argument("--in", dest="input", required=True)
    p_pc.add_argument("--pending", action="store_true", help="Save as pending diff-review in Web UI instead of overwriting")
    p_pc.add_argument("--allow-foreign", action="store_true")
    p_pc.set_defaults(func=cmd_polish_commit)

    p_prp = sub.add_parser("pronouns-prepare", help="Prepare standalone pronoun extraction bundle.")
    p_prp.add_argument("--project", required=True)
    p_prp.add_argument("--chapter", required=True)
    p_prp.add_argument("--out", required=True)
    p_prp.set_defaults(func=cmd_pronouns_prepare)

    p_prc = sub.add_parser("pronouns-commit", help="Validate and merge extracted pronouns into pronouns.json.")
    p_prc.add_argument("--project", required=True)
    p_prc.add_argument("--bundle", required=True)
    p_prc.add_argument("--in", dest="input", required=True)
    p_prc.set_defaults(func=cmd_pronouns_commit)

    p_rvp = sub.add_parser("review-prepare", help="Prepare translation quality review bundle.")
    p_rvp.add_argument("--project", required=True)
    p_rvp.add_argument("--chapter", required=True)
    p_rvp.add_argument("--out", required=True)
    p_rvp.set_defaults(func=cmd_review_prepare)

    p_rvc = sub.add_parser("review-commit", help="Validate and save review JSON into review.json & manual_check.json.")
    p_rvc.add_argument("--project", required=True)
    p_rvc.add_argument("--bundle", required=True)
    p_rvc.add_argument("--in", dest="input", required=True)
    p_rvc.set_defaults(func=cmd_review_commit)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
