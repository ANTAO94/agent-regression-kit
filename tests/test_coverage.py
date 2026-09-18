import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import AgentTrace, compare_trace_coverage, trace_tool_path
from agent_regression.cli import main
from agent_regression.reports import render_coverage_junit, render_coverage_markdown


def make_trace(run_id, tools):
    events = []
    sequence = 1
    for index, tool in enumerate(tools, start=1):
        call_id = f"call-{index}"
        events.extend(
            [
                {
                    "sequence": sequence,
                    "type": "tool_call",
                    "call_id": call_id,
                    "tool": tool,
                    "arguments": {},
                },
                {
                    "sequence": sequence + 1,
                    "type": "tool_result",
                    "call_id": call_id,
                    "result": {"ok": True},
                    "is_error": False,
                },
            ]
        )
        sequence += 2
    events.append(
        {
            "sequence": sequence,
            "type": "final_answer",
            "text": "done",
            "claims": {"ok": True},
        }
    )
    return AgentTrace.from_dict(
        {
            "schema_version": "0.1",
            "run_id": run_id,
            "agent": {"name": "coverage-test"},
            "events": events,
        }
    )


class CoverageTests(unittest.TestCase):
    def test_trace_tool_path_preserves_order(self):
        self.assertEqual(("lookup", "cancel"), trace_tool_path(make_trace("one", ["lookup", "cancel"])))

    def test_coverage_reports_observed_and_missing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "normal.trace.json").write_text(
                json.dumps(make_trace("normal", ["get_order"]).to_dict()), encoding="utf-8"
            )
            (root / "cancel.trace.json").write_text(
                json.dumps(make_trace("cancel", ["get_order", "cancel_order"]).to_dict()),
                encoding="utf-8",
            )
            report = compare_trace_coverage(
                root,
                expected_paths=["get_order", "get_order -> cancel_order", "get_order -> refund"],
            )

        self.assertFalse(report["passed"])
        self.assertEqual(2, report["case_count"])
        self.assertEqual(2, report["unique_path_count"])
        self.assertEqual(2, report["covered_expected_path_count"])
        self.assertEqual(66.67, report["coverage_percent"])
        self.assertEqual([["get_order", "refund"]], report["missing_paths"])

    def test_coverage_renderers_show_missing_branch(self):
        report = {
            "passed": False,
            "case_count": 1,
            "unique_path_count": 1,
            "expected_path_count": 2,
            "covered_expected_path_count": 1,
            "coverage_percent": 50.0,
            "paths": [{"path": ["get_order"], "signature": "get_order", "case_count": 1}],
            "expected_paths": [["get_order"], ["get_order", "cancel_order"]],
            "missing_paths": [["get_order", "cancel_order"]],
        }
        self.assertIn("`FAIL`", render_coverage_markdown(report))
        self.assertIn("get_order -> cancel_order", render_coverage_markdown(report))
        self.assertIn("AgentCoverageFailure", render_coverage_junit(report))

    def test_cli_coverage_returns_failure_for_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace_dir = root / "traces"
            trace_dir.mkdir()
            (trace_dir / "one.trace.json").write_text(
                json.dumps(make_trace("one", ["get_order"]).to_dict()), encoding="utf-8"
            )
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(
                    [
                        "coverage",
                        "--trace-dir",
                        str(trace_dir),
                        "--expected-path",
                        "get_order",
                        "--expected-path",
                        "get_order -> cancel_order",
                        "--format",
                        "markdown",
                    ]
                )
        self.assertEqual(1, status)
        self.assertIn("missing", output.getvalue())


if __name__ == "__main__":
    unittest.main()
