import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores.translation.prompts import build_single_prompt, project_polish_prompt


class TranslationPromptTests(unittest.TestCase):
    def test_project_custom_prompts_are_loaded_from_repository_truyen(self):
        projects_dir = Path(__file__).resolve().parents[1] / "truyen"
        with tempfile.TemporaryDirectory(dir=projects_dir) as directory:
            project = Path(directory)
            (project / "context.json").write_text(
                json.dumps(
                    {
                        "prompt_role": "Vai trò dịch riêng",
                        "prompt_task": "Nhiệm vụ dịch riêng",
                        "polish_prompt_role": "Vai trò hiệu đính riêng",
                        "polish_prompt_task": "Nhiệm vụ hiệu đính riêng",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"NOVEL_PROJECT": project.name}):
                prompt = build_single_prompt(
                    {"title": "Tiêu đề", "content": "Nội dung"}, "", "", ""
                )
                polish_role, polish_task = project_polish_prompt()

        self.assertIn("Vai trò dịch riêng", prompt)
        self.assertIn("Nhiệm vụ dịch riêng", prompt)
        self.assertEqual("Vai trò hiệu đính riêng", polish_role)
        self.assertEqual("Nhiệm vụ hiệu đính riêng", polish_task)


if __name__ == "__main__":
    unittest.main()
