"""Minimal project-owned MCP 2025-11-25 Streamable HTTP fixture."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .mcp_stdio_server import FixtureServer


class HttpFixtureHandler(BaseHTTPRequestHandler):
    server_version = "AgentRegressionFixture/1.1"

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        try:
            message = json.loads(self.rfile.read(length))
            response = self.server.fixture.handle(message)  # type: ignore[attr-defined]
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(exc)},
            }

        session_id = self.server.session_id  # type: ignore[attr-defined]
        received_session = self.headers.get("Mcp-Session-Id")
        if received_session not in (None, session_id):
            self.send_error(400, "invalid session")
            return
        if session_id is None:
            session_id = "fixture-http-session"
            self.server.session_id = session_id  # type: ignore[attr-defined]

        if response is None:
            self.send_response(202)
            self.send_header("Mcp-Session-Id", session_id)
            self.end_headers()
            return

        rendered = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Mcp-Session-Id", session_id)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(rendered)))
        self.end_headers()
        self.wfile.write(rendered)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        del format, args


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), HttpFixtureHandler)
    server.fixture = FixtureServer()  # type: ignore[attr-defined]
    server.session_id = None  # type: ignore[attr-defined]
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
