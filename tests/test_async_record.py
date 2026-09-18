import asyncio
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import (
    AsyncCallableAgentAdapter,
    ComparisonPolicy,
    async_record_run,
    compare_traces,
    record_async_run,
)
from agent_regression.cli import main


ROOT = Path(__file__).resolve().parents[1]


class AsyncTools:
    async def call_async(self, tool, arguments):
        await asyncio.sleep(0.02 if tool == "get_order" else 0.001)
        return {"tool": tool, "order_id": arguments["order_id"]}


async def parallel_agent(request, context, second_group=False):
    order_id = str(request).rsplit(" ", 1)[-1]
    group = "group-2" if second_group else "group-1"
    order, shipping = await asyncio.gather(
        context.call_tool("get_order", {"order_id": order_id}, parallel_group=group),
        context.call_tool("get_shipping", {"order_id": order_id}, parallel_group=group),
    )
    context.final_answer(
        "done",
        {"order_id": order_id, "order": order["tool"], "shipping": shipping["tool"]},
    )


def make_adapter(second_group=False):
    async def runner(request, context):
        await parallel_agent(request, context, second_group=second_group)

    return AsyncCallableAgentAdapter({"name": "async-test-agent"}, runner)


class AsyncRecordTests(unittest.TestCase):
    def test_parallel_results_are_stable_and_grouped_by_call_creation(self):
        first = record_async_run(
            make_adapter(), AsyncToolsRequest(), AsyncTools(), run_id="first"
        )
        second = record_async_run(
            make_adapter(), AsyncToolsRequest(), AsyncTools(), run_id="second"
        )

        self.assertEqual(
            ["tool_call", "tool_call", "tool_result", "tool_result", "final_answer"],
            [event["type"] for event in first.events],
        )
        self.assertEqual(
            [event["type"] for event in first.events],
            [event["type"] for event in second.events],
        )
        self.assertEqual(
            [event["tool"] for event in first.events if event["type"] == "tool_call"],
            ["get_order", "get_shipping"],
        )
        self.assertEqual(
            [event["call_id"] for event in first.events if event["type"] == "tool_result"],
            ["call-1", "call-2"],
        )
        self.assertEqual(
            {"group_id": "group-1", "call_ids": ["call-1", "call-2"], "call_count": 2},
            first.metadata["execution"]["parallel_groups"][0],
        )
        self.assertEqual(first.events, second.events)

    def test_async_record_can_be_awaited_inside_an_event_loop(self):
        async def run():
            return await async_record_run(
                make_adapter(), AsyncToolsRequest(), AsyncTools(), run_id="inside-loop"
            )

        trace = asyncio.run(run())
        self.assertEqual("async", trace.metadata["execution"]["mode"])

    def test_parallel_group_change_is_a_blocking_comparison_difference(self):
        baseline = record_async_run(
            make_adapter(), AsyncToolsRequest(), AsyncTools(), run_id="baseline"
        )
        candidate = record_async_run(
            make_adapter(second_group=True), AsyncToolsRequest(), AsyncTools(), run_id="candidate"
        )
        report = compare_traces(baseline, candidate, ComparisonPolicy())
        self.assertFalse(report["passed"])
        self.assertIn("execution_concurrency", {item["category"] for item in report["differences"]})

    def test_async_record_cli_writes_markdown_execution_report(self):
        with self.subTest("cli"):
            with __import__("tempfile").TemporaryDirectory() as directory:
                output = Path(directory) / "async.md"
                with redirect_stdout(io.StringIO()):
                    status = main(
                        [
                            "async-record",
                            "--scenario",
                            str(ROOT / "examples/async-order/parallel.scenario.json"),
                            "--out",
                            str(output),
                            "--format",
                            "markdown",
                        ]
                    )
                self.assertEqual(0, status)
                rendered = output.read_text(encoding="utf-8")
                self.assertIn("Agent Async Trace", rendered)
                self.assertIn("group-1", rendered)


class AsyncToolsRequest:
    def __str__(self):
        return "查询订单 123"


if __name__ == "__main__":
    unittest.main()
