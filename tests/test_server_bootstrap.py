import unittest

from server.bootstrap import run_server


class _Server:
    def __init__(self, interrupt=False):
        self.interrupt = interrupt
        self.served = False
        self.closed = False

    def serve_forever(self):
        self.served = True
        if self.interrupt:
            raise KeyboardInterrupt()

    def server_close(self):
        self.closed = True


class _Timer:
    def __init__(self, delay, callback, calls):
        self.delay = delay
        self.callback = callback
        self.calls = calls

    def start(self):
        self.calls.append(self.delay)
        self.callback()


class ServerBootstrapTests(unittest.TestCase):
    def test_lan_disabled_binds_loopback_and_opens_loopback_url(self):
        created = []
        timers = []
        opened = []
        output = []
        state = {}

        def factory(address, handler):
            created.append((address, handler))
            return _Server()

        run_server(
            object(),
            8765,
            lambda: (False, ""),
            lambda: "192.168.1.5",
            state,
            server_factory=factory,
            timer_factory=lambda delay, callback: _Timer(delay, callback, timers),
            browser_open=opened.append,
            output=output.append,
        )

        self.assertEqual(("127.0.0.1", 8765), created[0][0])
        self.assertEqual("127.0.0.1", state["host"])
        self.assertEqual([0.8], timers)
        self.assertEqual(["http://127.0.0.1:8765"], opened)
        self.assertEqual(1, len(output))

    def test_lan_enabled_binds_all_interfaces_and_prints_mobile_url(self):
        created = []
        output = []
        state = {}

        run_server(
            object(),
            9000,
            lambda: (True, "123456"),
            lambda: "192.168.1.8",
            state,
            server_factory=lambda address, _handler: created.append(address)
            or _Server(),
            output=output.append,
            open_browser=False,
        )

        self.assertEqual(("0.0.0.0", 9000), created[0])
        self.assertEqual("0.0.0.0", state["host"])
        self.assertIn("http://192.168.1.8:9000", output[1])

    def test_keyboard_interrupt_closes_server(self):
        server = _Server(interrupt=True)

        run_server(
            object(),
            8765,
            lambda: (False, ""),
            lambda: "127.0.0.1",
            {},
            server_factory=lambda _address, _handler: server,
            output=lambda _message: None,
            open_browser=False,
        )

        self.assertTrue(server.served)
        self.assertTrue(server.closed)


if __name__ == "__main__":
    unittest.main()
