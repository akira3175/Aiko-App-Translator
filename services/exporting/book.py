"""Build Markdown, DOCX and EPUB books from prepared chapter sections."""

from __future__ import annotations

import html
import io
import mimetypes
import re
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps


def _plain_markdown(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", lambda m: f"[Hình ảnh: {m.group(1) or 'minh họa'}]", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    return re.sub(r"(?<!\\)[*_~`]", "", text)


def _blocks(section: dict):
    image_re = re.compile(r"!\[([^\]]*)\]\((?:\.\./)?image/([\w.-]+)\)")
    blocks, cursor = [], 0
    for match in image_re.finditer(section["body"]):
        text = section["body"][cursor:match.start()]
        for paragraph in re.split(r"\n\s*\n", _plain_markdown(text)):
            value = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
            if value:
                blocks.append(("text", value))
        image_path = (section["project_path"] / "image" / match.group(2)).resolve()
        if image_path.parent == (section["project_path"] / "image").resolve() and image_path.exists():
            blocks.append(("image", image_path, match.group(1)))
        cursor = match.end()
    for paragraph in re.split(r"\n\s*\n", _plain_markdown(section["body"][cursor:])):
        value = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        if value:
            blocks.append(("text", value))
    return blocks


def _without_leading_title(body: str, title: str) -> str:
    def normalized(value: str) -> str:
        value = unicodedata.normalize("NFKC", value or "")
        value = re.sub(r"^\s*#{1,6}\s*", "", value)
        return " ".join(value.split()).casefold()

    lines = body.splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is not None and normalized(lines[first]) == normalized(title):
        lines.pop(first)
    return "\n".join(lines).strip()


def _image_asset(path: Path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        width, height = image.size
        extension = path.suffix.lower()
        if extension in {".jpg", ".jpeg", ".png"}:
            return path.read_bytes(), extension, mimetypes.guess_type(path.name)[0], width, height
        output = io.BytesIO()
        if "A" in image.getbands():
            image.save(output, format="PNG")
            return output.getvalue(), ".png", "image/png", width, height
        image.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue(), ".jpg", "image/jpeg", width, height


def _paragraph(text: str, style: str | None = None, page_break=False):
    properties = []
    if style:
        properties.append(f'<w:pStyle w:val="{style}"/>')
    if page_break:
        properties.append('<w:pageBreakBefore/>')
    ppr = f"<w:pPr>{''.join(properties)}</w:pPr>" if properties else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{html.escape(text)}</w:t></w:r></w:p>'


def _image_paragraph(rid: str, name: str, width: int, height: int, drawing_id: int):
    scale = min(5257800 / max(width, 1), 6858000 / max(height, 1))
    cx, cy = max(1, round(width * scale)), max(1, round(height * scale))
    name = html.escape(name)
    return f'''<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="120" w:after="160"/></w:pPr><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{drawing_id}" name="{name}"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr><pic:cNvPr id="{drawing_id}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'''


def _docx(project_name: str, sections: list[dict]) -> bytes:
    paragraphs, images = [_paragraph(project_name, "Title")], []
    for section in sections:
        paragraphs.append(_paragraph(section["title"], "Heading1", page_break=True))
        for block in _blocks(section):
            if block[0] == "text":
                paragraphs.append(_paragraph(block[1]))
                continue
            rid = f"rId{len(images) + 2}"
            data, extension, mime_type, width, height = _image_asset(block[1])
            target = f"media/image{len(images) + 1}{extension}"
            images.append((rid, target, data, mime_type))
            paragraphs.append(_image_paragraph(rid, block[1].name, width, height, len(images)))
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>' + "".join(paragraphs) + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1134" w:right="1276" w:bottom="1134" w:left="1276"/></w:sectPr></w:body></w:document>'
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos" w:eastAsia="Yu Mincho"/><w:sz w:val="22"/><w:lang w:val="vi-VN"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="330" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="360"/><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="44"/><w:szCs w:val="44"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="0" w:after="300"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="177E68"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style></w:styles>'''
    extensions = {Path(target).suffix.lower().lstrip(".") for _, target, _, _ in images}
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
    defaults = "".join(f'<Default Extension="{ext}" ContentType="{mime_map.get(ext, f"image/{ext}")}"/>' for ext in sorted(extensions))
    content_types = f'''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>{defaults}<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
    image_rels = "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{target}"/>' for rid, target, _data, _mime in images)
    doc_rels = f'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>{image_rels}</Relationships>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/_rels/document.xml.rels", doc_rels)
        for _rid, target, data, _mime in images:
            archive.writestr(f"word/{target}", data)
    return output.getvalue()


def _epub(project_name: str, sections: list[dict]) -> bytes:
    chapter_files, nav_items, manifest, spine, images = [], [], [], [], {}
    css = "body{font-family:serif;line-height:1.65;margin:5%;}h2{font-size:1.1em;}p{text-align:justify;margin:.65em 0;}figure{margin:1em 0;text-align:center;}img{max-width:100%;height:auto;}"
    for index, section in enumerate(sections, 1):
        blocks = []
        epub_section = {**section, "body": _without_leading_title(section["body"], section["title"])}
        for block in _blocks(epub_section):
            if block[0] == "text":
                blocks.append(f"<p>{html.escape(block[1])}</p>")
            else:
                key = str(block[1])
                if key not in images:
                    data, extension, mime_type, _width, _height = _image_asset(block[1])
                    images[key] = (f"images/image-{len(images)+1}{extension}", data, mime_type)
                href, _data, _mime = images[key]
                blocks.append(f'<figure><img src="{html.escape(href)}" alt="{html.escape(block[2])}"/></figure>')
        filename = f"chapter-{index}.xhtml"
        page = f'''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="vi"><head><title>{html.escape(section['title'])}</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body>{''.join(blocks)}</body></html>'''
        chapter_files.append((filename, page))
        nav_items.append(f'<li><a href="{filename}">{html.escape(section["title"])}</a></li>')
        manifest.append(f'<item id="c{index}" href="{filename}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{index}"/>')
    nav = f'''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Mục lục</title></head><body><nav epub:type="toc"><h1>Mục lục</h1><ol>{''.join(nav_items)}</ol></nav></body></html>'''
    image_manifest = "".join(f'<item id="img{i}" href="{href}" media-type="{mime}"/>' for i, (href, _data, mime) in enumerate(images.values(), 1))
    opf = f'''<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">urn:uuid:{uuid.uuid4()}</dc:identifier><dc:title>{html.escape(project_name)}</dc:title><dc:language>vi</dc:language><meta property="dcterms:modified">{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}</meta></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="css" href="style.css" media-type="text/css"/>{''.join(manifest)}{image_manifest}</manifest><spine>{''.join(spine)}</spine></package>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>', compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/style.css", css, compress_type=zipfile.ZIP_DEFLATED)
        for filename, page in chapter_files:
            archive.writestr(f"OEBPS/{filename}", page, compress_type=zipfile.ZIP_DEFLATED)
        for href, data, _mime in images.values():
            archive.writestr(f"OEBPS/{href}", data, compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()


def build_export(project_name: str, sections: list[dict], export_format: str):
    safe_name = re.sub(r"[^\w.-]+", "-", project_name, flags=re.UNICODE).strip("-.") or "truyen"
    if export_format == "markdown":
        content = f"# {project_name}\n\n" + "\n\n".join(f"## {item['title']}\n\n{item['body']}" for item in sections)
        return content.encode("utf-8"), "text/markdown; charset=utf-8", f"{safe_name}.md"
    if export_format == "docx":
        return _docx(project_name, sections), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"{safe_name}.docx"
    if export_format == "epub":
        return _epub(project_name, sections), "application/epub+zip", f"{safe_name}.epub"
    raise ValueError("Định dạng xuất không được hỗ trợ")
