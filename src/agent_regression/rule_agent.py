"""Deterministic reference Agent that decides from live tool results."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .adapters import RunContext


NORMAL = "normal"
PARAMETER_REGRESSION = "parameter_regression"
RESULT_MISREAD = "result_misread"
_BEHAVIORS = {NORMAL, PARAMETER_REGRESSION, RESULT_MISREAD}


class RuleBasedOrderAgentAdapter:
    """Choose the order tool, call it, then answer from its returned value.

    Two controlled defects make regression behavior reproducible:
    ``parameter_regression`` sends a numeric ID as an integer, while
    ``result_misread`` interprets ``not_shipped`` as ``shipped``.
    """

    def __init__(self, behavior: str = NORMAL):
        if behavior not in _BEHAVIORS:
            raise ValueError(f"unsupported rule-agent behavior: {behavior!r}")
        self.behavior = behavior

    @property
    def identity(self) -> Mapping[str, Any]:
        return {
            "name": "rule-order-agent",
            "version": "1.0.0",
            "behavior": self.behavior,
        }

    def run(self, request: Any, context: RunContext) -> None:
        order_id = _extract_order_id(request)
        tool_order_id: Any = order_id
        if self.behavior == PARAMETER_REGRESSION and order_id.isdecimal():
            tool_order_id = int(order_id)

        result = context.call_tool("get_order", {"order_id": tool_order_id})
        if not isinstance(result, dict):
            context.final_answer(
                "订单查询失败：工具返回了无法识别的结果。",
                {"order_id": order_id, "error": "invalid_tool_result"},
            )
            return

        if isinstance(result.get("error"), str):
            message = str(result.get("message", result["error"]))
            context.final_answer(
                f"订单查询失败：{message}",
                {"order_id": order_id, "error": result["error"]},
            )
            return

        returned_order_id = str(result.get("order_id", order_id))
        status = result.get("status")
        interpreted_status = (
            "shipped"
            if self.behavior == RESULT_MISREAD and status == "not_shipped"
            else status
        )
        context.final_answer(
            _render_answer(returned_order_id, interpreted_status),
            {"order_id": returned_order_id, "order_status": interpreted_status},
        )


def _extract_order_id(request: Any) -> str:
    if isinstance(request, dict):
        order_id = request.get("order_id")
        if isinstance(order_id, (str, int)) and not isinstance(order_id, bool):
            return str(order_id)
    if isinstance(request, str):
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", request)
        if tokens:
            return tokens[-1]
    raise ValueError("order query must contain an order_id")


def _render_answer(order_id: str, status: Any) -> str:
    if status == "not_shipped":
        return f"订单 {order_id} 尚未发货。"
    if status == "shipped":
        return f"订单 {order_id} 已发货。"
    if status == "not_found":
        return f"未找到订单 {order_id}。"
    return f"订单 {order_id} 的状态为 {status!s}。"
