"""Proxy behavior tests, all hermetic (no LM Studio required).

``cll`` runs the proxy in-process sharing stderr with the Claude Code TUI, so a benign
client disconnect must not dump a traceback to stderr (which corrupts the display).
And the proxy must forward requests while folding stray system messages.
"""
import http.client
import http.server
import io
import json
import sys
import threading

from claude_lms.proxy import _debug, make_server


def test_handle_error_swallows_connection_errors_silently():
    server = make_server(listen_port=0)
    captured = io.StringIO()
    original = sys.stderr
    sys.stderr = captured
    try:
        raise ConnectionResetError("peer reset")
    except ConnectionResetError:
        server.handle_error(None, ("127.0.0.1", 0))
    finally:
        sys.stderr = original
        server.server_close()
    assert captured.getvalue() == ""


def test_debug_is_a_noop_without_the_env_flag(monkeypatch):
    monkeypatch.delenv("CLAUDE_LMS_DEBUG", raising=False)
    captured = io.StringIO()
    original = sys.stderr
    sys.stderr = captured
    try:
        _debug("ignored message")
        _debug()  # traceback path
    finally:
        sys.stderr = original
    assert captured.getvalue() == ""


def _start_echo_upstream():
    """An upstream that echoes the request body it received (so the proxy's
    forwarded, normalized body comes back in the response)."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            received = self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(received)))
            self.end_headers()
            self.wfile.write(received)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_proxy_forwards_and_folds_stray_system_messages():
    upstream = _start_echo_upstream()
    up_host, up_port = upstream.server_address
    proxy = make_server(listen_port=0, upstream_host=up_host, upstream_port=up_port)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    p_host, p_port = proxy.server_address

    payload = json.dumps(
        {
            "system": "top",
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "system", "content": "folded"},
            ],
        }
    )
    conn = http.client.HTTPConnection(p_host, p_port, timeout=5)
    conn.request("POST", "/v1/messages", payload, {"Content-Type": "application/json"})
    response = conn.getresponse()
    forwarded = json.loads(response.read())
    conn.close()
    proxy.shutdown()
    upstream.shutdown()

    assert response.status == 200
    assert all(m["role"] != "system" for m in forwarded["messages"])
    assert any(block["text"] == "folded" for block in forwarded["system"])
