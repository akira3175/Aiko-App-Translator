import unittest

import app


class TaskAliasTests(unittest.TestCase):
    def test_legacy_interactions_task_uses_canonical_id(self):
        self.assertEqual(app.canonical_task_kind("v1-interactions"), "interactions")
        self.assertIn("interactions", app.PIPELINES)
        self.assertNotIn("v1-interactions", app.PIPELINES)


if __name__ == "__main__":
    unittest.main()
