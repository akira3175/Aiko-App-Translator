"""Bounded, literal chapter search. Offsets use JavaScript UTF-16 units."""

import re
import unicodedata

from .repository import chapter_key


def search_chapters(raw, translated, safe_file, read_text, query):
    term = query.get("q", [""])[0].strip()
    scope = query.get("scope", ["target"])[0]
    if not term or len(term) > 200:
        raise ValueError("Nhập từ cần tìm (tối đa 200 ký tự).")
    if scope not in ("source", "target", "both"):
        raise ValueError("Phạm vi tìm kiếm không hợp lệ.")
    try:
        file_index, offset = map(int, query.get("cursor", ["0:0"])[0].split(":"))
        if file_index < 0 or offset < 0:
            raise ValueError()
    except ValueError:
        raise ValueError("Vị trí tìm kiếm không hợp lệ.") from None
    folders = [("source", raw), ("target", translated)]
    names = sorted({p.name for _, folder in folders for p in folder.glob("*.md")}, key=chapter_key)
    files = [(name, kind, folder) for name in names for kind, folder in folders
             if scope in (kind, "both") and (folder / name).is_file()]
    pattern = re.compile(re.escape(term), 0 if query.get("case", ["0"])[0] == "1" else re.IGNORECASE)
    whole_word = query.get("word", ["0"])[0] == "1"
    def word_char(char):
        return char == "_" or unicodedata.category(char)[0] in "LNM"
    items = []
    scanned = 0
    while file_index < len(files) and scanned < 20:
        name, kind, folder = files[file_index]
        text = read_text(safe_file(folder, name)).replace("\r\n", "\n").replace("\r", "\n")
        title = next((line.lstrip("# ") for line in text.splitlines() if line.strip()), name)[:180]
        for match in pattern.finditer(text, offset):
            start, end = match.span()
            if whole_word and ((start and word_char(text[start - 1])) or (end < len(text) and word_char(text[end]))):
                continue
            items.append({"name": name, "kind": kind, "title": title,
                          "start": len(text[:start].encode("utf-16-le")) // 2,
                          "end": len(text[:end].encode("utf-16-le")) // 2,
                          "match": match.group(), "before": text[max(0, start - 65):start],
                          "after": text[end:end + 85]})
            if len(items) == 100:
                return {"items": items, "next": f"{file_index}:{end}"}
        file_index += 1
        offset = 0
        scanned += 1
    return {"items": items, "next": f"{file_index}:0" if file_index < len(files) else None}
