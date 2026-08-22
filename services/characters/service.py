"""Read and safely update project character profiles."""

import os
import re
import shutil


class CharacterService:
    def __init__(self, safe_project):
        self._safe_project = safe_project

    def data(self, project_name):
        path = self._safe_project(project_name) / "characters.md"
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        names = re.findall(r"(?m)^##\s+(.+?)\s*$", content)
        return {
            "content": content,
            "exists": path.exists(),
            "count": len(names),
            "backup": path.with_name(path.name + ".bak").exists(),
            "updated_at": path.stat().st_mtime if path.exists() else None,
        }

    def save(self, project_name, payload):
        path = self._safe_project(project_name) / "characters.md"
        content = str(payload.get("content", "")).replace("\r\n", "\n")
        if "\x00" in content or len(content.encode("utf-8")) > 5 * 1024 * 1024:
            raise ValueError("Hồ sơ nhân vật không hợp lệ hoặc vượt quá 5 MB")
        if path.exists() and path.stat().st_size and not content.strip():
            raise ValueError("Không thể vô tình xóa sạch hồ sơ nhân vật")
        if content and not content.endswith("\n"):
            content += "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
        return self.data(project_name)
