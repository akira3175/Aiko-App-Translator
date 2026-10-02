"""Responses transport authenticated by a local ChatGPT plan grant."""

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.chatgpt_plan import RESOURCE, access_token


def _failure_message(code, fallback, model=None):
    if code == "subscription_sharing_usage_limit_exceeded":
        current_model = f"{model}" if model else "đang dùng"
        return ("ChatGPT Plan đã chạm giới hạn sử dụng. Có hai khả năng: "
                f"(1) model {current_model} đã hết lượt, hãy thử model khác trong Quy trình dịch; "
                "(2) tài khoản hoặc ứng dụng đã hết hạn mức, hãy kiểm tra trong ChatGPT → Settings → Usage: "
                "https://chatgpt.com/settings/usage. "
                f"Mã lỗi: {code}")
    if code == "subscription_sharing_usage_unavailable":
        return ("ChatGPT tạm thời không kiểm tra được mức sử dụng. Hãy thử lại sau. "
                f"Mã lỗi: {code}")
    return f"ChatGPT không hoàn tất phản hồi: {code or fallback}"


def _stream_text(response, *, model=None):
    chunks = []
    completed = False
    for raw in response:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data:") or line == "data: [DONE]":
            continue
        event = json.loads(line[5:].strip())
        kind = event.get("type")
        if kind == "response.output_text.delta":
            chunks.append(event.get("delta", ""))
        elif kind in ("response.failed", "response.incomplete"):
            terminal = event.get("response") or {}
            detail = terminal.get("error") or terminal.get("incomplete_details") or {}
            raise RuntimeError(_failure_message(detail.get("code"), detail.get("reason") or kind, model))
        elif kind == "response.completed":
            completed = True
    if not completed:
        raise RuntimeError("Luồng ChatGPT kết thúc trước khi hoàn tất phản hồi.")
    text = "".join(chunks).strip()
    if not text:
        raise RuntimeError("ChatGPT trả về nội dung trống.")
    return text


def call_chatgpt_plan(prompt, *, model, reasoning_effort, stage, document=None, documents=None):
    if not model:
        raise RuntimeError("Hãy chọn model ChatGPT trong Cài đặt trước khi dịch.")
    content = [{"type": "input_text", "text": prompt}]
    for item in list(documents or ([] if document is None else [document])):
        if not str(item.get("content", "")).strip():
            continue
        mime = str(item.get("mime_type", "text/plain"))
        encoded = base64.b64encode(str(item["content"]).encode("utf-8")).decode("ascii")
        content.append({"type": "input_file", "filename": str(item.get("name", "attachment.txt")),
                        "file_data": f"data:{mime};base64,{encoded}"})
    payload = {"model": model, "input": [{"role": "user", "content": content}],
               "store": False, "stream": True}
    effort = str(reasoning_effort or "").strip().lower()
    if effort and effort != "auto":
        payload["reasoning"] = {"effort": effort}
    request = Request(RESOURCE + "/responses", json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers={"Authorization": "Bearer " + access_token(),
                               "Content-Type": "application/json", "Accept": "text/event-stream"}, method="POST")
    try:
        with urlopen(request, timeout=300) as response:
            return _stream_text(response, model=model)
    except HTTPError as exc:
        try:
            error = json.loads(exc.read().decode("utf-8"))
            info = error.get("error") or {}
            code = info.get("code")
            detail = code or info.get("message") or error.get("detail")
        except (ValueError, AttributeError):
            code = None
            detail = None
        raise RuntimeError(_failure_message(code, f"HTTP {exc.code}: {detail or 'không thể gửi yêu cầu'}", model)) from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Không thể kết nối ChatGPT ở bước {stage}: {exc}") from exc
