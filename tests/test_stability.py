import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import (
    CallableAgentAdapter,
    ComparisonPolicy,
    FixtureTools,
    ScenarioCase,
    ScriptedAgentAdapter,
    StabilityPolicy,
    StatefulFixtureTools,
    evaluate_stability,
    record_run,
    record_stability,
)
from agent_regression.cli import main


ROOT = Path(__file__).resolve().parents[1]


def make_trace(run_id, *, text="paid", path=None):
    actions = [
        {
            "type": "tool_call",
            "tool": "get_order",
            "arguments": {"order_id": "123"},
        }
    ]
    if path == "shipping":
        actions.append(
            {
                "type": "tool_call",
                "tool": "get_shipping",
                "arguments": {"order_id": "123"},
            }
        )
    actions.append(
        {
            "type": "final_answer",
            "text": text,
            "claims": {"order_status": "paid"},
        }
    )
    return record_run(
        ScriptedAgentAdapter({"name": "stability-agent"}, actions),
        "lookup 123",
        FixtureTools(
            {
                "get_order": {"order_id": "123", "status": "paid"},
                "get_shipping": {"order_id": "123", "eta": "tomorrow"},
            }
        ),
        run_id=run_id,
    )


class StabilityTests(unittest.TestCase):
    def test_identical_repeated_traces_pass_stability_thresholds(self):
        report = evaluate_stability(
            make_trace("baseline"),
            [make_trace("run-1"), make_trace("run-2")],
        )
        self.assertTrue(report.passed)
        self.assertEqual(1.0, report.pass_rate)
        self.assertEqual(1.0, report.claims_match_rate)
        self.assertEqual(1, len(report.path_variants))

    def test_claims_only_mode_allows_wording_variation(self):
        report = evaluate_stability(
            make_trace("baseline", text="订单已支付。"),
            [make_trace("run-1", text="支付状态正常。")],
            comparison_policy=ComparisonPolicy(final_answer_mode="claims-only"),
        )
        self.assertTrue(report.passed)
        self.assertEqual(1.0, report.claims_match_rate)
        self.assertEqual(0, report.runs[0].comparison["blocking_difference_count"])

    def test_path_variant_threshold_blocks_a_new_agent_path(self):
        report = evaluate_stability(
            make_trace("baseline"),
            [make_trace("run-1", path="shipping")],
            policy=StabilityPolicy(max_path_variants=1),
        )
        self.assertFalse(report.passed)
        self.assertEqual(2, len(report.path_variants))

    def test_record_stability_reuses_no_mutable_state_between_repeats(self):
        created = []

        def increment(world, arguments):
            del arguments
            world.data["count"] += 1
            return {"count": world.data["count"]}

        def runner(request, context):
            value = context.call_tool("increment", {})
            context.final_answer(str(request), {"count": value["count"]})

        def make_tools():
            tools = StatefulFixtureTools({"count": 0}, {"increment": increment})
            created.append(tools)
            return tools

        def make_adapter():
            return CallableAgentAdapter({"name": "stable-state-agent"}, runner)

        baseline = record_run(
            make_adapter(),
            "request",
            make_tools(),
            run_id="baseline",
        )
        case = ScenarioCase(
            case_id="state-case",
            request="request",
            run_id="state-case",
            adapter_factory=make_adapter,
            tools_factory=make_tools,
            isolate=True,
        )
        report = record_stability(baseline, case, repeats=3, max_workers=2)

        self.assertTrue(report.passed)
        self.assertEqual(3, report.run_count)
        self.assertTrue(all(tool.snapshot()["count"] == 0 for tool in created[1:]))

    def test_failed_repeat_is_reported_and_blocks_the_gate(self):
        case = ScenarioCase(
            case_id="broken-case",
            request="request",
            run_id="broken-case",
            adapter_factory=lambda: (_ for _ in ()).throw(RuntimeError("model unavailable")),
            tools_factory=lambda: FixtureTools({}),
        )
        report = record_stability(
            make_trace("baseline"),
            case,
            repeats=2,
            max_workers=2,
        )
        self.assertFalse(report.passed)
        self.assertEqual(0.0, report.pass_rate)
        self.assertIn("model unavailable", report.runs[0].error)

    def test_stability_cli_writes_a_markdown_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.trace.json"
            scenario = root / "scenario.json"
            output = root / "stability.md"
            baseline.write_text(
                (ROOT / "baselines/order-123.trace.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            scenario.write_text(
                (ROOT / "examples/order-123/baseline.scenario.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                status = main(
                    [
                        "stability",
                        "--baseline",
                        str(baseline),
                        "--scenario",
                        str(scenario),
                        "--repeats",
                        "2",
                        "--workers",
                        "2",
                        "--format",
                        "markdown",
                        "--out",
                        str(output),
                    ]
                )
            self.assertEqual(0, status)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("Agent Stability Evaluation", rendered)
            self.assertIn("`PASS`", rendered)


if __name__ == "__main__":
    unittest.main()
