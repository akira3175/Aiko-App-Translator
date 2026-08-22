import unittest
import importlib
from unittest.mock import patch

from providers.registry import pipeline_config, provider_payload
from cores.stages import generate_for_stage


pipeline = importlib.import_module("cores.translation.__main__")


class ProviderRegistryTests(unittest.TestCase):
    def test_exposes_provider_capabilities(self):
        providers = {item["id"]: item for item in provider_payload()}
        self.assertIn("translate", providers["gemini-api"]["capabilities"]["stages"])
        self.assertIn("review", providers["openai-api"]["capabilities"]["stages"])
        self.assertIn("polish", providers["gemini-web"]["capabilities"]["stages"])
        self.assertIn("pronouns", providers["gemini-web"]["capabilities"]["stages"])
        self.assertIn("review", providers["gemini-web"]["capabilities"]["stages"])
        for provider in providers.values():
            self.assertIn("glossary", provider["capabilities"]["stages"])
            self.assertIn("characters", provider["capabilities"]["stages"])

    def test_resolves_supported_stage_profiles(self):
        config = pipeline_config({
            "translate_provider": "chatgpt-web",
            "polish_provider": "chatgpt-web",
            "pronouns_provider": "off",
            "review_provider": "chatgpt-web",
        })
        self.assertEqual(config["resolved_pipeline"], "stage")
        self.assertEqual(config["stage_providers"]["pronouns"], "off")

    def test_chatgpt_web_can_mix_with_other_stage_providers(self):
        config = pipeline_config({
            "translate_provider": "chatgpt-web",
            "polish_provider": "gemini-api",
            "pronouns_provider": "openai-api",
            "review_provider": "gemini-web",
        })
        self.assertEqual(config["resolved_pipeline"], "stage")
        self.assertEqual(
            config["stage_providers"],
            {
                "translate": "chatgpt-web",
                "polish": "gemini-api",
                "pronouns": "openai-api",
                "review": "gemini-web",
            },
        )

    def test_all_provider_stage_combinations_use_shared_transport_contract(self):
        stages = ("translate", "polish", "pronouns", "review")
        for provider in ("gemini-api", "gemini-web", "openai-api", "chatgpt-web"):
            calls = []

            def transport(prompt, **kwargs):
                calls.append((prompt, kwargs))
                return "ok"

            for stage in stages:
                response = generate_for_stage(
                    provider,
                    stage,
                    "prompt",
                    "model",
                    "high",
                    {provider: transport},
                )
                self.assertEqual(response.text, "ok")
                self.assertEqual(response.provider, provider)
            self.assertEqual(len(calls), 4)

    def test_resolves_mixed_stage_providers(self):
        config = pipeline_config({
            "translate_provider": "gemini-web",
            "polish_provider": "gemini-web",
            "pronouns_provider": "gemini-web",
            "review_provider": "openai-api",
            "translate_stage_model": "translate-model",
            "translate_stage_thinking": "extended",
            "polish_stage_model": "polish-model",
            "polish_stage_thinking": "high",
        })
        self.assertEqual(config["resolved_pipeline"], "stage")
        self.assertNotIn("review_handled_by_postprocess", config)
        self.assertEqual(config["gemini_web_model"], "translate-model")
        self.assertEqual(config["gemini_thinking"], "extended")
        self.assertEqual(config["polish_stage_model"], "polish-model")
        self.assertEqual(config["polish_stage_thinking"], "high")

    def test_pipeline_entrypoint_runs_resolved_compatibility_runner(self):
        config = {
            "translate_provider": "openai-api",
            "polish_provider": "openai-api",
            "pronouns_provider": "off",
            "review_provider": "off",
        }
        with patch.object(pipeline, "task_config", return_value=config), patch.object(
            pipeline, "run_translation"
        ) as run_translation:
            pipeline.main()
        run_translation.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
