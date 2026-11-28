import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from providers import antigravity_cli_client
from services import antigravity_cli


class AntigravityCliTests(unittest.TestCase):
    def setUp(self):
        antigravity_cli._models_cache.clear()

    def test_resolve_binary_checks_custom_path_and_gemini_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_exe = Path(tmp) / "agy.exe"
            fake_exe.write_text("bin", encoding="utf-8")
            self.assertEqual(
                antigravity_cli.resolve_agy_binary(str(fake_exe)),
                str(fake_exe.resolve()),
            )

            home = Path(tmp) / "home"
            gemini_bin = home / ".gemini" / "bin"
            gemini_bin.mkdir(parents=True)
            fallback_exe = gemini_bin / ("agy.exe" if antigravity_cli.os.name == "nt" else "agy")
            fallback_exe.write_text("bin", encoding="utf-8")
            with patch.object(antigravity_cli.shutil, "which", return_value=None), patch.object(
                antigravity_cli.Path, "home", return_value=home
            ):
                self.assertEqual(
                    antigravity_cli.resolve_agy_binary(""),
                    str(fallback_exe.resolve()),
                )

    def test_list_models_parses_tab_separated_lines_and_caches(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout=(
                "Fetching available models...\n"
                "gemini-4-carbon-medium\tGemini 4 Carbon (Medium)\n"
                "gemini-3.8-flash-low\tGemini 3.8 Flash (Low)\n"
            ),
            stderr="",
        )
        with patch.object(antigravity_cli, "resolve_agy_binary", return_value="/bin/agy"), patch.object(
            antigravity_cli.subprocess, "run", return_value=completed
        ) as run_mock:
            first = antigravity_cli.list_models()
            second = antigravity_cli.list_models()

        self.assertEqual(
            first,
            [
                {"slug": "gemini-4-carbon-medium", "display_name": "Gemini 4 Carbon (Medium)"},
                {"slug": "gemini-3.8-flash-low", "display_name": "Gemini 3.8 Flash (Low)"},
            ],
        )
        self.assertEqual(first, second)
        run_mock.assert_called_once()

    def test_service_status_handles_missing_binary_and_auth_error(self):
        service = antigravity_cli.AntigravityCliService()
        with patch.object(antigravity_cli, "resolve_agy_binary", return_value=None):
            missing = service.status()
        self.assertFalse(missing["installed"])
        self.assertFalse(missing["connected"])

        failed = SimpleNamespace(returncode=1, stdout="", stderr="authentication required")
        with patch.object(antigravity_cli, "resolve_agy_binary", return_value="/bin/agy"), patch.object(
            antigravity_cli, "cli_version", return_value="1.5.19"
        ), patch.object(antigravity_cli.subprocess, "run", return_value=failed):
            unauthed = service.status(refresh=True)
        self.assertTrue(unauthed["installed"])
        self.assertFalse(unauthed["connected"])
        self.assertIn("Chưa đăng nhập", unauthed["error"])

    def test_call_antigravity_cli_streams_stdin_inline_for_normal_prompts(self):
        stream_stdout = "\n".join([
            json.dumps({"event": "init", "conversation_id": "conv-1", "init": {"permission_mode": "strict"}}),
            json.dumps({
                "event": "step_update",
                "step_update": {"step_type": "agent_response", "state": "ACTIVE", "text_delta": "###TITLE###\nChương 1\n"},
            }),
            json.dumps({
                "event": "result",
                "result": {
                    "status": "SUCCESS",
                    "response": "###TITLE###\nChương 1\n###CONTENT###\nXin chào\n###END###\n",
                    "duration_seconds": 2.1,
                    "usage": {"output_tokens": 12},
                },
            }),
        ])
        fake_proc = MagicMock()
        fake_proc.communicate.return_value = (stream_stdout, "")

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(antigravity_cli_client, "WORKSPACE_DIR", Path(tmp)), patch.object(
                antigravity_cli_client, "resolve_agy_binary", return_value="/bin/agy"
            ), patch.object(antigravity_cli_client, "option", return_value=""), patch.object(
                antigravity_cli_client, "int_option", side_effect=lambda _k, default, **_kw: default
            ), patch.object(antigravity_cli_client.subprocess, "Popen", return_value=fake_proc) as popen_mock:
                output = antigravity_cli_client.call_antigravity_cli(
                    "Dịch chương này",
                    model="gemini-4-carbon-medium",
                    reasoning_effort="auto",
                    stage="translate",
                    documents=[{"name": "characters.md", "content": "Nhân vật A"}],
                )

            self.assertIn("###TITLE###", output)
            cmd = popen_mock.call_args.args[0]
            self.assertIn("--input-format", cmd)
            self.assertIn("stream-json", cmd)
            self.assertIn("--model", cmd)
            self.assertIn("gemini-4-carbon-medium", cmd)
            self.assertNotIn("--effort", cmd)

            sent_stdin = fake_proc.communicate.call_args.kwargs["input"]
            parsed_stdin = json.loads(sent_stdin.strip())
            self.assertEqual(parsed_stdin["event"], "user")
            self.assertEqual(len(parsed_stdin["message"]["content"]), 2)
            self.assertIn("characters.md", parsed_stdin["message"]["content"][1]["text"])
            self.assertTrue((Path(tmp) / "inline" / "AGENTS.md").is_file())

    def test_call_antigravity_cli_uses_chunk_files_for_large_prompts_and_cleans_up(self):
        large_prompt = "Trích xuất glossary:\n" + ("알렉산더 그로세프와 베니샤의 아카데미 생활.\n" * 2000)
        captured = {}

        def fake_popen(cmd, **kwargs):
            cwd = Path(kwargs["cwd"])
            chunks = sorted(cwd.glob("chunk_*.txt"))
            captured["chunk_count"] = len(chunks)
            captured["reconstructed"] = "".join(c.read_text(encoding="utf-8") for c in chunks)
            captured["settings"] = json.loads((cwd / "session_settings.json").read_text(encoding="utf-8"))
            captured["cwd"] = cwd
            proc = MagicMock()
            proc.communicate.return_value = (
                json.dumps({
                    "event": "result",
                    "result": {
                        "status": "SUCCESS",
                        "response": "알렉산더 그로세프 = Alexander Grosev\n",
                        "duration_seconds": 5.0,
                        "usage": {"output_tokens": 10},
                    },
                }),
                "",
            )
            return proc

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(antigravity_cli_client, "WORKSPACE_DIR", Path(tmp)), patch.object(
                antigravity_cli_client, "resolve_agy_binary", return_value="/bin/agy"
            ), patch.object(antigravity_cli_client, "option", return_value=""), patch.object(
                antigravity_cli_client, "int_option", side_effect=lambda _k, default, **_kw: default
            ), patch.object(antigravity_cli_client.subprocess, "Popen", side_effect=fake_popen):
                result = antigravity_cli_client.call_antigravity_cli(
                    large_prompt,
                    model="gemini-4-carbon-high",
                    reasoning_effort="auto",
                    stage="glossary",
                )

            self.assertIn("Alexander Grosev", result)
            self.assertGreater(captured["chunk_count"], 3)
            self.assertEqual(captured["reconstructed"], large_prompt)
            self.assertEqual(captured["settings"]["toolPermission"], "request-review")
            self.assertFalse(captured["cwd"].exists())

    def test_call_antigravity_cli_does_not_retry_invalid_effort_error(self):
        fake_proc = MagicMock()
        fake_proc.communicate.return_value = (
            "",
            'gemini-pro-orchestrator: effort isn\'t adjustable for the current model',
        )
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(antigravity_cli_client, "WORKSPACE_DIR", Path(tmp)), patch.object(
                antigravity_cli_client, "resolve_agy_binary", return_value="/bin/agy"
            ), patch.object(antigravity_cli_client, "option", return_value=""), patch.object(
                antigravity_cli_client, "int_option", side_effect=lambda _k, default, **_kw: default
            ), patch.object(antigravity_cli_client.subprocess, "Popen", return_value=fake_proc) as popen_mock:
                with self.assertRaises(RuntimeError) as ctx:
                    antigravity_cli_client.call_antigravity_cli(
                        "Test",
                        model="gemini-pro-orchestrator",
                        reasoning_effort="max",
                        stage="translate",
                    )
        self.assertIn("Tự động theo model", str(ctx.exception))
        self.assertEqual(popen_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
