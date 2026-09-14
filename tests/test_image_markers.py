import tempfile
import unittest
import importlib
import os
from pathlib import Path
from unittest.mock import Mock, patch

from cores.chapters.files import load_md_chapter, save_translated_md
from cores.chapters.images import mark_images, restore_images, uses_image_markers
from cores.translation.prompts import build_single_prompt
from cores.postprocess.polish import polish_translation
from cores.postprocess.language_check import fix_translation


class ImageMarkerTests(unittest.TestCase):
    def test_inline_consecutive_and_parenthesized_image_paths(self):
        source = "Before ![a](../image/a(1).webp)![b](b.png) after"
        marked, images = mark_images(source)
        self.assertEqual("Before [[IMAGE_001]][[IMAGE_002]] after", marked)
        self.assertEqual(source, restore_images(marked, images))

    def test_invalid_markers_are_rejected(self):
        _, images = mark_images("![a](a.png)\n\n![b](b.webp)")
        for output in (
            "missing", "[[IMAGE_001]]", "[[IMAGE_001]][[IMAGE_001]][[IMAGE_002]]",
            "[[IMAGE_002]][[IMAGE_001]]", "[[IMAGE_001]][[IMAGE_003]]",
            "[[IMAGE_001]][[IMAGE_002]][[IMAGE_999]]",
            "[[IMAGE_001]][[IMAGE_002]]![extra](x.png)",
        ):
            with self.subTest(output=output), self.assertRaises(ValueError):
                restore_images(output, images)
        with self.assertRaises(ValueError):
            restore_images("[[IMAGE_001]][[IMAGE_002]]", images, "[[IMAGE_001]]")

    def test_merged_paragraphs_save_and_reload_for_polish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "v1_c1_s1.md"
            source.write_text("# Original\n\nFirst\n\nSecond\n\n![a](a.webp)\n\nThird", encoding="utf-8")
            chapter = load_md_chapter(source, image_markers=True)
            self.assertIn("Second\n\n[[IMAGE_001]]\n\nThird", chapter["content"])
            self.assertIn("[[IMAGE_001]]", build_single_prompt(chapter, "", "", ""))
            saved = Path(save_translated_md(source, root / "translated", "Title",
                "Merged first and second\n\n[[IMAGE_001]]\n\nLast", image_markers=chapter["_image_markers"]))
            expected = "# Title\n\nMerged first and second\n\n![a](a.webp)\n\nLast\n"
            self.assertEqual(expected, saved.read_text(encoding="utf-8"))
            self.assertTrue(uses_image_markers(saved))
            reloaded = load_md_chapter(saved, image_markers=uses_image_markers(saved))
            self.assertEqual("Merged first and second\n\n[[IMAGE_001]]\n\nLast", reloaded["content"])
            with self.assertRaises(ValueError):
                save_translated_md(source, saved.parent, "Bad", "Lost image", image_markers=chapter["_image_markers"])
            self.assertEqual(expected, saved.read_text(encoding="utf-8"))
            save_translated_md(source, saved.parent, "Legacy", "First\nSecond\nThird")
            self.assertFalse(uses_image_markers(saved))

    def test_no_images_and_reserved_marker_collision(self):
        self.assertEqual(("Plain text", {}), mark_images("Plain text"))
        self.assertEqual("Translated", restore_images("Translated", {}))
        with self.assertRaises(ValueError):
            mark_images("A literal [[IMAGE_001]]")

    def test_polish_retries_missing_marker_and_preserves_valid_result(self):
        runtime = Mock()
        runtime.model_and_thinking.return_value = ("model", "high")
        runtime.provider.return_value = "test"
        runtime.int_option.return_value = 20
        runtime.project_polish_prompt.return_value = ("Editor", "Polish")
        runtime.wrap_r19_prompt.side_effect = lambda value: value
        runtime.generate.side_effect = [
            ("###TITLE###\nTitle\n###CONTENT###\nLost\n###END###", "test", "model"),
            ("###TITLE###\nTitle\n###CONTENT###\nBefore [[IMAGE_001]] after\n###END###", "test", "model"),
        ]
        chapter = {"translation": "Before [[IMAGE_001]] after", "_image_markers": {"[[IMAGE_001]]": "![a](a.png)"}}
        with patch("cores.postprocess.polish.build_characters_snapshot", return_value=None), patch("cores.postprocess.polish.time.sleep"):
            result = polish_translation(runtime, chapter, 1, "", "", None, None)
        self.assertEqual(("Title", "Before [[IMAGE_001]] after"), result)
        self.assertEqual(2, runtime.generate.call_count)
        self.assertIn("đúng một lần", runtime.generate.call_args.args[1])

    def test_language_fix_does_not_accept_missing_image(self):
        runtime = Mock()
        runtime.FIX_MAX_RETRY = 2
        runtime.model_and_thinking.return_value = ("model", "high")
        runtime.has_foreign.return_value = True
        runtime.wrap_r19_prompt.side_effect = lambda value: value
        runtime.generate.side_effect = [
            ("###TITLE###\nTitle\n###CONTENT###\nLost\n###END###", "test", "model"),
            ("###TITLE###\nTitle\n###CONTENT###\nFixed [[IMAGE_001]]\n###END###", "test", "model"),
        ]
        chapter = {"translation": "Original [[IMAGE_001]]", "_image_markers": {"[[IMAGE_001]]": "![a](a.png)"}}
        with patch("cores.postprocess.language_check.time.sleep"), patch("cores.postprocess.language_check.save_manual_check_id"):
            result = fix_translation(runtime, chapter, 1)
        self.assertEqual(("Title", "Fixed [[IMAGE_001]]"), result)
        self.assertEqual(2, runtime.generate.call_count)

    def test_standalone_polish_keeps_saved_mode_when_setting_is_off(self):
        module = importlib.import_module("cores.postprocess.__main__")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_dir = root / "raw"
            raw_dir.mkdir()
            translated_dir = root / "translated"
            source = raw_dir / "v1_c1_s1.md"
            source.write_text("# Source\n\nOne\n\nTwo\n\n![a](a.png)\n\nThree", encoding="utf-8")
            chapter = load_md_chapter(source, image_markers=True)
            saved = save_translated_md(source, translated_dir, "Title", "Merged [[IMAGE_001]] after", image_markers=chapter["_image_markers"])

            def polish(item, *_args, **_kwargs):
                self.assertEqual("Merged [[IMAGE_001]] after", item["translation"])
                self.assertEqual(chapter["_image_markers"], item["_image_markers"])
                return "Title", "Polished [[IMAGE_001]] after"

            with patch.dict(os.environ), patch.object(module, "RAW_DIR", raw_dir), patch.object(module, "TRANSLATED_DIR", translated_dir), patch.object(module, "task_config", return_value={"image_markers": "off"}), patch.object(module, "option", return_value=source.name), patch.object(module, "filtered_context_and_names", return_value=("", [], None)), patch.object(module, "format_pronoun_context", return_value=""), patch.object(module, "runtime") as runtime:
                runtime.provider.return_value = "test"
                runtime.polish_translation.side_effect = polish
                runtime.fix_translation.side_effect = lambda item, *_args: (item["title_translation"], item["translation"])
                module.main()
            self.assertEqual("# Title\n\nPolished ![a](a.png) after\n", Path(saved).read_text(encoding="utf-8"))
            self.assertTrue(uses_image_markers(saved))


if __name__ == "__main__":
    unittest.main()
