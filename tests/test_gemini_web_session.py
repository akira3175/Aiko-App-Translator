import unittest

from cores.gemini.web_session import GeminiWebSession


class _Options:
    def __init__(self):
        self.arguments = []
        self.experimental = {}

    def add_argument(self, value):
        self.arguments.append(value)

    def add_experimental_option(self, key, value):
        self.experimental[key] = value


class _Driver:
    current_url = "https://gemini.google.com/app"

    def __init__(self):
        self.closed = False
        self.cdp = []

    def execute_cdp_cmd(self, name, value):
        self.cdp.append((name, value))

    def quit(self):
        self.closed = True


class GeminiWebSessionTests(unittest.TestCase):
    def test_reuses_and_closes_one_driver(self):
        created = []

        def create_driver(**_kwargs):
            driver = _Driver()
            created.append(driver)
            return driver

        session = GeminiWebSession(
            "profile",
            lambda: "service",
            lambda _options: None,
            lambda: None,
            driver_factory=create_driver,
            options_factory=_Options,
        )
        first = session.get_driver()
        self.assertIs(first, session.get_driver())
        self.assertEqual(1, len(created))
        self.assertEqual(1, len(first.cdp))

        session.close()
        self.assertTrue(first.closed)
        self.assertIsNone(session.driver)


if __name__ == "__main__":
    unittest.main()
