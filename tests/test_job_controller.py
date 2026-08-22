import tempfile
import unittest
from pathlib import Path

from server.job_controller import JobController, JobRequestError


class _Thread:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.created.append(self)

    def start(self):
        return None


class _Process:
    def __init__(self, pid, return_code=None):
        self.pid = pid
        self.return_code = return_code

    def poll(self):
        return self.return_code


class _Runner:
    def __init__(self, root):
        self.root = root

    def run(self, *_args):
        return None

    def retranslate(self, *_args):
        return None

    def task_stop_file(self, kind):
        return self.root / f"{kind}.stop"


class JobControllerTests(unittest.TestCase):
    def setUp(self):
        _Thread.created.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "Demo"
        (self.project / "raw").mkdir(parents=True)
        (self.project / "translated").mkdir()
        self.pipeline = self.root / "pipeline.py"
        self.pipeline.write_text("", encoding="utf-8")
        self.jobs = {}
        self.processes = {}
        self.terminated = []

    def tearDown(self):
        self.temp.cleanup()

    def controller(self, **overrides):
        values = {
            "pipelines": {"pipeline": self.pipeline, "review": self.pipeline},
            "jobs": self.jobs,
            "processes": self.processes,
            "translation_kinds": {"pipeline", "manual"},
            "canonical_kind": lambda value: str(value),
            "active_translation": lambda: None,
            "safe_project": lambda _name: self.project,
            "validate_hako_targets": lambda value: value,
            "pipeline_config": lambda value: value,
            "project_folders": lambda _name: (
                self.project / "raw",
                self.project / "translated",
            ),
            "safe_file": lambda folder, name: folder / name,
            "claim_translation": lambda _kind, _project: "claim-1",
            "release_translation": lambda _claim: None,
            "runner": _Runner(self.root),
            "translation_stop_file": lambda claim: self.root / f"{claim}.stop",
            "terminate_process_tree": self.terminated.append,
            "thread_factory": _Thread,
        }
        values.update(overrides)
        return JobController(**values)

    def test_start_converts_numeric_limits_before_launch(self):
        result = self.controller().start(
            "pipeline",
            "Demo",
            {"config": {"max_chapters": "3", "batch_runs": "0"}},
        )

        config = _Thread.created[0].kwargs["args"][2]
        self.assertEqual({"ok": True}, result)
        self.assertEqual(3, config["max_chapters"])
        self.assertEqual(0, config["batch_runs"])

    def test_start_reports_conflict_when_pipeline_is_running(self):
        self.jobs["pipeline"] = {"status": "running"}

        with self.assertRaises(JobRequestError) as raised:
            self.controller().start("pipeline", "Demo", {"config": {}})

        self.assertEqual(409, raised.exception.status)
        self.assertEqual([], _Thread.created)

    def test_immediate_cancel_terminates_only_matching_pid(self):
        self.jobs["pipeline"] = {
            "status": "running",
            "claim_id": "claim-1",
        }
        self.processes["pipeline"] = _Process(321)
        controller = self.controller(
            active_translation=lambda: {"claim_id": "claim-1", "pid": 321}
        )

        result = controller.cancel_translation({"mode": "immediate"})

        self.assertEqual({"ok": True, "mode": "immediate"}, result)
        self.assertEqual([321], self.terminated)
        self.assertTrue((self.root / "claim-1.stop").exists())

    def test_immediate_cancel_rejects_process_with_different_pid(self):
        self.jobs["pipeline"] = {
            "status": "running",
            "claim_id": "claim-1",
        }
        self.processes["pipeline"] = _Process(999)
        controller = self.controller(
            active_translation=lambda: {"claim_id": "claim-1", "pid": 321}
        )

        with self.assertRaisesRegex(JobRequestError, "đúng tiến trình"):
            controller.cancel_translation({"mode": "immediate"})

        self.assertEqual([], self.terminated)


if __name__ == "__main__":
    unittest.main()
