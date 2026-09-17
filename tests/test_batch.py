import json
import tempfile
import unittest
from pathlib import Path

from agent_regression import compare_trace_batch


ROOT = Path(__file__).resolve().parents[1]


class BatchComparisonTests(unittest.TestCase):
    def test_batch_compare_matches_nested_cases_and_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baselines"
            candidate = root / "candidate"
            baseline.mkdir()
            candidate.mkdir()
            source = json.loads(
                (ROOT / "baselines/order-123.trace.json").read_text(encoding="utf-8")
            )
            nested = baseline / "orders/order-123.trace.json"
            nested.parent.mkdir()
            nested.write_text(json.dumps(source), encoding="utf-8")
            changed = dict(source)
            changed["run_id"] = "candidate"
            changed["events"] = [dict(event) for event in source["events"]]
            changed["events"][-1]["text"] = "changed"
            (candidate / "orders").mkdir()
            (candidate / "orders/order-123.trace.json").write_text(
                json.dumps(changed), encoding="utf-8"
            )
            (candidate / "extra.trace.json").write_text(json.dumps(source), encoding="utf-8")

            report = compare_trace_batch(baseline, candidate)

        self.assertFalse(report["passed"])
        self.assertEqual(2, report["case_count"])
        self.assertEqual(["extra.trace.json"], report["missing_baselines"])
        self.assertEqual(2, report["failed_case_count"])

    def test_empty_batch_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = compare_trace_batch(root / "baseline", root / "candidate")
        self.assertTrue(report["passed"])
        self.assertEqual(0, report["case_count"])


if __name__ == "__main__":
    unittest.main()
