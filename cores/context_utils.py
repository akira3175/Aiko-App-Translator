"""Shared persistence and merge helpers for glossary generation."""

import yaml


def _literal_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def save_yaml(data, path):
    dumper = yaml.Dumper
    dumper.add_representer(str, _literal_representer)
    with open(path, "w", encoding="utf-8") as file:
        yaml.dump(
            data,
            file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            Dumper=dumper,
        )


def merge_context(old, new_text):
    if not new_text.strip():
        return old

    if "###START###" in new_text and "###END###" in new_text:
        start = new_text.index("###START###") + len("###START###")
        end = new_text.index("###END###")
        new_text = new_text[start:end]
    elif "###START###" in new_text:
        start = new_text.index("###START###") + len("###START###")
        new_text = new_text[start:]

    new_lines = [line.strip() for line in new_text.splitlines() if line.strip()]
    old_lines = str(old.get("glossary", "")).splitlines()
    merged = []
    for line in old_lines + new_lines:
        if line.strip() and line not in merged:
            merged.append(line)

    old["glossary"] = "\n".join(merged).strip()
    return old
