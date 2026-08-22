"""Application HTTP server startup and lifecycle."""

import threading
import webbrowser
from http.server import ThreadingHTTPServer


def run_server(
    handler,
    port,
    lan_configuration,
    network_ip,
    server_state,
    *,
    server_factory=ThreadingHTTPServer,
    timer_factory=threading.Timer,
    browser_open=webbrowser.open,
    output=print,
    open_browser=True,
):
    lan_ready, _pin = lan_configuration()
    host = "0.0.0.0" if lan_ready else "127.0.0.1"
    server_state["host"] = host
    server = server_factory((host, port), handler)
    url = f"http://127.0.0.1:{port}"
    output(f"Novel Translator is running at {url} - press Ctrl+C to stop")
    if lan_ready:
        output(f"Mobile LAN access: http://{network_ip()}:{port}")
    if open_browser:
        timer_factory(0.8, lambda: browser_open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
