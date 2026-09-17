import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression.cli import main


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_parameter_regression_returns_failure_status(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.json"
            candidate = Path(directory) / "candidate.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(
                        [
                            "record",
                            "--scenario",
                            str(ROOT / "examples/order-123/baseline.scenario.json"),
                            "--out",
                            str(baseline),
                        ]
                    ),
                )
                self.assertEqual(
                    0,
                    main(
                        [
                            "record",
                            "--scenario",
                            str(ROOT / "examples/order-123/candidate-regression.scenario.json"),
                            "--out",
                            str(candidate),
                        ]
                    ),
                )
                self.assertEqual(
                    1,
                    main(
                        [
                            "compare",
                            "--baseline",
                            str(baseline),
                            "--candidate",
                            str(candidate),
                        ]
                    ),
                )

    def test_mcp_record_replay_compare_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.json"
            candidate_ok = Path(directory) / "candidate-ok.json"
            candidate_bad = Path(directory) / "candidate-bad.json"
            output = io.StringIO()
            with redirect_stdout(output):
                for scenario, destination in [
                    ("baseline.scenario.json", baseline),
                    ("candidate-ok.scenario.json", candidate_ok),
                    ("candidate-regression.scenario.json", candidate_bad),
                ]:
                    self.assertEqual(
                        0,
                        main(
                            [
                                "mcp-record",
                                "--scenario",
                                str(ROOT / "examples/order-123" / scenario),
                                "--out",
                                str(destination),
                            ]
                        ),
                    )
                self.assertEqual(0, main(["replay", "--trace", str(baseline)]))
                self.assertEqual(0, main(["validate", "--trace", str(baseline)]))
                accepted = Path(directory) / "accepted/baseline.json"
                self.assertEqual(
                    0,
                    main(
                        [
                            "baseline",
                            "accept",
                            "--trace",
                            str(baseline),
                            "--out",
                            str(accepted),
                        ]
                    ),
                )
                self.assertEqual(
                    0,
                    main(["baseline", "show", "--baseline", str(accepted)]),
                )
                self.assertEqual(
                    0,
                    main(
                        [
                            "compare",
                            "--baseline",
                            str(baseline),
                            "--candidate",
                            str(candidate_ok),
                        ]
                    ),
                )
                self.assertEqual(
                    1,
                    main(
                        [
                            "compare",
                            "--baseline",
                            str(baseline),
                            "--candidate",
                            str(candidate_bad),
                        ]
                    ),
                )
                self.assertEqual(
                    0,
                    main(
                        [
                            "compare",
                            "--baseline",
                            str(baseline),
                            "--candidate",
                            str(candidate_bad),
                            "--allow-category",
                            "tool_name",
                            "--allow-category",
                            "tool_arguments",
                            "--allow-category",
                            "tool_result",
                            "--allow-category",
                            "tool_error_state",
                            "--allow-category",
                            "result_interpretation",
                            "--allow-category",
                            "final_answer",
                        ]
                    ),
                )
                junit = Path(directory) / "report.xml"
                self.assertEqual(
                    1,
                    main(
                        [
                            "compare",
                            "--baseline",
                            str(baseline),
                            "--candidate",
                            str(candidate_bad),
                            "--format",
                            "junit",
                            "--out",
                            str(junit),
                        ]
                    ),
                )
                self.assertIn("<failure", junit.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
