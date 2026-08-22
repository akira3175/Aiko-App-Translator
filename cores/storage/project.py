"""Project storage and safe migration from legacy YAML files."""

import json
import os
import shutil
from pathlib import Path

import yaml


def _atomic_text(path: Path, content: str, backup=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    if backup and path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    os.replace(temporary, path)


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data, backup=False):
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if json.loads(content) != data:
        raise ValueError(f"Không thể xác minh dữ liệu JSON: {path}")
    _atomic_text(Path(path), content, backup=backup)


def load_context(project_dir):
    project = Path(project_dir)
    migrate_project(project)
    data = load_json(project / "context.json", {})
    data["glossary"] = (
        (project / "glossary.txt").read_text(encoding="utf-8").strip()
        if (project / "glossary.txt").exists() else ""
    )
    return data


def save_context(project_dir, data, backup=False):
    project = Path(project_dir)
    metadata = dict(data or {})
    glossary = str(metadata.pop("glossary", "")).strip()
    save_json(project / "context.json", metadata, backup=backup)
    _atomic_text(
        project / "glossary.txt",
        glossary + "\n" if glossary else "",
        backup=backup,
    )


def _verified_yaml(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if data is not None else {}


def _archive_legacy(path):
    legacy = path.with_name(path.name + ".legacy")
    if not legacy.exists():
        os.replace(path, legacy)
    elif path.exists():
        path.unlink()


def migrate_project(project_dir):
    """Idempotently create v1 TXT/JSON files and preserve each YAML as .legacy."""
    project = Path(project_dir)
    if not project.is_dir():
        return []
    migrated = []
    context_yaml = project / "context.yaml"
    if context_yaml.exists() and not (project / "context.json").exists():
        data = _verified_yaml(context_yaml)
        if not isinstance(data, dict):
            raise ValueError(f"context.yaml không phải object: {project.name}")
        save_context(project, data)
        saved = load_json(project / "context.json", {})
        saved["glossary"] = (project / "glossary.txt").read_text(encoding="utf-8").strip()
        if saved != data:
            raise ValueError(f"Xác minh context thất bại: {project.name}")
        _archive_legacy(context_yaml)
        migrated.append("context.yaml")

    mappings = {
        "pronouns.yaml": "pronouns.json",
        "publishing.yaml": "publishing.json",
        "sharing.yaml": "sharing.json",
        "manual_check.yaml": "manual_check.json",
    }
    for old_name, new_name in mappings.items():
        old, new = project / old_name, project / new_name
        if old.exists() and not new.exists():
            data = _verified_yaml(old)
            save_json(new, data)
            if load_json(new) != data:
                raise ValueError(f"Xác minh {new_name} thất bại: {project.name}")
            _archive_legacy(old)
            migrated.append(old_name)

    char_index = project / "char_index.yaml"
    state_path = project / "project_state.json"
    if char_index.exists() and not state_path.exists():
        data = _verified_yaml(char_index)
        if not isinstance(data, dict):
            raise ValueError(f"char_index.yaml không phải object: {project.name}")
        save_json(state_path, {"schema_version": 1, **data})
        _archive_legacy(char_index)
        migrated.append("char_index.yaml")

    for old in project.glob("review*.yaml"):
        new = old.with_suffix(".json")
        if not new.exists():
            data = _verified_yaml(old)
            save_json(new, data)
            if load_json(new) != data:
                raise ValueError(f"Xác minh {new.name} thất bại: {project.name}")
            _archive_legacy(old)
            migrated.append(old.name)
    return migrated
