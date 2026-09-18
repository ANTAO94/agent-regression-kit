"""Optional LangChain Core integration with no model or provider credentials.

Install the optional dependency first::

    python -m pip install -r examples/optional-requirements.txt

This example uses a real LangChain Core ``RunnableLambda`` as the framework
owned execution boundary. The tool call and structured answer remain explicit
Agent Regression Kit observations.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.runnables import RunnableLambda

from agent_regression import CallableAgentAdapter, FixtureTools, check_adapter_contract


def invoke_langchain(request, context):
    lookup = RunnableLambda(
        lambda payload: context.call_tool("get_order", {"order_id": payload["order_id"]})
    )
    order = lookup.invoke(request)
    context.final_answer(
        f"Order {request['order_id']} status: {order['status']}",
        {"order_id": request["order_id"], "order_status": order["status"]},
    )


def build_report():
    adapter = CallableAgentAdapter(
        {"name": "langchain-core-example", "version": "1.0.0", "framework": "langchain-core"},
        invoke_langchain,
    )
    return check_adapter_contract(
        adapter,
        {"order_id": "123"},
        FixtureTools({"get_order": {"order_id": "123", "status": "paid"}}),
        run_id="langchain-core-order-123",
        expected_tool_path=["get_order"],
        expected_claims={"order_status": "paid"},
    )


if __name__ == "__main__":
    report = build_report()
    if not report["ok"]:
        raise SystemExit(json.dumps(report, ensure_ascii=False, indent=2))
    destination = Path("work/langchain-core.trace.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report["trace"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(destination)
