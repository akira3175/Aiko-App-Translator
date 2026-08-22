"""Application settings, UI preferences, and Gemini API-key configuration."""

import json
import os
import re
import secrets


class ConfigurationService:
    def __init__(
        self,
        *,
        settings_path,
        ui_preferences_path,
        setting_defaults,
        setting_labels,
        setting_ranges,
        setting_meta,
        secret_settings,
        optional_settings,
        hidden_settings,
        default_pinned_sidebar,
        sidebar_features,
        fixed_sidebar_features,
        api_keys,
        api_keys_path,
        api_key_state_path,
    ):
        self._settings_path = settings_path
        self._ui_preferences_path = ui_preferences_path
        self.setting_defaults = setting_defaults
        self.setting_labels = setting_labels
        self.setting_ranges = setting_ranges
        self.setting_meta = setting_meta
        self.secret_settings = secret_settings
        self.optional_settings = optional_settings
        self.hidden_settings = hidden_settings
        self.default_pinned_sidebar = default_pinned_sidebar
        self.sidebar_features = sidebar_features
        self.fixed_sidebar_features = fixed_sidebar_features
        self.api_keys = api_keys
        self._api_keys_path = api_keys_path
        self._api_key_state_path = api_key_state_path

    @staticmethod
    def _path(source):
        return source() if callable(source) else source

    def saved_settings(self):
        path = self._path(self._settings_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            key: data[key]
            for key in self.setting_defaults
            if key in data
        }

    def settings_payload(self):
        saved = self.saved_settings()
        return {
            "items": [
                {
                    "key": key,
                    "label": self.setting_labels[key],
                    "value": saved.get(key, default),
                    "default": default,
                    "type": (
                        "number"
                        if isinstance(default, int)
                        else ("password" if key in self.secret_settings else "text")
                    ),
                    "min": self.setting_ranges.get(key, (None, None))[0],
                    "max": self.setting_ranges.get(key, (None, None))[1],
                    "overridden": key in saved,
                    **self.setting_meta.get(key, {"group": "general"}),
                }
                for key, default in self.setting_defaults.items()
                if key not in self.hidden_settings
            ]
        }

    def write_settings(self, payload):
        path = self._path(self._settings_path)
        if payload.get("reset"):
            path.unlink(missing_ok=True)
            return self.settings_payload()
        values = payload.get("values")
        if not isinstance(values, dict):
            raise ValueError("Dữ liệu cài đặt không hợp lệ")
        cleaned = {}
        for key, default in self.setting_defaults.items():
            if key not in values:
                continue
            value = values[key]
            if isinstance(default, int):
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    raise ValueError(
                        f"{self.setting_labels[key]} phải là số nguyên"
                    ) from None
                minimum, maximum = self.setting_ranges.get(key, (1, 20))
                if not minimum <= value <= maximum:
                    raise ValueError(
                        f"{self.setting_labels[key]} phải từ {minimum} đến {maximum}"
                    )
            else:
                value = str(value).strip()
                max_length = 5000 if key == "review_bg_criteria" else 500
                if (
                    (not value and key not in self.optional_settings)
                    or len(value) > max_length
                ):
                    raise ValueError(f"{self.setting_labels[key]} không hợp lệ")
                if (
                    value
                    and key == "gemini_api_thinking"
                    and value
                    not in {"auto", "off", "minimal", "low", "medium", "high"}
                ):
                    raise ValueError("Cấp độ suy nghĩ Gemini API không hợp lệ")
                if key == "lan_enabled" and value not in {"off", "on"}:
                    raise ValueError("Chế độ truy cập LAN không hợp lệ")
                if key == "lan_pin" and value and not re.fullmatch(
                    r"\d{6,12}", value
                ):
                    raise ValueError("Mã PIN LAN phải gồm 6–12 chữ số")
                if value and key == "gemini_api_max_output_tokens":
                    try:
                        number = float(value)
                    except ValueError:
                        raise ValueError(
                            f"{self.setting_labels[key]} phải là một số"
                        ) from None
                    if number < 1:
                        raise ValueError(
                            f"{self.setting_labels[key]} nằm ngoài phạm vi cho phép"
                        )
                    if not number.is_integer():
                        raise ValueError(
                            f"{self.setting_labels[key]} phải là số nguyên"
                        )
            if value != default:
                cleaned[key] = value
        if cleaned.get("lan_enabled") == "on" and not cleaned.get("lan_pin"):
            cleaned["lan_pin"] = f"{secrets.randbelow(1_000_000):06d}"
        path.parent.mkdir(exist_ok=True)
        if cleaned:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(cleaned, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        else:
            path.unlink(missing_ok=True)
        return self.settings_payload()

    def ui_preferences(self):
        path = self._path(self._ui_preferences_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        sidebar = data.get("sidebar", {}) if isinstance(data, dict) else {}
        pinned = sidebar.get("pinned") if isinstance(sidebar, dict) else None
        if not isinstance(pinned, list):
            return {"sidebar": {"pinned": list(self.default_pinned_sidebar)}}
        cleaned = []
        for item in pinned:
            item = str(item)
            if (
                item in self.sidebar_features
                and item not in self.fixed_sidebar_features
                and item not in cleaned
            ):
                cleaned.append(item)
        return {"sidebar": {"pinned": cleaned}}

    def write_ui_preferences(self, payload):
        sidebar = payload.get("sidebar", {}) if isinstance(payload, dict) else {}
        pinned = sidebar.get("pinned") if isinstance(sidebar, dict) else None
        if not isinstance(pinned, list):
            raise ValueError("Danh sách chức năng đã ghim không hợp lệ")
        cleaned = []
        for item in pinned:
            item = str(item)
            if item not in self.sidebar_features:
                raise ValueError(f"Chức năng không hợp lệ: {item}")
            if item not in self.fixed_sidebar_features and item not in cleaned:
                cleaned.append(item)
        path = self._path(self._ui_preferences_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"sidebar": {"pinned": cleaned}},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return {"sidebar": {"pinned": cleaned}}

    def api_keys_payload(self):
        return self.api_keys.payload(
            self._path(self._api_keys_path),
            self._path(self._api_key_state_path),
        )

    def write_api_keys(self, payload):
        return self.api_keys.save(
            payload,
            self._path(self._api_keys_path),
            self._path(self._api_key_state_path),
        )

    def set_active_api_key(self, payload):
        return self.api_keys.set_active(
            payload,
            self._path(self._api_keys_path),
            self._path(self._api_key_state_path),
        )

    def test_api_key(self, payload):
        model = str(
            self.saved_settings().get(
                "translate_model", self.setting_defaults["translate_model"]
            )
        ).strip()
        return self.api_keys.test_key(payload.get("key", ""), model)
