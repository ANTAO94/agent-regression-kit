import sys
import unittest
from pathlib import Path

from agent_regression import (
    McpProtocolError,
    McpTransportError,
    ScriptedAgentAdapter,
    StdioMcpClient,
    record_mcp_run,
)


ROOT = Path(__file__).resolve().parents[1]
SERVER_COMMAND = [
    sys.executable,
    str(ROOT / "src/agent_regression/fixtures/mcp_stdio_server.py"),
]


class McpFixtureTests(unittest.TestCase):
    def test_lifecycle_list_and_successful_tool_call(self):
        with StdioMcpClient(SERVER_COMMAND) as client:
            initialized = client.initialize()
            tools = client.list_tools()
            result = client.call_tool("get_order", {"order_id": "123"})

            self.assertEqual("2025-11-25", initialized["protocolVersion"])
            self.assertEqual(["get_order"], [tool["name"] for tool in tools])
            self.assertFalse(result["isError"])
            self.assertEqual("not_shipped", result["structuredContent"]["status"])

            methods = [
                entry["message"].get("method")
                for entry in client.transcript
                if entry["direction"] == "client_to_server"
            ]
        self.assertEqual(
            ["initialize", "notifications/initialized", "tools/list", "tools/call"],
            methods,
        )

    def test_content_length_framing_is_supported(self):
        with StdioMcpClient(SERVER_COMMAND, framing="content-length") as client:
            client.initialize()
            result = client.call_tool("get_order", {"order_id": "123"})
        self.assertEqual("not_shipped", result["structuredContent"]["status"])

    def test_task_metadata_can_be_requested_for_a_tool_call(self):
        with StdioMcpClient(SERVER_COMMAND) as client:
            client.initialize()
            result = client.call_tool(
                "get_order",
                {"order_id": "123"},
                task={"ttl": 60_000, "pollInterval": 100},
            )

        self.assertEqual("not_shipped", result["structuredContent"]["status"])
        request = next(
            entry["message"]
            for entry in client.transcript
            if entry["direction"] == "client_to_server"
            and entry["message"].get("method") == "tools/call"
        )
        self.assertEqual({"ttl": 60_000, "pollInterval": 100}, request["params"]["task"])

    def test_client_capabilities_are_sent_and_tasks_are_explicit(self):
        with StdioMcpClient(
            SERVER_COMMAND,
            client_capabilities={"sampling": {"tools": True}},
        ) as client:
            client.initialize()
            tasks = list(client.iter_tasks())
            task = client.get_task("task-1")
            result = client.get_task_result("task-1")
            cancelled = client.cancel_task("task-1")

        self.assertEqual({"sampling": {"tools": True}}, client.transcript[0]["message"]["params"]["capabilities"])
        self.assertEqual([], tasks)
        self.assertEqual("completed", task["status"])
        self.assertEqual("task-1", result["taskId"])
        self.assertEqual("cancelled", cancelled["status"])

    def test_parameter_error_is_a_tool_result(self):
        with StdioMcpClient(SERVER_COMMAND) as client:
            client.initialize()
            result = client.call_tool("get_order", {"order_id": 123})

            self.assertTrue(result["isError"])
            self.assertEqual("invalid_arguments", result["structuredContent"]["error"])

    def test_resources_and_prompts_are_available(self):
        with StdioMcpClient(SERVER_COMMAND) as client:
            client.initialize()
            resources = client.list_resources()
            resource = client.read_resource("orders://123")
            prompts = client.list_prompts()
            prompt = client.get_prompt("order-status", {"order_id": "123"})

        self.assertEqual("orders://123", resources[0]["uri"])
        self.assertIn('"status": "not_shipped"', resource["contents"][0]["text"])
        self.assertEqual("order-status", prompts[0]["name"])
        self.assertIn("查询订单 123", prompt["messages"][0]["content"]["text"])

    def test_pagination_and_cancellation_are_recorded(self):
        with StdioMcpClient(SERVER_COMMAND) as client:
            client.initialize()
            first_page, cursor = client.list_tools_page()
            all_tools = list(client.iter_tools())
            client.cancel(42, "superseded")

        self.assertEqual("get_order", first_page[0]["name"])
        self.assertEqual("page-2", cursor)
        self.assertEqual(["get_order"], [tool["name"] for tool in all_tools])
        self.assertEqual("notifications/cancelled", client.transcript[-1]["message"]["method"])

    def test_fixture_can_return_a_deterministic_tool_failure(self):
        with StdioMcpClient(SERVER_COMMAND) as client:
            client.initialize()
            result = client.call_tool("get_order", {"order_id": "500"})

            self.assertTrue(result["isError"])
            self.assertEqual("tool_failure", result["structuredContent"]["error"])

    def test_unknown_tool_is_a_protocol_error(self):
        with StdioMcpClient(SERVER_COMMAND) as client:
            client.initialize()
            with self.assertRaises(McpProtocolError) as raised:
                client.call_tool("missing_tool", {})
            self.assertEqual(-32602, raised.exception.code)

    def test_start_failure_is_a_transport_error(self):
        with self.assertRaisesRegex(McpTransportError, "failed to start"):
            StdioMcpClient(["/definitely/missing/agent-regression-server"]).start()

    def test_timeout_becomes_an_error_trace_without_retry(self):
        adapter = ScriptedAgentAdapter(
            {"name": "toy-mcp-agent"},
            [
                {"type": "tool_call", "tool": "get_order", "arguments": {"order_id": "slow"}},
                {"type": "final_answer", "text": "查询超时。", "claims": {"error": "timeout"}},
            ],
        )
        trace = record_mcp_run(
            adapter,
            "查询慢订单",
            SERVER_COMMAND,
            run_id="mcp-timeout",
            timeout_seconds=0.05,
        )

        result_event = trace.events[1]
        self.assertTrue(result_event["is_error"])
        self.assertEqual("mcp_timeout", result_event["result"]["error"])
        self.assertEqual(0, result_event["metadata"]["retry_count"])

    def test_mcp_run_becomes_agent_trace(self):
        adapter = ScriptedAgentAdapter(
            {"name": "toy-mcp-agent", "version": "1.0.0"},
            [
                {
                    "type": "tool_call",
                    "tool": "get_order",
                    "arguments": {"order_id": "123"},
                },
                {
                    "type": "final_answer",
                    "text": "订单 123 尚未发货。",
                    "claims": {"order_status": "not_shipped"},
                },
            ],
        )

        trace = record_mcp_run(
            adapter,
            "查询订单 123",
            SERVER_COMMAND,
            run_id="mcp-order-123",
        )

        self.assertEqual("not_shipped", trace.events[1]["result"]["status"])
        self.assertFalse(trace.events[1]["is_error"])
        self.assertEqual(3, trace.events[1]["metadata"]["mcp_request_id"])
        self.assertEqual("2025-11-25", trace.metadata["mcp"]["protocol_version"])
        self.assertEqual("none", trace.metadata["mcp"]["retry_policy"])
        self.assertEqual("server_subprocess", trace.metadata["mcp"]["side_effect_boundary"])
        self.assertEqual(7, len(trace.metadata["mcp"]["transcript"]))

    def test_mcp_tool_error_is_recorded_without_aborting_trace(self):
        adapter = ScriptedAgentAdapter(
            {"name": "toy-mcp-agent", "version": "1.0.0"},
            [
                {
                    "type": "tool_call",
                    "tool": "get_order",
                    "arguments": {"order_id": 123},
                },
                {
                    "type": "final_answer",
                    "text": "订单号参数格式错误。",
                    "claims": {"error": "invalid_arguments"},
                },
            ],
        )

        trace = record_mcp_run(
            adapter,
            "查询订单 123",
            SERVER_COMMAND,
            run_id="mcp-order-123-invalid-arguments",
        )

        result_event = trace.events[1]
        self.assertTrue(result_event["is_error"])
        self.assertEqual("invalid_arguments", result_event["result"]["error"])
        self.assertEqual("order_id must be a string", result_event["error"])

    def test_mcp_transcript_and_trace_are_redacted(self):
        adapter = ScriptedAgentAdapter(
            {"name": "toy-mcp-agent"},
            [
                {
                    "type": "tool_call",
                    "tool": "get_order",
                    "arguments": {"order_id": "123", "api_key": "never-store-me"},
                },
                {"type": "final_answer", "text": "done"},
            ],
        )
        trace = record_mcp_run(
            adapter,
            "lookup",
            SERVER_COMMAND,
            run_id="mcp-redaction",
        )

        rendered = str(trace.to_dict())
        self.assertNotIn("never-store-me", rendered)
        self.assertIn("[REDACTED]", rendered)


if __name__ == "__main__":
    unittest.main()
