"""Replace project glossary with a complete, validated AI result."""


def parse_glossary(new_text):
    if new_text.count("###START###") != 1 or new_text.count("###END###") != 1:
        raise ValueError("Glossary phải có đủ marker START/END.")
    start = new_text.index("###START###") + len("###START###")
    end = new_text.index("###END###")
    if end < start:
        raise ValueError("Marker glossary không đúng thứ tự.")
    new_text = new_text[start:end]
    new_lines = [line.strip() for line in new_text.splitlines() if line.strip()]
    if not new_lines:
        raise ValueError("Glossary trả về rỗng.")
    for line in new_lines:
        source, separator, target = line.partition("=")
        if not separator or not source.strip() or not target.strip():
            raise ValueError("Glossary phải có dạng Nguyên văn = Bản dịch.")
    return "\n".join(new_lines)


def merge_context(old, new_text):
    old["glossary"] = parse_glossary(new_text)
    return old
