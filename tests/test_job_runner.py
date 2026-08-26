import json
import tempfile
import unittest
from pathlib import Path

from server.job_runner import JobRunner


class _Process:
    def __init__(self, returncode=0):
        self.pid = 321
        self.returncode = returncode


class JobRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "Demo"
        self.raw = self.project / "raw"
        self.translated = self.project / "translated"
        self.raw.mkdir(parents=True)
        self.translated.mkdir()
        self.pipeline = self.root / "pipeline.py"
        self.pipeline.write_text("", encoding="utf-8")
        self.interactions = self.root / "interactions.py"
        self.interactions.write_text("", encoding="utf-8")
        self.jobs = {}
        self.processes = {}
        self.events = {}
        self.started = []
        self.released = []
        self.pids = []
        self.process = _Process()

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, stream=None):
        def popen(*args, **kwargs):
            self.started.append((args, kwargs))
            return self.process

        return JobRunner(
            root=self.root,
            pipelines={
                "pipeline": self.pipeline,
                "interactions": self.interactions,
                "manual": self.pipeline,
            },
            jobs=self.jobs,
            processes=self.processes,
            stream_events=self.events,
            saved_settings=lambda: {"base": True, "shared": "settings"},
            task_options=lambda _project: {"r19": True, "shared": "r19"},
            safe_project=lambda _name: self.project,
            project_folders=lambda _name: (self.raw, self.translated),
            safe_file=lambda folder, name: folder / name,
            translation_stop_file=lambda claim: self.root / f"{claim}.stop",
            update_translation_pid=lambda claim, pid: self.pids.append((claim, pid)),
            release_translation=self.released.append,
            stream_process_output=stream or (lambda _process, _key: "completed"),
            process_kwargs=lambda: {},
            active_translation=lambda: None,
            popen=popen,
        )

    def test_run_merges_config_and_cleans_process_state(self):
        runner = self.runner()

        runner.run("pipeline", "Demo", {"shared": "request"}, "claim-1")

        environment = self.started[0][1]["env"]
        config = json.loads(environment["NOVEL_WEB_CONFIG"])
        self.assertEqual("r19", config["shared"])
        self.assertEqual("done", self.jobs["pipeline"]["status"])
        self.assertEqual([], list(self.processes))
        self.assertEqual([("claim-1", 321)], self.pids)
        self.assertEqual(["claim-1"], self.released)

    def test_manual_result_is_written_atomically_before_launch(self):
        runner = self.runner()

        runner.run("manual", "Demo", {"manual_result": "Bản dịch"}, "claim-2")

        self.assertEqual(
            "Bản dịch",
            (self.project / ".manual_result.txt").read_text(encoding="utf-8"),
        )
        config = json.loads(self.started[0][1]["env"]["NOVEL_WEB_CONFIG"])
        self.assertNotIn("manual_result", config)
        self.assertTrue(config["manual_result_ready"])

    def test_gemini_api_streaming_routes_pipeline_to_interactions(self):
        streaming_states = []
        runner = self.runner(
            stream=lambda _process, key: streaming_states.append(
                self.jobs[key]["streaming"]
            ) or "completed"
        )

        runner.run(
            "pipeline",
            "Demo",
            {"translate_provider": "gemini-api", "gemini_api_streaming": "on"},
            "claim-stream",
        )

        command = self.started[0][0][0]
        self.assertEqual(str(self.interactions), command[2])
        self.assertEqual([True], streaming_states)

    def test_retranslate_restores_backup_when_process_fails(self):
        chapter = "c1.md"
        target = self.translated / chapter
        target.write_text("old translation", encoding="utf-8")
        self.process = _Process(returncode=1)
        runner = self.runner(stream=lambda _process, _key: "provider failed")

        runner.retranslate("gemini-api", "Demo", chapter, "claim-3")

        self.assertEqual("old translation", target.read_text(encoding="utf-8"))
        self.assertFalse(target.with_suffix(".md.web-backup").exists())
        self.assertEqual("error", self.jobs["retranslate"]["status"])
        self.assertEqual(["claim-3"], self.released)


if __name__ == "__main__":
    unittest.main()
