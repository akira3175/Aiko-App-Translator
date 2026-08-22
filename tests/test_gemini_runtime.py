import tempfile
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from cores.gemini.runtime import GeminiRuntime, load_api_keys


class GeminiRuntimeTests(unittest.TestCase):
    def test_load_api_keys_ignores_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keys.txt"
            path.write_text("first\n\n second \n", encoding="utf-8")
            self.assertEqual(load_api_keys(path), ["first", "second"])

    def test_switch_updates_current_key_and_persists_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            runtime = GeminiRuntime(
                ["first", "second"], state, lambda **kwargs: kwargs,
            )
            runtime.switch()
            self.assertEqual(runtime.current_key, "second")
            restored = GeminiRuntime(
                ["second", "first"], state, lambda **kwargs: kwargs,
            )
            self.assertEqual(restored.current_key, "second")

    def test_generate_uses_current_client_and_forwards_options(self):
        calls = []

        def generate(client, prompt, model, **options):
            calls.append((client, prompt, model, options))
            return "result"

        with tempfile.TemporaryDirectory() as directory:
            runtime = GeminiRuntime(
                ["key"],
                Path(directory) / "state.json",
                lambda **kwargs: kwargs,
                generate=generate,
            )
            result = runtime.generate(
                "prompt", "model", max_output_tokens=123, thinking_level="high"
            )
        self.assertEqual(result, "result")
        self.assertEqual(calls[0][0], {"api_key": "key"})
        self.assertEqual(calls[0][3]["max_output_tokens"], 123)
        self.assertEqual(calls[0][3]["thinking_level"], "high")

    def test_generate_retries_5xx_forever_without_switching_key(self):
        calls = []
        sleeps = []

        class ServerError(RuntimeError):
            status_code = 503

        def generate(client, prompt, model, **options):
            calls.append(client)
            if len(calls) < 4:
                raise ServerError("raw API response from Gemini")
            return "result"

        with tempfile.TemporaryDirectory() as directory:
            runtime = GeminiRuntime(
                ["first", "second"],
                Path(directory) / "state.json",
                lambda **kwargs: kwargs,
                generate=generate,
                sleep=sleeps.append,
            )
            output = io.StringIO()
            with redirect_stdout(output):
                result = runtime.generate("prompt", "model")

        self.assertEqual(result, "result")
        self.assertEqual(calls, [{"api_key": "first"}] * 4)
        self.assertEqual(sleeps, [15, 15, 15])
        self.assertEqual(
            output.getvalue().count(
                "raw API response from Gemini"
            ),
            3,
        )
        self.assertEqual(output.getvalue().count("Thử lại sau 15 giây"), 3)

    def test_generate_rotates_key_and_retries_429_forever(self):
        calls = []
        sleeps = []

        class RateLimitError(RuntimeError):
            status_code = 429

        def generate(client, prompt, model, **options):
            calls.append(client)
            if len(calls) < 3:
                raise RateLimitError("429 RESOURCE_EXHAUSTED: raw Gemini response")
            return "result"

        with tempfile.TemporaryDirectory() as directory:
            runtime = GeminiRuntime(
                ["first", "second", "third"],
                Path(directory) / "state.json",
                lambda **kwargs: kwargs,
                generate=generate,
                sleep=sleeps.append,
            )
            output = io.StringIO()
            with redirect_stdout(output):
                result = runtime.generate("prompt", "model")

        self.assertEqual(result, "result")
        self.assertEqual(
            calls,
            [
                {"api_key": "first"},
                {"api_key": "second"},
                {"api_key": "third"},
            ],
        )
        self.assertEqual(sleeps, [30, 30])
        self.assertEqual(output.getvalue().count("raw Gemini response"), 2)
        self.assertIn("Đổi API key: 1 → 2", output.getvalue())
        self.assertIn("Đổi API key: 2 → 3", output.getvalue())

    def test_generate_does_not_hide_non_5xx_errors(self):
        def generate(*args, **kwargs):
            raise RuntimeError("bad request")

        with tempfile.TemporaryDirectory() as directory:
            runtime = GeminiRuntime(
                ["key"],
                Path(directory) / "state.json",
                lambda **kwargs: kwargs,
                generate=generate,
                sleep=lambda _seconds: None,
            )
            with self.assertRaisesRegex(RuntimeError, "bad request"):
                runtime.generate("prompt", "model")


if __name__ == "__main__":
    unittest.main()
