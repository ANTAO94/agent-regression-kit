import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import evaluate_readiness
from agent_regression.cli import main


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReadinessTests(unittest.TestCase):
    def _write_common_reports(self, root: Path) -> dict[str, dict[str, str]]:
        benchmark = root / "heldout-score.json"
        benchmark.write_text(
            json.dumps(
                {
                    "report_type": "benchmark_score",
                    "scope": {
                        "evaluated_samples": 300,
                        "unsupported": 0,
                    },
                    "confusion_matrix": {
                        "true_pass": 250,
                        "true_block": 50,
                        "false_alarm": 0,
                        "missed_failure": 0,
                    },
                    "metrics": {
                        "failure_recall": 1.0,
                        "false_alarm_rate": 0.0,
                    },
                }
            ),
            encoding="utf-8",
        )
        performance = root / "performance.json"
        performance.write_text(
            json.dumps(
                {
                    "report_type": "agent_performance",
                    "workloads": [
                        {"name": "small", "trace_count": 10_000, "elapsed_seconds": 2.0}
                    ],
                    "environment": {"peak_rss_bytes": 1024},
                }
            ),
            encoding="utf-8",
        )
        evidence = root / "consumer-ci.txt"
        evidence.write_text("consumer CI run: success\n", encoding="utf-8")
        return {
            "benchmark": {"path": benchmark.name, "sha256": _sha256(benchmark)},
            "performance": {"path": performance.name, "sha256": _sha256(performance)},
            "evidence": {"path": evidence.name, "sha256": _sha256(evidence)},
        }

    def _manifest(self, root: Path, *, external_status: str = "pending") -> Path:
        reports = self._write_common_reports(root)
        human = root / "human-study.json"
        human.write_text(
            json.dumps({"participant": "external", "completed": True}),
            encoding="utf-8",
        )
        checks = [
            {"id": "heldout-quality", "kind": "benchmark", "report": reports["benchmark"]},
            {"id": "performance", "kind": "performance", "report": reports["performance"]},
            {"id": "consumer-ci", "kind": "evidence", "files": [reports["evidence"]]},
            {
                "id": "human-usability",
                "kind": "external",
                "status": external_status,
                "reason": "requires a participant who did not implement the core framework",
                "evidence": (
                    [{"path": human.name, "sha256": _sha256(human)}]
                    if external_status == "passed"
                    else []
                ),
            },
        ]
        manifest = root / "readiness.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "profile": "final-v4",
                    "target_version": "4.35.0",
                    "checks": checks,
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_quantitative_gates_and_pending_external_evidence_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._manifest(Path(directory))
            report = evaluate_readiness(manifest)
            self.assertTrue(report["ok"])
            self.assertFalse(report["ready"])
            self.assertEqual(3, report["summary"]["passed"])
            self.assertEqual(1, report["summary"]["pending"])
            self.assertEqual("pending", report["checks"][-1]["status"])
            self.assertEqual(300, report["checks"][0]["observed"]["evaluated_samples"])

    def test_all_required_evidence_can_make_a_ready_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = evaluate_readiness(self._manifest(Path(directory), external_status="passed"))
            self.assertTrue(report["ready"])
            self.assertEqual(4, report["summary"]["passed"])

    def test_cli_returns_one_and_renders_markdown_when_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest(root)
            output = root / "readiness.md"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    1,
                    main(
                        [
                            "readiness",
                            "--manifest",
                            str(manifest),
                            "--format",
                            "markdown",
                            "--out",
                            str(output),
                        ]
                    ),
                )
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("NOT READY", rendered)
            self.assertIn("human-usability", rendered)

    def test_hash_mismatch_and_weaker_threshold_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest(root)
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["checks"][0]["report"]["sha256"] = "0" * 64
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                evaluate_readiness(manifest)

            value = json.loads(self._manifest(root).read_text(encoding="utf-8"))
            value["thresholds"] = {"min_evaluated_samples": 1}
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot be weaker"):
                evaluate_readiness(manifest)


if __name__ == "__main__":
    unittest.main()
