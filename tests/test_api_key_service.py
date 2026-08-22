import tempfile
import unittest
from pathlib import Path

from services.api_keys import diagnostics, repository


class _Models:
    def __init__(self, error=None):
        self.error = error

    def generate_content(self, **_kwargs):
        if self.error:
            raise self.error


class _Client:
    def __init__(self, error=None):
        self.models = _Models(error)


class _ApiError(Exception):
    def __init__(self, code):
        super().__init__(str(code))
        self.code = code


class ApiKeyServiceTests(unittest.TestCase):
    def test_active_key_survives_reordering_by_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keys_file = root / "keys.txt"
            state_file = root / "state.json"
            repository.save(
                {"keys": ["first-key", "second-key"]}, keys_file, state_file
            )
            repository.set_active(
                {"active_index": 1}, keys_file, state_file
            )
            repository.save(
                {"keys": ["second-key", "first-key"]}, keys_file, state_file
            )

            result = repository.payload(keys_file, state_file)

        self.assertEqual(0, result["active_index"])
        self.assertEqual("second-key", result["keys"][result["active_index"]])

    def test_diagnostic_reports_429_without_hiding_provider_reason(self):
        result = diagnostics.test_key(
            "valid-key",
            "test-model",
            client_factory=lambda **_kwargs: _Client(_ApiError(429)),
            config_factory=lambda **kwargs: kwargs,
        )

        self.assertFalse(result["ok"])
        self.assertEqual("429", result["code"])
        self.assertIn("quota", result["message"])

    def test_diagnostic_makes_bounded_generation_request(self):
        calls = []

        class RecordingModels:
            def generate_content(self, **kwargs):
                calls.append(kwargs)

        class RecordingClient:
            models = RecordingModels()

        result = diagnostics.test_key(
            "valid-key",
            "test-model",
            client_factory=lambda **_kwargs: RecordingClient(),
            config_factory=lambda **kwargs: kwargs,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(8, calls[0]["config"]["max_output_tokens"])


if __name__ == "__main__":
    unittest.main()
