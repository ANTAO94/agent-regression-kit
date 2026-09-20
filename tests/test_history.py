import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import build_history_report
from agent_regression.cli import main
from agent_regression.reports import render_history_junit, render_history_markdown


def write_report(root: Path, name: str, value):
    path = root / name
    path.write_text(json.dumps(value), encoding="utf-8")


class HistoryTests(unittest.TestCase):
    def test_history_rejects_unknown_explicit_types_and_non_boolean_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_report(
                root,
                "001-unknown.json",
                {
                    "report_type": "made_up",
                    "candidate_run_id": "candidate",
                    "blocking_difference_count": 0,
                    "passed": True,
                },
            )
            write_report(
                root,
                "002-bad-status.json",
                {
                    "report_type": "agent_compare",
                    "candidate_run_id": "candidate",
                    "blocking_difference_count": 1,
                    "passed": "false",
                },
            )
            write_report(
                root,
                "003-valid.json",
                {
                    "report_type": "agent_compare",
                    "candidate_run_id": "candidate",
                    "blocking_difference_count": 0,
                    "passed": True,
                },
            )
            report = build_history_report(root)

        self.assertEqual(1, report.point_count)
        self.assertTrue(report.passed)
        self.assertEqual(
            ["unrecognized regression report", "recognized report passed must be a boolean"],
            [entry["reason"] for entry in report.skipped],
        )

    def test_history_orders_points_and_calculates_metric_deltas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_report(
                root,
                "002-v2.9.json",
                {
                    "report_type": "agent_stability",
                    "label": "v2.9.0",
                    "passed": True,
                    "pass_rate": 0.9,
                    "claims_match_rate": 1.0,
                    "tool_error_rate": 0.1,
                    "path_variant_count": 2,
                },
            )
            write_report(
                root,
                "001-v2.8.json",
                {
                    "report_type": "agent_stability",
                    "label": "v2.8.0",
                    "passed": True,
                    "pass_rate": 1.0,
                    "claims_match_rate": 1.0,
                    "tool_error_rate": 0.0,
                    "path_variant_count": 1,
                },
            )
            write_report(root, "notes.json", {"hello": "world"})
            report = build_history_report(root)

        self.assertTrue(report.passed)
        self.assertEqual(["v2.8.0", "v2.9.0"], [point.label for point in report.points])
        self.assertEqual(2, report.point_count)
        self.assertEqual(0.9, report.metric_trends["pass_rate"]["latest"])
        self.assertEqual(-0.1, report.metric_trends["pass_rate"]["delta"])
        self.assertEqual([{"source": "notes.json", "reason": "unrecognized regression report"}], report.skipped)

    def test_history_normalizes_compare_batch_and_coverage_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_report(
                root,
                "001-compare.json",
                {
                    "candidate_run_id": "candidate-1",
                    "passed": False,
                    "difference_count": 2,
                    "blocking_difference_count": 1,
                },
            )
            write_report(
                root,
                "002-batch.json",
                {
                    "report_type": "agent_batch",
                    "passed": True,
                    "case_count": 2,
                    "passed_case_count": 2,
                    "failed_case_count": 0,
                    "cases": [],
                },
            )
            write_report(
                root,
                "003-coverage.json",
                {
                    "report_type": "agent_coverage",
                    "passed": True,
                    "case_count": 2,
                    "unique_path_count": 2,
                    "coverage_percent": 100.0,
                },
            )
            report = build_history_report(root)

        self.assertEqual(
            ["agent_compare", "agent_batch", "agent_coverage"],
            [point.report_type for point in report.points],
        )
        self.assertFalse(report.points[0].passed)
        self.assertEqual(1.0, report.points[1].metrics["pass_rate"])
        self.assertEqual(100.0, report.points[2].metrics["coverage_percent"])
        self.assertTrue(report.passed)
        self.assertEqual(1, report.regression_count)

    def test_history_latest_failure_is_the_gate_and_renderers_expose_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_report(
                root,
                "001-pass.json",
                {"report_type": "agent_stability", "label": "pass", "passed": True, "pass_rate": 1.0},
            )
            write_report(
                root,
                "002-fail.json",
                {"report_type": "agent_stability", "label": "fail", "passed": False, "pass_rate": 0.0},
            )
            report = build_history_report(root).to_dict()

        self.assertFalse(report["passed"])
        self.assertEqual("fail", report["latest_label"])
        self.assertIn("Agent Regression History", render_history_markdown(report))
        self.assertIn("AgentHistoryRegression", render_history_junit(report))

    def test_history_cli_writes_markdown_for_example_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "history.md"
            with redirect_stdout(io.StringIO()):
                status = main(
                    [
                        "history",
                        "--report-dir",
                        str(Path(__file__).resolve().parents[1] / "examples/history"),
                        "--format",
                        "markdown",
                        "--out",
                        str(output),
                    ]
                )
            self.assertEqual(0, status)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("v3.0.0", rendered)
            self.assertIn("Metric trends", rendered)


if __name__ == "__main__":
    unittest.main()
