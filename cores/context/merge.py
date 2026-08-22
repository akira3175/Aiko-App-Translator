"""Merge generated glossary text into project context state."""


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
