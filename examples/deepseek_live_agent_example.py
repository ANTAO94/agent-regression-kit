"""Low-cost live DeepSeek Agent regression example.

Requires ``DEEPSEEK_API_KEY``. The secret is read by the library and is never
written to the generated Trace.
"""

import json
import os
from pathlib import Path

from agent_regression import record_deepseek_tool_run


def get_order(order_id: str) -> dict:
    """Return the same deterministic business fixture as the reviewed baseline."""
    return {"order_id": order_id, "status": "not_shipped"}


def extract_claims(content: str) -> dict:
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("DeepSeek final answer must be a JSON object")
    return {
        "order_id": str(value["order_id"]),
        "order_status": value["order_status"],
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Return the current state of one order by its exact ID.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
    }
]


def main() -> None:
    trace = record_deepseek_tool_run(
        "查询订单 123",
        run_id="deepseek-live-order-123",
        system_prompt=(
            "你是订单 Agent。必须先调用 get_order，严格使用用户给出的订单号。"
            "拿到结果后只输出 JSON，格式为 "
            '{"order_id":"123","order_status":"not_shipped"}。'
        ),
        tools=TOOLS,
        tool_handlers={"get_order": get_order},
        claims_extractor=extract_claims,
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        force_first_tool="get_order",
        max_tokens=64,
        timeout=45.0,
    )
    destination = Path(
        os.environ.get("AGENT_TRACE_OUT", "work/deepseek-live.trace.json")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(destination)


if __name__ == "__main__":
    main()
