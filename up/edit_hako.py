"""Update existing Hako chapters from the active App Translator project."""

import asyncio
import json
import os
import re
import sys

from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cores.runtime_config import option, stop_requested
from up import up_md


EDIT_URL = "https://docln.sbs/action/chapter/{chapter_id}/edit"


def normalized_title(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def edit_targets():
    raw = option("hako_edit_targets", [])
    if not isinstance(raw, list) or not raw or len(raw) > 50:
        raise RuntimeError("Danh sách chương Hako cần cập nhật không hợp lệ")
    targets = []
    seen = set()
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise RuntimeError(f"Mapping Hako dòng {index} không hợp lệ")
        local_name = str(item.get("local_name", "")).strip()
        chapter_id = str(item.get("chapter_id", "")).strip()
        remote_title = str(item.get("remote_title", "")).strip()
        if not re.fullmatch(r"v\d+_c\d+_s\d+\.md", local_name):
            raise RuntimeError(f"Tên chương local dòng {index} không hợp lệ")
        if not chapter_id.isdigit() or not remote_title:
            raise RuntimeError(f"Chương Hako dòng {index} chưa được đối chiếu")
        if chapter_id in seen:
            raise RuntimeError(f"Chapter ID {chapter_id} bị chọn trùng")
        seen.add(chapter_id)
        targets.append((local_name, chapter_id, remote_title))
    return targets


def grouped_local_chapters():
    files = up_md.scan_translated_dir()
    grouped = {}
    for (volume, chapter), segments in up_md.group_segments_into_chapters(files):
        grouped[os.path.basename(segments[0][1])] = ((volume, chapter), segments)
    return grouped


async def update_chapter(page, local_name, chapter_id, expected_title, chapter_data, selectors):
    chapter_key, segments = chapter_data
    all_elements, local_title = [], ""
    for segment_index, (_segment_number, filepath) in enumerate(segments):
        parsed = up_md.parse_md_file(filepath)
        if segment_index == 0:
            local_title = parsed["title"]
        elif parsed["title"]:
            all_elements.append({"type": "text", "content": f"## {parsed['title']}"})
        all_elements.extend(parsed["elements"])
    if not local_title or not all_elements:
        raise RuntimeError(f"{local_name}: tiêu đề hoặc nội dung local đang trống")

    edit_url = EDIT_URL.format(chapter_id=chapter_id)
    print(f"Đang kiểm tra {local_name} ↔ {expected_title} (ID {chapter_id})")
    await page.goto(edit_url)
    await page.wait_for_load_state("networkidle")
    if "/login" in page.url:
        raise RuntimeError("Phiên đăng nhập Hako đã hết hạn")

    title_locator = page.locator(selectors["title"]).first
    editor_locator = page.locator(selectors["editor_body"]).first
    await title_locator.wait_for(state="visible", timeout=30000)
    await editor_locator.wait_for(state="visible", timeout=60000)
    actual_title = await title_locator.input_value()
    if normalized_title(actual_title) != normalized_title(expected_title):
        raise RuntimeError(
            f"Dừng để tránh ghi đè nhầm: Hako hiện là “{actual_title}”, "
            f"không phải “{expected_title}”"
        )

    all_elements, note_contents = up_md.extract_hako_notes(all_elements)
    note_ids = []
    for note_content in note_contents:
        note_ids.append(await up_md.create_hako_note(page, up_md.note_text_to_html(note_content)))
    if note_ids:
        all_elements = up_md.insert_hako_note_ids(all_elements, note_ids)
    html_parts, image_count = up_md.elements_to_html_parts(all_elements, local_title)
    html_content = "".join(html_parts)
    if "[Lỗi tải ảnh]" in html_content or "[Không tìm thấy ảnh]" in html_content:
        raise RuntimeError(f"{local_name}: thiếu ảnh, chưa cập nhật Hako")

    await title_locator.fill(local_title)
    await editor_locator.click()
    await page.keyboard.press("Control+a")
    await editor_locator.evaluate("""(el, html) => {
        const transfer = new DataTransfer();
        transfer.setData('text/html', html);
        transfer.setData('text/plain', html.replace(/<[^>]+>/g, ''));
        el.dispatchEvent(new ClipboardEvent('paste', {
            clipboardData: transfer, bubbles: true, cancelable: true
        }));
    }""", html_content)
    submit = page.locator(selectors["submit_button"]).last
    await submit.wait_for(state="visible", timeout=20000)
    await submit.click()
    await page.wait_for_timeout(1500)
    if "/login" in page.url or await page.locator("text=500 Server Error").count():
        raise RuntimeError(f"{local_name}: Hako không xác nhận cập nhật")
    await page.goto(edit_url)
    await page.wait_for_load_state("networkidle")
    saved_title = await page.locator(selectors["title"]).first.input_value()
    if normalized_title(saved_title) != normalized_title(local_title):
        raise RuntimeError(f"{local_name}: đọc lại Hako không thấy tiêu đề vừa cập nhật")
    print(f"Đã cập nhật {local_name}: “{local_title}” ({image_count} ảnh)")


async def main():
    targets = edit_targets()
    local = grouped_local_chapters()
    missing = [name for name, _chapter_id, _title in targets if name not in local]
    if missing:
        raise RuntimeError("Không tìm thấy chương local: " + ", ".join(missing))
    username = str(option("hako_username", "")).strip()
    password = str(option("hako_password", ""))
    if not username or not password:
        raise RuntimeError("Chưa nhập tài khoản Hako trong Cài đặt > Xuất bản")
    selectors = {
        "title": "input[name='title']",
        "editor_body": ".tiptap.ProseMirror, .ProseMirror[contenteditable='true']",
        "submit_button": "button[type='submit']",
    }
    print(f"Chuẩn bị cập nhật {len(targets)} chương Hako")
    async with async_playwright() as playwright:
        launch = {"headless": False, "args": ["--disable-blink-features=AutomationControlled"]}
        if os.path.isfile(up_md.PORTABLE_CHROME):
            launch["executable_path"] = up_md.PORTABLE_CHROME
        else:
            launch["channel"] = "chrome"
        browser = await playwright.chromium.launch(**launch)
        context = await browser.new_context()
        page = await context.new_page()
        await up_md.stealth_async(page)
        await page.goto("https://docln.sbs/login")
        await page.locator("#name").fill(username)
        await page.locator("#password").fill(password)
        print("Hãy giải reCAPTCHA và đăng nhập trên cửa sổ Chrome (tối đa 5 phút)")
        for _ in range(300):
            if "/login" not in page.url and await page.locator("#name").count() == 0:
                break
            await page.wait_for_timeout(1000)
        else:
            raise RuntimeError("Hết thời gian chờ đăng nhập Hako")
        for index, (local_name, chapter_id, title) in enumerate(targets, 1):
            if stop_requested():
                print("Đã dừng trước chương tiếp theo")
                break
            print(f"[{index}/{len(targets)}]")
            await update_chapter(page, local_name, chapter_id, title, local[local_name], selectors)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
