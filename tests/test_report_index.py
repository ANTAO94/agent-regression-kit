import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import build_report_index, render_report_index_markdown
from agent_regression.cli import main


class ReportIndexTests(unittest.TestCase):
    def _write(self, root: Path, relative: str, value):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_index_keeps_relative_paths_and_safe_summaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "compare/order.json",
                {
                    "candidate_run_id": "candidate-1",
                    "baseline_run_id": "baseline-1",
                    "passed": False,
                    "difference_count": 2,
                    "blocking_difference_count": 1,
                    "differences": [{"candidate": "should-not-be-embedded"}],
                },
            )
            self._write(
                root,
                "history/ok.json",
                {
                    "report_type": "agent_stability",
                    "label": "v3.2.2",
                    "passed": True,
                    "pass_rate": 1.0,
                    "claims_match_rate": 1.0,
                    "tool_error_rate": 0.0,
                    "path_variant_count": 1,
                },
            )
            self._write(root, "ignored.json", {"not": "a regression report"})
            report = build_report_index(root)
            self.assertFalse(report["passed"])
            self.assertNotIn(str(root), json.dumps(report))
            self.assertEqual(2, report["report_count"])
            self.assertEqual("compare/order.json", report["entries"][0]["source"])
            self.assertNotIn("differences", json.dumps(report))
            self.assertEqual("ignored.json", report["skipped"][0]["source"])

    def test_invalid_json_reason_does_not_echo_an_absolute_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "broken.json").write_text("{broken", encoding="utf-8")
            report = build_report_index(root)
            self.assertIn("invalid JSON", report["skipped"][0]["reason"])
            self.assertNotIn(str(root), json.dumps(report))

    def test_markdown_and_cli_support_a_non_gating_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "ok.json",
                {
                    "report_type": "agent_compare",
                    "baseline_run_id": "b",
                    "candidate_run_id": "c",
                    "passed": True,
                    "difference_count": 0,
                    "blocking_difference_count": 0,
                },
            )
            report = build_report_index(root)
            self.assertIn("ok.json", render_report_index_markdown(report))
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["report-index", "--report-dir", str(root)]))
            self.assertEqual(1, json.loads(output.getvalue())["report_count"])

    def test_cli_can_turn_a_failed_index_into_a_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "failed.json",
                {
                    "candidate_run_id": "c",
                    "baseline_run_id": "b",
                    "passed": False,
                    "difference_count": 1,
                    "blocking_difference_count": 1,
                },
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    1,
                    main(["report-index", "--report-dir", str(root), "--fail-on-regression"]),
                )


if __name__ == "__main__":
    unittest.main()
