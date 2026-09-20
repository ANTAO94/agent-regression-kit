import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from pathlib import Path

from agent_regression import decide_benchmark, prepare_benchmark, score_benchmark
from agent_regression.cli import main


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BenchmarkTests(unittest.TestCase):
    def _write_fixture(self, root: Path) -> Path:
        baseline = root / "baseline.trace.json"
        candidate_ok = root / "candidate-ok.trace.json"
        candidate_bad = root / "candidate-bad.trace.json"
        source = ROOT / "baselines/order-123.trace.json"
        baseline.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        candidate_ok.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        bad = json.loads(source.read_text(encoding="utf-8"))
        bad["events"][-1]["text"] = "the order has shipped"
        candidate_bad.write_text(json.dumps(bad), encoding="utf-8")

        evidence = root / "evidence.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "samples": [
                        {"id": "pass-case", "baseline": baseline.name, "candidate": candidate_ok.name},
                        {"id": "block-case", "baseline": baseline.name, "candidate": candidate_bad.name},
                    ],
                }
            ),
            encoding="utf-8",
        )
        contracts = root / "contracts.json"
        contracts.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "cases": [
                        {"id": "pass-case", "contract": {}},
                        {"id": "block-case", "contract": {}},
                    ],
                }
            ),
            encoding="utf-8",
        )
        split = root / "split.json"
        split.write_text(json.dumps({"name": "evaluation", "ids": ["pass-case", "block-case"]}), encoding="utf-8")
        labels = root / "labels.json"
        labels.write_text(
            json.dumps(
                {
                    "labels": [
                        {"sample_id": "pass-case", "passed": True},
                        {"sample_id": "block-case", "passed": False},
                    ]
                }
            ),
            encoding="utf-8",
        )
        manifest = root / "benchmark.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "benchmark_id": "fixture-evaluation-v1",
                    "source": {
                        "repository": "https://example.invalid/fixture",
                        "revision": "v1.0.0",
                        "data_path": evidence.name,
                        "data_sha256": digest(evidence),
                    },
                    "split": {
                        "name": "evaluation",
                        "path": split.name,
                        "sha256": digest(split),
                    },
                    "contract_bundle": {"path": contracts.name, "sha256": digest(contracts)},
                    "evidence": {"path": evidence.name, "sha256": digest(evidence)},
                    "labels": {"path": labels.name, "sha256": digest(labels)},
                    "agent_regression": {"version": "4.14.0", "commit": "fixture-commit"},
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_prepare_decide_score_separate_labels_and_emit_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._write_fixture(Path(directory))
            prepared = prepare_benchmark(manifest)
            self.assertTrue(prepared["ok"])
            self.assertEqual(2, prepared["scope"]["sample_count"])
            decisions = decide_benchmark(manifest)
            self.assertEqual(
                ["pass", "block"],
                [item["status"] for item in decisions["decisions"]],
            )
            self.assertIn("decision_digest", decisions)
            decision_path = manifest.parent / "decisions.json"
            decision_path.write_text(json.dumps(decisions), encoding="utf-8")
            score = score_benchmark(manifest, decision_path)
            self.assertEqual(
                {"true_pass": 1, "true_block": 1, "false_alarm": 0, "missed_failure": 0},
                score["confusion_matrix"],
            )
            self.assertEqual(1.0, score["metrics"]["accuracy"])
            self.assertEqual(2, score["scope"]["evaluated_samples"])
            self.assertEqual(64, len(score["provenance"]["decisions_sha256"]))
            self.assertIsNotNone(score["wilson_95"]["accuracy"])

    def test_score_rejects_modified_decision_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._write_fixture(Path(directory))
            decisions = decide_benchmark(manifest)
            decisions["decisions"][0]["status"] = "block"
            path = manifest.parent / "decisions.json"
            path.write_text(json.dumps(decisions), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "decision file was modified"):
                score_benchmark(manifest, path)

    def test_prepare_rejects_moving_source_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._write_fixture(Path(directory))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["source"]["revision"] = "main"
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "immutable tag or commit"):
                prepare_benchmark(manifest)

    def test_cli_runs_the_three_benchmark_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._write_fixture(root)
            prepared = io.StringIO()
            with redirect_stdout(prepared):
                self.assertEqual(
                    0,
                    main(["benchmark", "prepare", "--manifest", str(manifest)]),
                )
            decisions = root / "cli-decisions.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(
                        [
                            "benchmark",
                            "decide",
                            "--manifest",
                            str(manifest),
                            "--out",
                            str(decisions),
                        ]
                    ),
                )
            score = root / "cli-score.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(
                        [
                            "benchmark",
                            "score",
                            "--manifest",
                            str(manifest),
                            "--decisions",
                            str(decisions),
                            "--out",
                            str(score),
                        ]
                    ),
                )
            self.assertTrue(json.loads(score.read_text(encoding="utf-8"))["ok"])


if __name__ == "__main__":
    unittest.main()
