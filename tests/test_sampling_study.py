import hashlib
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

    def add_evidence_index(self, manifest: Path, roles: tuple[str, ...]) -> Path:
        root = manifest.parent
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        entries = []
        for role in roles:
            path = root / "evidence" / f"{role}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"role": role}) + "\n", encoding="utf-8")
            entries.append(
                {
                    "id": f"{role}-evidence",
                    "role": role,
                    "path": str(path.relative_to(root)),
                    "sha256": sha256_file(path),
                }
            )
        raw["evidence"] = entries
        raw["integrity"] = {
            "require_evidence_index": True,
            "required_evidence_roles": list(roles),
        }
        manifest.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
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

    def test_evidence_index_binds_roles_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.add_evidence_index(
                self.make_manifest(Path(directory)),
                ("input", "tool_schema", "adapter"),
            )

            report = evaluate_sampling_study(manifest).to_dict()

            index = report["evidence_index"]
            self.assertTrue(index["required"])
            self.assertTrue(index["verified"])
            self.assertEqual(3, index["entry_count"])
            self.assertEqual(["adapter", "input", "tool_schema"], index["roles"])
            self.assertTrue(report["evidence_integrity"]["evidence_index_verified"])

    def test_evidence_index_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.add_evidence_index(
                self.make_manifest(Path(directory)),
                ("adapter",),
            )
            evidence_path = manifest.parent / "evidence/adapter.json"
            evidence_path.write_text(
                evidence_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                evaluate_sampling_study(manifest)

    def test_evidence_index_requires_declared_roles(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.make_manifest(Path(directory))
            root = manifest.parent
            evidence = root / "evidence/input.json"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text('{"role": "input"}\n', encoding="utf-8")
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            raw["evidence"] = [
                {
                    "id": "input-evidence",
                    "role": "input",
                    "path": "evidence/input.json",
                    "sha256": sha256_file(evidence),
                }
            ]
            raw["integrity"] = {
                "require_evidence_index": True,
                "required_evidence_roles": ["input", "adapter"],
            }
            manifest.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "missing required evidence roles"):
                evaluate_sampling_study(manifest)

    def add_evidence_bindings(self, manifest: Path) -> Path:
        root = manifest.parent
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        descriptors = {
            "input": {"input_sha256": raw["provenance"]["input_sha256"]},
            "tool_schema": {
                "tool_schema_sha256": raw["provenance"]["tool_schema_sha256"]
            },
            "adapter": {"adapter": raw["provenance"]["adapter"]},
        }
        entries = []
        for role, descriptor in descriptors.items():
            path = root / "evidence" / f"{role}-descriptor.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(descriptor) + "\n", encoding="utf-8")
            entries.append(
                {
                    "id": f"{role}-descriptor",
                    "role": role,
                    "path": str(path.relative_to(root)),
                    "sha256": sha256_file(path),
                }
            )
        raw["evidence"] = entries
        raw["evidence_bindings"] = [
            {
                "evidence_id": "input-descriptor",
                "target": "provenance.input_sha256",
                "field": "input_sha256",
            },
            {
                "evidence_id": "tool_schema-descriptor",
                "target": "provenance.tool_schema_sha256",
                "field": "tool_schema_sha256",
            },
            {
                "evidence_id": "adapter-descriptor",
                "target": "provenance.adapter",
                "field": "adapter",
            },
        ]
        raw["integrity"] = {
            "require_evidence_index": True,
            "required_evidence_roles": ["adapter", "input", "tool_schema"],
            "require_evidence_bindings": True,
            "required_evidence_bindings": [
                "provenance.adapter",
                "provenance.input_sha256",
                "provenance.tool_schema_sha256",
            ],
        }
        manifest.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest

    def test_evidence_bindings_match_provenance_without_exposing_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.add_evidence_bindings(self.make_manifest(Path(directory)))

            report = evaluate_sampling_study(manifest).to_dict()

            bindings = report["evidence_bindings"]
            self.assertTrue(bindings["required"])
            self.assertTrue(bindings["verified"])
            self.assertEqual(3, bindings["binding_count"])
            self.assertEqual(
                [
                    "provenance.adapter",
                    "provenance.input_sha256",
                    "provenance.tool_schema_sha256",
                ],
                bindings["targets"],
            )
            self.assertTrue(report["evidence_integrity"]["evidence_bindings_verified"])
            self.assertNotIn("fixture-provider", json.dumps(bindings))

    def test_evidence_bindings_reject_semantic_mismatch_even_when_file_hash_is_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.add_evidence_bindings(self.make_manifest(Path(directory)))
            root = manifest.parent
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            descriptor = root / "evidence/input-descriptor.json"
            descriptor.write_text(json.dumps({"input_sha256": "0" * 64}) + "\n", encoding="utf-8")
            for entry in raw["evidence"]:
                if entry["id"] == "input-descriptor":
                    entry["sha256"] = sha256_file(descriptor)
            manifest.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "does not match provenance.input_sha256"):
                evaluate_sampling_study(manifest)

    def test_evidence_bindings_require_indexed_roles_and_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.add_evidence_bindings(self.make_manifest(Path(directory)))
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            raw["evidence_bindings"] = raw["evidence_bindings"][:1]
            manifest.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "missing required evidence bindings"):
                evaluate_sampling_study(manifest)

    def test_evidence_bindings_cover_provider_model_and_dataset_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.add_evidence_bindings(self.make_manifest(Path(directory)))
            root = manifest.parent
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            extended = {
                "provider": (
                    "provider-output-descriptor",
                    {"provider": raw["provenance"]["provider"]},
                ),
                "model": (
                    "model-output-descriptor",
                    {"model": raw["provenance"]["model"]},
                ),
                "dataset_revision": (
                    "dataset-descriptor",
                    {"dataset_revision": raw["provenance"]["dataset_revision"]},
                ),
            }
            for field, (evidence_id, descriptor) in extended.items():
                role = "dataset" if field == "dataset_revision" else "provider_output"
                path = root / "evidence" / f"{evidence_id}.json"
                path.write_text(json.dumps(descriptor) + "\n", encoding="utf-8")
                raw["evidence"].append(
                    {
                        "id": evidence_id,
                        "role": role,
                        "path": str(path.relative_to(root)),
                        "sha256": sha256_file(path),
                    }
                )
                raw["evidence_bindings"].append(
                    {
                        "evidence_id": evidence_id,
                        "target": f"provenance.{field}",
                        "field": field,
                    }
                )
            raw["integrity"]["required_evidence_roles"].extend(
                ["provider_output", "dataset"]
            )
            raw["integrity"]["required_evidence_bindings"].extend(
                [
                    "provenance.provider",
                    "provenance.model",
                    "provenance.dataset_revision",
                ]
            )
            manifest.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            report = evaluate_sampling_study(manifest).to_dict()

            self.assertEqual(6, report["evidence_bindings"]["binding_count"])
            self.assertIn("provenance.provider", report["evidence_bindings"]["targets"])
            self.assertIn("provenance.model", report["evidence_bindings"]["targets"])
            self.assertIn(
                "provenance.dataset_revision",
                report["evidence_bindings"]["targets"],
            )

    def test_study_writes_a_sha256_sidecar_for_the_rendered_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.make_manifest(root)
            for format_name, suffix in (("json", ".json"), ("markdown", ".md"), ("junit", ".xml")):
                report_path = root / "reports" / f"study-{format_name}{suffix}"
                checksum_path = root / "reports" / f"study-{format_name}{suffix}.sha256"
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        0,
                        main(
                            [
                                "study",
                                "--manifest",
                                str(manifest),
                                "--format",
                                format_name,
                                "--out",
                                str(report_path),
                                "--checksum-out",
                                str(checksum_path),
                            ]
                        ),
                    )
                digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
                self.assertEqual(f"{digest}  {report_path.name}\n", checksum_path.read_text())

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
