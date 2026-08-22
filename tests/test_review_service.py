import json
import tempfile
import unittest
from pathlib import Path

from services.reviews import ReviewService


class ReviewServiceTests(unittest.TestCase):
    def _service(self, project):
        return ReviewService(lambda _name: project)

    def test_payload_chooses_first_source_and_sorts_chapters(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "review_z.json").write_text("{}", encoding="utf-8")
            (project / "review_a.json").write_text(
                json.dumps(
                    {
                        "later": {"chapter_number": 5, "issues": [1, 2]},
                        "first": {"chapter_number": 1, "issue_count": 1},
                    }
                ),
                encoding="utf-8",
            )

            result = self._service(project).payload("project")

            self.assertEqual("review_a.json", result["source"])
            self.assertEqual(
                ["review_a.json", "review_z.json"], result["sources"]
            )
            self.assertEqual(
                ["first", "later"],
                [item["chapter_id"] for item in result["items"]],
            )
            self.assertEqual(2, result["items"][1]["issue_count"])

    def test_source_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(Path(directory))
            with self.assertRaisesRegex(ValueError, "Invalid review source"):
                service.data("project", "../review.json")


if __name__ == "__main__":
    unittest.main()
