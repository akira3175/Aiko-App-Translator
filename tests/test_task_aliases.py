import unittest

from server.jobs import TRANSLATION_KINDS, canonical_task_kind


class TaskAliasTests(unittest.TestCase):
    def test_legacy_interactions_task_uses_canonical_id(self):
        self.assertEqual(canonical_task_kind("v1-interactions"), "interactions")
        self.assertIn("interactions", TRANSLATION_KINDS)
        self.assertNotIn("v1-interactions", TRANSLATION_KINDS)


if __name__ == "__main__":
    unittest.main()
