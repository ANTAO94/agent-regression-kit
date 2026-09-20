"""Low-cost live DeepSeek multi-tool dependency-chain example.

Requires ``DEEPSEEK_API_KEY``. The model must copy status and amount from the
first tool result into the second tool call; the generated Trace contains no
provider credential.
"""

import json
import os
from pathlib import Path

from agent_regression import record_deepseek_tool_run


def get_order(order_id: str) -> dict:
    return {"order_id": order_id, "status": "not_shipped", "paid_amount": 88}


def check_refund_eligibility(
    order_id: str, order_status: str, paid_amount: float
) -> dict:
    return {
        "order_id": order_id,
        "eligible": order_status == "not_shipped",
        "refund_amount": paid_amount if order_status == "not_shipped" else 0,
    }


def extract_claims(content: str) -> dict:
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("DeepSeek final answer must be a JSON object")
    return {
        "order_id": str(value["order_id"]),
        "order_status": value["order_status"],
        "refund_eligible": value["refund_eligible"],
        "refund_amount": value["refund_amount"],
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Return order status and paid amount for an exact order ID.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_refund_eligibility",
            "description": "Check refund eligibility from the observed order data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "order_status": {"type": "string"},
                    "paid_amount": {"type": "number"},
                },
                "required": ["order_id", "order_status", "paid_amount"],
                "additionalProperties": False,
            },
        },
    },
]


def main() -> None:
    trace = record_deepseek_tool_run(
        "查询订单 123；如果尚未发货，检查退款资格并返回可退款金额。",
        run_id="deepseek-live-refund-123",
        system_prompt=(
            "你是订单退款 Agent。先查询订单，再把查询结果中的真实订单号、状态和已付金额"
            "传给退款资格工具，不得猜测或修改字段。最后只输出 JSON："
            '{"order_id":"123","order_status":"not_shipped",'
            '"refund_eligible":true,"refund_amount":88}。'
        ),
        tools=TOOLS,
        tool_handlers={
            "get_order": get_order,
            "check_refund_eligibility": check_refund_eligibility,
        },
        claims_extractor=extract_claims,
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        required_tool_sequence=("get_order", "check_refund_eligibility"),
        max_tokens=96,
        timeout=45.0,
    )
    destination = Path(
        os.environ.get("AGENT_TRACE_OUT", "work/deepseek-multi-tool.trace.json")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(destination)


if __name__ == "__main__":
    main()
