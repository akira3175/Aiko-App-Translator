import unittest
from unittest.mock import patch

from cores.translation.orchestration import run_requested_chapters


class StageRunnerTests(unittest.TestCase):
    def test_blank_limit_runs_until_no_chapter_remains(self):
        remaining = [1, 1, 0]
        with patch("cores.translation.orchestration.stop_requested", return_value=False):
            processed = run_requested_chapters(None, lambda: remaining.pop(0))
        self.assertEqual(processed, 2)

    def test_numeric_limit_stops_at_exact_total(self):
        calls = []

        def run_chapter():
            calls.append(1)
            return 1

        with patch("cores.translation.orchestration.stop_requested", return_value=False):
            processed = run_requested_chapters(3, run_chapter)
        self.assertEqual(processed, 3)
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
