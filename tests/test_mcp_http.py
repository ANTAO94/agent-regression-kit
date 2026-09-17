import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent_regression import (
    McpTimeoutError,
    ScriptedAgentAdapter,
    StreamableHttpMcpClient,
    record_mcp_http_run,
)
from agent_regression.fixtures.mcp_stdio_server import FixtureServer


class _McpHttpHandler(BaseHTTPRequestHandler):
    server_version = "AgentRegressionFixture/1.1"

    def do_POST(self):  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        try:
            message = json.loads(self.rfile.read(length))
            if "method" not in message and "id" in message:
                self.server.received_responses.append(message)  # type: ignore[attr-defined]
                response = None
            else:
                response = self.server.fixture.handle(message)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - defensive fixture boundary
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(exc)},
            }

        session_id = self.server.session_id  # type: ignore[attr-defined]
        received_session = self.headers.get("Mcp-Session-Id")
        required_header = getattr(self.server, "required_header", None)
        if required_header and self.headers.get(required_header[0]) != required_header[1]:
            self.send_error(401, "missing required header")
            return
        self.server.received_sessions.append(received_session)  # type: ignore[attr-defined]
        self.server.received_versions.append(self.headers.get("MCP-Protocol-Version"))  # type: ignore[attr-defined]
        if received_session not in (None, session_id):
            self.send_error(400, "invalid session")
            return
        if session_id is None:
            session_id = "fixture-session"
            self.server.session_id = session_id  # type: ignore[attr-defined]

        if response is None:
            self.send_response(202)
            self.send_header("Mcp-Session-Id", session_id)
            self.end_headers()
            return

        rendered = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Mcp-Session-Id", session_id)
        if self.server.use_sse:  # type: ignore[attr-defined]
            messages = []
            if self.server.include_server_request and message.get("method") == "tools/call":  # type: ignore[attr-defined]
                messages.append(
                    {
                        "jsonrpc": "2.0",
                        "id": 77,
                        "method": "ping",
                        "params": {},
                    }
                )
            messages.append(response)
            payload = b"".join(
                b"event: message\ndata: "
                + json.dumps(item, separators=(",", ":")).encode("utf-8")
                + b"\n\n"
                for item in messages
            )
            self.send_header("Content-Type", "text/event-stream")
        else:
            payload = rendered
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):  # noqa: N802 - stdlib handler API
        session_id = self.server.session_id  # type: ignore[attr-defined]
        if self.headers.get("Mcp-Session-Id") != session_id:
            self.send_error(400, "invalid session")
            return
        last_event_id = self.headers.get("Last-Event-ID")
        self.server.received_last_event_ids.append(last_event_id)  # type: ignore[attr-defined]
        events = [
            ("1", {"jsonrpc": "2.0", "method": "notifications/tools/list_changed", "params": {}}),
            ("2", {"jsonrpc": "2.0", "id": 99, "method": "ping", "params": {}}),
        ]
        if self.server.include_progress:  # type: ignore[attr-defined]
            events.insert(
                0,
                (
                    "0",
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/progress",
                        "params": {"progressToken": "run-1", "progress": 1},
                    },
                ),
            )
        if last_event_id:
            events = [(event_id, event) for event_id, event in events if event_id > last_event_id]
        payload = b"".join(
            b"event: message\nid: "
            + event_id.encode("utf-8")
            + b"\ndata: "
            + json.dumps(event, separators=(",", ":")).encode("utf-8")
            + b"\n\n"
            for event_id, event in events
        )
        self.send_response(200)
        self.send_header("Mcp-Session-Id", session_id)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):  # noqa: A002 - stdlib handler API
        del format, args


class McpHttpFixtureTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _McpHttpHandler)
        self.server.fixture = FixtureServer()
        self.server.session_id = None
        self.server.received_sessions = []
        self.server.received_versions = []
        self.server.received_responses = []
        self.server.received_last_event_ids = []
        self.server.include_progress = False
        self.server.use_sse = False
        self.server.include_server_request = False
        self.server.required_header = None
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/mcp"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_json_transport_lifecycle_and_session(self):
        with StreamableHttpMcpClient(self.url) as client:
            initialized = client.initialize()
            tools = client.list_tools()
            result = client.call_tool("get_order", {"order_id": "123"})

        self.assertEqual("2025-11-25", initialized["protocolVersion"])
        self.assertEqual(["get_order"], [tool["name"] for tool in tools])
        self.assertEqual("not_shipped", result["structuredContent"]["status"])
        self.assertEqual([None, "fixture-session", "fixture-session", "fixture-session"], self.server.received_sessions)
        self.assertEqual(["2025-11-25"] * 4, self.server.received_versions)

    def test_custom_headers_are_sent_on_http_requests(self):
        self.server.required_header = ("Authorization", "Bearer fixture")
        with StreamableHttpMcpClient(
            self.url,
            headers={"Authorization": "Bearer fixture"},
        ) as client:
            client.initialize()
            result = client.call_tool("get_order", {"order_id": "123"})
        self.assertEqual("not_shipped", result["structuredContent"]["status"])

    def test_resources_and_prompts_are_available_over_http(self):
        with StreamableHttpMcpClient(self.url) as client:
            client.initialize()
            resources = client.list_resources()
            resource = client.read_resource("orders://123")
            prompts = client.list_prompts()
            prompt = client.get_prompt("order-status", {"order_id": "123"})

        self.assertEqual("orders://123", resources[0]["uri"])
        self.assertIn('"status": "not_shipped"', resource["contents"][0]["text"])
        self.assertEqual("order-status", prompts[0]["name"])
        self.assertIn("查询订单 123", prompt["messages"][0]["content"]["text"])

    def test_concurrent_tool_calls_preserve_input_order(self):
        with StreamableHttpMcpClient(self.url) as client:
            client.initialize()
            results = client.call_tools_concurrently(
                [
                    ("get_order", {"order_id": "slow"}),
                    ("get_order", {"order_id": "123"}),
                ],
                max_workers=2,
            )
        self.assertEqual("not_found", results[0]["structuredContent"]["status"])
        self.assertEqual("not_shipped", results[1]["structuredContent"]["status"])

    def test_reconnect_starts_a_new_http_session_lifecycle(self):
        with StreamableHttpMcpClient(self.url) as client:
            first = client.initialize()
            first_session = client.session_id
            second = client.reconnect()
            second_session = client.session_id

        self.assertEqual("2025-11-25", first["protocolVersion"])
        self.assertEqual("2025-11-25", second["protocolVersion"])
        self.assertEqual("fixture-session", first_session)
        self.assertEqual(first_session, second_session)

    def test_sse_response_is_decoded(self):
        self.server.use_sse = True
        with StreamableHttpMcpClient(self.url) as client:
            client.initialize()
            result = client.call_tool("get_order", {"order_id": "123"})
        self.assertEqual("not_shipped", result["structuredContent"]["status"])

    def test_post_sse_can_auto_respond_to_an_in_band_server_request(self):
        self.server.use_sse = True
        self.server.include_server_request = True
        with StreamableHttpMcpClient(
            self.url,
            server_request_handler=lambda event: {"pong": event["method"]},
        ) as client:
            client.initialize()
            result = client.call_tool("get_order", {"order_id": "123"})

        self.assertEqual("not_shipped", result["structuredContent"]["status"])
        self.assertEqual({"pong": "ping"}, self.server.received_responses[0]["result"])

    def test_long_lived_event_stream_reads_notifications_and_requests(self):
        with StreamableHttpMcpClient(self.url) as client:
            client.initialize()
            with client.open_event_stream() as stream:
                events = list(stream)
        self.assertEqual(
            ["notifications/tools/list_changed", "ping"],
            [event["method"] for event in events],
        )
        self.assertEqual(99, events[1]["id"])
        self.assertEqual("notifications/tools/list_changed", client.transcript[-2]["message"]["method"])

    def test_event_stream_can_resume_from_last_event_id(self):
        with StreamableHttpMcpClient(self.url) as client:
            client.initialize()
            with client.open_event_stream() as stream:
                first_events = list(stream)
            with client.open_event_stream(last_event_id="1") as stream:
                resumed_events = list(stream)
        self.assertEqual(2, len(first_events))
        self.assertEqual(["ping"], [event["method"] for event in resumed_events])
        self.assertEqual([None, "1"], self.server.received_last_event_ids)
        self.assertEqual("2", client.last_event_id)

    def test_event_stream_can_auto_respond_to_server_request(self):
        with StreamableHttpMcpClient(self.url) as client:
            client.initialize()
            with client.open_event_stream(
                request_handler=lambda event: {"pong": event["method"]}
            ) as stream:
                events = list(stream)
        self.assertEqual(2, len(events))
        self.assertEqual({"pong": "ping"}, self.server.received_responses[0]["result"])

    def test_progress_iterator_filters_progress_notifications(self):
        self.server.include_progress = True
        with StreamableHttpMcpClient(self.url) as client:
            client.initialize()
            with client.open_event_stream() as stream:
                progress = list(stream.iter_progress())
        self.assertEqual(1, len(progress))
        self.assertEqual("run-1", progress[0]["params"]["progressToken"])

    def test_server_request_can_receive_an_explicit_response(self):
        with StreamableHttpMcpClient(self.url) as client:
            client.initialize()
            with client.open_event_stream() as stream:
                events = list(stream)
                stream.respond(99, result={"accepted": True})
        self.assertEqual({"accepted": True}, self.server.received_responses[0]["result"])
        self.assertEqual(99, self.server.received_responses[0]["id"])
        self.assertEqual(2, len(events))

    def test_http_record_becomes_agent_trace(self):
        adapter = ScriptedAgentAdapter(
            {"name": "toy-http-agent", "version": "1.1.0"},
            [
                {"type": "tool_call", "tool": "get_order", "arguments": {"order_id": "123"}},
                {"type": "final_answer", "text": "订单 123 尚未发货。"},
            ],
        )
        trace = record_mcp_http_run(
            adapter,
            "查询订单 123",
            self.url,
            run_id="mcp-http-order-123",
        )
        self.assertEqual("not_shipped", trace.events[1]["result"]["status"])
        self.assertEqual(3, trace.events[1]["metadata"]["mcp_request_id"])
        self.assertEqual("streamable_http", trace.metadata["mcp"]["transport"])
        self.assertEqual("fixture-session", trace.metadata["mcp"]["session_id"])

    def test_http_timeout_is_reported_at_transport_boundary(self):
        with StreamableHttpMcpClient(self.url, timeout_seconds=0.05) as client:
            client.initialize()
            with self.assertRaises(McpTimeoutError):
                client.call_tool("get_order", {"order_id": "slow"})


if __name__ == "__main__":
    unittest.main()
