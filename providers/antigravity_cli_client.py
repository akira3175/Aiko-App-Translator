"""Headless Antigravity CLI (`agy`) transport for stage providers."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from cores.config.project_paths import USER_DATA_ROOT
from cores.config.runtime import int_option, option
from services.antigravity_cli import resolve_agy_binary, subprocess_window_kwargs


WORKSPACE_DIR = USER_DATA_ROOT / "antigravity-cli-workspace"

# Antigravity CLI caps inline <USER_REQUEST> and single `read_file` calls at ~46,080 UTF-8 bytes / 800 lines.
INLINE_MAX_BYTES = 32_000
INLINE_MAX_LINES = 700
CHUNK_MAX_BYTES = 36_000
CHUNK_MAX_LINES = 700

INLINE_AGENTS_MD = """# Aiko App Translator — Direct Text Mode

CRITICAL INSTRUCTIONS (MUST FOLLOW):
1. You are running headless as a pure text-generation model inside Aiko App Translator.
2. 100% of the prompt and any reference files (`characters.md`, `pronouns_snapshot.json`, `glossary.txt`, etc.) are ALREADY provided inline in the user message. Nothing is stored on disk.
3. NEVER call ANY tools (`run_command`, `read_file`, `view_file`, `list_dir`, `find_by_name`, `grep_search`, `write_to_file`, `replace_file_content`, `search_web`, `invoke_subagent`, etc.). Calling `run_command` or write tools immediately aborts the session!
4. Output ONLY the exact translated text, glossary, JSON, or structured markers requested by the user prompt, with zero extra commentary.
"""

CHUNKED_AGENTS_MD = """# Aiko App Translator — Chunked Large Input Mode

CRITICAL INSTRUCTIONS (MUST FOLLOW):
1. You are running headless inside Aiko App Translator. Because the input prompt is larger than the CLI inline limit, it has been split sequentially into `chunk_001.txt`, `chunk_002.txt`, ... in the current workspace directory.
2. Every chunk file is pre-sized to fit within a single `read_file` call (< 700 lines and < 36 KB). Call `read_file` in parallel on ALL listed `chunk_*.txt` files at once (using their full paths, WITHOUT `StartLine`, `EndLine`, or `ByteOffset`).
3. NEVER call `run_command`, `write_to_file`, `replace_file_content`, `edit_file`, `list_dir`, `find_by_name`, `grep_search`, `search_web`, or `invoke_subagent`. Calling `run_command` or any write tool will be denied and will immediately abort your turn!
4. Once you have read all `chunk_*.txt` files in order (`chunk_001.txt` + `chunk_002.txt` + ...), treat their concatenated text as the complete user prompt and output ONLY the exact result requested inside, directly in your text response (do NOT write output to a file).
"""

INLINE_SESSION_SETTINGS = json.dumps(
    {
        "notifications": False,
        "showTips": False,
        "showFeedbackSurvey": False,
        "allowNonWorkspaceAccess": False,
        "toolPermission": "strict",
    },
    ensure_ascii=False,
)

CHUNKED_SESSION_SETTINGS = json.dumps(
    {
        "notifications": False,
        "showTips": False,
        "showFeedbackSurvey": False,
        "allowNonWorkspaceAccess": False,
        "toolPermission": "request-review",
    },
    ensure_ascii=False,
)


class _NonRetryableCliError(RuntimeError):
    """Configuration, authentication, or quota error that should not be retried."""


def _write_if_changed(path: Path, content: str) -> None:
    try:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")
    except OSError:
        pass


def _ensure_inline_workspace(base_dir: Path | None = None) -> tuple[Path, Path]:
    base_dir = base_dir or WORKSPACE_DIR
    inline_dir = base_dir / "inline"
    rules_dir = inline_dir / ".agents" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    _write_if_changed(inline_dir / "AGENTS.md", INLINE_AGENTS_MD)
    _write_if_changed(
        rules_dir / "aiko_translator.md",
        "---\ntrigger: always_on\n---\n\n" + INLINE_AGENTS_MD,
    )
    settings_file = inline_dir / "session_settings.json"
    _write_if_changed(settings_file, INLINE_SESSION_SETTINGS)
    return inline_dir, settings_file


def _split_into_chunks(full_text: str) -> list[str]:
    chunks: list[str] = []
    current_lines: list[str] = []
    current_bytes = 0

    for line in full_text.splitlines(keepends=True):
        encoded_len = len(line.encode("utf-8"))
        if encoded_len > CHUNK_MAX_BYTES:
            if current_lines:
                chunks.append("".join(current_lines))
                current_lines = []
                current_bytes = 0
            # Safely slice an unusually long single line by character boundaries.
            segment: list[str] = []
            seg_bytes = 0
            for ch in line:
                ch_bytes = len(ch.encode("utf-8"))
                if seg_bytes + ch_bytes > CHUNK_MAX_BYTES and segment:
                    chunks.append("".join(segment))
                    segment = []
                    seg_bytes = 0
                segment.append(ch)
                seg_bytes += ch_bytes
            if segment:
                chunks.append("".join(segment))
            continue

        if current_lines and (
            current_bytes + encoded_len > CHUNK_MAX_BYTES
            or len(current_lines) >= CHUNK_MAX_LINES
        ):
            chunks.append("".join(current_lines))
            current_lines = []
            current_bytes = 0

        current_lines.append(line)
        current_bytes += encoded_len

    if current_lines:
        chunks.append("".join(current_lines))
    return chunks or [full_text]


def _prepare_chunked_workspace(full_text: str, base_dir: Path | None = None) -> tuple[Path, Path, str]:
    base_dir = base_dir or WORKSPACE_DIR
    runs_root = base_dir / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="req_", dir=str(runs_root)))
    rules_dir = run_dir / ".agents" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    _write_if_changed(run_dir / "AGENTS.md", CHUNKED_AGENTS_MD)
    _write_if_changed(
        rules_dir / "aiko_translator.md",
        "---\ntrigger: always_on\n---\n\n" + CHUNKED_AGENTS_MD,
    )
    settings_file = run_dir / "session_settings.json"
    _write_if_changed(settings_file, CHUNKED_SESSION_SETTINGS)

    chunks = _split_into_chunks(full_text)
    chunk_paths: list[Path] = []
    for idx, chunk in enumerate(chunks, start=1):
        chunk_file = run_dir / f"chunk_{idx:03d}.txt"
        chunk_file.write_text(chunk, encoding="utf-8")
        chunk_paths.append(chunk_file.resolve())

    file_list = "\n".join(f"- {path}" for path in chunk_paths)
    driver_prompt = (
        f"Prompt đầu vào dài ({len(full_text)} ký tự) đã được chia thành {len(chunk_paths)} phần theo thứ tự:\n"
        f"{file_list}\n\n"
        "Hãy gọi `read_file` đồng thời cho TẤT CẢ các file trên trong cùng 1 lượt (không truyền StartLine/EndLine/ByteOffset), "
        "KHÔNG gọi `run_command` hay tạo file mới, sau đó ghép nội dung từ phần 1 đến phần cuối và thực hiện CHÍNH XÁC yêu cầu bên trong. "
        "Chỉ xuất trực tiếp kết quả cuối cùng ra phản hồi văn bản."
    )
    return run_dir, settings_file, driver_prompt


def _classify_failure(detail: str, *, model: str, effort: str, stage: str) -> RuntimeError:
    clean = " ".join(str(detail or "").split())
    lowered = clean.lower()
    if "effort" in lowered and any(
        token in lowered for token in ("has no ", "invalid effort", "isn't adjustable", "not adjustable")
    ):
        return _NonRetryableCliError(
            f"Model {model or 'đang chọn'} không hỗ trợ mức suy nghĩ '{effort}'. "
            f"Hãy đặt Cấp độ suy nghĩ về 'Tự động theo model' (auto) hoặc chọn mức khác. Chi tiết: {clean}"
        )
    if any(token in lowered for token in ("authentication required", "unauthenticated", "not logged in", "sign in")):
        return _NonRetryableCliError(
            "Chưa đăng nhập Antigravity CLI. Hãy mở Cài đặt → Antigravity CLI và bấm “Mở Terminal agy” để đăng nhập."
        )
    if any(token in lowered for token in ("quota", "rate limit", "resource_exhausted", "insufficient credits", "usage limit")):
        return _NonRetryableCliError(
            f"Antigravity CLI chạm giới hạn hạn mức/credits với model {model or 'đang chọn'}. "
            f"Hãy thử đổi sang nhóm model khác hoặc kiểm tra bằng lệnh /usage trong agy. Chi tiết: {clean}"
        )
    if "unknown model" in lowered or "invalid model" in lowered or "model not found" in lowered:
        return _NonRetryableCliError(
            f"Model Antigravity CLI '{model}' không hợp lệ hoặc không có trong tài khoản: {clean}"
        )
    return RuntimeError(f"Antigravity CLI lỗi ở bước {stage}: {clean or 'không nhận được phản hồi hợp lệ'}")


def _parse_stream_output(stdout: str, stderr: str, *, model: str, effort: str, stage: str) -> tuple[str, dict]:
    deltas: list[str] = []
    terminal_result: dict | None = None
    non_json_lines: list[str] = []
    tool_errors: list[str] = []

    for raw_line in str(stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            non_json_lines.append(line)
            continue
        if not isinstance(payload, dict):
            continue
        event_type = payload.get("event")
        if event_type == "step_update":
            step = payload.get("step_update") or {}
            if step.get("step_type") == "agent_response" and isinstance(step.get("text_delta"), str):
                deltas.append(step["text_delta"])
            elif step.get("step_type") == "tool":
                tool_info = step.get("tool_info") or {}
                err = tool_info.get("error")
                if isinstance(err, dict) and err.get("message"):
                    tool_errors.append(str(err["message"]))
        elif event_type == "result":
            result_obj = payload.get("result")
            if isinstance(result_obj, dict):
                terminal_result = result_obj

    if terminal_result is None:
        combined_err = "\n".join([*(non_json_lines[-5:]), str(stderr or "").strip()]).strip()
        raise _classify_failure(combined_err, model=model, effort=effort, stage=stage)

    status = str(terminal_result.get("status", ""))
    if status != "SUCCESS":
        err_msg = str(terminal_result.get("error") or stderr or status).strip()
        raise _classify_failure(err_msg, model=model, effort=effort, stage=stage)

    response_text = str(terminal_result.get("response") or "".join(deltas)).strip()
    if not response_text:
        extra = f" ({tool_errors[-1][:200]})" if tool_errors else ""
        raise RuntimeError(f"Antigravity CLI trả về nội dung trống ở bước {stage}{extra}.")
    return response_text, terminal_result


def _combine_full_prompt(prompt: str, documents: list[dict]) -> str:
    blocks = [str(prompt)]
    for item in documents:
        content_text = str(item.get("content", "")).strip()
        if not content_text:
            continue
        filename = str(item.get("name", "attachment.txt"))
        blocks.append(f"## Reference file: {filename}\n\n{content_text}")
    return "\n\n".join(blocks)


def call_antigravity_cli(
    prompt,
    *,
    model,
    reasoning_effort,
    stage,
    document=None,
    documents=None,
):
    custom_path = str(option("antigravity_cli_path", "")).strip()
    binary = resolve_agy_binary(custom_path)
    if not binary:
        raise RuntimeError(
            "Không tìm thấy Antigravity CLI (agy). Hãy cài đặt Antigravity CLI "
            "hoặc nhập đường dẫn agy.exe trong Cài đặt → Antigravity CLI."
        )
    selected_model = str(model or "").strip()
    if not selected_model:
        raise RuntimeError("Hãy chọn model Antigravity CLI trong Cài đặt trước khi chạy.")

    doc_list = list(documents or ([] if document is None else [document]))
    full_text = _combine_full_prompt(str(prompt), doc_list)
    total_bytes = len(full_text.encode("utf-8"))
    total_lines = full_text.count("\n") + 1
    use_chunks = total_bytes > INLINE_MAX_BYTES or total_lines > INLINE_MAX_LINES

    effort = str(reasoning_effort or "").strip().lower()
    timeout = int_option("antigravity_cli_timeout", 600, minimum=30)
    retries = int_option("antigravity_cli_retries", 2, minimum=1)

    for attempt in range(retries):
        process = None
        cleanup_dir: Path | None = None
        try:
            if use_chunks:
                cwd_path, settings_file, driver_text = _prepare_chunked_workspace(full_text)
                cleanup_dir = cwd_path
                content_blocks = [{"type": "text", "text": driver_text}]
                mode_label = "chế độ chia phần chống cắt chữ"
            else:
                cwd_path, settings_file = _ensure_inline_workspace()
                content_blocks = [{"type": "text", "text": str(prompt)}]
                for item in doc_list:
                    content_text = str(item.get("content", "")).strip()
                    if not content_text:
                        continue
                    filename = str(item.get("name", "attachment.txt"))
                    content_blocks.append(
                        {"type": "text", "text": f"## Reference file: {filename}\n\n{content_text}"}
                    )
                mode_label = "trực tiếp"

            command = [
                binary,
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--disable-slash-commands",
                "--settings",
                str(settings_file),
                "--model",
                selected_model,
            ]
            if effort and effort != "auto":
                command.extend(["--effort", effort])

            stdin_payload = (
                json.dumps(
                    {"event": "user", "message": {"content": content_blocks}},
                    ensure_ascii=False,
                )
                + "\n"
            )
            print(
                f"📤 Đã gửi prompt ({len(full_text)} ký tự, {mode_label}) qua Antigravity CLI ({selected_model}). "
                "Đang chờ phản hồi...",
                flush=True,
            )
            process = subprocess.Popen(
                command,
                cwd=str(cwd_path),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **subprocess_window_kwargs(),
            )
            stdout, stderr = process.communicate(input=stdin_payload, timeout=timeout)
            text, result_meta = _parse_stream_output(
                stdout,
                stderr,
                model=selected_model,
                effort=effort or "auto",
                stage=stage,
            )
            duration = float(result_meta.get("duration_seconds") or 0.0)
            usage = result_meta.get("usage") or {}
            out_tokens = usage.get("output_tokens")
            if duration > 0 and out_tokens is not None:
                print(
                    f"📥 Antigravity CLI hoàn tất ({duration:.1f}s · {out_tokens} token đầu ra).",
                    flush=True,
                )
            return text
        except _NonRetryableCliError:
            raise
        except subprocess.TimeoutExpired as exc:
            if process is not None:
                process.kill()
                process.communicate()
            if attempt == retries - 1:
                raise RuntimeError(
                    f"Antigravity CLI quá thời gian chờ ({timeout}s) ở bước {stage}."
                ) from exc
        except (OSError, RuntimeError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(str(exc)) from exc
        finally:
            if cleanup_dir is not None:
                shutil.rmtree(cleanup_dir, ignore_errors=True)

        wait = min(5 * (attempt + 1), 15)
        print(f"[Antigravity CLI] Thử lại sau {wait}s...", flush=True)
        time.sleep(wait)

    raise RuntimeError(f"Antigravity CLI không hoàn tất bước {stage}.")
