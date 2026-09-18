import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import (
    CallableAgentAdapter,
    ScenarioCase,
    StatefulFixtureTools,
    record_scenario_batch,
)
from agent_regression.cli import main
from agent_regression.reports import (
    render_scenario_batch_junit,
    render_scenario_batch_markdown,
)


def _increment(world, arguments):
    del arguments
    world.data["count"] += 1
    return {"count": world.data["count"]}


class ParallelRecordingTests(unittest.TestCase):
    def test_callable_adapter_bridges_a_framework_invoke_callback(self):
        adapter = CallableAgentAdapter(
            {"name": "framework-bridge"},
            lambda request, context: context.final_answer(f"handled: {request}"),
        )
        self.assertEqual("framework-bridge", adapter.identity["name"])

    def test_parallel_cases_are_isolated_and_sorted_by_case_id(self):
        created = {}

        def make_case(case_id):
            def make_tools():
                tools = StatefulFixtureTools({"count": 0}, {"increment": _increment})
                created[case_id] = tools
                return tools

            def runner(request, context):
                result = context.call_tool("increment", {})
                context.final_answer(
                    f"{request}: {result['count']}",
                    {"count": result["count"]},
                )

            return ScenarioCase(
                case_id=case_id,
                request=f"request-{case_id}",
                run_id=f"run-{case_id}",
                adapter_factory=lambda: CallableAgentAdapter(
                    {"name": "parallel-agent"}, runner
                ),
                tools_factory=make_tools,
                isolate=True,
            )

        batch = record_scenario_batch(
            [make_case("case-b"), make_case("case-a")],
            max_workers=2,
        )

        self.assertTrue(batch.passed)
        self.assertEqual(["case-a", "case-b"], [item.case_id for item in batch.results])
        self.assertEqual([1, 1], [item.trace.metadata["world_state"]["final"]["count"] for item in batch.results])
        self.assertEqual(0, created["case-a"].snapshot()["count"])
        self.assertEqual(0, created["case-b"].snapshot()["count"])
        self.assertEqual(2, batch.to_dict()["passed_case_count"])

    def test_parallel_batch_collects_one_case_failure_without_hiding_other_cases(self):
        def broken_adapter():
            raise RuntimeError("framework startup failed")

        good = ScenarioCase(
            case_id="good",
            request="ok",
            run_id="good-run",
            adapter_factory=lambda: CallableAgentAdapter(
                {"name": "good"},
                lambda request, context: context.final_answer(str(request)),
            ),
            tools_factory=lambda: StatefulFixtureTools({}, {}),
        )
        broken = ScenarioCase(
            case_id="broken",
            request="bad",
            run_id="broken-run",
            adapter_factory=broken_adapter,
            tools_factory=lambda: StatefulFixtureTools({}, {}),
        )

        batch = record_scenario_batch([good, broken], max_workers=2)

        self.assertFalse(batch.passed)
        self.assertEqual(["broken", "good"], [item.case_id for item in batch.results])
        self.assertIn("framework startup failed", batch.results[0].error)
        self.assertTrue(batch.results[1].passed)
        self.assertEqual(1, batch.to_dict()["failed_case_count"])

    def test_parallel_batch_rejects_invalid_worker_count_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            record_scenario_batch([], max_workers=0)

        case = ScenarioCase(
            case_id="same",
            request="request",
            run_id="run",
            adapter_factory=lambda: CallableAgentAdapter(
                {"name": "agent"}, lambda request, context: context.final_answer(str(request))
            ),
            tools_factory=lambda: StatefulFixtureTools({}, {}),
        )
        with self.assertRaises(ValueError):
            record_scenario_batch([case, case])

    def test_batch_record_cli_writes_sorted_trace_files_and_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario_dir = root / "scenarios"
            scenario_dir.mkdir()
            source = Path(__file__).resolve().parents[1] / "examples/order-123/baseline.scenario.json"
            first = json.loads(source.read_text(encoding="utf-8"))
            second = dict(first)
            second["run_id"] = "second"
            (scenario_dir / "z.scenario.json").write_text(
                json.dumps(first), encoding="utf-8"
            )
            (scenario_dir / "a.scenario.json").write_text(
                json.dumps(second), encoding="utf-8"
            )
            trace_dir = root / "traces"
            report_path = root / "batch-report.json"
            with redirect_stdout(io.StringIO()):
                status = main(
                    [
                        "batch-record",
                        "--scenario-dir",
                        str(scenario_dir),
                        "--out-dir",
                        str(trace_dir),
                        "--workers",
                        "2",
                        "--report",
                        str(report_path),
                    ]
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(0, status)
            self.assertEqual(["a.scenario.json", "z.scenario.json"], [case["case_id"] for case in report["cases"]])
            self.assertTrue((trace_dir / "a.trace.json").exists())
            self.assertTrue((trace_dir / "z.trace.json").exists())
            self.assertEqual("second", json.loads((trace_dir / "a.trace.json").read_text(encoding="utf-8"))["run_id"])
            self.assertIn("Agent Scenario Batch Recording", render_scenario_batch_markdown(report))
            self.assertIn("testsuite", render_scenario_batch_junit(report))


if __name__ == "__main__":
    unittest.main()
