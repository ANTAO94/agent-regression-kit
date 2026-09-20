import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression.cli import main


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_init_scaffolds_a_project_without_overwriting_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["init", "--directory", directory]))
            root = Path(directory)
            expected = [
                "AGENT_REGRESSION.md",
                ".gitignore",
                ".agent-regression/config.json",
                "baselines/README.md",
                "baselines/my-agent.trace.json",
                "work/my-agent.trace.json",
                "scripts/record_agent.py",
                ".github/workflows/agent-regression.yml",
                ".github/workflows/agent-coverage.yml",
            ]
            for relative in expected:
                self.assertTrue((root / relative).exists(), relative)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(["check", "--config", str(root / ".agent-regression/config.json")]),
                )
                self.assertEqual(
                    0,
                    main(["compare", "--config", str(root / ".agent-regression/config.json")]),
                )
            workflow = (root / ".github/workflows/agent-regression.yml").read_text(encoding="utf-8")
            self.assertIn("@4.28.0", workflow)
            script = root / "scripts/record_agent.py"
            original = script.read_text(encoding="utf-8")
            script.write_text("custom\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["init", "--directory", directory]))
            self.assertEqual("custom\n", script.read_text(encoding="utf-8"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["init", "--directory", directory, "--force"]))
            self.assertEqual(original, script.read_text(encoding="utf-8"))

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

    def test_compare_can_load_project_config_and_claims_only_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
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
                            str(ROOT / "examples/order-123/candidate-ok.scenario.json"),
                            "--out",
                            str(candidate),
                        ]
                    ),
                )
            candidate_value = json.loads(candidate.read_text(encoding="utf-8"))
            candidate_value["events"][-1]["text"] = "Equivalent wording"
            candidate.write_text(json.dumps(candidate_value), encoding="utf-8")

            config = root / ".agent-regression/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "baseline": "baseline.json",
                        "candidate": "candidate.json",
                        "report": "outputs/compare.md",
                        "format": "markdown",
                        "final_answer_mode": "claims-only",
                        "contract": {
                            "assertions": [
                                {
                                    "path": "final_answer.claims.order_status",
                                    "equals": "not_shipped",
                                }
                            ],
                            "must_call": [{"tool": "get_order"}],
                            "must_not_call": ["delete_order"],
                            "max_steps": 1,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["compare", "--config", str(config)]))
            self.assertIn("`PASS`", (root / "outputs/compare.md").read_text(encoding="utf-8"))

    def test_batch_compare_can_load_project_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "source-baseline.json"
            candidate = root / "source-candidate.json"
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
                            str(ROOT / "examples/order-123/candidate-ok.scenario.json"),
                            "--out",
                            str(candidate),
                        ]
                    ),
                )
            baseline_dir = root / "baselines"
            candidate_dir = root / "candidate"
            baseline_dir.mkdir()
            candidate_dir.mkdir()
            (baseline_dir / "order.trace.json").write_text(
                baseline.read_text(encoding="utf-8"), encoding="utf-8"
            )
            (candidate_dir / "order.trace.json").write_text(
                candidate.read_text(encoding="utf-8"), encoding="utf-8"
            )
            config = root / ".agent-regression/batch.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "baseline_dir": "baselines",
                        "candidate_dir": "candidate",
                        "report": "outputs/batch.md",
                        "format": "markdown",
                    }
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["batch-compare", "--config", str(config)]))
            self.assertIn("`PASS`", (root / "outputs/batch.md").read_text(encoding="utf-8"))

    def test_config_validate_preflights_single_and_batch_shapes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            single = root / "single.json"
            single.write_text(
                json.dumps(
                    {
                        "baseline": "baselines/order.trace.json",
                        "candidate": "work/order.trace.json",
                        "report": "outputs/order.junit.xml",
                    }
                ),
                encoding="utf-8",
            )
            batch = root / "batch.json"
            batch.write_text(
                json.dumps(
                    {
                        "baseline_dir": "baselines",
                        "candidate_dir": "work",
                        "format": "markdown",
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["config", "validate", "--config", str(single)]))
                self.assertEqual(
                    0,
                    main(
                        [
                            "config",
                            "validate",
                            "--config",
                            str(batch),
                            "--kind",
                            "batch",
                        ]
                    ),
                )
            rendered = output.getvalue()
            self.assertIn('"kind": "single"', rendered)
            self.assertIn('"kind": "batch"', rendered)

    def test_config_rejects_unknown_result_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "baseline": "baseline.json",
                        "candidate": "candidate.json",
                        "result_alignment": "position",
                    }
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(2, main(["config", "validate", "--config", str(config)]))

    def test_config_rejects_unknown_fields_instead_of_ignoring_typos(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "baseline": "baseline.json",
                        "candidate": "candidate.json",
                        "must_not_cal": ["delete_order"],
                    }
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(2, main(["config", "validate", "--config", str(config)]))

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
