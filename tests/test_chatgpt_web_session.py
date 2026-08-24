import unittest
from unittest.mock import patch

from cores.chatgpt import web_client
from cores.chatgpt.web_session import ChatGPTWebSession
from cores.json_output import parse_complete_json_object


class _Options:
    def add_argument(self, _value):
        pass

    def add_experimental_option(self, _key, _value):
        pass


class _Driver:
    current_url = "https://chatgpt.com/"

    def __init__(self):
        self.closed = False
        self.visited = []

    def execute_cdp_cmd(self, _name, _value):
        pass

    def get(self, url):
        self.visited.append(url)

    def quit(self):
        self.closed = True


class ChatGPTWebSessionTests(unittest.TestCase):
    def test_web_completion_only_accepts_known_json_schemas(self):
        self.assertTrue(web_client._is_known_structured_response('{"character_pairs": []}'))
        self.assertTrue(web_client._is_known_structured_response('{"overall_score": 9, "issues": []}'))
        self.assertFalse(web_client._is_known_structured_response('Bản dịch có {"note": "ví dụ"}'))

    def test_complete_json_detection_accepts_plain_and_legacy_output(self):
        plain = '{"character_pairs": []}'
        legacy = '```json\n{"character_pairs": []}\n```\n###END###'
        surrounded = 'Dưới đây là kết quả:\n{"character_pairs": []}\nHy vọng hữu ích!'
        self.assertEqual({"character_pairs": []}, parse_complete_json_object(plain))
        self.assertEqual({"character_pairs": []}, parse_complete_json_object(legacy))
        self.assertEqual({"character_pairs": []}, parse_complete_json_object(surrounded))
        self.assertIsNone(parse_complete_json_object('{"character_pairs": ['))

    def test_end_marker_waits_three_seconds_and_uses_refreshed_response(self):
        with patch.object(web_client.time, "sleep") as sleep, patch.object(
            web_client, "_chatgpt_response_text", return_value="JSON}\n###END###\n"
        ):
            result = web_client._settle_end_marker_response(
                object(), object(), "token", 1, "JSON}\n###END###"
            )

        sleep.assert_called_once_with(3)
        self.assertEqual(result, "JSON}\n###END###\n")

    def test_reuses_and_closes_driver(self):
        created = []

        def create(**_kwargs):
            driver = _Driver()
            created.append(driver)
            return driver

        session = ChatGPTWebSession(
            "profile",
            lambda: "service",
            lambda _options: None,
            driver_factory=create,
            options_factory=_Options,
        )
        driver = session.get_driver()
        self.assertIs(driver, session.get_driver())
        self.assertEqual(1, len(created))
        session.close()
        self.assertTrue(driver.closed)

    def test_setup_opens_configured_chat_link(self):
        driver = _Driver()
        session = ChatGPTWebSession(
            "profile",
            lambda: "service",
            lambda _options: None,
            driver_factory=lambda **_kwargs: driver,
            options_factory=_Options,
        )
        link = "https://chatgpt.com/c/custom-chat"
        session.setup(skip_login_prompt=True, link=link)
        self.assertEqual([link], driver.visited)


if __name__ == "__main__":
    unittest.main()
