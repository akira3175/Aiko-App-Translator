import unittest

from cores.chatgpt.web_session import ChatGPTWebSession


class _Options:
    def add_argument(self, _value):
        pass

    def add_experimental_option(self, _key, _value):
        pass


class _Driver:
    current_url = "https://chatgpt.com/"

    def __init__(self):
        self.closed = False

    def execute_cdp_cmd(self, _name, _value):
        pass

    def quit(self):
        self.closed = True


class ChatGPTWebSessionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
