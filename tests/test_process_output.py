import unittest

from app import merge_process_output


class ProcessOutputTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
