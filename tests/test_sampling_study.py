import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import (
    ComparisonPolicy,
    SamplingProvenance,
    canonical_sha256,
    evaluate_sampling_study,
    sha256_file,
)
from agent_regression.cli import main


ROOT = Path(__file__).resolve().parents[1]


def write_trace(path: Path, run_id: str) -> None:
    value = json.loads(
        (ROOT / "baselines/order-123.trace.json").read_text(encoding="utf-8")
    )
    value["run_id"] = run_id
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SamplingStudyTests(unittest.TestCase):
    def make_manifest(self, root: Path) -> Path:
        baseline = root / "baseline.trace.json"
        run_one = root / "runs/run-1.trace.json"
        run_two = root / "runs/run-2.trace.json"
        baseline.write_text(
            (ROOT / "baselines/order-123.trace.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        run_one.parent.mkdir(parents=True, exist_ok=True)
        write_trace(run_one, "study-run-1")
        write_trace(run_two, "study-run-2")
        manifest = root / "study.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "study_id": "order-provider-sampling",
                    "baseline": "baseline.trace.json",
                    "runs": [
                        {"id": "study-run-1", "trace": "runs/run-1.trace.json"},
                        {"id": "study-run-2", "trace": "runs/run-2.trace.json"},
                    ],
                    "provenance": {
                        "provider": "fixture-provider",
                        "model": "fixture-model-v1",
                        "adapter": "callable-agent",
                        "study_id": "order-provider-sampling",
                        "input_sha256": canonical_sha256({"request": "lookup order 123"}),
                        "tool_schema_sha256": canonical_sha256(
                            {"tools": ["get_order", "get_balance"]}
                        ),
                        "dataset_revision": "fixture-2026-09-21",
                        "parameters": {"temperature": 0.2, "seed": 7},
                    },
                    "policy": {"min_runs": 2},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return manifest

    def test_evaluates_recorded_runs_and_keeps_provenance_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.make_manifest(Path(directory))
            report = evaluate_sampling_study(manifest)
            value = report.to_dict()

            self.assertTrue(report.passed)
            self.assertEqual("agent_sampling_study", value["report_type"])
            self.assertEqual(2, value["run_count"])
            self.assertEqual("fixture-provider", value["provenance"]["provider"])
            self.assertEqual("fixture-model-v1", value["provenance"]["model"])
            self.assertEqual(64, len(value["manifest_sha256"]))
            self.assertEqual(2, len(value["runs"]))
            self.assertNotIn("request", value["provenance"])

    def test_study_cli_renders_auditable_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.make_manifest(Path(directory))
            output = Path(directory) / "study.md"
            with redirect_stdout(io.StringIO()):
                status = main(
                    [
                        "study",
                        "--manifest",
                        str(manifest),
                        "--format",
                        "markdown",
                        "--out",
                        str(output),
                    ]
                )
            self.assertEqual(0, status)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("Agent Sampling Study", rendered)
            self.assertIn("fixture-provider", rendered)
            self.assertIn("fixture-model-v1", rendered)
            self.assertIn("Input SHA-256", rendered)
            self.assertIn("Pass rate 95% interval", rendered)

    def test_integrity_policy_binds_baseline_runs_and_normalized_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.make_manifest(Path(directory))
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            root = manifest.parent
            raw["runs"] = [
                {
                    **item,
                    "sha256": sha256_file(root / item["trace"]),
                }
                for item in raw["runs"]
            ]
            raw["integrity"] = {
                "require_trace_hashes": True,
                "baseline_sha256": sha256_file(root / raw["baseline"]),
                "comparison_policy_sha256": canonical_sha256(
                    ComparisonPolicy().to_dict()
                ),
            }
            manifest.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            report = evaluate_sampling_study(manifest).to_dict()

            self.assertTrue(report["evidence_integrity"]["trace_hashes_required"])
            self.assertTrue(report["evidence_integrity"]["trace_hashes_verified"])
            self.assertEqual(2, len(report["evidence_integrity"]["runs"]))
            self.assertEqual(
                raw["integrity"]["baseline_sha256"],
                report["evidence_integrity"]["baseline_sha256"],
            )

    def test_integrity_policy_rejects_tampered_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.make_manifest(Path(directory))
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            root = manifest.parent
            raw["runs"] = [
                {
                    **item,
                    "sha256": sha256_file(root / item["trace"]),
                }
                for item in raw["runs"]
            ]
            raw["integrity"] = {
                "require_trace_hashes": True,
                "baseline_sha256": sha256_file(root / raw["baseline"]),
            }
            manifest.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tampered = root / raw["runs"][0]["trace"]
            tampered.write_text(tampered.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                evaluate_sampling_study(manifest)

    def test_integrity_policy_requires_hash_for_every_run(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.make_manifest(Path(directory))
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            root = manifest.parent
            raw["integrity"] = {
                "require_trace_hashes": True,
                "baseline_sha256": sha256_file(root / raw["baseline"]),
            }
            manifest.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "sha256 is required"):
                evaluate_sampling_study(manifest)

    def test_provenance_rejects_secret_like_parameters(self):
        with self.assertRaisesRegex(ValueError, "must not contain credentials"):
            SamplingProvenance(
                provider="provider",
                model="model",
                input_sha256="0" * 64,
                parameters={"api_key": "never-store-this"},
            )

    def test_manifest_rejects_paths_outside_study_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "baseline.trace.json"
            outside.write_text(
                (ROOT / "baselines/order-123.trace.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            study_dir = root / "study"
            study_dir.mkdir()
            manifest = study_dir / "study.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "study_id": "escape",
                        "baseline": "../baseline.trace.json",
                        "runs": [],
                        "provenance": {
                            "provider": "provider",
                            "model": "model",
                            "input_sha256": "0" * 64,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "must stay inside"):
                evaluate_sampling_study(manifest)


if __name__ == "__main__":
    unittest.main()
