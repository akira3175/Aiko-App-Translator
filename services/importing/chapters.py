"""Stage, align, preview, and commit imported novel chapters."""

from __future__ import annotations

import difflib
import re
import secrets
import shutil
import time
import unicodedata
from pathlib import Path
from services.importing.uploads import write_upload


CHAPTER_FILE_RE = re.compile(r"^v(\d+)_c(\d+)_s(\d+)\.md$", re.IGNORECASE)
previews: dict[str, dict] = {}


def _chapter_groups(raw_dir: Path):
    groups: dict[tuple[int, int], list[Path]] = {}
    for path in raw_dir.glob("v*_c*_s*.md") if raw_dir.is_dir() else []:
        match = CHAPTER_FILE_RE.match(path.name)
        if match:
            key = (int(match.group(1)), int(match.group(2)))
            groups.setdefault(key, []).append(path)
    for paths in groups.values():
        paths.sort(key=lambda item: int(CHAPTER_FILE_RE.match(item.name).group(3)))
    return groups


def _chapter_text(paths):
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in paths
    )


def _normalized_anchor_text(value, *, title=False):
    value = unicodedata.normalize("NFKC", str(value)).casefold()
    if title:
        value = re.sub(
            r"^(?:chapter|chap|chương|第|제)\s*\d+\s*(?:章|話|话|幕|화|장)?",
            "",
            value,
        )
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    return re.sub(
        r"[^\w\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+", "", value
    )[:1600]


def _anchor_features(text):
    lines = text.splitlines()
    return (
        _normalized_anchor_text(lines[0] if lines else "", title=True),
        _normalized_anchor_text("\n".join(lines[1:])),
    )


def _anchor_score(source_features, existing_features):
    source_title, source_body = source_features
    existing_title, existing_body = existing_features
    title_score = (
        difflib.SequenceMatcher(None, source_title, existing_title).ratio()
        if source_title and existing_title
        else 0
    )
    body_score = (
        difflib.SequenceMatcher(None, source_body, existing_body).ratio()
        if source_body and existing_body
        else 0
    )
    score = title_score * 0.4 + body_score * 0.6
    valid = body_score >= 0.72 or (title_score >= 0.9 and body_score >= 0.35)
    return score if valid else 0


def _splitter(source_format):
    from split.chapter_splitter_novelpia_md import split_epub_to_md, split_txt_to_md

    return split_epub_to_md if source_format == "epub" else split_txt_to_md


def create_preview(
    project_name,
    project_path: Path,
    raw_dir: Path,
    runtime_root: Path,
    source_format,
    segment_limit,
    content,
    splitter=None,
):
    if source_format not in {"epub", "txt"}:
        raise ValueError("Chỉ hỗ trợ file EPUB hoặc TXT")
    if not 500 <= segment_limit <= 50000:
        raise ValueError("Giới hạn segment phải từ 500 đến 50.000")
    token = secrets.token_urlsafe(18)
    staging = runtime_root / "chapter-imports" / token
    staging.mkdir(parents=True)
    upload = staging / f"source.{source_format}"
    try:
        write_upload(upload, content)
        split = splitter or _splitter(source_format)
        result = split(
            str(upload),
            0,
            str(runtime_root.parent),
            project_dir=str(staging),
            segment_limit=segment_limit,
            return_details=True,
        )
        upload.unlink(missing_ok=True)
        source_groups = _chapter_groups(staging / "raw")
        if not source_groups:
            raise ValueError(f"Không tách được chương nào từ {source_format.upper()}")
        existing_groups = _chapter_groups(raw_dir)
        existing_features = {
            key: _anchor_features(_chapter_text(paths))
            for key, paths in existing_groups.items()
        }
        title_keys, body_keys = {}, {}
        for key, (title, body) in existing_features.items():
            if title:
                title_keys.setdefault(title, []).append(key)
            if body:
                body_keys.setdefault(body[:240], []).append(key)
        anchors, chapters = [], []
        for (_volume, source_index), paths in sorted(source_groups.items()):
            text = _chapter_text(paths)
            title = (
                text.splitlines()[0].removeprefix("# ").strip()
                if text
                else f"Chương {source_index}"
            )
            features = _anchor_features(text)
            source_title, source_body = features
            candidates = set(title_keys.get(source_title, [])) | set(
                body_keys.get(source_body[:240], [])
            )
            if not candidates and source_title:
                for close_title in difflib.get_close_matches(
                    source_title, title_keys, n=5, cutoff=0.55
                ):
                    candidates.update(title_keys[close_title])
            if not candidates and source_body:
                for close_body in difflib.get_close_matches(
                    source_body[:240], body_keys, n=5, cutoff=0.55
                ):
                    candidates.update(body_keys[close_body])
            ranked = sorted(
                (
                    (_anchor_score(features, existing_features[key]), key)
                    for key in candidates
                ),
                reverse=True,
            )
            best_score, best_key = ranked[0] if ranked else (0, None)
            second_score = ranked[1][0] if len(ranked) > 1 else 0
            matched = (
                best_key
                if best_score >= 0.62 and best_score - second_score >= 0.08
                else None
            )
            if matched:
                anchors.append((source_index, matched[0], matched[1], best_score))
            chapters.append(
                {
                    "source_index": source_index,
                    "title": title,
                    "segments": len(paths),
                    "match": f"v{matched[0]}_c{matched[1]}" if matched else "",
                    "match_score": round(best_score, 2) if matched else 0,
                }
            )
        mappings = {}
        for source_index, volume, chapter, _score in anchors:
            mappings.setdefault((volume, chapter - source_index), []).append(source_index)
        best_mapping, mapped = (
            max(mappings.items(), key=lambda item: len(item[1]))
            if mappings
            else ((None, None), [])
        )
        if mapped:
            volume, offset = best_mapping
            suggested_from = max(mapped) + 1
            no_new = suggested_from > chapters[-1]["source_index"]
            source_from = chapters[-1]["source_index"] if no_new else suggested_from
            target_start = source_from + offset
            confidence = "high" if len(mapped) >= 2 else "medium"
        else:
            latest = max(existing_groups, default=(1, -1))
            volume = latest[0]
            source_from = chapters[0]["source_index"]
            target_start = latest[1] + 1
            confidence = "manual"
            no_new = False
        source_to = chapters[-1]["source_index"]
        for chapter in chapters:
            chapter["selected"] = (
                not no_new and source_from <= chapter["source_index"] <= source_to
            )
        previews[token] = {
            "project": project_path.name,
            "staging": staging,
            "created": time.time(),
            "source_groups": source_groups,
        }
        return {
            **result,
            "token": token,
            "chapters": chapters,
            "chapter_count": result.get("chapters", len(chapters)),
            "source_from": source_from,
            "source_to": source_to,
            "target_volume": volume,
            "target_start": target_start,
            "anchors": len(mapped),
            "confidence": confidence,
            "no_new": no_new,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def confirm(project_name, project_path: Path, raw_dir: Path, payload):
    token = str(payload.get("token", ""))
    preview = previews.get(token)
    if not preview or preview["project"] != project_name:
        raise ValueError("Bản xem trước đã hết hạn; hãy phân tích lại file")
    source_from = int(payload.get("source_from", 0))
    source_to = int(payload.get("source_to", -1))
    target_volume = int(payload.get("target_volume", 0))
    target_start = int(payload.get("target_start", 0))
    conflict = str(payload.get("conflict", "skip"))
    if source_from < 0 or source_to < source_from or target_volume < 0 or target_start < 0:
        raise ValueError("Range hoặc chương đích không hợp lệ")
    if conflict not in {"skip", "overwrite"}:
        raise ValueError("Cách xử lý chương trùng không hợp lệ")
    selected = {int(value) for value in payload.get("selected", [])}
    image_dir = project_path / "image"
    image_dir.mkdir(exist_ok=True)
    imported = skipped = overwritten = 0
    first_file = ""
    imported_images = set()
    try:
        for (_volume, source_index), paths in sorted(preview["source_groups"].items()):
            if not source_from <= source_index <= source_to or (
                selected and source_index not in selected
            ):
                continue
            target_chapter = target_start + source_index - source_from
            existing = list(raw_dir.glob(f"v{target_volume}_c{target_chapter}_s*.md"))
            if existing and conflict == "skip":
                skipped += 1
                continue
            if existing:
                for path in existing:
                    shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
                    path.unlink()
                overwritten += 1
            for segment, source_path in enumerate(paths, 1):
                target = raw_dir / f"v{target_volume}_c{target_chapter}_s{segment}.md"
                shutil.copy2(source_path, target)
                imported_images.update(
                    Path(match).name
                    for match in re.findall(
                        r"\.\./image/([^\s)]+)",
                        source_path.read_text(encoding="utf-8", errors="replace"),
                    )
                )
                first_file = first_file or target.name
            imported += 1
        for image_name in imported_images:
            image = preview["staging"] / "image" / image_name
            if image.is_file():
                shutil.copy2(image, image_dir / image.name)
        return {
            "ok": True,
            "imported": imported,
            "skipped": skipped,
            "overwritten": overwritten,
            "first_file": first_file,
        }
    finally:
        previews.pop(token, None)
        shutil.rmtree(preview["staging"], ignore_errors=True)


def cancel(token):
    preview = previews.pop(str(token), None)
    if preview:
        shutil.rmtree(preview["staging"], ignore_errors=True)
    return {"ok": True}
