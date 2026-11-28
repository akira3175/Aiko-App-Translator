import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
BRIDGE = APP_ROOT / ".agents" / "skills" / "aiko-novel-pipeline" / "scripts" / "aiko_bridge.py"


class AikoBridgeTests(unittest.TestCase):
    def _run_bridge(self, *args: str) -> dict:
        completed = subprocess.run(
            [sys.executable, str(BRIDGE), *args],
            cwd=str(APP_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if completed.returncode != 0:
            self.fail(f"Bridge failed ({completed.returncode}): {completed.stderr}\n{completed.stdout}")
        lines = [ln for ln in completed.stdout.strip().splitlines() if ln.strip()]
        # Find trailing JSON block
        raw_out = completed.stdout.strip()
        start = raw_out.find("{")
        self.assertGreaterEqual(start, 0, f"Expected JSON in stdout, got: {raw_out}")
        return json.loads(raw_out[start:])

    def test_end_to_end_prepare_and_commit_stages(self):
        project_name = "_test_aiko_bridge_tmp"
        project_dir = APP_ROOT / "truyen" / project_name
        try:
            raw_dir = project_dir / "raw"
            trans_dir = project_dir / "translated"
            raw_dir.mkdir(parents=True, exist_ok=True)
            trans_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / "v1_c1_s1.md").write_text(
                "# 제1화 입학식\n\n사무엘 아즈얀은 베니샤에게 인사했다.\n",
                encoding="utf-8",
            )

            with tempfile.TemporaryDirectory() as scratch_str:
                scratch = Path(scratch_str)

                # 1. Status
                st = self._run_bridge("status", "--project", project_name)
                self.assertEqual(st["total_raw"], 1)
                self.assertEqual(st["total_translated"], 0)

                # 2. Glossary prepare & commit
                g_dir = scratch / "glossary"
                g_meta = self._run_bridge("glossary-prepare", "--project", project_name, "--count", "5", "--out", str(g_dir))
                self.assertEqual(g_meta["chapter_count"], 1)
                g_res = g_dir / "res.txt"
                g_res.write_text("###START###\n사무엘 아즈얀 = Samuel Azyan\n베니샤 = Benisha\n###END###", encoding="utf-8")
                g_commit = self._run_bridge("glossary-commit", "--project", project_name, "--bundle", str(g_dir), "--in", str(g_res))
                self.assertEqual(g_commit["glossary_terms_count"], 2)

                # 3. Characters prepare & commit
                c_dir = scratch / "chars"
                self._run_bridge("characters-prepare", "--project", project_name, "--count", "5", "--out", str(c_dir))
                c_res = c_dir / "res.json"
                c_res.write_text(
                    json.dumps({
                        "characters": [
                            {
                                "name": "Samuel Azyan",
                                "updates": [{"field": "gender", "value": "Nam", "chapter": "v1_c1_s1"}],
                                "events": [{"chapter": "v1_c1_s1", "text": "Chào Benisha tại lễ nhập học."}],
                            }
                        ]
                    }, ensure_ascii=False),
                    encoding="utf-8",
                )
                c_commit = self._run_bridge("characters-commit", "--project", project_name, "--bundle", str(c_dir), "--in", str(c_res))
                self.assertEqual(c_commit["new_index"], 1)

                # 4. Translate prepare & commit
                t_dir = scratch / "trans"
                t_meta = self._run_bridge("translate-prepare", "--project", project_name, "--out", str(t_dir))
                self.assertEqual(t_meta["chapter"], "v1_c1_s1.md")
                t_res = t_dir / "res.txt"
                t_res.write_text(
                    "###TITLE###\nChương 1: Lễ nhập học\n###CONTENT###\nSamuel Azyan mỉm cười chào Benisha.\n###END###",
                    encoding="utf-8",
                )
                t_commit = self._run_bridge("translate-commit", "--project", project_name, "--bundle", str(t_dir), "--in", str(t_res))
                self.assertTrue(t_commit["ok"])

                # 5. Polish (--with-pronouns) prepare & commit
                p_dir = scratch / "polish"
                self._run_bridge("polish-prepare", "--project", project_name, "--chapter", "v1_c1_s1.md", "--with-pronouns", "--out", str(p_dir))
                p_res = p_dir / "res.txt"
                p_res.write_text(
                    '###TITLE###\nChương 1: Lễ nhập học\n###CONTENT###\n"Chào em," Samuel Azyan mỉm cười chào Benisha.\n'
                    '###PRONOUNS###\n{"character_pairs":[{"speaker":"Samuel Azyan","listener":"Benisha","speaker_self":"anh","speaker_to_listener":"em","temporary_address":"","relationship_status":"Vợ chồng mới cưới","emotional_tone":"Ấm áp"}]}\n'
                    "###END###",
                    encoding="utf-8",
                )
                p_commit = self._run_bridge("polish-commit", "--project", project_name, "--bundle", str(p_dir), "--in", str(p_res))
                self.assertEqual(p_commit["pronouns_updated"], 1)

                # 6. Review prepare & commit
                r_dir = scratch / "review"
                self._run_bridge("review-prepare", "--project", project_name, "--chapter", "v1_c1_s1.md", "--out", str(r_dir))
                r_res = r_dir / "res.json"
                r_res.write_text(
                    json.dumps({
                        "chapter_id": "v1_c1_s1",
                        "overall_score": 9.5,
                        "issues": [],
                        "gender_ok": True,
                        "address_ok": True,
                        "summary": "Bản dịch mượt và chính xác.",
                    }, ensure_ascii=False),
                    encoding="utf-8",
                )
                r_commit = self._run_bridge("review-commit", "--project", project_name, "--bundle", str(r_dir), "--in", str(r_res))
                self.assertEqual(r_commit["score"], 9.5)
        finally:
            import shutil
            shutil.rmtree(project_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
