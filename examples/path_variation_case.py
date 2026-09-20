"""Show how a Contract can allow safe path variation without going open-ended."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping

from agent_regression import (
    AgentTrace,
    ComparisonPolicy,
    ContractPolicy,
    compare_traces,
    record_run,
)


ROOT = Path(__file__).resolve().parents[1]
BEHAVIORS = {"normal", "extra-query", "reordered", "forbidden"}


def get_order(_world, arguments):
    return {"order_id": str(arguments["order_id"]), "status": "paid"}


def get_payment_status(_world, arguments):
    return {"order_id": str(arguments["order_id"]), "payment_status": "paid"}


def get_shipping(_world, arguments):
    return {"order_id": str(arguments["order_id"]), "shipping_status": "not_shipped"}


def delete_order(_world, arguments):
    return {"order_id": str(arguments["order_id"]), "deleted": True}


class PathVariationAgent:
    """Reference Agent with one valid path variation and two regressions."""

    def __init__(self, behavior: str):
        if behavior not in BEHAVIORS:
            raise ValueError(f"unsupported path variation behavior: {behavior!r}")
        self.behavior = behavior

    @property
    def identity(self) -> Mapping[str, Any]:
        return {
            "name": "path-variation-agent",
            "version": "1.0.0",
            "behavior": self.behavior,
        }

    def run(self, request: Any, context) -> None:
        order_id = str(request["order_id"])
        if self.behavior == "reordered":
            context.call_tool("get_payment_status", {"order_id": order_id})
            context.call_tool("get_order", {"order_id": order_id})
        else:
            context.call_tool("get_order", {"order_id": order_id})
            if self.behavior == "extra-query":
                context.call_tool("get_shipping", {"order_id": order_id})
            if self.behavior == "forbidden":
                context.call_tool("delete_order", {"order_id": order_id})
            context.call_tool("get_payment_status", {"order_id": order_id})
        context.final_answer(
            f"订单 {order_id} 已支付。",
            {"order_id": order_id, "status": "paid"},
        )


def build_tools():
    from agent_regression import StatefulFixtureTools

    return StatefulFixtureTools(
        {},
        {
            "get_order": get_order,
            "get_payment_status": get_payment_status,
            "get_shipping": get_shipping,
            "delete_order": delete_order,
        }
    )


def build_contract() -> ContractPolicy:
    return ContractPolicy.from_dict(
        {
            "required_claims": [
                "final_answer.claims.order_id",
                "final_answer.claims.status",
            ],
            "must_call": [{"tool": "get_order"}, {"tool": "get_payment_status"}],
            "must_not_call": ["delete_order"],
            "path_rules": {
                "mode": "ordered_subsequence",
                "any_of": [[
                    {"tool": "get_order", "is_error": False},
                    {"tool": "get_payment_status", "is_error": False},
                ]],
            },
            "max_steps": 3,
        }
    )


def write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(
    behavior: str,
    out: Path,
    compare_to: Path | None = None,
    report: Path | None = None,
) -> int:
    trace = record_run(
        PathVariationAgent(behavior),
        {"order_id": "123", "request": "查询订单 123"},
        build_tools(),
        run_id=f"path-variation-{behavior}",
    )
    write_json(out, trace.to_dict())
    if compare_to is None:
        print(f"recorded {behavior}: {out}")
        return 0

    baseline = AgentTrace.from_dict(json.loads(compare_to.read_text(encoding="utf-8")))
    result = compare_traces(
        baseline,
        trace,
        ComparisonPolicy(
            final_answer_mode="claims-only",
            contract=build_contract(),
        ),
    )
    if report:
        write_json(report, result)
    print(
        json.dumps(
            {
                "behavior": behavior,
                "passed": result["passed"],
                "blocking_difference_count": result["blocking_difference_count"],
            },
            ensure_ascii=False,
        )
    )
    for difference in result["differences"]:
        if not difference.get("allowed"):
            print(
                f"- {difference['category']} at {difference['path']}: "
                f"{difference.get('message', 'observed difference')}"
            )
    return 0 if result["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--behavior", choices=sorted(BEHAVIORS), default="normal")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compare-to", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    return run(args.behavior, args.out, args.compare_to, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
