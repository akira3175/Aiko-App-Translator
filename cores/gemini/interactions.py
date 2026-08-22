"""Minimal Gemini Interactions SSE client used by the Beta translation engine."""

import json
import base64
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
SUPPORTED_DOCUMENT_MIME_TYPES = {"application/pdf", "text/csv"}


def _interaction_reference_part(item):
    content = item.get("content", "")
    if not content.strip():
        return None
    mime_type = item.get("mime_type", "")
    if mime_type in SUPPORTED_DOCUMENT_MIME_TYPES:
        return {
            "type": "document",
            "data": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "mime_type": mime_type,
        }
    name = item.get("name") or "reference"
    return {"type": "text", "text": f"## Reference file: {name}\n\n{content}"}


def stream_interaction(
    *,
    api_key,
    model,
    prompt,
    generation_config=None,
    system_instruction=None,
    document=None,
    documents=None,
    on_text=None,
    stop_requested=lambda: False,
    opener=urlopen,
):
    attached_documents = list(documents or ([] if document is None else [document]))
    document_parts = [
        part
        for item in attached_documents
        if item and (part := _interaction_reference_part(item))
    ]
    payload = {
        "model": model,
        "input": [
            {"type": "text", "text": prompt},
            *document_parts,
        ] if document_parts else prompt,
        "stream": True,
        "store": False,
    }
    if generation_config:
        payload["generation_config"] = generation_config
    if system_instruction:
        payload["system_instruction"] = system_instruction
    request = Request(
        f"{INTERACTIONS_URL}?{urlencode({'alt': 'sse'})}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    chunks = []
    completed = False
    try:
        response = opener(request, timeout=600)
        with response:
            for raw_line in response:
                if stop_requested():
                    raise InterruptedError("Đã dừng Gemini Interactions streaming")
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    continue
                event = json.loads(data)
                event_type = event.get("event_type")
                if event_type == "step.delta":
                    delta = event.get("delta") or {}
                    text = delta.get("text") if delta.get("type") == "text" else None
                    if text:
                        chunks.append(text)
                        if on_text:
                            on_text(text)
                        print(text, flush=True)
                elif event_type == "interaction.completed":
                    status = (event.get("interaction") or {}).get("status")
                    if status not in (None, "completed"):
                        raise RuntimeError(
                            f"Gemini Interactions kết thúc với trạng thái {status}"
                        )
                    completed = True
                elif event_type == "error":
                    error = event.get("error") or {}
                    raise RuntimeError(
                        error.get("message") or "Gemini Interactions stream gặp lỗi"
                    )
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini Interactions HTTP {exc.code}: {detail}") from exc
    if not completed:
        raise RuntimeError("Gemini Interactions stream kết thúc trước khi hoàn tất")
    return "".join(chunks)
