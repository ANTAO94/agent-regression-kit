"""Run the complete offline refund business case.

This example deliberately keeps the Agent deterministic so the repository can
prove the contract itself. Replace ``RefundAgent`` with a real framework
adapter after the business rules are understood.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping

from agent_regression import (
    ComparisonPolicy,
    ContractPolicy,
    StatefulFixtureTools,
    ToolExecutionResult,
    compare_traces,
    record_run,
)


ROOT = Path(__file__).resolve().parents[1]
BEHAVIORS = {"normal", "wrong-order", "wrong-amount", "skip-eligibility", "duplicate-refund"}
INITIAL_STATE = {
    "orders": {
        "123": {
            "customer_id": "customer-7",
            "status": "not_shipped",
            "paid_amount": 88,
            "refund_eligible": True,
            "refund_count": 0,
            "refunded_amount": 0,
        },
        "456": {
            "customer_id": "customer-9",
            "status": "shipped",
            "paid_amount": 40,
            "refund_eligible": False,
            "refund_count": 0,
            "refunded_amount": 0,
        },
    }
}


def get_order(world, arguments):
    order_id = str(arguments["order_id"])
    order = world.data["orders"].get(order_id)
    if order is None:
        return ToolExecutionResult(
            {"order_id": order_id, "found": False},
            is_error=True,
            error="order_not_found",
        )
    return {"order_id": order_id, "found": True, **deepcopy(order)}


def check_refund_eligibility(world, arguments):
    order_id = str(arguments["order_id"])
    order = world.data["orders"].get(order_id)
    if order is None:
        return ToolExecutionResult(
            {"order_id": order_id, "eligible": False, "max_refund_amount": 0},
            is_error=True,
            error="order_not_found",
        )
    return {
        "order_id": order_id,
        "eligible": order["refund_eligible"] and order["refund_count"] == 0,
        "max_refund_amount": order["paid_amount"],
    }


def refund_order(world, arguments):
    order_id = str(arguments["order_id"])
    amount = arguments["amount"]
    order = world.data["orders"].get(order_id)
    if order is None:
        return ToolExecutionResult(
            {"order_id": order_id, "refunded": False, "refunded_amount": 0},
            is_error=True,
            error="order_not_found",
        )
    if amount > order["paid_amount"]:
        return ToolExecutionResult(
            {
                "order_id": order_id,
                "refunded": False,
                "refunded_amount": 0,
                "paid_amount": order["paid_amount"],
                "requested_amount": amount,
            },
            is_error=True,
            error="amount_exceeds_paid_amount",
        )
    if order["refund_count"] > 0:
        return ToolExecutionResult(
            {"order_id": order_id, "refunded": False, "refunded_amount": 0},
            is_error=True,
            error="duplicate_refund",
        )
    if not order["refund_eligible"]:
        return ToolExecutionResult(
            {"order_id": order_id, "refunded": False, "refunded_amount": 0},
            is_error=True,
            error="refund_not_eligible",
        )
    order["refund_count"] += 1
    order["refunded_amount"] = amount
    order["status"] = "refunded"
    return {
        "order_id": order_id,
        "refunded": True,
        "refunded_amount": amount,
    }


class RefundAgent:
    """Reference Agent whose answer is derived from live tool results."""

    def __init__(self, behavior: str):
        if behavior not in BEHAVIORS:
            raise ValueError(f"unsupported refund behavior: {behavior!r}")
        self.behavior = behavior

    @property
    def identity(self) -> Mapping[str, Any]:
        return {"name": "refund-business-agent", "version": "1.0.0", "behavior": self.behavior}

    def run(self, request: Any, context) -> None:
        requested_order_id = str(request["order_id"])
        lookup_order_id = "456" if self.behavior == "wrong-order" else requested_order_id
        order = context.call_tool("get_order", {"order_id": lookup_order_id})
        if not order.get("found"):
            context.final_answer(
                f"未找到订单 {requested_order_id}。",
                {
                    "order_id": requested_order_id,
                    "refund_status": "not_found",
                    "refund_amount": 0,
                    "refund_eligible": False,
                },
            )
            return

        eligibility = {"eligible": False, "max_refund_amount": 0}
        if self.behavior != "skip-eligibility":
            eligibility = context.call_tool(
                "check_refund_eligibility", {"order_id": lookup_order_id}
            )
        amount = 880 if self.behavior == "wrong-amount" else order["paid_amount"]
        refund = context.call_tool(
            "refund_order", {"order_id": lookup_order_id, "amount": amount}
        )
        if self.behavior == "duplicate-refund":
            refund = context.call_tool(
                "refund_order", {"order_id": lookup_order_id, "amount": amount}
            )

        successful = bool(refund.get("refunded"))
        context.final_answer(
            f"订单 {requested_order_id}退款{'完成' if successful else '失败'}。",
            {
                "order_id": requested_order_id,
                "refund_status": "refunded" if successful else "rejected",
                "refund_amount": amount if successful else 0,
                "refund_eligible": bool(eligibility.get("eligible")),
            },
        )


def build_tools() -> StatefulFixtureTools:
    return StatefulFixtureTools(
        INITIAL_STATE,
        {
            "get_order": get_order,
            "check_refund_eligibility": check_refund_eligibility,
            "refund_order": refund_order,
        },
    )


def build_contract() -> ContractPolicy:
    return ContractPolicy.from_dict(
        {
            "required_claims": [
                "final_answer.claims.order_id",
                "final_answer.claims.refund_status",
                "final_answer.claims.refund_amount",
                "final_answer.claims.refund_eligible",
            ],
            "assertions": [
                {"path": "final_answer.claims.order_id", "equals": "123"},
                {"path": "final_answer.claims.refund_status", "equals": "refunded"},
                {"path": "final_answer.claims.refund_amount", "equals": 88},
                {"path": "final_answer.claims.refund_eligible", "equals": True},
            ],
            "must_call": [
                {"tool": "get_order"},
                {"tool": "check_refund_eligibility"},
                {"tool": "refund_order"},
            ],
            "tool_limits": [
                {"tool": "get_order", "min_calls": 1, "max_calls": 1},
                {
                    "tool": "check_refund_eligibility",
                    "min_calls": 1,
                    "max_calls": 1,
                },
                {"tool": "refund_order", "min_calls": 1, "max_calls": 1},
            ],
            "tool_allowlist": [
                "get_order",
                "check_refund_eligibility",
                "refund_order",
            ],
            "must_not_call": ["delete_order"],
            "path_rules": {
                "any_of": [[
                    {"tool": "get_order", "is_error": False},
                    {"tool": "check_refund_eligibility", "is_error": False},
                    {"tool": "refund_order", "is_error": False},
                ]]
            },
            "side_effects": [
                {"path": "orders.123.refund_count", "from": 0, "to": 1},
                {"path": "orders.123.refunded_amount", "from": 0, "to": 88},
                {"path": "orders.123.status", "from": "not_shipped", "to": "refunded"},
            ],
            "relations": [
                {
                    "left": "tool_calls[0].arguments.order_id",
                    "operator": "equals",
                    "value": "123",
                    "message": "退款必须先查询用户请求中的订单",
                },
                {
                    "left": "tool_calls[1].arguments.order_id",
                    "operator": "equals_path",
                    "right_path": "tool_results[0].result.order_id",
                    "message": "资格检查必须使用订单查询返回的订单号",
                },
                {
                    "left": "tool_calls[2].arguments.order_id",
                    "operator": "equals_path",
                    "right_path": "tool_results[0].result.order_id",
                    "message": "退款必须使用订单查询返回的订单号",
                },
                {
                    "left": "tool_calls[2].arguments.amount",
                    "operator": "less_or_equal_path",
                    "right_path": "tool_results[0].result.paid_amount",
                    "message": "退款金额不得超过订单实付金额",
                },
                {
                    "left": "tool_calls[2].arguments.amount",
                    "operator": "equals_path",
                    "right_path": "tool_results[1].result.max_refund_amount",
                    "message": "退款金额必须遵守资格检查给出的上限",
                },
            ],
            "max_steps": 3,
        }
    )


def write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(behavior: str, out: Path, compare_to: Path | None = None, report: Path | None = None) -> int:
    trace = record_run(
        RefundAgent(behavior),
        {"order_id": "123", "request": "请退掉订单 123"},
        build_tools(),
        run_id=f"refund-{behavior}",
        metadata={"case": "order-refund", "behavior": behavior},
    )
    write_json(out, trace.to_dict())
    if compare_to is None:
        print(f"recorded {behavior}: {out}")
        return 0

    baseline = json.loads(compare_to.read_text(encoding="utf-8"))
    from agent_regression import AgentTrace

    result = compare_traces(
        AgentTrace.from_dict(baseline),
        trace,
        ComparisonPolicy(final_answer_mode="claims-only", contract=build_contract()),
    )
    if report:
        write_json(report, result)
    print(json.dumps({"passed": result["passed"], "blocking_difference_count": result["blocking_difference_count"]}, ensure_ascii=False))
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
