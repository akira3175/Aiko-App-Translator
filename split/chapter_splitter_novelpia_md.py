"""
chapter_splitter_novelpia_md.py
================================
Tách file EPUB (Novelpia) thành các file .md riêng lẻ.

Quy ước đặt tên:
  - File MD  : truyen/raw/vx_cy_sz.md
  - File ảnh : truyen/image/vx_cy_sz_linet.ext
                 x = số vol (0-based từ EPUB, nhập tay)
                 y = số chương (0-based)
                 z = số segment (1-based, chương dài được chia theo giới hạn nhập)
                 t = số dòng trong file .md (1-based, dòng ngay trước placeholder ảnh)

Nội dung file .md:
  - Dòng đầu tiên: tiêu đề chương
  - Các dòng tiếp: nội dung văn bản
  - Placeholder ảnh: ![image](../image/vx_cy_sz_linet.ext)
    (được chèn đúng vị trí trong luồng nội dung, để up.py xử lý)
"""

import re
import time
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ============================================================
# HTML PARSER
# ============================================================

class EpubHTMLParser(HTMLParser):
    """
    Parser HTML cho một file chương trong EPUB.
    Trả về:
      - title: tiêu đề chương (từ thẻ h1/h2/h3...)
      - elements: list theo thứ tự xuất hiện, mỗi phần tử là dict:
            {'type': 'text', 'content': '...'} hoặc
            {'type': 'image', 'src': '...'}
    """
    def __init__(self):
        super().__init__()
        self.title = None
        self.elements = []          # kết quả cuối
        self._current_tag = None
        self._current_text = []
        self._in_body = False
        self._in_header = False
        self._header_tags = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
        self._skip_tags = {'style', 'script', 'head'}
        self._skip_depth = 0
        self._in_p = False
        self._attrs_stack = {}      # tag -> attrs (để lấy src của img trong <p>)

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return

        self._current_tag = tag
        attrs_dict = dict(attrs)

        if tag == 'body':
            self._in_body = True

        if tag in self._header_tags:
            self._in_header = True
            self._current_text = []

        if tag == 'p' and self._in_body:
            self._current_text = []
            self._in_p = True

        # Ảnh đứng độc lập hoặc bên trong <p>
        if tag == 'img' and self._in_body:
            src = attrs_dict.get('src', '')
            if src:
                # Flush text đang dang dở trước khi thêm ảnh
                if self._in_p and self._current_text:
                    text = ''.join(self._current_text).strip()
                    if text:
                        self.elements.append({'type': 'text', 'content': text})
                    self._current_text = []
                self.elements.append({'type': 'image', 'src': src})

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return

        if tag in self._header_tags and self._in_header:
            header_text = ''.join(self._current_text).strip()
            if header_text and self.title is None:
                self.title = header_text
            # Tiêu đề cũng là element text
            if header_text:
                self.elements.append({'type': 'text', 'content': header_text})
            self._in_header = False
            self._current_text = []

        if tag == 'p' and self._in_body:
            text = ''.join(self._current_text).strip()
            if text:
                self.elements.append({'type': 'text', 'content': text})
            self._current_text = []
            self._in_p = False

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if self._in_header or (self._in_body and self._current_tag in (
                'p', 'div', 'span', 'em', 'strong', 'b', 'i', 'a')):
            self._current_text.append(data)


# ============================================================
# EPUB UTILITIES
# ============================================================

def get_epub_toc(z):
    """Trích xuất TOC từ NCX. Trả về dict: href -> title."""
    toc = {}
    ncx_files = [n for n in z.namelist() if n.endswith('.ncx')]
    if not ncx_files:
        return toc
    ncx_content = z.read(ncx_files[0]).decode('utf-8')
    root = ET.fromstring(ncx_content)
    ns = {'ncx': 'http://www.daisy.org/z3986/2005/ncx/'}
    for np in root.findall('.//ncx:navPoint', ns):
        label = np.find('ncx:navLabel/ncx:text', ns)
        content_elem = np.find('ncx:content', ns)
        if label is not None and content_elem is not None:
            href = content_elem.get('src', '').split('#')[0]
            title = label.text.strip() if label.text else ''
            if title:
                toc[href] = title
    return toc


def get_epub_spine(z):
    """
    Trả về (opf_base, spine_hrefs, id_to_href_all).
    opf_base: thư mục chứa OPF (kết thúc bằng '/')
    spine_hrefs: list href theo thứ tự spine
    """
    opf_files = [n for n in z.namelist() if n.endswith('.opf')]
    if not opf_files:
        return '', [], {}
    opf_path = opf_files[0]
    opf_base = os.path.dirname(opf_path)
    if opf_base:
        opf_base += '/'
    opf_content = z.read(opf_path).decode('utf-8')
    root = ET.fromstring(opf_content)
    ns = {'opf': 'http://www.idpf.org/2007/opf'}

    # Manifest: id -> href
    manifest = root.find('.//opf:manifest', ns) or root.find('manifest')
    id_to_href = {}
    if manifest is not None:
        for item in manifest:
            item_id = item.get('id', '')
            href = item.get('href', '')
            media_type = item.get('media-type', '')
            if 'html' in media_type or href.endswith(('.html', '.xhtml')):
                id_to_href[item_id] = href

    # Spine order
    spine = root.find('.//opf:spine', ns) or root.find('spine')
    hrefs = []
    if spine is not None:
        for itemref in spine:
            idref = itemref.get('idref', '')
            if idref in id_to_href:
                hrefs.append(id_to_href[idref])
    return opf_base, hrefs, id_to_href


def resolve_img_path(z, opf_base, html_href, img_src):
    """
    Giải quyết đường dẫn ảnh tương đối trong EPUB.
    Trả về đường dẫn đầy đủ trong zip hoặc None nếu không tìm thấy.
    """
    html_dir = html_href.rsplit('/', 1)[0] + '/' if '/' in html_href else ''
    # Gộp đường dẫn và normalize
    combined = html_dir + img_src
    # Xử lý '../'
    parts = combined.split('/')
    resolved = []
    for p in parts:
        if p == '..':
            if resolved:
                resolved.pop()
        elif p != '.':
            resolved.append(p)
    img_href = '/'.join(resolved)

    candidates = [
        opf_base + img_href,
        img_href,
        opf_base + img_src,
        img_src,
    ]
    names = z.namelist()
    for c in candidates:
        if c in names:
            return c
    return None


def parse_epub_chapter(z, opf_base, html_href):
    """
    Parse một file HTML trong EPUB.
    Trả về (title, elements) với elements là list:
      {'type': 'text', 'content': str} hoặc
      {'type': 'image', 'src': str (đường dẫn zip)}
    """
    full_path = opf_base + html_href
    if full_path not in z.namelist():
        full_path = html_href
    if full_path not in z.namelist():
        return None, []

    try:
        content = z.read(full_path).decode('utf-8')
    except UnicodeDecodeError:
        content = z.read(full_path).decode('latin-1')

    parser = EpubHTMLParser()
    parser.feed(content)

    # Resolve image src thành đường dẫn thực trong zip
    resolved_elements = []
    for elem in parser.elements:
        if elem['type'] == 'image':
            zip_path = resolve_img_path(z, opf_base, html_href, elem['src'])
            resolved_elements.append({'type': 'image', 'zip_path': zip_path, 'src': elem['src']})
        else:
            resolved_elements.append(elem)

    return parser.title, resolved_elements


# ============================================================
# SEGMENT + TXT HELPERS
# ============================================================

CJK_PATTERN = re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]')
CHAPTER_PATTERN = re.compile(
    r'^(?:chapter|chap|chương)\s*\d{1,5}\b|^第\s*\d{1,5}\s*[章話话幕]|^제\s*\d{1,5}\s*[화장]',
    re.IGNORECASE,
)
SPECIAL_CHAPTER_PATTERN = re.compile(
    r'^(?:prologue|epilogue|interlude|foreword|lời\s+mở\s+đầu|lời\s+kết|序章|終章|终章|序幕|終幕|后记|後記|프롤로그|에필로그)\b',
    re.IGNORECASE,
)


def cjk_character_ratio(text):
    """Return the CJK/Hangul share of all non-whitespace characters."""
    compact = re.sub(r'\s+', '', text)
    if not compact:
        return 0.0
    return len(CJK_PATTERN.findall(compact)) / len(compact)


def uses_character_limit(text):
    """CJK/Hangul uses characters; space-delimited languages use words."""
    return cjk_character_ratio(text) >= 0.2


def unit_count(text, character_based):
    return len(re.sub(r'\s+', '', text)) if character_based else len(text.split())


def split_long_text(text, limit, character_based):
    if unit_count(text, character_based) <= limit:
        return [text]
    sentences = [part.strip() for part in re.split(r'(?<=[.!?。！？])\s*', text) if part.strip()]
    if len(sentences) == 1:
        if character_based:
            compact_parts = [text[index:index + limit] for index in range(0, len(text), limit)]
        else:
            words = text.split()
            compact_parts = [' '.join(words[index:index + limit]) for index in range(0, len(words), limit)]
        return compact_parts
    parts, current = [], ''
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and unit_count(candidate, character_based) > limit:
            parts.extend(split_long_text(current, limit, character_based) if unit_count(current, character_based) > limit else [current])
            current = sentence
        else:
            current = candidate
    if current:
        parts.extend(split_long_text(current, limit, character_based) if unit_count(current, character_based) > limit else [current])
    return parts


def segment_elements(elements, limit, character_based=None):
    all_text = '\n'.join(elem.get('content', '') for elem in elements if elem['type'] == 'text')
    if character_based is None:
        character_based = uses_character_limit(all_text)
    segments, current, current_size = [], [], 0
    for elem in elements:
        if elem['type'] == 'image':
            current.append(elem)
            continue
        for text_part in split_long_text(elem['content'], limit, character_based):
            part_size = unit_count(text_part, character_based)
            if current_size and current_size + part_size > limit:
                segments.append(current)
                current, current_size = [], 0
            current.append({'type': 'text', 'content': text_part})
            current_size += part_size
    if current:
        segments.append(current)
    return segments or [[]], ('characters' if character_based else 'words')


def write_document_segments(elements, title, vol_num, chap_index, raw_dir, img_dir, segment_limit, archive=None, character_based=None):
    segments, metric = segment_elements(elements, segment_limit, character_based)
    written = 0
    for seg_index, segment in enumerate(segments, 1):
        prefix = f"v{vol_num}_c{chap_index}_s{seg_index}"
        lines, image_count = [], 0
        for elem in segment:
            if elem['type'] == 'text':
                lines.append(elem['content'])
                continue
            src = elem.get('src', '')
            ext = src.rsplit('.', 1)[-1].lower() if '.' in src else 'jpg'
            ext = ext.split('?', 1)[0].split('#', 1)[0]
            if ext not in {'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'}:
                ext = 'jpg'
            image_count += 1
            image_id = f"{prefix}_img_{time.time_ns()}_{image_count:03d}"
            filename = f"{image_id}.{ext}"
            relative = f"../image/{filename}"
            zip_path = elem.get('zip_path')
            if archive is not None and zip_path:
                try:
                    with open(os.path.join(img_dir, filename), 'wb') as output:
                        output.write(archive.read(zip_path))
                except Exception as exc:
                    print(f"  [IMG] Lỗi lưu ảnh {filename}: {exc}")
                    relative += "  <!-- MISSING -->"
            elif archive is not None:
                relative += "  <!-- NOT FOUND -->"
            lines.append(f"![image:{image_id}]({relative})")

        filename = f"{prefix}.md"
        with open(os.path.join(raw_dir, filename), 'w', encoding='utf-8') as output:
            output.write(f"# {title}\n\n")
            for line in lines:
                output.write(line + "\n\n")
        written += 1
        print(f"[OK] {filename} ({unit_count(' '.join(lines), metric == 'characters')} {metric}, {image_count} ảnh)")
    return written, metric


def read_text_file(file_path):
    data = open(file_path, 'rb').read()
    encodings = ['utf-8-sig', 'utf-16', 'gb18030', 'big5']
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Không đọc được mã hóa TXT; hãy lưu file dưới dạng UTF-8")


def txt_documents(file_path):
    lines = read_text_file(file_path).splitlines()
    documents, title, content = [], None, []
    for raw_line in lines:
        line = re.sub(r'[\u200B\u200C\u200D\u2060\uFEFF]', '', raw_line).strip()
        if not line:
            continue
        if CHAPTER_PATTERN.match(line) or SPECIAL_CHAPTER_PATTERN.match(line):
            if title is not None or content:
                documents.append((title or f"Chương {len(documents) + 1}", content))
            title, content = line, []
        else:
            content.append({'type': 'text', 'content': line})
    if title is not None or content:
        documents.append((title or "Chương 1", content))
    return [(chapter_title, chapter_content) for chapter_title, chapter_content in documents if chapter_content]


def split_txt_to_md(file_path, vol_num, base_dir, project_dir=None, segment_limit=5000, return_details=False):
    output_root = project_dir or os.path.join(base_dir, 'truyen')
    raw_dir, img_dir = os.path.join(output_root, 'raw'), os.path.join(output_root, 'image')
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)
    documents = txt_documents(file_path)
    full_text = '\n'.join(
        elem.get('content', '')
        for _title, elements in documents
        for elem in elements
        if elem['type'] == 'text'
    )
    ratio = cjk_character_ratio(full_text)
    character_based = ratio >= 0.2
    metric_name = 'characters' if character_based else 'words'
    print(f"[METRIC] CJK/Hangul: {ratio:.1%} -> {metric_name} cho toàn bộ TXT")
    segment_count, metrics = 0, set()
    for chap_index, (title, elements) in enumerate(documents):
        written, metric = write_document_segments(
            elements, title, vol_num, chap_index, raw_dir, img_dir, segment_limit,
            character_based=character_based,
        )
        segment_count += written
        metrics.add(metric)
    result = {'chapters': len(documents), 'segments': segment_count, 'metrics': sorted(metrics)}
    print(f"[DONE] Đã tách TXT: {result}")
    return result if return_details else segment_count


# ============================================================
# CORE: TÁCH EPUB -> MD
# ============================================================

def split_epub_to_md(epub_path, vol_num, base_dir, project_dir=None, segment_limit=5000, return_details=False):
    """
    Tách EPUB thành các file .md trong base_dir/truyen/raw/
    Ảnh lưu vào base_dir/truyen/image/

    Tên file MD  : vx_cy_sz.md   (x=vol, y=chap_index, z=1)
    Tên file ảnh : vx_cy_sz_linet.ext (t = số dòng trong file md)

    Trả về số lượng chương đã xử lý.
    """
    output_root = project_dir or os.path.join(base_dir, 'truyen')
    raw_dir = os.path.join(output_root, 'raw')
    img_dir = os.path.join(output_root, 'image')
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)

    if not os.path.exists(epub_path):
        print(f"[LỖI] Không tìm thấy file: {epub_path}")
        return 0

    try:
        z = zipfile.ZipFile(epub_path, 'r')
    except zipfile.BadZipFile:
        print(f"[LỖI] File không phải EPUB hợp lệ: {epub_path}")
        return 0

    toc = get_epub_toc(z)
    print(f"[TOC] Tìm thấy {len(toc)} mục lục trong TOC")

    opf_base, spine_hrefs, _ = get_epub_spine(z)
    if not spine_hrefs:
        html_files = sorted([
            n for n in z.namelist()
            if n.endswith(('.html', '.xhtml')) and 'META-INF' not in n
        ])
        # Tạo href tương đối (bỏ opf_base)
        html_hrefs = [
            f[len(opf_base):] if f.startswith(opf_base) else f
            for f in html_files
        ]
    else:
        html_hrefs = spine_hrefs

    print(f"[INFO] Tìm thấy {len(html_hrefs)} file chương trong spine")

    # EPUB thương mại thường đặt tranh minh họa trong một XHTML riêng.
    # Gộp trang chỉ có ảnh vào tài liệu văn bản liền trước để giữ thứ tự spine
    # mà không tạo thêm một "chương" giả. Ảnh đầu sách được đưa vào tài liệu đầu.
    documents = []
    leading_images = []
    for href in html_hrefs:
        title, elements = parse_epub_chapter(z, opf_base, href)
        for elem in elements:
            if elem['type'] == 'text':
                elem['content'] = re.sub(
                    r'[\u200B\u200C\u200D\u2060\uFEFF]', '', elem['content']
                ).strip()
        elements = [
            elem for elem in elements
            if elem['type'] != 'text' or elem['content']
        ]

        # Bỏ qua nếu không có nội dung
        text_elements = [e for e in elements if e['type'] == 'text']
        if not text_elements:
            if documents:
                documents[-1][2].extend(elements)
            else:
                leading_images.extend(elements)
            continue
        if leading_images:
            elements = leading_images + elements
            leading_images = []
        documents.append([href, title, elements])

    chapter_count = 0
    segment_count = 0
    metrics = set()
    chap_index = 0  # 0-based chapter index (y)

    full_text = '\n'.join(
        elem.get('content', '')
        for _href, _title, elements in documents
        for elem in elements
        if elem['type'] == 'text'
    )
    ratio = cjk_character_ratio(full_text)
    character_based = ratio >= 0.2
    metric_name = 'characters' if character_based else 'words'
    print(f"[METRIC] CJK/Hangul: {ratio:.1%} -> {metric_name} cho toàn bộ EPUB")

    for href, title, elements in documents:
        text_elements = [e for e in elements if e['type'] == 'text']

        # Nếu không có title từ h1, fallback sang TOC
        if not title:
            for toc_href, toc_title in toc.items():
                if href.endswith(toc_href) or toc_href in href or href.endswith(os.path.basename(toc_href)):
                    title = toc_title
                    break
        if not title:
            title = f"Chương {chap_index + 1}"

        written, metric = write_document_segments(
            elements, title, vol_num, chap_index, raw_dir, img_dir, segment_limit,
            archive=z, character_based=character_based,
        )
        segment_count += written
        metrics.add(metric)

        chapter_count += 1
        chap_index += 1

    z.close()
    print(f"\n[DONE] Đã tách {chapter_count} chương -> {raw_dir}")
    print(f"[DONE] Ảnh lưu tại: {img_dir}")
    result = {'chapters': chapter_count, 'segments': segment_count, 'metrics': sorted(metrics)}
    return result if return_details else segment_count


# ============================================================
# MAIN
# ============================================================

def main():
    import tkinter as tk
    from tkinter import filedialog

    print("--- TÁCH EPUB THÀNH FILE MD (NOVELPIA) ---")
    print("(Nhấn Enter để sử dụng giá trị mặc định)\n")

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    # Chọn file EPUB
    print("Đang mở hộp thoại chọn file EPUB...")
    input_file = filedialog.askopenfilename(
        title="Chọn file EPUB (Novelpia)",
        filetypes=[("EPUB files", "*.epub"), ("All files", "*.*")]
    )
    if not input_file:
        print("[INFO] Đã hủy. Thoát.")
        return
    if not input_file.lower().endswith('.epub'):
        print("[LỖI] File phải có đuôi .epub!")
        return
    if not os.path.exists(input_file):
        print(f"[LỖI] Không tìm thấy file: {input_file}")
        return

    print(f"File đã chọn: {input_file}")

    # Số volume (x trong vx_cy_sz)
    vol_str = input("Nhập số volume (mặc định: 1): ").strip() or "1"
    try:
        vol_num = int(vol_str)
    except ValueError:
        print("[LỖI] Số volume không hợp lệ!")
        return

    # Thư mục gốc (nơi chứa truyen/raw và truyen/image)
    # Mặc định = thư mục chứa script này
    default_base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    print(f"Thư mục gốc mặc định: {default_base}")
    use_dialog = input("Chọn thư mục gốc khác? (y/n) [n]: ").strip().lower() == 'y'
    base_dir = default_base
    if use_dialog:
        selected = filedialog.askdirectory(title="Chọn thư mục gốc", initialdir=default_base)
        if selected:
            base_dir = selected
            print(f"Thư mục gốc đã chọn: {base_dir}")
        else:
            print(f"[INFO] Dùng mặc định: {default_base}")

    # Xác nhận
    raw_dir = os.path.join(base_dir, 'truyen', 'raw')
    img_dir = os.path.join(base_dir, 'truyen', 'image')
    print(f"\nXác nhận:")
    print(f"  EPUB     : {input_file}")
    print(f"  Volume   : {vol_num}")
    print(f"  MD output: {raw_dir}")
    print(f"  IMG out  : {img_dir}")
    confirm = input("\nTiếp tục? (y/n) [y]: ").strip().lower() or 'y'
    if confirm != 'y':
        print("Hủy!")
        return

    split_epub_to_md(input_file, vol_num, base_dir)


if __name__ == "__main__":
    main()
