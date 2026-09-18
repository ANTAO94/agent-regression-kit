"""LangChain Core event callback -> AgentTrace example.

This uses a real LangChain Core RunnableLambda, but no model provider. The
framework callback owns the runnable; Agent Regression Kit only receives
tool-start, tool-end and final-answer lifecycle events.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.runnables import RunnableLambda

from agent_regression import record_framework_run


def run_framework(request, events):
    def lookup(payload):
        call_id = events.tool_start("get_order", {"order_id": payload["order_id"]})
        result = {"order_id": payload["order_id"], "status": "paid"}
        events.tool_end(call_id, result)
        return result

    order = RunnableLambda(lookup).invoke(request)
    events.final_answer(
        f"Order {order['order_id']} status: {order['status']}",
        {"order_id": order["order_id"], "order_status": order["status"]},
    )


def build_trace():
    return record_framework_run(
        {"name": "langchain-core-events", "version": "1.0.0", "framework": "langchain-core"},
        run_framework,
        {"order_id": "123"},
        run_id="langchain-core-events-123",
    )


if __name__ == "__main__":
    trace = build_trace()
    destination = Path("work/langchain-core-events.trace.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8")
    print(destination)
