"""Discover and normalize project review results stored as JSON."""

import re

from cores.storage.project import load_json


class ReviewService:
    def __init__(self, safe_project):
        self._safe_project = safe_project

    def sources(self, project_name):
        project = self._safe_project(project_name)
        return sorted(
            item.name
            for item in project.glob("review*.json")
            if item.is_file()
        )

    def payload(self, project_name, requested_source=""):
        sources = self.sources(project_name)
        source = str(requested_source or (sources[0] if sources else ""))
        return {
            "sources": sources,
            "source": source,
            "items": self.data(project_name, source) if source else [],
        }

    def data(self, project_name, source):
        project = self._safe_project(project_name)
        source = re.sub(r"\.yaml$", ".json", str(source), flags=re.IGNORECASE)
        if not re.fullmatch(r"review(?:_[\w-]+)?\.json", source):
            raise ValueError("Invalid review source")
        path = (project / source).resolve()
        if project.resolve() not in path.parents or not path.exists():
            raise ValueError("Review source not found")
        data = load_json(path, {})
        if not isinstance(data, dict):
            return []
        items = []
        for chapter_id, value in data.items():
            if not isinstance(value, dict):
                continue
            items.append(
                {
                    "chapter_id": str(chapter_id),
                    "chapter_number": value.get("chapter_number"),
                    "score": value.get("score"),
                    "issue_count": value.get(
                        "issue_count", len(value.get("issues") or [])
                    ),
                    "summary": value.get("summary", ""),
                    "issues": value.get("issues") or [],
                }
            )
        return sorted(
            items,
            key=lambda item: (
                item["chapter_number"] is None,
                item["chapter_number"] or 0,
            ),
        )
