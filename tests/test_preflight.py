import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression.cli import main


ROOT = Path(__file__).resolve().parents[1]


class PreflightTests(unittest.TestCase):
    def test_check_validates_single_config_and_trace_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["record", "--scenario", str(ROOT / "examples/order-123/baseline.scenario.json"), "--out", str(baseline)]))
                self.assertEqual(0, main(["record", "--scenario", str(ROOT / "examples/order-123/candidate-ok.scenario.json"), "--out", str(candidate)]))
            config = root / ".agent-regression/config.json"
            config.parent.mkdir()
            config.write_text(json.dumps({"baseline": "baseline.json", "candidate": "candidate.json"}), encoding="utf-8")
            check_output = io.StringIO()
            with redirect_stdout(check_output):
                self.assertEqual(0, main(["check", "--config", str(config)]))
            report = json.loads(check_output.getvalue())
            self.assertTrue(report["ok"])
            self.assertEqual("single", report["kind"])
            self.assertEqual(2, len(report["traces"]))

    def test_check_returns_input_error_for_missing_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text(json.dumps({"baseline": "missing.json", "candidate": "missing-2.json"}), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(2, main(["check", "--config", str(config)]))
            self.assertIn("trace not found", output.getvalue())

    def test_check_surfaces_v413_contract_migration_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["record", "--scenario", str(ROOT / "examples/order-123/baseline.scenario.json"), "--out", str(baseline)]))
                self.assertEqual(0, main(["record", "--scenario", str(ROOT / "examples/order-123/candidate-ok.scenario.json"), "--out", str(candidate)]))
            config = root / ".agent-regression/config.json"
            config.parent.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "baseline": "baseline.json",
                        "candidate": "candidate.json",
                        "contract": {
                            "state_equivalence": {
                                "mode": "outcome",
                                "paths": ["world_state.order.status"],
                                "allow_failed_expected": True,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["check", "--config", str(config)]))
            report = json.loads(output.getvalue())
            codes = {item["code"] for item in report["diagnostics"]}
            self.assertEqual(
                {"legacy_allow_failed_expected", "implicit_state_scope"},
                codes,
            )

    def test_check_validates_matching_batch_trace_sets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline_dir = root / "baselines"
            candidate_dir = root / "candidate"
            baseline_dir.mkdir()
            candidate_dir.mkdir()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main([
                        "record",
                        "--scenario",
                        str(ROOT / "examples/order-123/baseline.scenario.json"),
                        "--out",
                        str(baseline_dir / "order.trace.json"),
                    ]),
                )
                self.assertEqual(
                    0,
                    main([
                        "record",
                        "--scenario",
                        str(ROOT / "examples/order-123/candidate-ok.scenario.json"),
                        "--out",
                        str(candidate_dir / "order.trace.json"),
                    ]),
                )
            config = root / ".agent-regression/batch.json"
            config.parent.mkdir()
            config.write_text(
                json.dumps({"baseline_dir": "baselines", "candidate_dir": "candidate"}),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["check", "--config", str(config), "--kind", "batch"]))
            report = json.loads(output.getvalue())
            self.assertTrue(report["ok"])
            self.assertEqual("batch", report["kind"])
            self.assertEqual(2, report["trace_count"])
