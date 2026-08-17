import unittest

from cores.dich_utils import _ready_chatgpt_send_button


class FakeButton:
    def __init__(self, *, displayed=True, enabled=True, disabled=None, aria_disabled=None):
        self.displayed = displayed
        self.enabled = enabled
        self.attributes = {"disabled": disabled, "aria-disabled": aria_disabled}

    def is_displayed(self):
        return self.displayed

    def is_enabled(self):
        return self.enabled

    def get_attribute(self, name):
        return self.attributes.get(name)


class FakeDriver:
    def __init__(self, button):
        self.button = button

    def find_elements(self, _by, _selector):
        return [self.button]


class ChatGPTSendReadyTests(unittest.TestCase):
    def test_waits_while_send_button_is_disabled(self):
        button = FakeButton(enabled=False, disabled="true", aria_disabled="true")
        self.assertFalse(_ready_chatgpt_send_button(FakeDriver(button)))

    def test_returns_send_button_when_chatgpt_enables_it(self):
        button = FakeButton()
        self.assertIs(_ready_chatgpt_send_button(FakeDriver(button)), button)


if __name__ == "__main__":
    unittest.main()
