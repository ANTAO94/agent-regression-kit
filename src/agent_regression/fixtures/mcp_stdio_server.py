"""Minimal project-owned MCP 2025-11-25 stdio fixture.

This implements only the lifecycle and tools methods needed by the test suite.
It is deliberately not an MCP conformance implementation.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict, Tuple


PROTOCOL_VERSION = "2025-11-25"
ORDERS = {"123": {"order_id": "123", "status": "not_shipped"}}
ORDER_TOOL = {
    "name": "get_order",
    "description": "Return a deterministic fixture order by ID.",
    "inputSchema": {
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"],
        "additionalProperties": False,
    },
}
ORDER_RESOURCE = {
    "uri": "orders://123",
    "name": "order-123",
    "description": "Deterministic order resource.",
    "mimeType": "application/json",
}
ORDER_PROMPT = {
    "name": "order-status",
    "description": "Ask for the status of an order.",
    "arguments": [{"name": "order_id", "description": "Order ID", "required": True}],
}


class FixtureServer:
    def __init__(self) -> None:
        self.initialized = False
        self.ready = False
        self.notifications = []

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any] | None:
        request_id = message.get("id")
        if message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return error(request_id, -32600, "Invalid Request")
        method = message["method"]
        params = message.get("params", {})
        if method == "initialize":
            self.initialized = True
            return success(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"listChanged": False},
                        "prompts": {"listChanged": False},
                        "tasks": {"list": {}, "cancel": {}, "requests": {"tools": {"call": {}}}},
                    },
                    "serverInfo": {
                        "name": "agent-regression-kit-fixture",
                        "version": "1.0.0",
                    },
                },
            )
        if method == "notifications/initialized" and request_id is None:
            if self.initialized:
                self.ready = True
            return None
        if method == "notifications/cancelled" and request_id is None:
            self.notifications.append({"method": method, "params": params})
            return None
        if not self.ready:
            return error(request_id, -32002, "Server is not initialized")
        if method == "tools/list":
            return page(request_id, "tools", [ORDER_TOOL], params)
        if method == "tools/call":
            return self.call_tool(request_id, params)
        if method == "resources/list":
            return page(request_id, "resources", [ORDER_RESOURCE], params)
        if method == "resources/read":
            if not isinstance(params, dict) or params.get("uri") != ORDER_RESOURCE["uri"]:
                return error(request_id, -32602, "Unknown resource")
            return success(
                request_id,
                {
                    "contents": [
                        {
                            "uri": ORDER_RESOURCE["uri"],
                            "mimeType": "application/json",
                            "text": json.dumps(ORDERS["123"], ensure_ascii=False),
                        }
                    ]
                },
            )
        if method == "prompts/list":
            return page(request_id, "prompts", [ORDER_PROMPT], params)
        if method == "prompts/get":
            if not isinstance(params, dict) or params.get("name") != ORDER_PROMPT["name"]:
                return error(request_id, -32602, "Unknown prompt")
            order_id = params.get("arguments", {}).get("order_id", "123")
            return success(
                request_id,
                {
                    "description": ORDER_PROMPT["description"],
                    "messages": [
                        {
                            "role": "user",
                            "content": {"type": "text", "text": f"查询订单 {order_id} 的状态"},
                        }
                    ],
                },
            )
        if method == "tasks/list":
            return page(request_id, "tasks", [], params)
        if method == "tasks/get":
            return success(request_id, {"taskId": params.get("taskId"), "status": "completed"})
        if method == "tasks/result":
            return success(request_id, {"taskId": params.get("taskId"), "result": {}})
        if method == "tasks/cancel":
            return success(request_id, {"taskId": params.get("taskId"), "status": "cancelled"})
        return error(request_id, -32601, "Method not found")

    def call_tool(self, request_id: Any, params: Any) -> Dict[str, Any]:
        if not isinstance(params, dict) or params.get("name") != "get_order":
            return error(request_id, -32602, "Unknown tool")
        arguments = params.get("arguments", {})
        order_id = arguments.get("order_id") if isinstance(arguments, dict) else None
        if not isinstance(order_id, str):
            message = "order_id must be a string"
            return success(
                request_id,
                {
                    "content": [{"type": "text", "text": message}],
                    "structuredContent": {"error": "invalid_arguments", "message": message},
                    "isError": True,
                },
            )
        if order_id == "slow":
            time.sleep(0.2)
        if order_id == "500":
            message = "fixture order service unavailable"
            return success(
                request_id,
                {
                    "content": [{"type": "text", "text": message}],
                    "structuredContent": {"error": "tool_failure", "message": message},
                    "isError": True,
                },
            )
        order = ORDERS.get(order_id)
        if order is None:
            order = {"order_id": order_id, "status": "not_found"}
        return success(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(order, ensure_ascii=False)}],
                "structuredContent": order,
                "isError": False,
            },
        )


def success(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def page(
    request_id: Any, key: str, items: list[Dict[str, Any]], params: Any
) -> Dict[str, Any]:
    if isinstance(params, dict) and params.get("cursor") == "page-2":
        return success(request_id, {key: []})
    return success(request_id, {key: items, "nextCursor": "page-2"})


def error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def read_message(stream: Any) -> Tuple[Dict[str, Any] | None, str]:
    first_line = stream.readline()
    if not first_line:
        return None, "newline"
    if first_line.lower().startswith(b"content-length:"):
        try:
            length = int(first_line.split(b":", 1)[1].strip())
        except (IndexError, ValueError) as exc:
            raise ValueError("invalid Content-Length") from exc
        while True:
            header = stream.readline()
            if not header:
                raise ValueError("incomplete Content-Length headers")
            if header in {b"\n", b"\r\n"}:
                break
        payload = stream.read(length)
        if len(payload) != length:
            raise ValueError("truncated Content-Length payload")
        return json.loads(payload), "content-length"
    return json.loads(first_line), "newline"


def write_message(stream: Any, message: Dict[str, Any], framing: str) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if framing == "content-length":
        stream.write(b"Content-Length: " + str(len(payload)).encode("ascii") + b"\r\n\r\n" + payload)
    else:
        stream.write(payload + b"\n")
    stream.flush()


def main() -> int:
    server = FixtureServer()
    stream = sys.stdin.buffer
    output = sys.stdout.buffer
    while True:
        try:
            message, framing = read_message(stream)
            if message is None:
                break
            response = server.handle(message) if isinstance(message, dict) else error(None, -32600, "Invalid Request")
        except json.JSONDecodeError:
            response = error(None, -32700, "Parse error")
        except Exception as exc:
            response = error(None, -32603, f"Internal error: {exc}")
        if response is not None:
            write_message(output, response, framing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
