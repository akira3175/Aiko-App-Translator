"""Localize BBCode images before publishing through the existing R2 transport."""

import hashlib
import html
import io
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image

IMAGE_TAG = re.compile(r'\[img(?:\s*=\s*\d+\s*,\s*\d+)?\]\s*(.*?)\s*\[/img\]', re.I | re.S)
MAX_IMAGE_BYTES = 25 * 1024 * 1024


def download_image(value, directory):
    url = html.unescape(value).replace('\\:', ':').replace('\\/', '/').strip()
    url = re.sub(r'\\([\[\]()])', r'\1', url)
    markdown_link = re.fullmatch(r'\[[^\r\n]*\]\((.*)\)', url)
    if markdown_link:
        url = markdown_link.group(1).strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('Link ảnh phải là HTTP hoặc HTTPS.')
    directory = Path(directory)
    name = 'remote_' + hashlib.sha256(url.encode()).hexdigest()
    for extension in ('jpg', 'png', 'gif', 'webp'):
        cached = directory / f'{name}.{extension}'
        if cached.is_file():
            return str(cached.resolve())
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://book.sfacg.com/' if parsed.hostname.endswith('.sfacg.com') else f'{parsed.scheme}://{parsed.netloc}/'})
    with urlopen(request, timeout=30) as response:
        data = response.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Ảnh vượt quá 25 MB.')
    with Image.open(io.BytesIO(data)) as image:
        extension = {'JPEG': 'jpg', 'PNG': 'png', 'GIF': 'gif', 'WEBP': 'webp'}.get(image.format)
        image.verify()
    if not extension:
        raise ValueError('Định dạng ảnh không hỗ trợ.')
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f'{name}.{extension}'
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(destination)
    return str(destination.resolve())


def localize_bbcode_images(elements, directory):
    result = []
    for element in elements:
        if element['type'] != 'text':
            result.append(element)
            continue
        content = element['content']
        cursor = 0
        for match in IMAGE_TAG.finditer(content):
            if content[cursor:match.start()].strip():
                result.append({'type': 'text', 'content': content[cursor:match.start()]})
            try:
                path = download_image(match.group(1), directory)
            except Exception as error:
                raise RuntimeError(f"Không tải được ảnh để xuất bản: {match.group(1)} ({error})") from error
            result.append({'type': 'image', 'content': f'![image]({path})'})
            cursor = match.end()
        if cursor == 0:
            result.append(element)
        elif content[cursor:].strip():
            result.append({'type': 'text', 'content': content[cursor:]})
    return result
