"""LAN login, status, and authorization middleware."""

import json
from http import HTTPStatus

from server.lan.login_page import LOGIN_HTML


class LanRoutes:
    def __init__(self, auth, host, port, network_ip):
        self.auth = auth
        self.host = host
        self.port = port
        self.network_ip = network_ip

    def require(self, handler, api_request=False):
        if self.auth.authorized(
            handler.client_address[0], handler.headers.get("Cookie", "")
        ):
            return False
        if api_request:
            handler.json_response(
                {"error": "Điện thoại chưa đăng nhập mã PIN LAN."},
                HTTPStatus.UNAUTHORIZED,
            )
        else:
            body = LOGIN_HTML.encode("utf-8")
            handler.send_response(HTTPStatus.UNAUTHORIZED)
            handler.send_header("Content-Type", "text/html; charset=utf-8")
            handler.send_header("Content-Length", str(len(body)))
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            handler.wfile.write(body)
        return True

    def handle_get(self, handler, path):
        if path != "/api/lan/status":
            return False
        configured, pin = self.auth.configuration_loader()
        loopback = self.auth.is_loopback(handler.client_address[0])
        handler.json_response(
            {
                "configured": configured,
                "active": self.host() == "0.0.0.0",
                "url": f"http://{self.network_ip()}:{self.port}" if configured else "",
                "pin": pin if loopback else "",
            }
        )
        return True

    def handle_post(self, handler, path):
        if path != "/api/lan/login":
            return False
        try:
            supplied_pin = str(handler.body().get("pin", "")).strip()
        except (ValueError, json.JSONDecodeError):
            supplied_pin = ""
        status, payload, token = self.auth.login(
            handler.client_address[0], supplied_pin
        )
        if status != HTTPStatus.OK:
            handler.json_response(payload, status)
            return True
        body = json.dumps(payload).encode("utf-8")
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header(
            "Set-Cookie",
            f"nts_lan_session={token}; Path=/; HttpOnly; SameSite=Strict",
        )
        handler.end_headers()
        handler.wfile.write(body)
        return True
