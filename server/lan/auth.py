"""PIN, session, rate-limit, and network helpers for LAN access."""

import ipaddress
import re
import secrets
import socket
import time


def configuration(settings_loader):
    settings = settings_loader()
    enabled = settings.get("lan_enabled") == "on"
    pin = str(settings.get("lan_pin", ""))
    return enabled and bool(re.fullmatch(r"\d{6,12}", pin)), pin


def network_ip():
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        connection.connect(("8.8.8.8", 80))
        return connection.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        connection.close()


class LanAuth:
    def __init__(self, configuration_loader, clock=time.time, token_factory=None):
        self.configuration_loader = configuration_loader
        self.clock = clock
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self.sessions = set()
        self.login_attempts = {}

    @staticmethod
    def is_loopback(address):
        try:
            return ipaddress.ip_address(address).is_loopback
        except ValueError:
            return False

    def authorized(self, address, cookie=""):
        if self.is_loopback(address):
            return True
        configured, _pin = self.configuration_loader()
        if not configured:
            return False
        token = next(
            (
                part.split("=", 1)[1]
                for part in cookie.split(";")
                if part.strip().startswith("nts_lan_session=")
            ),
            "",
        ).strip()
        return token in self.sessions

    def login(self, address, supplied_pin):
        configured, expected_pin = self.configuration_loader()
        if not configured:
            return 403, {"error": "Truy cập LAN chưa được bật."}, ""
        now = self.clock()
        attempts = [
            stamp
            for stamp in self.login_attempts.get(address, [])
            if now - stamp < 300
        ]
        if len(attempts) >= 10:
            return (
                429,
                {"error": "Đã nhập sai quá nhiều lần. Hãy chờ 5 phút."},
                "",
            )
        if not secrets.compare_digest(str(supplied_pin), expected_pin):
            attempts.append(now)
            self.login_attempts[address] = attempts
            return 401, {"error": "Mã PIN không đúng."}, ""
        self.login_attempts.pop(address, None)
        token = self.token_factory()
        self.sessions.add(token)
        return 200, {"ok": True}, token
