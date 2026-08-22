"""Bounded Gemini API-key generation check."""


def test_key(key, model, client_factory=None, config_factory=None):
    key = str(key).strip()
    if not key or len(key) > 500 or any(char.isspace() for char in key):
        raise ValueError("Gemini API key không hợp lệ")

    if client_factory is None or config_factory is None:
        from google import genai
        from google.genai import types

        client_factory = client_factory or genai.Client
        config_factory = config_factory or types.GenerateContentConfig
    try:
        client = client_factory(api_key=key)
        client.models.generate_content(
            model=model,
            contents="Reply with OK only.",
            config=config_factory(max_output_tokens=8),
        )
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code in (400, 401, 403):
            message = "Key sai, bị chặn hoặc không có quyền"
        elif code == 429:
            message = "Hết quota hoặc bị giới hạn tần suất"
        elif code == 404:
            message = f"Model {model} không khả dụng"
        else:
            code = "NETWORK"
            message = "Không thể kết nối Gemini"
        return {
            "ok": False,
            "code": str(code),
            "message": message,
            "model": model,
        }
    return {
        "ok": True,
        "code": "OK",
        "message": "Sinh nội dung thành công",
        "model": model,
    }
