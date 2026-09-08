import subprocess
import unittest
from pathlib import Path


class FrontendRuntimeTests(unittest.TestCase):
    def test_app_modules_initialize_without_runtime_error(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", "tests/frontend_runtime_check.mjs"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("runtime-import-ok", result.stdout)

    def test_project_loading_delay_retry_and_stale_completion(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", "tests/project_loading_check.mjs"], cwd=root,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_web_review_hides_parallel_workers(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "web" / "features" / "pipeline.js").read_text(
            encoding="utf-8"
        )
        settings_script = (root / "web" / "features" / "settings.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("filter(([id])=>id!=='workers')", script)
        self.assertIn("config.workers=1", script)
        self.assertIn("xử lý tuần tự từng chương", script)
        self.assertIn("function render(nextItems)", settings_script)
        self.assertIn("let activeGroup='pipeline'", settings_script)
        self.assertIn("items=nextItems", settings_script)
        self.assertNotIn("items=items", settings_script)
        self.assertIn("const button=$('#savePythonSettings')", settings_script)
        self.assertIn("const button=$('#resetPythonSettings')", settings_script)
        self.assertNotIn("const button=$('#save')", settings_script)
        self.assertNotIn("const button=$('#reset')", settings_script)

    def test_editor_review_uses_the_configured_review_provider(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "web" / "features" / "project-memory.js").read_text(
            encoding="utf-8"
        )
        app = (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("review_provider:getSetting('pipeline_review_provider')", script)
        self.assertIn("review_stage_model:getSetting('pipeline_review_model')", script)
        self.assertIn("review_stage_thinking:getSetting('pipeline_review_thinking')", script)
        self.assertIn("getSetting:key=>settingsFeature.getValue(key)", app)

    def test_hako_edit_uses_injected_project_and_pipeline_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "web" / "features" / "hako-edit.js").read_text(
            encoding="utf-8"
        )
        app = (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("executePipeline,getProject,getTargets", script)
        self.assertIn("hako-public-url:${getProject()||''}", script)
        self.assertNotIn("hako-public-url:${state.project||''}", script)
        self.assertIn(
            "createHakoEditFeature({api,escapeHtml,executePipeline:(...args)=>pipelineFeature.execute(...args)",
            app,
        )

    def test_console_only_follows_output_when_reader_is_near_bottom(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "web" / "features" / "pipeline.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("let consoleFollowOutput=true", script)
        self.assertIn("consoleFollowOutput=distanceFromBottom<=24", script)
        self.assertIn("const shouldFollow=consoleFollowOutput&&distanceFromBottom<=24", script)
        self.assertIn("if(shouldFollow)output.scrollTop=output.scrollHeight", script)
        self.assertIn("else output.scrollTop=previousTop", script)

    def test_pipeline_model_sources_reference_available_settings(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "web" / "features" / "settings.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("context:['context_model','gemini_api_thinking']", script)
        self.assertIn("characters:['translate_model','gemini_api_thinking']", script)
        self.assertNotIn("characters:['character_model'", script)
        self.assertIn("pronouns:['ai_studio_pronoun_model','ai_studio_thinking']", script)
        self.assertIn("review:['ai_studio_review_model','ai_studio_thinking']", script)
        self.assertIn("default:sourceModel?.default||''", script)

    def test_focus_mode_fills_viewport_and_restores_short_label(self):
        root = Path(__file__).resolve().parents[1]
        editor_script = (root / "web" / "features" / "editor.js").read_text(
            encoding="utf-8"
        )
        styles = (root / "web" / "ui-refinement.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("?'Thoát tập trung':'Tập trung'", editor_script)
        self.assertIn("body.focus #workspaceView.active {\n  height: 100dvh;", styles)
        self.assertIn("body.focus #workspaceView.active .editor-grid {\n  height: auto;", styles)

    def test_gemini_api_streaming_opens_the_existing_job_event_stream(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "web" / "features" / "pipeline.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("config.gemini_api_streaming=saved('gemini_api_streaming')||'off'", script)
        self.assertIn("config.gemini_api_streaming==='on'", script)
        self.assertIn("if(streaming)openNovelEventStream(kind)", script)

    def test_job_events_refresh_review_and_open_ai_log_only(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "web" / "features" / "pipeline.js").read_text(
            encoding="utf-8"
        )
        app = (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("if(event.type==='review_saved'){reviewsChanged=true;continue;}", script)
        self.assertIn("if(reviewsChanged)await loadReviews", script)
        self.assertIn("if(aiLogsChanged&&$('#aiLogDrawer').classList.contains('open'))", script)
        self.assertIn("{aiLogFeature,api,editorRuntime", app)


if __name__ == "__main__":
    unittest.main()
