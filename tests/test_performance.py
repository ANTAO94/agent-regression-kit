import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression.cli import main
from agent_regression.performance import (
    evaluate_performance_gate,
    run_performance_benchmark,
)


class PerformanceTests(unittest.TestCase):
    def test_fixed_workloads_emit_environment_and_throughput(self):
        report = run_performance_benchmark(
            small_count=4,
            medium_count=2,
            medium_tool_calls=10,
        )
        self.assertEqual("agent_performance", report["report_type"])
        self.assertTrue(report["passed"])
        self.assertEqual(["small", "medium"], [item["name"] for item in report["workloads"]])
        self.assertEqual(21, report["workloads"][1]["events_per_trace"])
        self.assertIn("python", report["environment"])
        self.assertGreater(report["workloads"][0]["traces_per_second"], 0)

    def test_gate_warns_and_blocks_only_at_explicit_thresholds(self):
        baseline = {
            "workloads": [
                {"name": "small", "elapsed_seconds": 1.0},
                {"name": "medium", "elapsed_seconds": 2.0},
            ]
        }
        warning = {
            "workloads": [
                {"name": "small", "elapsed_seconds": 1.3},
                {"name": "medium", "elapsed_seconds": 2.0},
            ]
        }
        blocked = {
            "workloads": [
                {"name": "small", "elapsed_seconds": 1.41},
                {"name": "medium", "elapsed_seconds": 2.0},
            ]
        }
        warning_report = evaluate_performance_gate(warning, baseline)
        self.assertTrue(warning_report["passed"])
        self.assertEqual("warning", warning_report["comparisons"][0]["status"])
        blocked_report = evaluate_performance_gate(blocked, baseline)
        self.assertFalse(blocked_report["passed"])
        self.assertEqual("blocked", blocked_report["comparisons"][0]["status"])

    def test_cli_runs_and_gates_a_performance_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "current.json"
            baseline = root / "baseline.json"
            gate = root / "gate.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(
                        [
                            "performance",
                            "run",
                            "--small-count",
                            "2",
                            "--medium-count",
                            "1",
                            "--out",
                            str(current),
                        ]
                    ),
                )
            current_value = json.loads(current.read_text(encoding="utf-8"))
            baseline_value = json.loads(json.dumps(current_value))
            baseline_value["workloads"][0]["elapsed_seconds"] = max(
                current_value["workloads"][0]["elapsed_seconds"] * 2, 1.0
            )
            baseline.write_text(json.dumps(baseline_value), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(
                        [
                            "performance",
                            "gate",
                            "--current",
                            str(current),
                            "--baseline",
                            str(baseline),
                            "--out",
                            str(gate),
                        ]
                    ),
                )
            self.assertTrue(json.loads(gate.read_text(encoding="utf-8"))["passed"])
