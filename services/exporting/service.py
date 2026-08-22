"""Select project chapters and prepare them for book exporters."""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.exporting.book import build_export


@dataclass(frozen=True)
class BookExportService:
    library: object

    def export(self, project_name: str, options: dict):
        export_format = str(options.get("format", "epub")).lower()
        if export_format not in {"epub", "docx", "markdown"}:
            raise ValueError("Định dạng xuất không được hỗ trợ")
        sections = self.sections(project_name, options)
        return build_export(project_name, sections, export_format)

    def sections(self, project_name: str, options: dict):
        items, source = self._selected_chapters(project_name, options)
        project_path = self.library.safe_project(project_name)
        sections = []
        for item in items:
            title = item["title"] or item["id"]
            if source == "bilingual":
                body = "### Bản gốc\n\n" + self._body(item["raw_text"])
                body += "\n\n### Bản dịch\n\n" + self._body(item["translated_text"])
            else:
                body = self._body(item[f"{source}_text"])
            sections.append(
                {
                    "title": title,
                    "body": body,
                    "name": item["name"],
                    "project_path": project_path,
                }
            )
        return sections

    def _selected_chapters(self, project_name: str, options: dict):
        items = self.library.chapters(project_name)
        scope = str(options.get("scope", "all"))
        if scope == "volume":
            volume = int(options.get("volume", 0))
            items = [
                item
                for item in items
                if re.match(rf"^v{volume}_", item["name"], re.IGNORECASE)
            ]
        elif scope == "range":
            items = self._chapter_range(items, options)
        elif scope != "all":
            raise ValueError("Phạm vi xuất không hợp lệ")
        if not items:
            raise ValueError("Không có chương nào trong phạm vi đã chọn")

        raw_dir, translated_dir = self.library.project_folders(project_name)
        source = str(options.get("source", "translated"))
        if source not in {"translated", "raw", "bilingual"}:
            raise ValueError("Nguồn nội dung không hợp lệ")
        selected = []
        for item in items:
            raw_path = self.library.safe_file(raw_dir, item["name"])
            translated_path = self.library.safe_file(translated_dir, item["name"])
            raw_text = self.library.read_text(raw_path) if raw_path.exists() else ""
            translated_text = (
                self.library.read_text(translated_path)
                if translated_path.exists()
                else ""
            )
            if source == "translated" and not translated_text:
                continue
            if source == "raw" and not raw_text:
                continue
            selected.append(
                {**item, "raw_text": raw_text, "translated_text": translated_text}
            )
        if not selected:
            label = "bản dịch" if source == "translated" else "bản gốc"
            raise ValueError(f"Không tìm thấy {label} trong phạm vi đã chọn")
        return selected, source

    @staticmethod
    def _chapter_range(items: list[dict], options: dict):
        names = [item["name"] for item in items]
        start = str(options.get("from", ""))
        end = str(options.get("to", ""))
        if start not in names or end not in names:
            raise ValueError("Phạm vi chương không hợp lệ")
        first, last = names.index(start), names.index(end)
        if first > last:
            first, last = last, first
        return items[first : last + 1]

    @staticmethod
    def _body(text: str) -> str:
        lines = text.replace("\r\n", "\n").split("\n")
        for index, line in enumerate(lines):
            if line.strip():
                if re.match(r"^\s*#{1,6}\s+", line):
                    lines.pop(index)
                break
        return "\n".join(lines).strip()
