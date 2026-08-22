"""Persistence and pipeline options for project-scoped R19 settings."""

import json
import os


def _terms(words):
    return [
        source
        for line in words.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
        for source in [line.partition("=")[0].strip()]
        if source
    ]


def project_enabled(project_path):
    try:
        data = json.loads((project_path / ".r19.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("enabled", False)) if isinstance(data, dict) else False


def payload(
    project_path,
    words_file,
    config_file,
    default_words_file,
    default_model,
    default_context_chapters,
    default_prompt_prefix,
):
    try:
        words = words_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        try:
            words = default_words_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            words = ""
    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config = {}
    terms = _terms(words)
    defaults = {
        "model": default_model,
        "context_chapters": default_context_chapters,
        "prompt_prefix": default_prompt_prefix,
        "words": default_words_file.read_text(encoding="utf-8")
        if default_words_file.exists()
        else "",
    }
    return {
        "enabled": project_enabled(project_path) if project_path else False,
        "words": words,
        "count": len(dict.fromkeys(term.casefold() for term in terms if term)),
        "model": str(config.get("model", defaults["model"])),
        "context_chapters": int(
            config.get("context_chapters", defaults["context_chapters"])
        ),
        "prompt_prefix": str(config.get("prompt_prefix", default_prompt_prefix)),
        "defaults": defaults,
    }


def save(
    project_path,
    request,
    words_file,
    config_file,
    default_model,
    default_context_chapters,
    default_prompt_prefix,
):
    words = str(request.get("words", "")).replace("\r\n", "\n").replace("\r", "\n")
    if len(words) > 100_000:
        raise ValueError("Danh sách R19 vượt quá 100.000 ký tự")
    terms = _terms(words)
    if len(terms) > 5000 or any(len(term) > 200 for term in terms):
        raise ValueError(
            "Danh sách R19 chỉ hỗ trợ tối đa 5.000 dòng, mỗi dòng 200 ký tự"
        )
    enabled = bool(request.get("enabled", False))
    if enabled and not terms:
        raise ValueError("Hãy thêm ít nhất một cụm từ trước khi bật Dịch R19")
    model = str(request.get("model", default_model)).strip()
    prompt_prefix = str(request.get("prompt_prefix", default_prompt_prefix)).strip()
    try:
        context_chapters = int(
            request.get("context_chapters", default_context_chapters)
        )
    except (TypeError, ValueError):
        raise ValueError("Số chương ngữ cảnh R19 phải là số nguyên") from None
    if not model or len(model) > 200:
        raise ValueError("Model dịch từ R19 không hợp lệ")
    if not prompt_prefix or len(prompt_prefix) > 2000:
        raise ValueError("Dòng mở đầu prompt R19 không hợp lệ")
    if not 0 <= context_chapters <= 20:
        raise ValueError("Số chương ngữ cảnh R19 phải từ 0 đến 20")

    words_file.parent.mkdir(parents=True, exist_ok=True)
    words_temporary = words_file.with_suffix(".tmp")
    words_temporary.write_text(
        words.rstrip() + "\n" if words.strip() else "", encoding="utf-8"
    )
    os.replace(words_temporary, words_file)

    config_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_file.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "model": model,
                "context_chapters": context_chapters,
                "prompt_prefix": prompt_prefix,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, config_file)

    project_config = project_path / ".r19.json"
    project_temporary = project_config.with_suffix(".tmp")
    project_temporary.write_text(
        json.dumps({"enabled": enabled}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(project_temporary, project_config)


def task_options(data):
    options = {
        "r19_mode": data["enabled"],
        "r19_model": data["model"],
        "r19_prompt_prefix": data["prompt_prefix"],
    }
    if data["enabled"]:
        options["previous_context_chapters"] = data["context_chapters"]
    return options
