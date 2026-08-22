"""Read and safely edit project pronoun history."""

from cores.storage.project import load_json, save_json


class PronounService:
    def __init__(self, safe_project):
        self._safe_project = safe_project

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
            latest = timeline[-1] if timeline else {}
            previous = timeline[-2] if len(timeline) > 1 else {}
            changed = bool(
                previous
                and (
                    previous.get("speaker_self") != latest.get("speaker_self")
                    or previous.get("speaker_to_listener")
                    != latest.get("speaker_to_listener")
                )
            )
            pairs.append(
                {
                    "key": str(key),
                    "characters": [
                        str(item) for item in value.get("characters", [])[:2]
                    ],
                    "timeline": timeline,
                    "latest": latest,
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
        data = load_json(path, {})
        if not isinstance(data, dict):
            raise ValueError("pronouns.json không hợp lệ")
        key = str(payload.get("key", "")).strip()
        if not key or key not in data or not isinstance(data[key], dict):
            raise ValueError("Không tìm thấy cặp xưng hô")
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
        save_json(path, data, backup=True)
        return self.data(project_name)

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
