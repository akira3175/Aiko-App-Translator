import unittest
from unittest.mock import Mock, patch
from cores.gemini import web_client as client
from cores.gemini.web_response import submission_state
from cores.web_errors import RetryableWebError, WebQuotaError, WebSubmissionUncertain


class SubmissionTests(unittest.TestCase):
    def test_user_turn_without_activity_is_pending(self):
        driver = Mock()
        driver.execute_script.side_effect = [True, None]
        self.assertEqual('pending', submission_state(driver, 'token', 0))

    def test_no_new_turn_or_answer_is_absent(self):
        driver = Mock()
        driver.execute_script.side_effect = [False, None]
        self.assertEqual('absent', submission_state(driver, 'token', 1))

    def test_empty_response_shell_is_pending(self):
        root = Mock()
        root.find_elements.return_value = []
        driver = Mock()
        driver.execute_script.side_effect = [True, root]
        self.assertEqual('pending', submission_state(driver, 'token', 0))

    def test_thinking_in_new_response_confirms_processing(self):
        root = Mock()
        thinking = Mock(text='Analyzing the request')
        root.find_elements.side_effect = [[], [], [thinking]]
        driver = Mock()
        driver.execute_script.side_effect = [True, root]
        self.assertEqual('processing', submission_state(driver, 'token', 0))

    def test_wait_accepts_delayed_send(self):
        with patch.object(client, 'check_quota'), patch.object(client, '_gemini_submission_state', side_effect=['absent', 'processing']) as sent, patch.object(client.time, 'monotonic', side_effect=[0, 1]), patch.object(client.time, 'sleep'):
            client._wait_for_submission(Mock(), 'token', 0)
        self.assertEqual(2, sent.call_count)

    def test_unsent_prompt_fails_in_30_seconds(self):
        with patch.object(client, 'check_quota'), patch.object(client, '_gemini_submission_state', return_value='absent') as sent, patch.object(client.time, 'monotonic', side_effect=[0, 30]):
            with self.assertRaisesRegex(RetryableWebError, '30 giây'):
                client._wait_for_submission(Mock(), 'token', 0)
        self.assertEqual(2, sent.call_count)

    def test_last_history_check_prevents_resend(self):
        with patch.object(client, 'check_quota'), patch.object(client, '_gemini_submission_state', side_effect=['absent', 'processing']), patch.object(client.time, 'monotonic', side_effect=[0, 30]):
            client._wait_for_submission(Mock(), 'token', 0)

    def test_quota_exits_without_waiting(self):
        with patch.object(client, 'check_quota', side_effect=WebQuotaError('quota')), patch.object(client, '_gemini_submission_state') as sent:
            with self.assertRaises(WebQuotaError):
                client._wait_for_submission(Mock(), 'token', 0)
        sent.assert_not_called()

    def test_pending_times_out_without_resending(self):
        with patch.object(client, 'check_quota'), patch.object(client, '_gemini_submission_state', return_value='pending'), patch.object(client.time, 'monotonic', side_effect=[0, 90]):
            with self.assertRaises(WebSubmissionUncertain):
                client._wait_for_submission(Mock(), 'token', 0)

    def test_pending_then_processing_is_accepted(self):
        with patch.object(client, 'check_quota'), patch.object(client, '_gemini_submission_state', side_effect=['pending', 'processing']), patch.object(client.time, 'monotonic', side_effect=[0, 30]), patch.object(client.time, 'sleep'):
            client._wait_for_submission(Mock(), 'token', 0)

    def test_disappearing_pending_bubble_is_not_resent(self):
        with patch.object(client, 'check_quota'), patch.object(client, '_gemini_submission_state', side_effect=['pending', 'absent', 'absent']), patch.object(client.time, 'monotonic', side_effect=[0, 1, 90]), patch.object(client.time, 'sleep'):
            with self.assertRaises(WebSubmissionUncertain):
                client._wait_for_submission(Mock(), 'token', 0)
