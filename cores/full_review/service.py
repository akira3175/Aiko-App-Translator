"""Prompting, API retry, and result normalization for full review."""

import json
import re
import time

from cores.config import REVIEW_BG_CRITERIA
from cores.gemini import switch_api_key
from cores.postprocess import build_translation_review_prompt
from cores.config.runtime import option
from cores.stages import generate_stage


TRANSPORT_OVERRIDES = {}


def build_review_prompt(
    chapter_id,
    chapter_number,
    raw_title,
    raw_content,
    title,
    content,
    context_text="",
):
    return build_translation_review_prompt(
        chapter_id,
        chapter_number,
        raw_title,
        raw_content,
        title,
        content,
        context_text,
        REVIEW_BG_CRITERIA,
    )


def call_review_api(prompt, provider):
    """Call the configured provider until a valid review JSON object is returned."""
    attempt = 0
    while True:
        attempt += 1
        try:
            text = generate_stage(
                "review",
                prompt,
                provider=provider,
                get_option=option,
                overrides=TRANSPORT_OVERRIDES,
            )[0].text.strip()
            if not text:
                print(f"  ⚠️ Response rỗng, thử lại (lần {attempt})...")
                time.sleep(5)
                continue
            clean = re.sub(r"```json\s*|\s*```", "", text).strip()
            start = clean.find("{")
            end = clean.rfind("}")
            if start != -1 and end != -1:
                return json.loads(clean[start : end + 1])
            print(f"  ⚠️ Không tìm thấy JSON trong response, thử lại (lần {attempt})...")
            time.sleep(3)
        except json.JSONDecodeError as error:
            print(f"  ⚠️ Lỗi parse JSON: {error}, thử lại (lần {attempt})...")
            time.sleep(3)
        except Exception as error:
            message = str(error)
            if provider == "gemini-api" and (
                "429" in message or "RESOURCE_EXHAUSTED" in message
            ):
                switch_api_key()
                delay = min(30 + attempt * 10, 120)
                print(f"  🔄 Lỗi 429! Đổi key, chờ {delay}s (lần {attempt})...")
                time.sleep(delay)
            elif any(code in message for code in ("500", "502", "503", "504")):
                delay = min(10 + attempt * 5, 60)
                print(f"  ⚠️ Lỗi 5xx, chờ {delay}s (lần {attempt})...")
                time.sleep(delay)
            else:
                print(f"  ⚠️ Lỗi: {message}, chờ 15s (lần {attempt})...")
                time.sleep(15)


def process_review_result(chapter_id, chapter_number, review_data, review_store, manual_list):
    if not review_data:
        return
    issues = review_data.get("issues", [])
    gender_ok = review_data.get("gender_ok", True)
    address_ok = review_data.get("address_ok", True)
    review_store[chapter_id] = {
        "chapter_number": chapter_number,
        "score": review_data.get("overall_score"),
        "issue_count": len(issues),
        "gender_ok": gender_ok,
        "address_ok": address_ok,
        "issues": issues,
        "summary": str(review_data.get("summary", ""))[:1500],
    }
    needs_manual = not gender_ok or not address_ok or any(
        issue.get("severity", "").lower() in ("nặng", "trung bình")
        for issue in issues
    )
    if needs_manual:
        if chapter_id not in manual_list:
            manual_list.append(chapter_id)
        print(f"  🔴 {chapter_id} — CẦN KIỂM TRA THỦ CÔNG (giới tính/xưng hô)")
    else:
        score = review_data.get("overall_score", "?")
        print(f"  ✅ {chapter_id} — Score: {score}/10, {len(issues)} issues")
