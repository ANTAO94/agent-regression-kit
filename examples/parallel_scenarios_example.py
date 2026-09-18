"""Record independent Agent scenarios concurrently.

Run from the repository root with:

    PYTHONPATH=src python3 examples/parallel_scenarios_example.py

The ``CallableAgentAdapter`` callback represents the small bridge around a
real framework's ``invoke`` method. Each case creates its own tools and state,
so workers can run concurrently without sharing mutations.
"""

from __future__ import annotations

import json

from agent_regression import (
    CallableAgentAdapter,
    ScenarioCase,
    StatefulFixtureTools,
    record_scenario_batch,
)


def get_order(world, arguments):
    return dict(world.data["orders"][arguments["order_id"]])


def make_case(case_id: str, request: str) -> ScenarioCase:
    def run_framework_agent(request_value, context):
        order_id = str(request_value).rsplit(" ", 1)[-1]
        order = context.call_tool("get_order", {"order_id": order_id})
        context.final_answer(
            f"订单 {order_id} 状态：{order['status']}。",
            {"order_id": order_id, "order_status": order["status"]},
        )

    return ScenarioCase(
        case_id=case_id,
        request=request,
        run_id=f"parallel-{case_id}",
        adapter_factory=lambda: CallableAgentAdapter(
            {"name": "framework-order-agent", "version": "1.0.0"},
            run_framework_agent,
        ),
        tools_factory=lambda: StatefulFixtureTools(
            {"orders": {"123": {"status": "paid"}}},
            {"get_order": get_order},
        ),
        isolate=True,
    )


def main() -> int:
    result = record_scenario_batch(
        [
            make_case("shipping", "查询订单 123"),
            make_case("status", "查询订单 123"),
        ],
        max_workers=2,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
