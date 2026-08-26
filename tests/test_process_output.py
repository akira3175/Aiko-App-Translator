import unittest
from datetime import datetime

from server.jobs import merge_process_output, timestamp_process_line


class ProcessOutputTests(unittest.TestCase):
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
