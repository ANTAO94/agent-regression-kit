"""Generated adapter integration templates."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def _sync_adapter(name: str) -> str:
    return f'''"""Framework adapter template for {name}."""

from agent_regression import AdapterSpec


SPEC = AdapterSpec(name={name!r}, version="0.1.0")


def invoke_framework(request, context):
    """Replace this body with LangChain, Spring AI, or your own Agent call."""
    order_id = str(request).rsplit(" ", 1)[-1]
    order = context.call_tool("get_order", {{"order_id": order_id}})
    context.final_answer(
        f"Order {{order_id}} status: {{order['status']}}",
        {{"order_id": order_id, "order_status": order["status"]}},
    )


def build_adapter():
    return SPEC.build_sync(invoke_framework)
'''


def _async_adapter(name: str) -> str:
    return f'''"""Async framework adapter template for {name}."""

import asyncio

from agent_regression import AdapterSpec


SPEC = AdapterSpec(name={name!r}, version="0.1.0")


async def invoke_framework(request, context):
    """Replace this body with your async Agent call."""
    order_id = str(request).rsplit(" ", 1)[-1]
    order, shipping = await asyncio.gather(
        context.call_tool("get_order", {{"order_id": order_id}}, parallel_group="lookup"),
        context.call_tool("get_shipping", {{"order_id": order_id}}, parallel_group="lookup"),
    )
    context.final_answer(
        f"Order {{order_id}} status: {{order['status']}}; ETA: {{shipping['eta']}}",
        {{"order_id": order_id, "order_status": order["status"], "shipping_eta": shipping["eta"]}},
    )


def build_adapter():
    return SPEC.build_async(invoke_framework)
'''


def _sync_test() -> str:
    return '''import unittest

from agent_regression import FixtureTools, record_run

from adapter import build_adapter


class AdapterContractTests(unittest.TestCase):
    def test_adapter_emits_a_valid_trace(self):
        trace = record_run(
            build_adapter(),
            "lookup order 123",
            FixtureTools({"get_order": {"order_id": "123", "status": "paid"}}),
            run_id="template-sync",
        )
        self.assertEqual("template-sync", trace.run_id)
        self.assertEqual("get_order", trace.events[0]["tool"])
        self.assertEqual("paid", trace.events[-1]["claims"]["order_status"])


if __name__ == "__main__":
    unittest.main()
'''


def _async_test() -> str:
    return '''import unittest

from agent_regression import FixtureTools, record_async_run

from adapter import build_adapter


class AdapterContractTests(unittest.TestCase):
    def test_adapter_emits_a_valid_async_trace(self):
        trace = record_async_run(
            build_adapter(),
            "lookup order 123",
            FixtureTools({
                "get_order": {"order_id": "123", "status": "paid"},
                "get_shipping": {"order_id": "123", "eta": "tomorrow"},
            }),
            run_id="template-async",
        )
        self.assertEqual("template-async", trace.run_id)
        self.assertEqual(1, len(trace.metadata["execution"]["parallel_groups"]))


if __name__ == "__main__":
    unittest.main()
'''


def _both_adapter(name: str) -> str:
    return f'''"""Sync and async adapter template for {name}."""

import asyncio

from agent_regression import AdapterSpec


SPEC = AdapterSpec(name={name!r}, version="0.1.0")


def invoke_framework(request, context):
    order_id = str(request).rsplit(" ", 1)[-1]
    order = context.call_tool("get_order", {{"order_id": order_id}})
    context.final_answer(
        f"Order {{order_id}} status: {{order['status']}}",
        {{"order_id": order_id, "order_status": order["status"]}},
    )


async def invoke_framework_async(request, context):
    order_id = str(request).rsplit(" ", 1)[-1]
    order, shipping = await asyncio.gather(
        context.call_tool("get_order", {{"order_id": order_id}}, parallel_group="lookup"),
        context.call_tool("get_shipping", {{"order_id": order_id}}, parallel_group="lookup"),
    )
    context.final_answer(
        f"Order {{order_id}} status: {{order['status']}}; ETA: {{shipping['eta']}}",
        {{"order_id": order_id, "order_status": order["status"], "shipping_eta": shipping["eta"]}},
    )


def build_sync_adapter():
    return SPEC.build_sync(invoke_framework)


def build_async_adapter():
    return SPEC.build_async(invoke_framework_async)
'''


def _both_test() -> str:
    return '''import unittest

from agent_regression import FixtureTools, record_async_run, record_run

from adapter import build_async_adapter, build_sync_adapter


TOOLS = {
    "get_order": {"order_id": "123", "status": "paid"},
    "get_shipping": {"order_id": "123", "eta": "tomorrow"},
}


class AdapterContractTests(unittest.TestCase):
    def test_sync_adapter_emits_a_valid_trace(self):
        trace = record_run(
            build_sync_adapter(), "lookup order 123", FixtureTools(TOOLS), run_id="template-sync"
        )
        self.assertEqual("paid", trace.events[-1]["claims"]["order_status"])

    def test_async_adapter_emits_a_valid_trace(self):
        trace = record_async_run(
            build_async_adapter(), "lookup order 123", FixtureTools(TOOLS), run_id="template-async"
        )
        self.assertEqual(1, len(trace.metadata["execution"]["parallel_groups"]))


if __name__ == "__main__":
    unittest.main()
'''


def _readme(name: str, mode: str) -> str:
    return f'''# {name} Agent adapter template

This directory is a thin integration boundary. Replace the body of
`adapter.py` with your framework's `invoke`/`run` call, but keep these two
responsibilities explicit:

1. send every tool request through the provided `context.call_tool`;
2. finish exactly once through `context.final_answer` with structured claims.

The generated contract test is offline and deterministic. Run it with:

```bash
PYTHONPATH=.. python -m unittest discover -s tests -v
```

Generated mode: `{mode}`. For async mode, use `parallel_group="name"` for
calls started together and `await async_record_run(...)` when already inside
an event loop. The template does not make a framework thread-safe and does
not infer business claims from free-form prose.

## 中文说明

这是一个最小接入边界：把真实框架的 `invoke` / `run` 放进 `adapter.py`，
工具调用统一走 `context.call_tool`，最终回答统一走
`context.final_answer`，并尽量输出结构化 `claims`。先运行生成的离线契约
测试，再把 FixtureTools 换成真实 ToolExecutor。
'''


def initialize_adapter_template(
    root: Path,
    *,
    name: str = "my-agent",
    mode: str = "sync",
    force: bool = False,
) -> Dict[str, Any]:
    """Generate a runnable sync, async, or dual adapter starter project."""
    if mode not in {"sync", "async", "both"}:
        raise ValueError("adapter template mode must be 'sync', 'async', or 'both'")
    if not name.strip():
        raise ValueError("adapter template name must not be empty")
    if mode == "sync":
        adapter = _sync_adapter(name)
        test = _sync_test()
    elif mode == "async":
        adapter = _async_adapter(name)
        test = _async_test()
    else:
        adapter = _both_adapter(name)
        test = _both_test()
    files = {
        "adapter.py": adapter,
        "tests/test_adapter_contract.py": test,
        "README.md": _readme(name, mode),
    }
    created: List[str] = []
    skipped: List[str] = []
    for relative, content in files.items():
        destination = root / relative
        if destination.exists() and not force:
            skipped.append(relative)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        created.append(relative)
    return {"created": created, "skipped": skipped, "mode": mode, "name": name}
