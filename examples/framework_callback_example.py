"""A dependency-free framework callback integration example.

Replace ``invoke_framework`` with the callback supplied by LangChain, Spring
AI, an OpenAI SDK wrapper, or a custom Agent. The observable boundary remains
the same: tool calls go through ``context.call_tool`` and the terminal answer
goes through ``context.final_answer``.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_regression import CallableAgentAdapter, FixtureTools, record_run


def invoke_framework(request, context):
    order_id = request["order_id"]
    order = context.call_tool("get_order", {"order_id": order_id})
    context.final_answer(
        f"订单 {order_id} 的状态是 {order['status']}。",
        {"order_id": order_id, "order_status": order["status"]},
    )


def build_trace():
    adapter = CallableAgentAdapter(
        {"name": "framework-callback-example", "version": "1.0.0"},
        invoke_framework,
    )
    return record_run(
        adapter,
        {"order_id": "123"},
        FixtureTools({"get_order": {"order_id": "123", "status": "not_shipped"}}),
        run_id="framework-callback-order-123",
    )


if __name__ == "__main__":
    trace = build_trace()
    destination = Path("work/framework-callback.trace.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(destination)
