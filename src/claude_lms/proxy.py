"""Normalizing reverse proxy for running Claude Code against LM Studio.

Claude Code's Anthropic ``/v1/messages`` requests can contain more than one system
message in different positions: the top-level ``system`` field plus a ``system``-role
message injected mid-``messages`` (e.g. SessionStart hook output). Strict chat
templates -- notably Qwen3.5 / Qwen3.6 -- hard-reject any system message that is not
the very first message::

    Jinja Exception: System message must be at the beginning.

so the request fails with HTTP 400 before inference even starts.

This proxy sits between Claude Code and LM Studio and folds every non-leading
``system`` message into the single leading ``system`` block before forwarding, so any
model's chat template accepts the request. Responses stream through unbuffered so live
token streaming keeps working.

Standalone usage (``claude-lms-proxy`` console script) reads configuration
from the environment:

    LM_STUDIO_URL   upstream LM Studio base URL   (default http://localhost:1234)
    LM_PROXY_PORT   port this proxy listens on    (default 1366)

Pure standard library; no third-party dependencies.
"""
from __future__ import annotations

import http.client
import http.server
import json
import os
import sys
import tempfile
import traceback
from urllib.parse import urlsplit

_DEBUG_LOG = os.path.join(tempfile.gettempdir(), "claude-lms-proxy.log")


def _debug(message: str = "") -> None:
    """Append to the debug log when ``CLAUDE_LMS_DEBUG`` is set; otherwise a no-op.

    With a ``message`` it writes that line; with none it writes the current
    exception's traceback. Never writes to stderr: ``cll`` runs this proxy in-process
    and stderr is the interactive Claude Code TUI, which such output would corrupt.
    """
    if not os.environ.get("CLAUDE_LMS_DEBUG"):
        return
    with open(_DEBUG_LOG, "a") as log:
        if message:
            log.write(message + "\n")
        else:
            traceback.print_exc(file=log)


def _text(content) -> str:
    """Flatten an Anthropic message/content value to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def normalize(payload: dict) -> dict:
    """Fold every non-leading ``system`` message into one leading ``system`` block.

    Returns the same dict, mutated in place. Safe to call on any request body: if
    there are no stray system messages it leaves the conversation untouched (beyond
    normalizing a string ``system`` field into a single-block list).
    """
    field = payload.get("system")
    if isinstance(field, str):
        system_blocks = [{"type": "text", "text": field}]
    elif isinstance(field, list):
        system_blocks = list(field)
    else:
        system_blocks = []

    kept, folded = [], []
    for message in payload.get("messages", []):
        if isinstance(message, dict) and message.get("role") == "system":
            text = _text(message.get("content"))
            if text:
                folded.append(text)
        else:
            kept.append(message)

    if folded:
        system_blocks += [{"type": "text", "text": text} for text in folded]
    if system_blocks:
        payload["system"] = system_blocks
    payload["messages"] = kept
    return payload


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # Disable Nagle's algorithm so each streamed SSE chunk goes out immediately
    # instead of being briefly buffered waiting for more data.
    disable_nagle_algorithm = True

    def log_message(self, *args):  # silence default access logging
        pass

    def _send_json_error(self, status: int, message: str) -> None:
        body = json.dumps(
            {"type": "error", "error": {"type": "proxy_error", "message": message}}
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        # Rewrite the request only when it carries a stray (non-leading) system
        # message — that's the sole thing normalize fixes. Skipping the re-encode
        # otherwise avoids a json.dumps of the (often large) body on every request.
        if self.command == "POST" and body:
            try:
                data = json.loads(body)
                if isinstance(data, dict) and any(
                    isinstance(m, dict) and m.get("role") == "system"
                    for m in data.get("messages", [])
                ):
                    body = json.dumps(normalize(data)).encode()
            except (ValueError, TypeError) as exc:
                _debug(f"normalize skipped (unparsed body): {exc}")

        # Forward upstream. Drop Accept-Encoding so the response is uncompressed and
        # safe to re-stream; http.client sets Content-Length from the body.
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in ("host", "content-length", "accept-encoding")
        }
        try:
            conn = http.client.HTTPConnection(
                self.server.upstream_host, self.server.upstream_port, timeout=600
            )
            conn.request(self.command, self.path, body, headers)
            response = conn.getresponse()
        except OSError as exc:
            self._send_json_error(
                502,
                f"cannot reach LM Studio at "
                f"{self.server.upstream_host}:{self.server.upstream_port}: {exc}",
            )
            return

        # Stream the response through unbuffered (chunked) to preserve SSE streaming.
        self.send_response(response.status)
        for key, value in response.getheaders():
            if key.lower() not in ("transfer-encoding", "content-length", "connection"):
                self.send_header(key, value)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            while True:
                # read1() returns as soon as any data is available (up to the cap),
                # so tokens forward the instant LM Studio emits them.
                chunk = response.read1(65536)
                if not chunk:
                    break
                # Write the chunk framing and body separately so the (large) body
                # is never copied into a combined buffer.
                self.wfile.write(b"%X\r\n" % len(chunk))
                self.wfile.write(chunk)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except OSError as exc:
            _debug(f"client stream closed early: {exc}")  # benign disconnect
        finally:
            conn.close()

    do_GET = _proxy
    do_POST = _proxy


class NormalizingProxy(http.server.ThreadingHTTPServer):
    """Threaded HTTP server that knows its LM Studio upstream."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, listen_addr, upstream_host: str, upstream_port: int):
        super().__init__(listen_addr, _Handler)
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port

    def handle_error(self, request, client_address):
        # Claude Code uses keep-alive and routinely resets pooled/streamed
        # connections; those socket errors are benign. Never let the default handler
        # print a traceback to stderr — cll runs this in-process and stderr is the
        # live Claude Code TUI, which such output corrupts.
        if isinstance(sys.exc_info()[1], OSError):
            return
        _debug()  # unexpected error -> debug log only, never the terminal


def make_server(
    listen_host: str = "127.0.0.1",
    listen_port: int = 0,
    upstream_host: str = "localhost",
    upstream_port: int = 1234,
) -> NormalizingProxy:
    """Create (but do not start) a normalizing proxy server.

    ``listen_port=0`` binds an ephemeral port; read ``server.server_address`` for the
    port that was actually assigned.
    """
    return NormalizingProxy((listen_host, listen_port), upstream_host, upstream_port)


def main() -> None:
    upstream = urlsplit(os.environ.get("LM_STUDIO_URL", "http://localhost:1234"))
    upstream_host = upstream.hostname or "localhost"
    upstream_port = upstream.port or 1234
    listen_port = int(os.environ.get("LM_PROXY_PORT", "1366"))

    server = make_server("127.0.0.1", listen_port, upstream_host, upstream_port)
    host, port = server.server_address
    # Standalone entrypoint only: here stderr is a normal terminal, so a startup
    # banner is fine. The in-process `cll` path uses make_server() directly and must
    # never reach this; the server/handler keep stderr silent for that reason.
    sys.stderr.write(
        f"claude-lms proxy: http://{host}:{port} "
        f"-> {upstream_host}:{upstream_port}\n"
    )
    sys.stderr.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
