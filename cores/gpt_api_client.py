"""Minimal OpenAI Responses API client used by the GPT API translation engine."""

import base64
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cores.runtime_config import int_option, option


def _response_text(data):
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks).strip()


def call_gpt_api(prompt, *, model, reasoning_effort, stage, document=None, documents=None):
    api_key = str(option("gpt_api_key", "")).strip()
    endpoint = str(
        option("gpt_api_endpoint", "https://api.openai.com/v1/responses")
    ).strip()
    if not api_key:
        raise RuntimeError("Chưa nhập GPT API key trong Cài đặt.")
    if not endpoint.startswith(("https://", "http://")):
        raise RuntimeError("Endpoint GPT API không hợp lệ.")

    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": int_option(
            "gpt_api_max_output_tokens", 30000, minimum=1000
        ),
    }
    attached_documents = list(documents or ([] if document is None else [document]))
    attached_documents = [item for item in attached_documents if str(item.get("content", "")).strip()]
    if attached_documents:
        file_parts = []
        for item in attached_documents:
            mime_type = str(item.get("mime_type", "text/plain")).strip()
            encoded = base64.b64encode(str(item["content"]).encode("utf-8")).decode("ascii")
            file_parts.append({
                "type": "input_file",
                "filename": str(item.get("name", "attachment.txt")),
                "file_data": f"data:{mime_type};base64,{encoded}",
            })
        payload["input"] = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    *file_parts,
                ],
            }
        ]
    effort = str(reasoning_effort or "").strip().lower()
    if effort:
        payload["reasoning"] = {"effort": effort}
    temperature = str(option("gpt_api_temperature", "")).strip()
    if temperature:
        try:
            payload["temperature"] = float(temperature)
        except ValueError as exc:
            raise RuntimeError("Temperature GPT API phải là một số.") from exc
        if not 0 <= payload["temperature"] <= 2:
            raise RuntimeError("Temperature GPT API phải từ 0 đến 2.")

    timeout = int_option("gpt_api_timeout", 300, minimum=30)
    retries = int_option("gpt_api_retries", 3, minimum=1)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(retries):
        request = Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            text = _response_text(data)
            if not text:
                raise RuntimeError("GPT API trả về nội dung trống.")
            return text
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt == retries - 1:
                raise RuntimeError(
                    f"GPT API lỗi HTTP {exc.code} ở bước {stage}: {detail}"
                ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"GPT API lỗi ở bước {stage}: {exc}") from exc
        wait = min(5 * (attempt + 1), 20)
        print(f"[GPT API] Thử lại sau {wait}s...")
        time.sleep(wait)

    raise RuntimeError(f"GPT API không hoàn tất bước {stage}.")
