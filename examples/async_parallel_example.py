"""Record parallel tool calls inside one asynchronous Agent run.

Run from the repository root with:

    PYTHONPATH=src python3 examples/async_parallel_example.py

The two tools deliberately finish at different times. Their result events are
still emitted in call-creation order, while the Trace metadata records the
parallel group explicitly.
"""

from __future__ import annotations

import asyncio
import json

from agent_regression import AsyncCallableAgentAdapter, record_async_run


class AsyncOrderTools:
    async def call_async(self, tool, arguments):
        await asyncio.sleep(0.02 if tool == "get_order" else 0.001)
        if tool == "get_order":
            return {"order_id": arguments["order_id"], "status": "not_shipped"}
        if tool == "get_shipping":
            return {"order_id": arguments["order_id"], "eta": "tomorrow"}
        raise KeyError(tool)


async def run_agent(request, context):
    order_id = str(request).rsplit(" ", 1)[-1]
    order, shipping = await asyncio.gather(
        context.call_tool(
            "get_order",
            {"order_id": order_id},
            parallel_group="order-lookup",
        ),
        context.call_tool(
            "get_shipping",
            {"order_id": order_id},
            parallel_group="order-lookup",
        ),
    )
    context.final_answer(
        f"订单 {order_id} 尚未发货，预计 {shipping['eta']}。",
        {
            "order_id": order["order_id"],
            "order_status": order["status"],
            "shipping_eta": shipping["eta"],
        },
    )


def main() -> int:
    trace = record_async_run(
        AsyncCallableAgentAdapter(
            {"name": "async-order-agent", "version": "1.0.0"},
            run_agent,
        ),
        "查询订单 123",
        AsyncOrderTools(),
        run_id="async-order-123",
    )
    print(json.dumps(trace.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
