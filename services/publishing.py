"""Publishing configuration, Hako lookup, and Cloudflare provisioning."""

import html
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cores.storage.project import load_json, save_json


class PublishingService:
    def __init__(
        self,
        *,
        root,
        safe_project,
        configuration,
        provision_share_worker,
        provision_publishing_r2,
        opener=urlopen,
    ):
        self.root = root
        self._safe_project = safe_project
        self.configuration = configuration
        self._provision_share_worker = provision_share_worker
        self._provision_publishing_r2 = provision_publishing_r2
        self._opener = opener

    def data(self, project_name):
        path = self._safe_project(project_name) / "publishing.json"
        data = load_json(path, {})
        hako = data.get("hako", {}) if isinstance(data, dict) else {}
        books = hako.get("books", []) if isinstance(hako, dict) else []
        normalized = []
        if isinstance(books, list):
            for book in books:
                if not isinstance(book, dict):
                    continue
                start = book.get("volume", book.get("from_volume"))
                end = book.get("volume", book.get("to_volume", start))
                try:
                    start, end = int(start), int(end)
                except (TypeError, ValueError):
                    continue
                for volume in range(start, end + 1):
                    normalized.append(
                        {
                            "label": str(book.get("label", "")).strip(),
                            "book_id": str(book.get("book_id", "")).strip(),
                            "volume": volume,
                        }
                    )
        return {"books": normalized, "exists": path.exists()}

    def save(self, project_name, payload):
        path = self._safe_project(project_name) / "publishing.json"
        incoming = payload.get("books")
        if not isinstance(incoming, list) or len(incoming) > 100:
            raise ValueError("Danh sách book Hako không hợp lệ")
        books = []
        occupied = {}
        for index, item in enumerate(incoming, 1):
            if not isinstance(item, dict):
                raise ValueError(f"Book {index} không hợp lệ")
            label = str(item.get("label", "")).strip()
            book_id = str(item.get("book_id", "")).strip()
            link_match = re.search(r"(?:book=)?(\d+)(?:\D*)$", book_id)
            if link_match:
                book_id = link_match.group(1)
            try:
                volume = int(item.get("volume"))
            except (TypeError, ValueError):
                raise ValueError(
                    f"Volume của book {index} phải là số nguyên"
                ) from None
            if len(label) > 100 or not book_id.isdigit() or len(book_id) > 20:
                raise ValueError(f"Book ID tại dòng {index} không hợp lệ")
            if volume < 0 or volume > 10000:
                raise ValueError(f"Volume tại dòng {index} không hợp lệ")
            label = label or f"Volume {volume}"
            if volume in occupied:
                raise ValueError(
                    f"Volume {volume} đang được gán cho cả “{occupied[volume]}” và “{label}”"
                )
            occupied[volume] = label
            books.append({"label": label, "book_id": book_id, "volume": volume})
        save_json(
            path,
            {"hako": {"books": sorted(books, key=lambda item: item["volume"])}},
            backup=True,
        )
        return self.data(project_name)

    def hako_chapters(self, public_url):
        public_url = str(public_url or "").strip()
        parsed = urlparse(public_url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "docln.sbs",
            "ln.hako.vn",
        }:
            raise ValueError("Hãy nhập URL trang truyện Hako hợp lệ")
        if not re.fullmatch(r"/truyen/\d+(?:-[^/?#]+)?/?", parsed.path):
            raise ValueError("URL phải là trang truyện Hako, không phải URL một chương")
        canonical_url = f"https://docln.sbs{parsed.path.rstrip('/')}"
        request = Request(
            canonical_url,
            headers={"User-Agent": "Mozilla/5.0 Aiko-App-Translator"},
        )
        try:
            source = self._opener(request, timeout=20).read().decode(
                "utf-8", "replace"
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ValueError(
                f"Không tải được danh sách chương Hako: {exc}"
            ) from None
        pattern = re.compile(
            r'<a\b[^>]*href=["\'](?P<href>[^"\']*/c(?P<id>\d+)-[^"\']*)["\'][^>]*>(?P<title>[\s\S]*?)</a>',
            re.IGNORECASE,
        )
        items, seen = [], set()
        for match in pattern.finditer(source):
            chapter_id = match.group("id")
            if chapter_id in seen:
                continue
            title = html.unescape(re.sub(r"<[^>]+>", "", match.group("title")))
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue
            href = match.group("href")
            if href.startswith("/"):
                href = "https://docln.sbs" + href
            items.append({"chapter_id": chapter_id, "title": title, "url": href})
            seen.add(chapter_id)
        if not items:
            raise ValueError("Không tìm thấy chương nào trên trang Hako này")
        return {"url": canonical_url, "items": items, "total": len(items)}

    @staticmethod
    def validate_hako_targets(value):
        if not isinstance(value, list) or not value or len(value) > 50:
            raise ValueError("Danh sách chương Hako cần cập nhật không hợp lệ")
        normalized, seen = [], set()
        for index, item in enumerate(value, 1):
            if not isinstance(item, dict):
                raise ValueError(f"Mapping Hako dòng {index} không hợp lệ")
            local_name = str(item.get("local_name", "")).strip()
            chapter_id = str(item.get("chapter_id", "")).strip()
            remote_title = str(item.get("remote_title", "")).strip()
            if not re.fullmatch(r"v\d+_c\d+_s\d+\.md", local_name):
                raise ValueError(f"Tên chương local dòng {index} không hợp lệ")
            if not chapter_id.isdigit() or len(chapter_id) > 20:
                raise ValueError(f"Chapter ID Hako dòng {index} không hợp lệ")
            if not remote_title or len(remote_title) > 500:
                raise ValueError(f"Tiêu đề Hako dòng {index} không hợp lệ")
            if chapter_id in seen:
                raise ValueError(f"Chapter ID {chapter_id} bị chọn trùng")
            seen.add(chapter_id)
            normalized.append(
                {
                    "local_name": local_name,
                    "chapter_id": chapter_id,
                    "remote_title": remote_title,
                }
            )
        return normalized

    def _save_setup(self, result):
        saved = self.configuration.saved_settings()
        saved.update(result["settings"])
        self.configuration.write_settings(
            {
                "values": {
                    key: saved.get(key, default)
                    for key, default in self.configuration.setting_defaults.items()
                }
            }
        )
        return {
            "ok": True,
            **{key: value for key, value in result.items() if key != "settings"},
            **self.configuration.settings_payload(),
        }

    def deploy_share_worker(self, payload):
        return self._save_setup(self._provision_share_worker(payload, self.root))

    def setup_publishing_r2(self, payload):
        return self._save_setup(self._provision_publishing_r2(payload))
