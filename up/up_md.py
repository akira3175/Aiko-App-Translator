"""
up_md.py
========
Upload chương lên docln từ truyen/translated/*.md.

Đặc điểm:
  - Đọc nội dung từ truyen/translated/vx_cy_sz.md (không dùng YAML hay EPUB)
  - Ảnh nằm inline trong MD dưới dạng ![image](truyen/image/vx_cy_sz_lineN.ext)
  - Upload ảnh ngay khi đăng chương đó (không upload hết 1 lần trước)
  - Nhiều file cùng vx_cy (segment khác nhau) được gộp lại thành 1 chương

Cách chạy:
  python up/up_md.py

Cấu hình: up/config_md.json
"""

import asyncio
import json
import re
import os
import sys
from collections import defaultdict
from urllib.parse import quote

import yaml

# Fix UnicodeEncodeError trên Windows console (emoji, ký tự đặc biệt)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from playwright.async_api import async_playwright, TimeoutError

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None

try:
    from playwright_stealth import stealth_async
except ImportError:
    async def stealth_async(page):
        pass

# ============================================================
# \u0110\u01af\u1eddNG D\u1eaaN
# ============================================================
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_PROJECT_ROOT)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from cores.runtime_config import bool_option, int_option, option, web_mode

PORTABLE_CHROME = os.path.join(
    _PROJECT_ROOT, "runtime", "chromium", "chrome-win64", "chrome.exe"
)

_PROJECT_NAME = os.environ.get("NOVEL_PROJECT", "").strip()
_PROJECT_DIR = os.path.join("truyen", _PROJECT_NAME) if _PROJECT_NAME else "truyen"
TRANSLATED_DIR = os.path.join(_PROJECT_DIR, "translated")
IMAGE_DIR      = os.path.join(_PROJECT_DIR, "image")
PUBLISHING_FILE = os.path.join(_PROJECT_DIR, "publishing.yaml")


def load_book_mappings(path=PUBLISHING_FILE):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    hako = data.get("hako", {}) if isinstance(data, dict) else {}
    books = hako.get("books", []) if isinstance(hako, dict) else []
    return books if isinstance(books, list) else []


def destination_for_volume(volume, book_mappings, fallback_url=""):
    for book in book_mappings:
        start = int(book.get("volume", book.get("from_volume")))
        end = int(book.get("volume", book.get("to_volume", start)))
        if start <= volume <= end:
            return (
                f"https://docln.sbs/action/chapter/create/book={book['book_id']}",
                str(book.get("label") or book["book_id"]),
            )
    if book_mappings:
        raise RuntimeError(
            f"Volume {volume} chưa được gán book ID trong publishing.yaml."
        )
    if fallback_url:
        return fallback_url, "URL Hako dự phòng"
    raise RuntimeError("Chưa cấu hình book ID cho truyện.")


# ============================================================
# \u0110\u1eccC MD
# ============================================================

def _sort_key_md(filename):
    """Sort key cho t\u00ean file vx_cy_sz.md."""
    m = re.match(r"v(\d+)_c(\d+)_s(\d+)\.md$", os.path.basename(filename))
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (9999, 9999, 9999)


def scan_translated_dir(directory=TRANSLATED_DIR):
    """Tr\u1ea3 v\u1ec1 list \u0111\u01b0\u1eddng d\u1eabn \u0111\u1ea7y \u0111\u1ee7 *.md trong translated/, s\u1eafp x\u1ebfp theo vx_cy_sz."""
    if not os.path.exists(directory):
        return []
    files = [f for f in os.listdir(directory) if f.endswith(".md")]
    files.sort(key=_sort_key_md)
    return [os.path.join(directory, f) for f in files]


def parse_md_file(filepath):
    """
    \u0110\u1ecdc file translated MD, tr\u1ea3 v\u1ec1 dict:
      {id, title, elements}
    elements: list theo th\u1ee9 t\u1ef1 \u2014 {'type': 'text'|'image', 'content': str}
    """
    chapter_id = os.path.splitext(os.path.basename(filepath))[0]
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    title = ""
    elements = []
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    title_found = False
    for block in blocks:
        if not title_found and block.startswith("# "):
            title = block[2:].strip()
            title_found = True
            continue
        if block.startswith("!["):
            elements.append({"type": "image", "content": block})
        else:
            elements.append({"type": "text", "content": block})

    return {"id": chapter_id, "title": title, "elements": elements}


def group_segments_into_chapters(md_files):
    """
    Nh\u00f3m c\u00e1c file vx_cy_sz.md th\u00e0nh chapters theo vx_cy.
    key = (vol, chap), value = list m\u00f4 t\u1ea3 segment (sorted by s)
    """
    chapters = defaultdict(list)
    for filepath in md_files:
        m = re.match(r"v(\d+)_c(\d+)_s(\d+)\.md$", os.path.basename(filepath))
        if m:
            vol, chap, seg = int(m.group(1)), int(m.group(2)), int(m.group(3))
            chapters[(vol, chap)].append((seg, filepath))

    # S\u1eafp x\u1ebfp segments trong m\u1ed7i chapter
    for key in chapters:
        chapters[key].sort(key=lambda x: x[0])

    # S\u1eafp x\u1ebfp chapters theo (vol, chap)
    sorted_chapters = sorted(chapters.items(), key=lambda x: x[0])
    return sorted_chapters


# ============================================================
# UPLOAD ẢNH
# ============================================================

_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image_cache.json")
_r2_config: dict = {}  # Được khởi tạo từ main()


def _load_cache() -> dict:
    """Load persistent image cache từ file JSON."""
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"  [CACHE] Đã load {len(data)} ảnh từ cache ({_CACHE_FILE})")
            return data
        except Exception as e:
            print(f"  [CACHE] Không đọc được cache file: {e}")
    return {}


def _save_cache(cache: dict) -> None:
    """Ghi persistent image cache xuống file JSON ngay lập tức."""
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [CACHE] Không ghi được cache file: {e}")


_image_url_cache: dict[str, str] = _load_cache()  # local_path -> url (persistent)


def _get_r2_client():
    """Tạo boto3 S3 client kết nối đến Cloudflare R2."""
    if boto3 is None:
        raise RuntimeError("boto3 chưa được cài. Chạy: pip install boto3")
    r2 = _r2_config
    endpoint = f"https://{r2['account_id']}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=r2["access_key_id"],
        aws_secret_access_key=r2["secret_access_key"],
        region_name="auto",
    )


def upload_image_file(local_path: str) -> str:
    """
    Upload 1 file ảnh lên Cloudflare R2 và trả về URL công khai.
    Cache theo đường dẫn để tránh upload lại trong cùng phiên.
    """
    cache_key = f"{_PROJECT_NAME}|{os.path.abspath(local_path)}"
    if cache_key in _image_url_cache:
        cached_url = _image_url_cache[cache_key]
        print(f"  [IMG] Cache hit: {os.path.basename(local_path)} → {cached_url}")
        return cached_url

    if not os.path.exists(local_path):
        print(f"  [IMG] Không tìm thấy file ảnh: {local_path}")
        return ""

    if not _r2_config:
        print("  [IMG] Lỗi: Chưa cấu hình cloudflare_r2 trong config_md.json")
        return ""

    ext = local_path.rsplit(".", 1)[-1].lower()
    mime = {"webp": "image/webp", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "gif": "image/gif"}.get(ext, "image/png")

    # Dùng tên file gốc làm object key (có thể thêm prefix nếu muốn)
    project_prefix = _PROJECT_NAME or "default"
    object_key = f"novel/{project_prefix}/{os.path.basename(local_path)}"
    bucket = _r2_config["bucket"]
    public_url_base = _r2_config["public_url"].rstrip("/")

    try:
        with open(local_path, "rb") as f:
            img_bytes = f.read()
        size_kb = len(img_bytes) // 1024
        print(f"  [IMG] Upload {os.path.basename(local_path)} ({size_kb} KB) → R2...")

        client = _get_r2_client()
        client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=img_bytes,
            ContentType=mime,
        )

        img_url = f"{public_url_base}/{quote(object_key, safe='/')}"
        _image_url_cache[cache_key] = img_url
        _save_cache(_image_url_cache)  # Ghi xuống disk ngay lập tức
        print(f"  [IMG] OK: {img_url}")
        return img_url

    except Exception as e:
        print(f"  [IMG] Exception khi upload R2: {e}")
    return ""


def extract_image_path(md_img_block: str) -> str:
    """
    Lấy đường dẫn ảnh từ block `![image](../image/vx_cy_sz_lineN.ext)`.
    Đường dẫn trong MD là relative từ thư mục chứa file MD (truyen/translated/).
    Trả về đường dẫn tuyệt đối đã chuẩn hóa.
    """
    m = re.search(r"!\[.*?\]\((.+?)\)", md_img_block)
    if not m:
        return ""
    rel = m.group(1).strip()
    if os.path.isabs(rel):
        return rel
    # Resolve relative to truyen/translated/ (nơi chứa file MD)
    base_dir = os.path.join(_PROJECT_ROOT, TRANSLATED_DIR)
    return os.path.normpath(os.path.join(base_dir, rel))


# ============================================================
# X\u00e2Y D\u1ef0NG HTML T\u1eeb ELEMENTS
# ============================================================

def md_to_html_inline(text: str) -> str:
    """Markdown inline formatting -> HTML."""
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    return text


def elements_to_html_parts(elements: list, chapter_title: str) -> list:
    """
    Chuy\u1ec3n list elements th\u00e0nh list html_parts.
    \u1ea2nh \u0111\u01b0\u1ee3c upload v\u00e0 thay th\u1ebf b\u1eb1ng <img> tag ngay t\u1ea1i \u0111\u00e2y.
    Chuyển list elements thành list html_parts.
    Ảnh được upload và thay thế bằng <img> tag ngay tại đây.
    Trả về (html_parts, image_count)
    """
    html_parts = []
    image_count = 0

    for elem in elements:
        if elem["type"] == "image":
            local_path = extract_image_path(elem["content"])
            if local_path:
                img_url = upload_image_file(local_path)
                if img_url:
                    html_parts.append(
                        f'<p style="text-align:center">'
                        f'<img src="{img_url}" style="max-width:100%;height:auto" />'
                        f'</p>'
                    )
                    image_count += 1
                else:
                    html_parts.append('<p style="text-align:center;color:red">[L\u1ed7i t\u1ea3i \u1ea3nh]</p>')
            else:
                html_parts.append('<p style="text-align:center;color:red">[Kh\u00f4ng t\u00ecm th\u1ea5y \u1ea3nh]</p>')

        elif elem["type"] == "text":
            # M\u1ed7i d\u00f2ng trong block th\u00e0nh 1 <p>
            block = elem["content"]

            # Thay '---' th\u00e0nh '...'
            if block.strip() == "---":
                html_parts.append("<p>...</p>")
                continue

            lines = block.split("\n")
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    html_parts.append("<p><br></p>")
                elif stripped.startswith("#"):
                    # Heading trong n\u1ed9i dung
                    converted = re.sub(r'^### (.+)$', r'<h3>\1</h3>', stripped, flags=re.MULTILINE)
                    converted = re.sub(r'^## (.+)$', r'<h2>\1</h2>', converted, flags=re.MULTILINE)
                    converted = re.sub(r'^# (.+)$', r'<h1>\1</h1>', converted, flags=re.MULTILINE)
                    html_parts.append(converted)
                else:
                    escaped = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    escaped = md_to_html_inline(escaped)
                    if escaped.startswith(("-", "*", "+")):
                        escaped = "&#8203;" + escaped
                    html_parts.append(f"<p>{escaped}</p>")

    return html_parts, image_count


# ============================================================
# UPLOAD L\u00eaN WEBSITE
# ============================================================

async def upload_chapter_to_site(chapter_key, segments_data, upload_url, page, selectors, config):
    """
    Upload 1 ch\u01b0\u01a1ng (g\u1ed3m nhi\u1ec1u segment) l\u00ean website.
    Upload \u1ea3nh ngay khi x\u1eed l\u00fd ch\u01b0\u01a1ng n\u00e0y.
    """
    vol, chap = chapter_key

    # Gh\u00e9p n\u1ed9i dung t\u1ea5t c\u1ea3 segments
    all_elements = []
    chapter_title = ""
    for seg_idx, (seg_num, filepath) in enumerate(segments_data):
        seg = parse_md_file(filepath)
        if seg_idx == 0:
            chapter_title = seg["title"]
        else:
            # Segment sau: n\u1ebfu c\u00f3 title ri\u00eang th\u00ec th\u00eam nh\u01b0 heading
            if seg["title"]:
                all_elements.append({"type": "text", "content": f"## {seg['title']}"})
        all_elements.extend(seg["elements"])

    if not all_elements and not chapter_title:
        print(f"  B\u1ecf qua ch\u01b0\u01a1ng v{vol}_c{chap}: kh\u00f4ng c\u00f3 n\u1ed9i dung.")
        return True

    print(f"\n  Ti\u00eau \u0111\u1ec1: {chapter_title}")
    print(f"  Elements: {len(all_elements)} blocks")

    # Build HTML + upload \u1ea3nh
    html_parts, img_count = elements_to_html_parts(all_elements, chapter_title)
    if img_count > 0:
        print(f"  \u0110\u00e3 upload {img_count} \u1ea3nh")

    html_content = "".join(html_parts)

    try:
        print(f"  \u0110i\u1ec1u h\u01b0\u1edbng \u0111\u1ebfn trang t\u1ea1o ch\u01b0\u01a1ng...")
        await page.goto(upload_url)
        await page.wait_for_load_state("networkidle")

        # \u0110i\u1ec1n ti\u00eau \u0111\u1ec1
        print(f"  \u0110i\u1ec1n ti\u00eau \u0111\u1ec1...")
        title_locator = page.locator(selectors["title"])
        await title_locator.wait_for(state="visible", timeout=30000)
        await title_locator.fill(chapter_title)

        # \u0110i\u1ec1n n\u1ed9i dung qua synthetic paste
        print(f"  \u0110i\u1ec1n n\u1ed9i dung ({len(html_content)} ky t\u1ef1 HTML)...")
        editor_selector = selectors.get("editor_body", ".tiptap.ProseMirror, .ProseMirror[contenteditable='true']")
        editor_locator = page.locator(editor_selector)
        await editor_locator.wait_for(state="visible", timeout=60000)
        await editor_locator.click()
        await page.keyboard.press("Control+a")

        await editor_locator.evaluate("""async (el, html) => {
            const dataTransfer = new DataTransfer();
            dataTransfer.setData('text/html', html);
            dataTransfer.setData('text/plain', html.replace(/<[^>]+>/g, ''));
            const pasteEvent = new ClipboardEvent('paste', {
                clipboardData: dataTransfer,
                bubbles: true,
                cancelable: true
            });
            el.dispatchEvent(pasteEvent);
        }""", html_content)

        await page.wait_for_timeout(1000)

        # Tr\u1ea1ng th\u00e1i ch\u01b0a ho\u00e0n th\u00e0nh
        if config.get("set_as_incomplete", False):
            radio_selector = selectors.get("incomplete_radio_button")
            if radio_selector:
                try:
                    await page.locator(radio_selector).click(timeout=3000)
                    print("  \u0110\u00e3 ch\u1ecdn 'Ch\u01b0a ho\u00e0n th\u00e0nh'.")
                except Exception:
                    pass

        # Submit
        submit_btn = page.locator(selectors["submit_button"])
        await submit_btn.wait_for(state="visible", timeout=20000)
        await submit_btn.click()

        print(f"  \u2705 \u0110\u00e3 g\u1eedi ch\u01b0\u01a1ng v{vol}_c{chap}. Ch\u1edd 7 gi\u00e2y...")
        await page.wait_for_timeout(7000)
        return True

    except Exception as e:
        print(f"  \u274c L\u1ed7i khi \u0111\u0103ng v{vol}_c{chap}: {e}")
        if not web_mode():
            await page.pause()
        return False


# ============================================================
# MAIN
# ============================================================

async def main():
    print("=" * 60)
    print(" UP_MD \u2014 Upload t\u1eeb MD files (truyen/translated/)")
    print("=" * 60)

    # \u0110\u1ecdc config
    config_path = "up/config_md.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy {config_path}")
        print("Vui lòng tạo file config_md.json theo hướng dẫn.")
        return
    except Exception as e:
        print(f"Lỗi đọc config: {e}")
        return

    # Khởi tạo Cloudflare R2 config
    global _r2_config
    r2_cfg = {
        "account_id": option("r2_account_id", ""),
        "access_key_id": option("r2_access_key_id", ""),
        "secret_access_key": option("r2_secret_access_key", ""),
        "bucket": option("r2_bucket", ""),
        "public_url": option("r2_public_url", ""),
    } if web_mode() else config.get("cloudflare_r2", {})
    required_r2_keys = ["account_id", "access_key_id", "secret_access_key", "bucket", "public_url"]
    if r2_cfg and all(r2_cfg.get(k) for k in required_r2_keys):
        _r2_config = r2_cfg
        print(f"☁️  R2 bucket: {r2_cfg['bucket']} | {r2_cfg['public_url']}")
    else:
        print("⚠️  Chưa cấu hình cloudflare_r2 đầy đủ — ảnh sẽ không được upload.")

    # Lấy thông tin từ config (không đổi)
    upload_url = str(option("hako_management_url", "")).strip() if web_mode() else config.get("management_url", "")
    book_mappings = load_book_mappings() if web_mode() else []
    md_dir     = TRANSLATED_DIR if web_mode() else config.get("md_dir", TRANSLATED_DIR)
    config["set_as_incomplete"] = bool_option("set_as_incomplete", config.get("set_as_incomplete", False))
    credentials = {
        "username": str(option("hako_username", "")).strip(),
        "password": str(option("hako_password", "")),
    } if web_mode() else config.get("credentials", {})

    if not upload_url and not book_mappings:
        raise RuntimeError(
            "Truyện chưa có mapping book ID và cũng chưa có URL Hako dự phòng."
        )
    if not credentials.get("username") or not credentials.get("password"):
        raise RuntimeError("Chưa nhập tên đăng nhập hoặc mật khẩu Hako trong Cài đặt.")

    # Scan và nhóm trước để hiện danh sách
    print(f"\n📂 Scan {md_dir}...")
    md_files = scan_translated_dir(md_dir)
    if not md_files:
        print(f"Không tìm thấy file .md nào trong {md_dir}")
        return

    sorted_chapters = group_segments_into_chapters(md_files)
    total = len(sorted_chapters)
    print(f"📚 Tìm thấy {total} chương")

    # Hiển thị vol có sẵn
    vol_groups = defaultdict(list)
    for (vol, chap), _ in sorted_chapters:
        vol_groups[vol].append(chap)
    for vol in sorted(vol_groups):
        chaps = vol_groups[vol]
        print(f"   Vol {vol}: chương {min(chaps)} → {max(chaps)} ({len(chaps)} chương)")

    # ── Hỏi range từ terminal ──────────────────────────────────
    def _int(prompt, default=None):
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            print(f"  ⚠️  Không hợp lệ, dùng mặc định: {default}")
            return default

    if web_mode():
        from_vol = int_option("from_vol")
        from_chap = int_option("from_chap")
        to_vol = int_option("to_vol")
        to_chap = int_option("to_chap")
    else:
        print("\n⚙️  CHỌN PHẠM VI UPLOAD (Enter = bỏ qua / tất cả):")
        from_vol  = _int("  Từ   vol  [Enter = đầu]: ")
        from_chap = _int("  Từ   chap [Enter = đầu]: ")
        to_vol    = _int("  Đến  vol  [Enter = cuối]: ")
        to_chap   = _int("  Đến  chap [Enter = cuối]: ")

    # Lọc theo range
    def in_range(key):
        vol, chap = key
        if from_vol is not None and from_chap is not None:
            if (vol, chap) < (from_vol, from_chap):
                return False
        elif from_vol is not None:
            if vol < from_vol:
                return False
        if to_vol is not None and to_chap is not None:
            if (vol, chap) > (to_vol, to_chap):
                return False
        elif to_vol is not None:
            if vol > to_vol:
                return False
        return True

    sorted_chapters = [(k, v) for k, v in sorted_chapters if in_range(k)]

    # Hiển thị range đã chọn
    from_label = f"v{from_vol}" + (f"_c{from_chap}" if from_chap is not None else "") if from_vol is not None else "đầu"
    to_label   = f"v{to_vol}"  + (f"_c{to_chap}"  if to_chap  is not None else "") if to_vol  is not None else "cuối"
    print(f"\n  ▸ Phạm vi : {from_label} → {to_label}")
    print(f"  ▸ Số chương: {len(sorted_chapters)}")

    if not sorted_chapters:
        print("Không có chương nào trong phạm vi đã chọn.")
        return

    destinations = {}
    for (volume, _), _segments in sorted_chapters:
        resolved_url, resolved_label = destination_for_volume(
            volume, book_mappings, upload_url
        )
        destinations[volume] = (resolved_url, resolved_label)
    print("  ▸ Đích đăng:")
    for volume in sorted(destinations):
        resolved_url, resolved_label = destinations[volume]
        print(f"     Vol {volume} → {resolved_label} ({resolved_url.rsplit('=', 1)[-1]})")

    selectors = config.get("selectors", {
        "title": "input[name='title']",
        "editor_body": ".tiptap.ProseMirror, .ProseMirror[contenteditable='true']",
        "submit_button": "button[type='submit']",
        "incomplete_radio_button": "input[name='complete'][value='0']"
    })

    # Kh\u1edfi \u0111\u1ed9ng browser
    print("\n\ud83c\udf0e Kh\u1edfi \u0111\u1ed9ng tr\u00ecnh duy\u1ec7t...")
    async with async_playwright() as p:
        launch_options = {
            "headless": False,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if os.path.isfile(PORTABLE_CHROME):
            launch_options["executable_path"] = PORTABLE_CHROME
        else:
            launch_options["channel"] = "chrome"
        browser = await p.chromium.launch(**launch_options)
        context = await browser.new_context()
        await context.grant_permissions(["clipboard-read", "clipboard-write"])
        page = await context.new_page()
        await stealth_async(page)

        # \u0110\u0103ng nh\u1eadp
        await page.goto("https://docln.sbs/login")
        await page.locator("#name").fill(credentials["username"])
        await page.locator("#password").fill(credentials["password"])

        print("=" * 60)
        print(">> Vui l\u00f2ng gi\u1ea3i reCAPTCHA v\u00e0 nh\u1ea5n '\u0110\u0103ng nh\u1eadp'.")
        print(">> Sau khi \u0111\u0103ng nh\u1eadp xong, quay l\u1ea1i \u0111\u00e2y v\u00e0 nh\u1ea5n Enter.")
        print("=" * 60)
        if web_mode():
            print("Đang chờ bạn đăng nhập thành công trên cửa sổ Chrome (tối đa 5 phút)...")
            for _ in range(300):
                if "/login" not in page.url and await page.locator("#name").count() == 0:
                    break
                await page.wait_for_timeout(1000)
            else:
                raise RuntimeError("Hết thời gian chờ đăng nhập Hako.")
        else:
            input("Nh\u1ea5n Enter \u0111\u1ec3 b\u1eaft \u0111\u1ea7u qu\u00e1 tr\u00ecnh \u0111\u0103ng h\u00e0ng lo\u1ea1t...")

        print(f"\n--- B\u1eaet \u0110\u1ea6U \u0110\u0102NG ({len(sorted_chapters)} ch\u01b0\u01a1ng) ---")

        failed = 0
        for i, (chapter_key, segments_data) in enumerate(sorted_chapters):
            vol, chap = chapter_key
            chapter_upload_url, destination_label = destinations[vol]
            print(f"\n({i+1}/{len(sorted_chapters)}) \u0110ang \u0111\u0103ng: v{vol}_c{chap} "
                  f"({len(segments_data)} segment(s)) → {destination_label}")
            ok = await upload_chapter_to_site(
                chapter_key, segments_data,
                chapter_upload_url, page, selectors, config
            )
            if not ok:
                failed += 1
                print("\n\u274c D\u1eebng do l\u1ed7i. Ki\u1ec3m tra tr\u00ecnh duy\u1ec7t r\u1ed3i \u0111\u00f3ng.")
                break

        if failed == 0:
            print(f"\n\ud83c\udf89 Ho\u00e0n t\u1ea5t! \u0110\u00e3 \u0111\u0103ng {len(sorted_chapters)} ch\u01b0\u01a1ng.")
        else:
            print(f"\n\u26a0\ufe0f  D\u1eebng t\u1ea1i ch\u01b0\u01a1ng th\u1ee9 {i+1} do c\u00f3 l\u1ed7i.")

        if not web_mode():
            print("Tr\u00ecnh duy\u1ec7t \u0111\u00f3ng sau 60 gi\u00e2y.")
            await asyncio.sleep(60)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
