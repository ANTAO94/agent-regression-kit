"""Evaluate repeated Agent runs without sharing mutable scenario state.

Run from the repository root with:

    PYTHONPATH=src python3 examples/stability_example.py

The example uses a deterministic fixture, but the same ``ScenarioCase`` can
wrap a real model-backed Agent. Each repeat receives fresh tools and an
isolated world state, then the report checks pass rate, claims, tool errors,
and observed tool paths.
"""

from __future__ import annotations

import json

from agent_regression import (
    CallableAgentAdapter,
    ScenarioCase,
    StabilityPolicy,
    StatefulFixtureTools,
    record_run,
    record_stability,
)


def get_order(world, arguments):
    return dict(world.data["orders"][arguments["order_id"]])


def run_agent(request, context):
    order_id = str(request).rsplit(" ", 1)[-1]
    order = context.call_tool("get_order", {"order_id": order_id})
    context.final_answer(
        f"订单 {order_id} 状态：{order['status']}。",
        {"order_id": order_id, "order_status": order["status"]},
    )


def make_tools():
    return StatefulFixtureTools(
        {"orders": {"123": {"status": "paid"}}},
        {"get_order": get_order},
    )


def make_adapter():
    return CallableAgentAdapter(
        {"name": "stability-example-agent", "version": "1.0.0"},
        run_agent,
    )


def main() -> int:
    request = "查询订单 123"
    baseline = record_run(
        make_adapter(),
        request,
        make_tools(),
        run_id="stability-baseline",
    )
    case = ScenarioCase(
        case_id="order-123-stability",
        request=request,
        run_id="order-123-stability",
        adapter_factory=make_adapter,
        tools_factory=make_tools,
        isolate=True,
    )
    report = record_stability(
        baseline,
        case,
        repeats=5,
        max_workers=3,
        policy=StabilityPolicy(
            min_pass_rate=1.0,
            min_claims_match_rate=1.0,
            max_tool_error_rate=0.0,
            max_path_variants=1,
        ),
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
