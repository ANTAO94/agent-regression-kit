"""Show how to isolate a tool executor backed by external mutable state.

Run from the repository root with:

    PYTHONPATH=src python3 examples/external_state_backend_example.py

Replace ``ExternalOrderStore`` with an adapter around a test database, cache,
or service emulator in a real project.
"""

from __future__ import annotations

from copy import deepcopy
import json

from agent_regression import ScriptedAgentAdapter, isolated_record_run


class ExternalOrderStore:
    """A deterministic stand-in for a database transaction fixture."""

    def __init__(self):
        self.data = {"orders": {"123": {"status": "paid"}}}

    def snapshot(self):
        return deepcopy(self.data)

    def restore(self, snapshot):
        self.data = deepcopy(snapshot)


class OrderTools:
    def __init__(self, store):
        self.store = store

    def call(self, tool, arguments):
        if tool != "cancel_order":
            raise KeyError(tool)
        order = self.store.data["orders"][arguments["order_id"]]
        order["status"] = "cancelled"
        return deepcopy(order)


def main() -> int:
    store = ExternalOrderStore()
    tools = OrderTools(store)
    adapter = ScriptedAgentAdapter(
        {"name": "external-state-demo", "version": "1.0.0"},
        [
            {
                "type": "tool_call",
                "tool": "cancel_order",
                "arguments": {"order_id": "123"},
            },
            {
                "type": "final_answer",
                "text": "订单已取消。",
                "claims": {"order_status": "cancelled"},
            },
        ],
    )

    trace = isolated_record_run(
        adapter,
        "取消订单 123",
        tools,
        state_backend=store,
        run_id="external-state-demo-123",
    )

    assert trace.metadata["world_state"]["final"]["orders"]["123"]["status"] == "cancelled"
    assert store.data["orders"]["123"]["status"] == "paid"
    print(
        json.dumps(
            {
                "trace_run_id": trace.run_id,
                "recorded_final_status": trace.metadata["world_state"]["final"]["orders"]["123"]["status"],
                "store_status_after_restore": store.data["orders"]["123"]["status"],
                "isolated": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
