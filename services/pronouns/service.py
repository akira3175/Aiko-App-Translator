"""Read and safely edit project pronoun history."""

import hashlib
import json

from cores.pronouns.normalize import group_directions, resolve_direction
from cores.pronouns.storage import edit_pronouns
from cores.storage.project import load_json


class PronounService:
    def __init__(self, safe_project):
        self._safe_project = safe_project

    @staticmethod
    def _revision(pair):
        """Bind an editor's indexes to the exact history and lock it displayed."""
        serialized = json.dumps(pair, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _direction_payload(state):
        record = state.get("record") or {}
        return {
            "speaker": state.get("speaker", ""),
            "listener": state.get("listener", ""),
            "speaker_self": state.get("speaker_self", ""),
            "speaker_to_listener": state.get("speaker_to_listener", ""),
            "temporary_address": state.get("temporary_address", ""),
            "relationship_status": state.get("relationship_status", ""),
            "emotional_tone": state.get("emotional_tone", ""),
            "chapter_number": state.get("chapter_number", 0),
            "since_chapter": state.get("since_chapter"),
            "previous": state.get("previous"),
            "changed": bool(state.get("changed")),
            "record_index": record.get("record_index"),
        }

    def data(self, project_name):
        path = self._safe_project(project_name) / "pronouns.json"
        raw_json = path.read_text(encoding="utf-8") if path.exists() else ""
        data = load_json(path, {})
        if not isinstance(data, dict):
            raise ValueError("pronouns.json không hợp lệ")
        pairs = []
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            timeline = [
                {**item, "record_index": index}
                for index, item in enumerate(value.get("timeline", []))
                if isinstance(item, dict)
            ]
            timeline.sort(key=lambda item: item.get("chapter_number", 0))
            directions = [
                self._direction_payload(resolve_direction(records))
                for records in group_directions(timeline).values()
            ]
            directions.sort(
                key=lambda item: item.get("chapter_number", 0) or 0, reverse=True
            )
            latest = dict(timeline[-1]) if timeline else {}
            if latest:
                # Fill blank/placeholder values with the stable value of the
                # same direction so the UI never shows "không rõ" as current.
                same_direction = next(
                    (
                        item
                        for item in directions
                        if item["speaker"] == latest.get("speaker", "")
                        and item["listener"] == latest.get("listener", "")
                    ),
                    None,
                )
                if same_direction:
                    for field in ("speaker_self", "speaker_to_listener"):
                        if same_direction[field]:
                            latest[field] = same_direction[field]
            changed = any(item["changed"] for item in directions)
            pairs.append(
                {
                    "key": str(key),
                    "revision": self._revision(value),
                    "characters": [
                        str(item) for item in value.get("characters", [])[:2]
                    ],
                    "timeline": timeline,
                    "latest": latest,
                    "directions": directions,
                    "locked": bool(value.get("locked", False)),
                    "changed": changed,
                }
            )
        pairs.sort(
            key=lambda item: item["latest"].get("chapter_number", 0),
            reverse=True,
        )
        return {
            "pairs": pairs,
            "count": len(pairs),
            "locked_count": sum(item["locked"] for item in pairs),
            "exists": path.exists(),
            "raw_json": raw_json,
        }

    def save(self, project_name, payload):
        path = self._safe_project(project_name) / "pronouns.json"
        with edit_pronouns(path, backup=True) as data:
            self._apply_edit(data, payload)
        return self.data(project_name)

    def _apply_edit(self, data, payload):
        key = str(payload.get("key", "")).strip()
        if not key or key not in data or not isinstance(data[key], dict):
            raise ValueError("Không tìm thấy cặp xưng hô")
        expected_revision = payload.get("expected_revision")
        # Indexed edits from older clients must reload instead of guessing
        # which record now occupies that index. Latest-entry callers may omit it.
        if expected_revision is not None or payload.get("timeline_index") is not None:
            if expected_revision != self._revision(data[key]):
                raise ValueError("Lịch sử xưng hô đã thay đổi; hãy tải lại dữ liệu rồi thử lại")
        if payload.get("action") == "delete":
            del data[key]
        else:
            pair = data[key]
            timeline = pair.get("timeline", [])
            if not isinstance(timeline, list) or not timeline:
                raise ValueError("Cặp xưng hô chưa có lịch sử để chỉnh sửa")
            latest_entry = self._requested_entry(timeline, payload)
            if latest_entry is None:
                raise ValueError("Không tìm thấy mốc lịch sử xưng hô")
            latest = latest_entry[1]
            expected_speaker = str(payload.get("expected_speaker", "")).strip()
            expected_listener = str(payload.get("expected_listener", "")).strip()
            if (
                expected_speaker
                and expected_speaker != str(latest.get("speaker", "")).strip()
            ) or (
                expected_listener
                and expected_listener != str(latest.get("listener", "")).strip()
            ):
                raise ValueError(
                    "Mốc lịch sử đã thay đổi; hãy tải lại dữ liệu rồi thử lại"
                )
            fields = {
                "speaker_self": str(payload.get("speaker_self", "")).strip(),
                "speaker_to_listener": str(
                    payload.get("speaker_to_listener", "")
                ).strip(),
                "relationship_status": str(
                    payload.get("relationship_status", "")
                ).strip(),
                "emotional_tone": str(payload.get("emotional_tone", "")).strip(),
            }
            if not fields["speaker_self"] or not fields["speaker_to_listener"]:
                raise ValueError(
                    "Cách tự xưng và gọi đối phương không được để trống"
                )
            if any(len(value) > 300 for value in fields.values()):
                raise ValueError("Nội dung quy tắc xưng hô quá dài")
            latest.update(fields)
            latest["source"] = "manual"
            pair["locked"] = bool(payload.get("locked", False))

    @staticmethod
    def _requested_entry(timeline, payload):
        requested_index = payload.get("timeline_index")
        if requested_index is None:
            return max(
                (
                    (index, item)
                    for index, item in enumerate(timeline)
                    if isinstance(item, dict)
                ),
                key=lambda entry: (entry[1].get("chapter_number", 0), entry[0]),
                default=None,
            )
        if isinstance(requested_index, bool) or not str(requested_index).isdigit():
            raise ValueError("Mốc lịch sử xưng hô không hợp lệ")
        index = int(requested_index)
        return (
            (index, timeline[index])
            if index < len(timeline) and isinstance(timeline[index], dict)
            else None
        )
