"""Replace source-language glossary terms inside a legacy YAML novel."""

import os

import yaml

from cores.context_utils import save_yaml

CONTEXT_FILE = "truyen/context.yaml"
INPUT_FILE = "truyen/novel.yaml"
OUTPUT_FILE = "truyen/truyen.yaml"


def load_yaml(path):
    if not os.path.exists(path):
        print(f"❌ Không tìm thấy file: {path}")
        return None
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def parse_glossary(glossary_text):
    entries = []
    for line in (glossary_text or "").splitlines():
        source, separator, target = line.partition("=")
        source, target = source.strip(), target.strip()
        if separator and source and target:
            entries.append((source, target))
    return sorted(entries, key=lambda item: len(item[0]), reverse=True)


def insert_glossary_to_content(content, glossary_entries):
    if not content:
        return content
    replacements = {}
    result = content
    for index, (source, target) in enumerate(glossary_entries):
        placeholder = f"\x00{index}\x00"
        if source in result:
            result = result.replace(source, placeholder)
            replacements[placeholder] = target
    for placeholder, target in replacements.items():
        result = result.replace(placeholder, target)
    return result


def apply_glossary(chapters, entries):
    changed = 0
    for chapter in chapters:
        content = chapter.get("content", "")
        updated = insert_glossary_to_content(content, entries)
        if updated != content:
            chapter["content"] = updated
            changed += 1
    return changed


def main():
    context = load_yaml(CONTEXT_FILE)
    if not context or not context.get("glossary"):
        print("❌ Không tìm thấy glossary trong context.yaml!")
        return

    entries = parse_glossary(context["glossary"])
    chapters = load_yaml(INPUT_FILE)
    if not chapters:
        return
    if isinstance(chapters, dict):
        chapters = chapters.get("chapters", [])

    changed = apply_glossary(chapters, entries)
    save_yaml(chapters, OUTPUT_FILE)
    print(f"✅ Đã thay glossary trong {changed}/{len(chapters)} chương.")
    print(f"✅ Đã lưu kết quả vào {OUTPUT_FILE}; file gốc không bị thay đổi.")


if __name__ == "__main__":
    main()
