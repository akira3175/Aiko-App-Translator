import re
import yaml
import os
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
import tkinter as tk
from tkinter import filedialog

class CustomDumper(yaml.Dumper):
    def represent_scalar(self, tag, value, style=None):
        if tag == 'tag:yaml.org,2002:str' and "\n" in value:
            style = '|'
        return super().represent_scalar(tag, value, style)

# Hàm riêng để xử lý chuỗi đa dòng
def represent_multiline_string(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


class EpubHTMLParser(HTMLParser):
    """Parser HTML trích xuất tiêu đề và nội dung text từ file EPUB."""
    def __init__(self):
        super().__init__()
        self.title = None
        self.paragraphs = []
        self._current_tag = None
        self._current_text = []
        self._in_body = False
        self._in_header = False
        self._header_tags = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
        self._skip_tags = {'style', 'script', 'head'}
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        self._current_tag = tag
        if tag == 'body':
            self._in_body = True
        if tag in self._header_tags:
            self._in_header = True
            self._current_text = []
        if tag == 'p' and self._in_body:
            self._current_text = []

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
            self._in_header = False
            self._current_text = []
        if tag == 'p' and self._in_body:
            text = ''.join(self._current_text).strip()
            if text:
                self.paragraphs.append(text)
            self._current_text = []
        if tag == 'br' and self._in_body:
            text = ''.join(self._current_text).strip()
            if text:
                self.paragraphs.append(text)
            self._current_text = []

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if self._in_header or (self._in_body and self._current_tag in ('p', 'div', 'span', 'em', 'strong', 'b', 'i', 'a')):
            self._current_text.append(data)


def get_output_filename(input_file, user_output, output_format, output_dir):
    """Xác định tên file đầu ra với logic thông minh tránh trùng lặp suffix."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    if not user_output.strip():
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        similar_suffixes = ['_split', '_seg', '_segment', '_chapter', '_divided']
        has_similar_suffix = any(base_name.endswith(suffix) for suffix in similar_suffixes)

        if has_similar_suffix:
            return os.path.join(output_dir, f"{base_name}.{output_format}")
        else:
            return os.path.join(output_dir, f"{base_name}_split.{output_format}")

    if os.path.dirname(user_output):
        if not user_output.endswith(f'.{output_format}'):
            return f"{user_output}.{output_format}"
        return user_output

    if not user_output.endswith(f'.{output_format}'):
        return os.path.join(output_dir, f"{user_output}.{output_format}")
    return os.path.join(output_dir, user_output)


def get_epub_toc(z):
    """Trích xuất TOC từ tệp NCX trong EPUB. Trả về dict: href -> title."""
    toc = {}
    ncx_files = [n for n in z.namelist() if n.endswith('.ncx')]
    if not ncx_files:
        return toc

    ncx_content = z.read(ncx_files[0]).decode('utf-8')
    root = ET.fromstring(ncx_content)
    ns = {'ncx': 'http://www.daisy.org/z3986/2005/ncx/'}
    nav_points = root.findall('.//ncx:navPoint', ns)

    for np in nav_points:
        label = np.find('ncx:navLabel/ncx:text', ns)
        content_elem = np.find('ncx:content', ns)
        if label is not None and content_elem is not None:
            href = content_elem.get('src', '')
            # Bỏ phần fragment (#...) nếu có
            href = href.split('#')[0]
            title = label.text.strip() if label.text else ''
            if title:
                toc[href] = title

    return toc


def get_epub_spine_order(z):
    """Lấy thứ tự spine từ OPF. Trả về danh sách href theo thứ tự đọc."""
    opf_files = [n for n in z.namelist() if n.endswith('.opf')]
    if not opf_files:
        return []

    opf_content = z.read(opf_files[0]).decode('utf-8')
    root = ET.fromstring(opf_content)
    ns = {'opf': 'http://www.idpf.org/2007/opf'}

    # Build id -> href mapping from manifest
    manifest = root.find('.//opf:manifest', ns)
    if manifest is None:
        # Try without namespace
        manifest = root.find('manifest')
    
    id_to_href = {}
    if manifest is not None:
        for item in manifest:
            item_id = item.get('id', '')
            href = item.get('href', '')
            media_type = item.get('media-type', '')
            if 'html' in media_type or href.endswith(('.html', '.xhtml')):
                id_to_href[item_id] = href

    # Get spine order
    spine = root.find('.//opf:spine', ns)
    if spine is None:
        spine = root.find('spine')
    
    ordered_hrefs = []
    if spine is not None:
        for itemref in spine:
            idref = itemref.get('idref', '')
            if idref in id_to_href:
                ordered_hrefs.append(id_to_href[idref])

    return ordered_hrefs


def parse_epub_chapter(z, file_path):
    """Đọc và parse một file HTML trong EPUB. Trả về (title, content_text)."""
    try:
        content = z.read(file_path).decode('utf-8')
    except (KeyError, UnicodeDecodeError):
        return None, ""

    parser = EpubHTMLParser()
    parser.feed(content)

    title = parser.title
    # Nối các đoạn văn bằng dòng trống
    content_text = "\n\n".join(parser.paragraphs)

    return title, content_text


def split_epub_content(epub_path):
    """Tách file EPUB thành các chương dựa trên cấu trúc nội bộ.
    Mỗi file HTML trong EPUB = 1 chương.
    Title lấy từ <h1> trong file hoặc từ TOC (NCX).
    
    Trả về: list of (section_id, section_lines, chapter_title, chapter_number)
    """
    if not os.path.exists(epub_path):
        print(f"[LOI] Khong tim thay file: {epub_path}")
        return []

    try:
        z = zipfile.ZipFile(epub_path, 'r')
    except zipfile.BadZipFile:
        print(f"[LOI] File khong phai EPUB hop le: {epub_path}")
        return []

    # Lấy TOC từ NCX
    toc = get_epub_toc(z)
    print(f"[TOC] Tim thay {len(toc)} muc luc trong TOC")

    # Lấy thứ tự spine
    spine_hrefs = get_epub_spine_order(z)
    
    # Nếu không có spine, fallback sang tìm tất cả HTML files
    if not spine_hrefs:
        html_files = sorted([
            n for n in z.namelist()
            if n.endswith(('.html', '.xhtml')) and 'META-INF' not in n
        ])
    else:
        # Xác định base path từ OPF
        opf_files = [n for n in z.namelist() if n.endswith('.opf')]
        base_path = ''
        if opf_files:
            base_path = os.path.dirname(opf_files[0])
            if base_path:
                base_path += '/'
        
        html_files = []
        for href in spine_hrefs:
            full_path = base_path + href
            if full_path in z.namelist():
                html_files.append(full_path)
            elif href in z.namelist():
                html_files.append(href)

    print(f"[INFO] Tim thay {len(html_files)} file chuong")

    sections = []
    chapter_counter = 0

    for file_path in html_files:
        title, content_text = parse_epub_chapter(z, file_path)
        
        if not content_text.strip():
            continue

        # Xác định title: ưu tiên <h1> trong file, fallback sang TOC
        if not title:
            # Tìm trong TOC bằng cách so sánh href
            for toc_href, toc_title in toc.items():
                if file_path.endswith(toc_href) or toc_href in file_path:
                    title = toc_title
                    break

        if not title:
            title = f"Chương {chapter_counter + 1}"

        chapter_counter += 1
        section_id = f"Volume_0_Chapter_{chapter_counter - 1}_Segment_{chapter_counter}"

        # section_lines: dòng đầu là title, còn lại là nội dung
        content_lines = [line for line in content_text.split('\n') if line.strip()]
        section_lines = [title] + content_lines

        sections.append((section_id, section_lines, title, chapter_counter))

    z.close()

    # Lọc bỏ section chỉ có title
    sections = [s for s in sections if len(s[1]) > 1]

    print(f"[OK] Tach thanh cong {len(sections)} chuong")
    return sections


def output_to_yaml_simple_segments(sections, output_file):
    """Xuất dữ liệu ra file YAML."""
    all_segments = []
    
    for section_id, section_lines, chapter_title, chapter_number in sections:
        content_lines = section_lines[1:]
        
        if not content_lines:
            continue
            
        content = "\n\n".join(content_lines)

        all_segments.append({
            "id": section_id,
            "title": chapter_title,
            "content": content
        })

    yaml.add_representer(str, represent_multiline_string, Dumper=CustomDumper)
    
    with open(output_file, 'w', encoding='utf-8') as yaml_file:
        yaml.dump(
            all_segments,
            yaml_file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            Dumper=CustomDumper
        )


def output_to_txt_simple_segments(sections, output_file):
    """Xuất dữ liệu ra file TXT."""
    with open(output_file, 'w', encoding='utf-8') as out_file:
        for section_id, section_lines, chapter_title, chapter_number in sections:
            content_lines = section_lines[1:]
            
            if not content_lines:
                continue
            
            out_file.write(f"{section_id}\n")
            out_file.write(f"{chapter_title}\n")
            for content_line in content_lines:
                out_file.write(f"{content_line}\n\n")
            out_file.write("\n")


def split_and_output(epub_path, output_path, output_format):
    """Tách EPUB và xuất ra file."""
    sections = split_epub_content(epub_path)

    if not sections:
        print("[LOI] Khong tim thay chuong nao trong EPUB!")
        return

    if output_format == "txt":
        output_to_txt_simple_segments(sections, output_path)
    else:
        output_to_yaml_simple_segments(sections, output_path)

    print(f"\n[DONE] Hoan thanh! Ket qua da duoc luu tai: {os.path.abspath(output_path)}")


def main():
    print("--- CHƯƠNG TRÌNH TÁCH CHƯƠNG EPUB (NOVELPIA) ---")
    print("(Nhấn Enter để sử dụng giá trị mặc định)\n")
    
    # Khởi tạo tkinter và ẩn cửa sổ chính
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True) # Đưa dialog lên trên cùng

    # Chọn file EPUB qua dialog
    print("Đang mở hộp thoại chọn file...")
    input_file = filedialog.askopenfilename(
        title="Chọn file EPUB (Novelpia)",
        filetypes=[("EPUB files", "*.epub"), ("All files", "*.*")]
    )

    if not input_file:
        print("[INFO] Đã hủy chọn file. Thoát chương trình.")
        return

    if not input_file.lower().endswith('.epub'):
        print("[LOI] File phải có đuôi .epub!")
        return

    if not os.path.exists(input_file):
        print(f"[LOI] Không tìm thấy file: {input_file}")
        return

    print(f"File đã chọn: {input_file}")

    print("\nChọn định dạng đầu ra:")
    print("1 - TXT")
    print("2 - YAML")
    format_choice = input("Nhập lựa chọn (1 hoặc 2) [2]: ").strip() or "2"
    output_format = "txt" if format_choice == "1" else "yaml"
    
    user_output = input("Nhập tên file đầu ra (để trống sẽ tự tạo): ").strip()
    
    default_output_dir = os.path.abspath("test/data/API_content")
    print(f"\nThư mục lưu trữ mặc định: {default_output_dir}")
    use_dialog_dir = input("Bạn có muốn chọn thư mục lưu trữ khác qua cửa sổ? (y/n) [n]: ").strip().lower() == 'y'
    
    output_dir = default_output_dir
    if use_dialog_dir:
        print("Đang mở hộp thoại chọn thư mục...")
        selected_dir = filedialog.askdirectory(title="Chọn thư mục lưu trữ kết quả", initialdir=default_output_dir)
        if selected_dir:
            output_dir = selected_dir
            print(f"Thư mục đã chọn: {output_dir}")
        else:
            print(f"[INFO] Đã hủy chọn thư mục. Sử dụng mặc định: {default_output_dir}")
    
    output_path = get_output_filename(input_file, user_output, output_format, output_dir)
    
    # Xác nhận
    print(f"\nXác nhận:")
    print(f"- Input EPUB: {input_file}")
    print(f"- File đầu ra: {output_path}")
    print(f"- Thư mục lưu trữ: {os.path.dirname(output_path)}")
    print(f"- Định dạng: {output_format.upper()}")
    
    confirm = input("\nTiếp tục? (y/n) [y]: ").strip().lower() or "y"

    if confirm != 'y':
        print("Hủy thao tác!")
        return

    split_and_output(input_file, output_path, output_format)


if __name__ == "__main__":
    main()