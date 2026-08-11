"""
gen_characters.py
=================
Phan tich va cap nhat thong tin nhan vat tu cac chuong truyen.
- Gui batch chuong len Gemini API de trich xuat thong tin nhan vat.
- Merge vao file characters.md co cau truc, de doc, de chinh sua.
- Chay duoc nhieu lan (incremental) — chi xu ly chuong chua phan tich.

Cach dung:
    python cores/gen_characters.py
"""

import os
import re
import sys
import time

import yaml

# Console Windows có thể dùng cp1252 khi script chạy độc lập. Ép UTF-8 trước
# khi in đường dẫn/tên truyện tiếng Việt để không làm gián đoạn sau khi ghi file.
for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

# Dung call_gemini + MD helpers tu dich_utils.py
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
from cores.dich_utils import (
    CHARACTERS_MD,
    CONTEXT_YAML,
    RAW_DIR,
    call_gemini,
    load_md_chapter,
    scan_md_dir,
    switch_api_key,
)
from cores.runtime_config import int_option, option, stop_requested
from cores.r19_translation import strip_r19_terms
from cores.translation_prompts import wrap_r19_prompt

# ============================================================
# CHUONG DAN
# ============================================================
CONTEXT_FILE = CONTEXT_YAML
CHAR_INDEX_FILE = os.path.join(os.path.dirname(RAW_DIR), "char_index.yaml")
BATCH_SIZE = min(int_option("character_batch_size", 10, minimum=1), 100)

# Model dung de phan tich nhan vat (co the doi)
CHAR_MODEL = str(option("character_model", "gemini-3.5-flash")).strip() or "gemini-3.5-flash"
MAX_RETRIES = min(int_option("character_retries", 3, minimum=1), 10)


# ============================================================
# GEMINI API
# ============================================================


def call_char_analysis(prompt: str) -> str:
    """
    Goi Gemini API phan tich nhan vat.
    Retry tu dong khi gap 429 / loi server.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        if stop_requested():
            raise InterruptedError("Đã dừng tác vụ hồ sơ nhân vật")
        try:
            result = call_gemini(
                prompt,
                model=CHAR_MODEL,
                temperature=0.4,
            )
            return result.strip() if result else ""
        except Exception as e:
            err = str(e)
            print(f"[API] Loi: {err[:120]}")
            if attempt >= MAX_RETRIES:
                raise
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                switch_api_key()
                wait = 10
            elif any(code in err for code in ["500", "502", "503", "504"]):
                wait = 8
            else:
                wait = 3
            print(f"[API] Thu lai {attempt + 1}/{MAX_RETRIES} sau {wait}s...")
            for _ in range(wait):
                if stop_requested():
                    raise InterruptedError("Đã dừng tác vụ hồ sơ nhân vật")
                time.sleep(1)
    return ""


# ============================================================
# GLOSSARY
# ============================================================


def load_glossary(path: str = CONTEXT_FILE) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        ctx = yaml.safe_load(f) or {}
    return ctx.get("glossary", "").strip()


# ============================================================
# PROMPT
# ============================================================


def build_character_prompt(chapters: list, existing_md: str, glossary: str = "") -> str:
    content_blocks = []
    for c in chapters:
        title = c.get("title", "")
        text = c.get("content", "")
        if text:
            content_blocks.append(f"### {title}\n{text}")

    full_text = strip_r19_terms("\n\n".join(content_blocks))
    glossary = strip_r19_terms(glossary)
    existing_md = strip_r19_terms(existing_md)

    prompt = f"""
# Vai tro
Ban la tro ly bien tap chuyen phan tich nhan vat trong tieu thuyet fantasy Han Quoc.

---

# Nhiem vu
Doc doan van ban goc ben duoi, sau do **trich xuat / cap nhat** thong tin nhan vat.

---

# Van ban goc (raw):
{full_text}

---

# Glossary ten nhan vat / thuat ngu (bat buoc dung lam ten header):
{glossary if glossary else "(Chua co glossary)"}

---

# Du lieu nhan vat hien co (de tham khao, tranh mau thuan, chi bo sung them):
{existing_md if existing_md else "(Chua co du lieu nhan vat)"}

---

# Yeu cau chi tiet

1. **Trich xuat** tat ca nhan vat QUAN TRONG (co thoai, hanh dong, tac dong den plot).
2. **Bo qua** NPC phu khong dang ke, chi xuat hien 1 lan.
3. Voi moi nhan vat, dien day du thong tin theo template ben duoi.
4. Neu nhan vat da co trong "Du lieu hien co", hay **hop nhat va bo sung** (khong xoa du lieu cu, chi cap nhat).
5. Thong tin bang tieng Viet. Ten nhan vat va thuat ngu theo glossary (neu biet).

**QUY TAC DAT TEN HEADER (BAT BUOC):**
- Header `## Ten nhan vat` PHAI la **ten day du, chinh thuc theo Glossary**.
- Neu nhan vat da co trong "Du lieu hien co", **giu nguyen ten header do**.
- Khong dung biet danh, danh hieu, hoac ten tat lam header.
- Neu ten khong co trong Glossary, dung ten rieng day du nhat co the tu van ban.

---

# Template cho moi nhan vat (bat buoc):

```
## [Ten nhan vat]

### Thong tin co ban
- **Ten goc**: (ten trong nguyen tac Han/Han/Anh)
- **Biet danh / Danh hieu**: (neu co)
- **Gioi tinh**: Nam / Nu / Khong xac dinh
- **Tuoi / Do tuoi uoc luong**:
- **Chung toc / Xuat than**:
- **Dia vi / Chuc vu**:
- **Phe / To chuc**:

### Ghi chu dich thuat
- (Ten goc, cach dich dac biet, luu y khi dich thoai...)
```

---

# Dinh dang dau ra
> Bat dau bang dong `###CHAR_START###`
> Ket thuc bang dong `###CHAR_END###`
> O giua: **toan bo** noi dung Markdown theo template tren cho tung nhan vat.
> KHONG them bat ky giai thich hay text nao ngoai phan giua hai marker.
"""
    return wrap_r19_prompt(prompt)


# ============================================================
# PARSE VA MERGE MARKDOWN
# ============================================================


def extract_char_block(raw_response: str) -> str:
    cleaned = (raw_response or "").strip()
    cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    cleaned = re.sub(r"(?m)^\\(?=#+\s*(?:CHAR_START|CHAR_END))", "", cleaned)

    start_match = re.search(
        r"(?im)^\s*#{3}\s*CHAR_START\s*#{3}\s*$", cleaned
    )
    end_match = re.search(
        r"(?im)^\s*#{3}\s*CHAR_END\s*#{3}\s*$", cleaned
    )
    if start_match and end_match and end_match.start() > start_match.end():
        return cleaned[start_match.end() : end_match.start()].strip()

    # Gemini đôi khi bỏ marker nhưng vẫn trả đúng các block nhân vật.
    if re.search(r"(?m)^##\s+\S", cleaned):
        return cleaned
    return ""


def parse_characters_from_md(md_text: str) -> dict:
    characters = {}
    if not md_text:
        return characters
    blocks = re.split(r"\n(?=## )", md_text)
    for block in blocks:
        block = block.strip()
        if not block or not block.startswith("## "):
            continue
        first_line = block.split("\n")[0]
        name = first_line.lstrip("# ").strip()
        if name:
            characters[name] = block
    return characters


def request_valid_character_block(prompt: str) -> str:
    request_prompt = prompt
    for output_attempt in range(1, MAX_RETRIES + 1):
        raw_response = call_char_analysis(request_prompt) or ""
        new_block = extract_char_block(raw_response)
        if new_block and parse_characters_from_md(new_block):
            return new_block

        marker_state = (
            "co marker"
            if "CHAR_START" in raw_response or "CHAR_END" in raw_response
            else "thieu marker"
        )
        print(
            f"   Output khong hop le ({marker_state}, {len(raw_response)} ky tu), "
            f"lan {output_attempt}/{MAX_RETRIES}."
        )
        if output_attempt < MAX_RETRIES:
            request_prompt = prompt + """

---
LƯU Ý SỬA OUTPUT: Lần trả lời trước không có hồ sơ nhân vật Markdown hợp lệ.
Hãy trả lại kết quả với ít nhất một header `## Tên nhân vật`, đặt toàn bộ nội dung
giữa `###CHAR_START###` và `###CHAR_END###`. Không trả lời giải thích.
"""

    raise ValueError(
        "Gemini trả output sai marker hoặc không có hồ sơ nhân vật hợp lệ "
        f"sau {MAX_RETRIES} lần; tiến độ chưa được tăng"
    )


def merge_characters(existing_md: str, new_md_block: str) -> str:
    existing_chars = parse_characters_from_md(existing_md)
    new_chars = parse_characters_from_md(new_md_block)

    if not new_chars:
        print("Khong parse duoc nhan vat tu response moi.")
        return existing_md

    merged = dict(existing_chars)
    added = 0
    updated = 0
    for name, block in new_chars.items():
        if name in merged:
            old_block = merged[name]
            missing_fields = []
            new_field_names = {
                match.group(1).strip().lower()
                for match in re.finditer(r"(?m)^- \*\*(.+?)\*\*\s*:", block)
            }
            for line in old_block.splitlines():
                match = re.match(r"^- \*\*(.+?)\*\*\s*:", line)
                if match and match.group(1).strip().lower() not in new_field_names:
                    missing_fields.append(line)
            if missing_fields:
                block = block.rstrip() + "\n\n### Thông tin được bảo toàn\n" + "\n".join(missing_fields)
            merged[name] = block
            updated += 1
        else:
            merged[name] = block
            added += 1

    print(f"   Da them {added} nhan vat moi, cap nhat {updated} nhan vat hien co.")

    sorted_names = sorted(merged.keys(), key=lambda x: x.lower())
    return "\n\n---\n\n".join(merged[n] for n in sorted_names)


# ============================================================
# DOC / GHI FILE
# ============================================================


def load_yaml_file(path: str):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def load_md(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_md(content: str, path: str):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Da luu: {path}")


def load_index(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("char_index", 0)


def save_index(index: int, path: str):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"char_index": index}, f, allow_unicode=True)


def build_header() -> str:
    return (
        "# Ho So Nhan Vat\n\n"
        "> File nay duoc tao tu dong boi `gen_characters.py`.  \n"
        "> Ban co the chinh sua truc tiep — script se doc va bo sung them khi chay lai.\n\n"
        "---\n\n"
    )


def split_header_and_body(md_text: str):
    match = re.search(r"\n## ", md_text)
    if match:
        return md_text[: match.start()].strip(), md_text[match.start() :].strip()
    return md_text.strip(), ""


# ============================================================
# MAIN
# ============================================================


def main():
    print("Phan tich thong tin nhan vat qua Gemini API")
    print("=" * 50)
    print(f"Model: {CHAR_MODEL}")
    print(f"Batch size: {BATCH_SIZE} chuong/batch")
    print()

    # Doc danh sach chuong tu truyen/raw/*.md
    raw_files = scan_md_dir(RAW_DIR)
    if not raw_files:
        print(f"Khong tim thay file .md nao trong {RAW_DIR}")
        return

    total_files = len(raw_files)
    requested_start = int_option("character_start", 1, minimum=1) - 1
    requested_end = int_option("character_end", total_files, minimum=1)
    force = str(option("character_force", "false")).lower() in {"1", "true", "yes", "on"}
    saved_index = load_index(CHAR_INDEX_FILE)
    start_idx = requested_start if force else max(saved_index, requested_start)
    end_idx = min(total_files, requested_end)
    if start_idx >= end_idx:
        print(f"Da phan tich het {total_files} chuong. Khong can chay them.")
        print("Chọn 'Chạy lại phạm vi' nếu muốn phân tích lại.")
        return

    files_to_process = raw_files[start_idx:end_idx]
    total = len(files_to_process)
    print(
        f"Tong chuong raw: {total_files} | Se xu ly: {total} (tu index {start_idx + 1})."
    )

    existing_md_full = load_md(CHARACTERS_MD)
    _, existing_body = split_header_and_body(existing_md_full)

    glossary = load_glossary(CONTEXT_FILE)
    if glossary:
        print(f"Da tai glossary ({len(glossary.splitlines())} muc) tu context.yaml")
    else:
        print("Khong tim thay glossary trong context.yaml")

    try:
        for i in range(0, total, BATCH_SIZE):
            if stop_requested():
                print("Đã dừng trước batch tiếp theo.")
                return
            batch_files = files_to_process[i : i + BATCH_SIZE]
            # Load noi dung tung file trong batch
            batch = [load_md_chapter(f) for f in batch_files]
            batch_num = i // BATCH_SIZE + 1
            from_chap = start_idx + i + 1
            to_chap = start_idx + i + len(batch)
            print(
                f"\n[Batch {batch_num}] Chuong {from_chap} -> {to_chap} ({len(batch)} chuong)..."
            )

            prompt = build_character_prompt(batch, existing_body, glossary)
            new_block = request_valid_character_block(prompt)
            existing_body = merge_characters(existing_body, new_block)

            final_md = build_header() + existing_body
            save_md(final_md, CHARACTERS_MD)

            new_index = start_idx + i + len(batch)
            save_index(max(saved_index, new_index), CHAR_INDEX_FILE)
            print(f"   Da luu tien do: index = {new_index} / {total_files}")

            if i + BATCH_SIZE < total:
                print("Nghi 5 giay truoc batch tiep theo...")
                time.sleep(5)

    except KeyboardInterrupt:
        print("\nDa dung boi Ctrl+C. Tien do da duoc luu.")

    print(f"\nXong! File nhan vat: {CHARACTERS_MD}")
    print(
        f"Tong chuong da phan tich: {min(start_idx + total, total_files)} / {total_files}"
    )


if __name__ == "__main__":
    main()
