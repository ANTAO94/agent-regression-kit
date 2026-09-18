"""Run a stateful order scenario and enforce its business side effect."""

from __future__ import annotations

from agent_regression import (
    ComparisonPolicy,
    ContractPolicy,
    ScriptedAgentAdapter,
    StatefulFixtureTools,
    compare_traces,
    record_run,
)


INITIAL_STATE = {"orders": {"123": {"status": "paid", "cancel_count": 0}}}


def get_order(world, arguments):
    return dict(world.data["orders"][arguments["order_id"]])


def cancel_order(world, arguments):
    order = world.data["orders"][arguments["order_id"]]
    order["status"] = "cancelled"
    order["cancel_count"] += 1
    return dict(order)


def record_cancel_run(run_id: str):
    tools = StatefulFixtureTools(
        INITIAL_STATE,
        {"get_order": get_order, "cancel_order": cancel_order},
    )
    agent = ScriptedAgentAdapter(
        {"name": "stateful-order-agent", "version": "1.0.0"},
        [
            {"type": "tool_call", "tool": "get_order", "arguments": {"order_id": "123"}},
            {"type": "tool_call", "tool": "cancel_order", "arguments": {"order_id": "123"}},
            {
                "type": "final_answer",
                "text": "订单 123 已取消。",
                "claims": {"order_status": "cancelled"},
            },
        ],
    )
    return record_run(agent, "cancel order 123", tools, run_id=run_id)


if __name__ == "__main__":
    baseline = record_cancel_run("baseline")
    candidate = record_cancel_run("candidate")
    report = compare_traces(
        baseline,
        candidate,
        ComparisonPolicy(
            contract=ContractPolicy(
                path_rules={
                    "any_of": [
                        ["get_order", "cancel_order"],
                        ["cancel_order"],
                    ]
                },
                side_effects=[
                    {"path": "orders.123.status", "from": "paid", "to": "cancelled"},
                    {"path": "orders.123.cancel_count", "to": 1},
                ],
            )
        ),
    )
    print("PASS" if report["passed"] else "FAIL")
    for difference in report["differences"]:
        print(difference)
