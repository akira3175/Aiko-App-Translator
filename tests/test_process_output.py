import unittest
from datetime import datetime

from server.jobs import format_process_line, merge_process_output, timestamp_process_line


class ProcessOutputTests(unittest.TestCase):
    def test_quiet_lines_keep_messages_paths_and_error_meaning(self):
        self.assertEqual("Đã chọn chế độ: Nhiệm vụ\n", format_process_line("✅ Đã chọn chế độ: Nhiệm vụ\n"))
        self.assertEqual("[PIPELINE] Hoàn tất\n", format_process_line("[PIPELINE] ✅ Hoàn tất\n"))
        self.assertEqual("[CHÚ Ý] Giữ mặc định\n", format_process_line("⚠️ Giữ mặc định\n"))
        self.assertEqual("[LỖI] Không tìm thấy chương\n", format_process_line("❌ Không tìm thấy chương\n"))
        self.assertEqual("[UPLOAD] C:\\truyen\\失业魔王\\ảnh.md\n", format_process_line("[UPLOAD] C:\\truyen\\失业魔王\\ảnh.md\n"))
        self.assertEqual("    at function()\n", format_process_line("    at function()\n"))
        self.assertEqual("", timestamp_process_line("─" * 55 + "\n"))

    def test_major_steps_get_one_blank_line(self):
        output = "[08:30:24] Streaming hoàn tất.\n"
        output = merge_process_output(output, "[08:30:24] [PIPELINE] Bước 1 — Biên tập trau chuốt...\n")
        self.assertIn("hoàn tất.\n\n[08:30:24]", output)
        output = merge_process_output(output, "\n")
        output = merge_process_output(output, "\n")
        self.assertTrue(output.endswith("\n\n"))
        self.assertFalse(output.endswith("\n\n\n"))

    def test_clean_progress_still_replaces_live_counter(self):
        output = ""
        for count in (10, 100, 1000):
            output = merge_process_output(output, timestamp_process_line(f"✍️ Đang nhận: {count} ký tự...\n"))
        self.assertEqual(1, len(output.splitlines()))
        self.assertIn("1000 ký tự", output)
        self.assertNotIn("✍", output)

    def test_hako_countdown_updates_one_line_and_preserves_chapter_logs(self):
        output = "[13:34:03] Đã cập nhật chương 1\n"
        for remaining in range(10, 0, -1):
            output = merge_process_output(
                output,
                f"[13:34:12] Chờ {remaining} giây trước khi cập nhật chương tiếp theo…\n",
            )
        self.assertEqual(len(output.splitlines()), 2)
        self.assertIn("Chờ 1 giây", output)
        output = merge_process_output(output, "[13:34:13] [2/50]\n")
        output = merge_process_output(output, "Đã cập nhật chương 2\n")
        output = merge_process_output(output, "Chờ 10 giây trước khi cập nhật chương tiếp theo…\n")
        self.assertEqual(len(output.splitlines()), 5)
        self.assertIn("[2/50]", output)

    def test_adds_timestamp_to_non_empty_process_line(self):
        line = timestamp_process_line(
            "Đang dịch chương 1...\n",
            now=datetime(2026, 8, 27, 23, 41, 8),
        )
        self.assertEqual("[23:41:08] Đang dịch chương 1...\n", line)

    def test_keeps_blank_process_lines_untouched(self):
        self.assertEqual("\n", timestamp_process_line("\n"))

    def test_replaces_chatgpt_receive_progress_line(self):
        output = "Bắt đầu\n✍️ Đang nhận: 13 ký tự...\n"
        updated = merge_process_output(output, "✍️ Đang nhận: 1269 ký tự...\n")
        self.assertEqual(updated, "Bắt đầu\n✍️ Đang nhận: 1269 ký tự...\n")

    def test_keeps_normal_log_after_progress(self):
        output = "✍️ Đang nhận: 1269 ký tự...\n"
        self.assertEqual(
            merge_process_output(output, "Hoàn tất\n"),
            "✍️ Đang nhận: 1269 ký tự...\nHoàn tất\n",
        )

    def test_replaces_timestamped_stream_progress_line(self):
        output = "[23:41:08] ✍️ Đang nhận: 1269 ký tự...\n"
        updated = merge_process_output(
            output, "[23:41:09] ✍️ Đang nhận: 2048 ký tự...\n"
        )
        self.assertEqual("[23:41:09] ✍️ Đang nhận: 2048 ký tự...\n", updated)


if __name__ == "__main__":
    unittest.main()
