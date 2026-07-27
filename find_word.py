#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Find Word — Tìm kiếm từ/cụm từ trong thư mục truyen/dich
Chỉ đọc, không thay đổi file nào.
"""

import io
import os
import re
import sys
import argparse
from pathlib import Path

# ── ANSI colors ───────────────────────────────────────────────────────────────
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RESET   = "\033[0m"

DICH_DIR = Path(__file__).parent / "truyen" / "translated"


# ── Helpers ───────────────────────────────────────────────────────────────────

def banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════════╗
║          🔎  Find Word — truyen/dich                 ║
╚══════════════════════════════════════════════════════╝{RESET}
""")


def help_text():
    print(f"""
{BOLD}Lệnh đặc biệt:{RESET}
  {CYAN}:q{RESET} hoặc {CYAN}:quit{RESET}    Thoát
  {CYAN}:help{RESET}           Hiện trợ giúp này
  {CYAN}:set{RESET}            Đổi tùy chọn (regex, case, pattern, context)
  {CYAN}:status{RESET}         Xem tùy chọn hiện tại

{BOLD}Tìm kiếm:{RESET}
  Nhập bất kỳ từ/cụm từ nào và Enter để tìm ngay.
""")


def print_status(opts: dict):
    print(f"""
{DIM}── Tùy chọn hiện tại ─────────────────────────────────{RESET}
  Regex        : {GREEN + 'bật' if opts['regex'] else DIM + 'tắt'}{RESET}
  Phân biệt HT : {GREEN + 'có' if opts['case'] else DIM + 'không'}{RESET}
  File pattern : {CYAN}{opts['pattern']}{RESET}
  Context      : {CYAN}{opts['ctx']} dòng{RESET}
{DIM}──────────────────────────────────────────────────────{RESET}
""")


def highlight(line: str, find: str, use_regex: bool, flags: int) -> str:
    """Tô màu đỏ phần khớp trong dòng."""
    if use_regex:
        return re.sub(find, lambda m: f"{RED}{BOLD}{m.group()}{RESET}", line, flags=flags)
    else:
        escaped = re.escape(find)
        return re.sub(escaped, lambda m: f"{RED}{BOLD}{m.group()}{RESET}", line, flags=flags)


def find_word(
    find: str,
    use_regex: bool = False,
    case_sensitive: bool = True,
    file_pattern: str = "*.md",
    context_lines: int = 0,
):
    flags = 0 if case_sensitive else re.IGNORECASE

    all_files = sorted(DICH_DIR.glob(file_pattern))
    if not all_files:
        print(f"{YELLOW}⚠  Không tìm thấy file nào khớp với pattern '{file_pattern}'{RESET}")
        return

    hits: dict[Path, list[tuple[int, str]]] = {}

    for fp in all_files:
        try:
            lines = fp.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            print(f"{YELLOW}⚠  Không đọc được {fp.name}: {e}{RESET}")
            continue

        file_hits = []
        for i, line in enumerate(lines, 1):
            if use_regex:
                try:
                    if re.search(find, line, flags=flags):
                        file_hits.append((i, line))
                except re.error:
                    pass
            else:
                if case_sensitive:
                    if find in line:
                        file_hits.append((i, line))
                else:
                    if find.lower() in line.lower():
                        file_hits.append((i, line))

        if file_hits:
            hits[fp] = file_hits

    if not hits:
        print(f"{YELLOW}🔍  Không tìm thấy '{find}' trong bất kỳ file nào.{RESET}\n")
        return

    total = sum(len(v) for v in hits.values())
    print(f"{GREEN}{BOLD}Tìm thấy {total} lần trong {len(hits)} file:{RESET}\n")

    for fp, file_hits in hits.items():
        print(f"  {CYAN}{BOLD}{fp.name}{RESET}  {DIM}({len(file_hits)} dòng){RESET}")

        all_lines = fp.read_text(encoding="utf-8").splitlines() if context_lines > 0 else []

        for lineno, raw in file_hits:
            hl = highlight(raw.strip(), find, use_regex, flags)
            print(f"    {DIM}L{lineno:<4}{RESET} {hl}")

            if context_lines > 0:
                start = max(0, lineno - 1 - context_lines)
                end   = min(len(all_lines), lineno + context_lines)
                for ci in range(start, end):
                    if ci + 1 == lineno:
                        continue
                    print(f"    {DIM}L{ci+1:<4}  {all_lines[ci].strip()}{RESET}")
                print()

        if context_lines == 0:
            print()

    print(f"{DIM}(Chỉ đọc — không file nào bị thay đổi){RESET}\n")


# ── Set options interactively ─────────────────────────────────────────────────

def set_options(opts: dict) -> dict:
    print(f"\n{BOLD}Đổi tùy chọn (Enter = giữ nguyên):{RESET}")

    raw = input(f"  Regex [{GREEN+'bật' if opts['regex'] else 'tắt'}{RESET}] (y/n): ").strip().lower()
    if raw == "y":
        opts["regex"] = True
    elif raw == "n":
        opts["regex"] = False

    raw = input(f"  Phân biệt hoa/thường [{GREEN+'có' if opts['case'] else 'không'}{RESET}] (y/n): ").strip().lower()
    if raw == "y":
        opts["case"] = True
    elif raw == "n":
        opts["case"] = False

    raw = input(f"  File pattern [{CYAN}{opts['pattern']}{RESET}]: ").strip()
    if raw:
        opts["pattern"] = raw

    raw = input(f"  Context lines [{CYAN}{opts['ctx']}{RESET}]: ").strip()
    if raw.isdigit():
        opts["ctx"] = int(raw)

    print()
    print_status(opts)
    return opts


# ── REPL ──────────────────────────────────────────────────────────────────────

def repl_mode():
    banner()

    opts = {
        "regex":   False,
        "case":    True,
        "pattern": "*.md",
        "ctx":     0,
    }

    print(f"{DIM}Gõ từ cần tìm và Enter. Lệnh: :set  :status  :help  :q{RESET}\n")

    while True:
        try:
            raw = input(f"{CYAN}{BOLD}find>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}Tạm biệt!{RESET}")
            break

        if not raw:
            continue
        if raw in (":q", ":quit", ":exit"):
            print(f"{DIM}Tạm biệt!{RESET}")
            break
        if raw == ":help":
            help_text()
            continue
        if raw == ":status":
            print_status(opts)
            continue
        if raw == ":set":
            opts = set_options(opts)
            continue

        # Tìm kiếm
        find_word(
            find=raw,
            use_regex=opts["regex"],
            case_sensitive=opts["case"],
            file_pattern=opts["pattern"],
            context_lines=opts["ctx"],
        )


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    # Fix Windows console encoding
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        os.system("")  # Enable ANSI

    parser = argparse.ArgumentParser(
        description="Tim kiem tu/cum tu trong truyen/dich (chi doc, khong thay the)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("find",    nargs="?",           help="Chuỗi cần tìm (bỏ trống = REPL)")
    parser.add_argument("-r", "--regex",      action="store_true", help="Dùng biểu thức chính quy (regex)")
    parser.add_argument("-i", "--ignore-case",action="store_true", help="Không phân biệt hoa/thường")
    parser.add_argument("-p", "--pattern",    default="*.md",      help="Pattern file (mặc định: *.md)")
    parser.add_argument("-C", "--context",    type=int, default=0, help="Số dòng context xung quanh kết quả")

    args = parser.parse_args()

    if not args.find:
        repl_mode()
    else:
        banner()
        find_word(
            find=args.find,
            use_regex=args.regex,
            case_sensitive=not args.ignore_case,
            file_pattern=args.pattern,
            context_lines=args.context,
        )


if __name__ == "__main__":
    main()
