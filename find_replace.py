#!/usr/bin/env python3
"""
Find & Replace Tool cho thư mục truyen/dich
Hỗ trợ: regex, preview, backup, nhiều cặp thay thế, chọn file.
"""

import os
import re
import sys
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# ── ANSI colors ──────────────────────────────────────────────────────────────
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RESET   = "\033[0m"

DICH_DIR = Path(__file__).parent / "truyen" / "translated"
BACKUP_DIR = Path(__file__).parent / "truyen" / "_backup"


# ── Helpers ───────────────────────────────────────────────────────────────────

def banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════════╗
║          🔍  Find & Replace — truyen/dich            ║
╚══════════════════════════════════════════════════════╝{RESET}
""")


def color_diff(original: str, replaced: str, find: str, use_regex: bool) -> str:
    """Highlight the changed part in replaced text."""
    if use_regex:
        highlighted = re.sub(find, lambda m: f"{RED}{BOLD}{m.group()}{RESET}", original)
    else:
        highlighted = original.replace(find, f"{RED}{BOLD}{find}{RESET}")
    return highlighted


def make_backup(files: list[Path]):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = BACKUP_DIR / ts
    bk.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, bk / f.name)
    print(f"{DIM}💾  Backup saved → {bk}{RESET}")
    return bk


def find_and_replace(
    find: str,
    replace: str,
    use_regex: bool = False,
    case_sensitive: bool = True,
    file_pattern: str = "*.md",
    dry_run: bool = False,
    interactive: bool = False,
    backup: bool = True,
):
    flags = 0 if case_sensitive else re.IGNORECASE

    # Collect matching files
    all_files = sorted(DICH_DIR.glob(file_pattern))
    if not all_files:
        print(f"{YELLOW}⚠  Không tìm thấy file nào khớp với pattern '{file_pattern}'{RESET}")
        return

    # First pass: find matches
    hits: dict[Path, list[tuple[int, str, str]]] = {}  # file → [(lineno, old, new)]
    for fp in all_files:
        text = fp.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        file_hits = []
        for i, line in enumerate(lines, 1):
            if use_regex:
                new_line = re.sub(find, replace, line, flags=flags)
            else:
                if case_sensitive:
                    new_line = line.replace(find, replace)
                else:
                    new_line = re.sub(re.escape(find), replace, line, flags=re.IGNORECASE)
            if new_line != line:
                file_hits.append((i, line.rstrip("\r\n"), new_line.rstrip("\r\n")))
        if file_hits:
            hits[fp] = file_hits

    if not hits:
        print(f"{YELLOW}🔍  Không tìm thấy '{find}' trong bất kỳ file nào.{RESET}")
        return

    # Summary
    total_matches = sum(len(v) for v in hits.values())
    print(f"{GREEN}{BOLD}Tìm thấy {total_matches} lần xuất hiện trong {len(hits)} file:{RESET}\n")

    for fp, file_hits in hits.items():
        print(f"  {CYAN}{fp.name}{RESET}  ({len(file_hits)} dòng)")
        for lineno, old, new in file_hits[:5]:  # preview up to 5 lines per file
            print(f"    {DIM}L{lineno:<4}{RESET} {RED}- {old}{RESET}")
            print(f"    {DIM}L{lineno:<4}{RESET} {GREEN}+ {new}{RESET}")
        if len(file_hits) > 5:
            print(f"    {DIM}… và {len(file_hits)-5} dòng nữa{RESET}")
        print()

    if dry_run:
        print(f"{YELLOW}[Dry-run] Không thay đổi file nào.{RESET}")
        return

    if interactive:
        ans = input(f"{BOLD}Tiến hành thay thế? [y/N] {RESET}").strip().lower()
        if ans != "y":
            print("Hủy.")
            return

    # Backup
    if backup:
        make_backup(list(hits.keys()))

    # Apply
    changed = 0
    for fp in hits:
        text = fp.read_text(encoding="utf-8")
        if use_regex:
            new_text = re.sub(find, replace, text, flags=flags)
        else:
            if case_sensitive:
                new_text = text.replace(find, replace)
            else:
                new_text = re.sub(re.escape(find), replace, text, flags=re.IGNORECASE)
        fp.write_text(new_text, encoding="utf-8")
        changed += 1

    print(f"{GREEN}{BOLD}✅  Đã cập nhật {changed} file.{RESET}")


# ── Interactive mode ──────────────────────────────────────────────────────────

def interactive_mode():
    banner()
    print(f"{BOLD}Chế độ: Tương tác (nhập thông tin bên dưới){RESET}\n")

    find_text   = input(f"{CYAN}Tìm (find)    : {RESET}")
    replace_text = input(f"{GREEN}Thay (replace): {RESET}")

    use_regex  = input(f"Dùng regex? [y/N]: ").strip().lower() == "y"
    case_sens  = input(f"Phân biệt hoa/thường? [Y/n]: ").strip().lower() != "n"
    pattern    = input(f"File pattern [*.md]: ").strip() or "*.md"
    do_backup  = input(f"Tạo backup? [Y/n]: ").strip().lower() != "n"

    print()
    find_and_replace(
        find=find_text,
        replace=replace_text,
        use_regex=use_regex,
        case_sensitive=case_sens,
        file_pattern=pattern,
        dry_run=False,
        interactive=True,
        backup=do_backup,
    )


# ── Batch mode (from file) ────────────────────────────────────────────────────

def batch_mode(pairs_file: str):
    """
    File format (one pair per two lines):
        FIND: <text>
        REPLACE: <text>
        ---
    """
    banner()
    p = Path(pairs_file)
    if not p.exists():
        print(f"{RED}File không tồn tại: {p}{RESET}")
        sys.exit(1)

    content = p.read_text(encoding="utf-8")
    pairs = []
    for block in content.split("---"):
        block = block.strip()
        if not block:
            continue
        find_m    = re.search(r"^FIND:\s*(.+)$", block, re.MULTILINE)
        replace_m = re.search(r"^REPLACE:\s*(.*)$", block, re.MULTILINE)
        regex_m   = re.search(r"^REGEX:\s*(true|false)$", block, re.MULTILINE | re.IGNORECASE)
        if find_m:
            pairs.append({
                "find": find_m.group(1),
                "replace": replace_m.group(1) if replace_m else "",
                "regex": regex_m.group(1).lower() == "true" if regex_m else False,
            })

    if not pairs:
        print(f"{YELLOW}Không tìm thấy cặp nào trong file batch.{RESET}")
        return

    print(f"{BOLD}Batch: {len(pairs)} cặp thay thế{RESET}\n")
    for i, pair in enumerate(pairs, 1):
        print(f"{CYAN}[{i}/{len(pairs)}] {BOLD}{pair['find']}{RESET} → {GREEN}{pair['replace']}{RESET}")
        find_and_replace(
            find=pair["find"],
            replace=pair["replace"],
            use_regex=pair["regex"],
            dry_run=False,
            interactive=False,
            backup=(i == 1),  # backup only once
        )
        print()


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Find & Replace trong truyen/dich",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("find",    nargs="?", help="Chuỗi cần tìm")
    parser.add_argument("replace", nargs="?", default="", help="Chuỗi thay thế")
    parser.add_argument("-r", "--regex",    action="store_true", help="Dùng biểu thức chính quy (regex)")
    parser.add_argument("-i", "--ignore-case", action="store_true", help="Không phân biệt hoa/thường")
    parser.add_argument("-p", "--pattern", default="*.md", help="Pattern file (mặc định: *.md)")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Chỉ xem trước, không thay đổi")
    parser.add_argument("--no-backup",   action="store_true", help="Không tạo backup")
    parser.add_argument("--interactive", action="store_true", help="Chế độ tương tác")
    parser.add_argument("--batch",       metavar="FILE",       help="File batch chứa nhiều cặp thay thế")

    args = parser.parse_args()

    # Enable ANSI on Windows
    if sys.platform == "win32":
        os.system("")

    if args.batch:
        batch_mode(args.batch)
    elif args.interactive or not args.find:
        interactive_mode()
    else:
        banner()
        find_and_replace(
            find=args.find,
            replace=args.replace,
            use_regex=args.regex,
            case_sensitive=not args.ignore_case,
            file_pattern=args.pattern,
            dry_run=args.dry_run,
            interactive=not args.dry_run,
            backup=not args.no_backup,
        )


if __name__ == "__main__":
    main()
