import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "agentdojo_matrix_validation.py"
SPEC = importlib.util.spec_from_file_location("agentdojo_matrix_validation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _run(tool_name="get_current_day"):
    return {
        "suite_name": "workspace",
        "pipeline_name": "gpt-4o-fixture",
        "user_task_id": "user_task_0",
        "injection_task_id": "injection_task_0",
        "attack_type": "direct",
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"function": {"name": tool_name, "args": {}}, "id": "call-1"}
                ],
            },
            {
                "role": "tool",
                "content": "ok",
                "tool_call_id": "call-1",
                "error": None,
            },
            {"role": "assistant", "content": "done", "tool_calls": None},
        ],
        "utility": True,
        "security": False,
    }


class AgentDojoMatrixValidationTests(unittest.TestCase):
    def _write_case(self, root, name="case.json", value=None):
        result = root / "results" / name
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(json.dumps(value or _run()), encoding="utf-8")
        return result

    def _manifest(self, root, result, case_id="workspace-direct"):
        return {
            "schema_version": "0.1",
            "repository": "https://example.invalid/agentdojo",
            "revision": "abc123",
            "cases": [
                {
                    "case_id": case_id,
                    "suite_name": "workspace",
                    "user_task_id": "user_task_0",
                    "injection_task_id": "injection_task_0",
                    "attack_type": "direct",
                    "dataset_path": "fixture.json",
                    "download_url": "https://example.invalid/abc123/fixture.json",
                    "result_file": result.name,
                    "sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
                    "expected_oracle": {"utility": True, "security": False},
                    "contract": {"must_call": [{"tool": "get_current_day"}], "max_steps": 1},
                }
            ],
        }

    def test_matrix_writes_case_reports_traces_and_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._write_case(root)
            manifest = root / "matrix.json"
            manifest.write_text(json.dumps(self._manifest(root, result)), encoding="utf-8")
            report = root / "report.json"
            args = MODULE.argparse.Namespace(
                manifest=manifest,
                results_dir=result.parent,
                out=report,
                trace_dir=root / "traces",
            )
            self.assertEqual(0, MODULE.run(args))
            value = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(value["gate"]["passed"])
            self.assertEqual(1, value["passed_case_count"])
            self.assertTrue((root / "cases" / "workspace-direct.report.json").exists())
            self.assertTrue((root / "traces" / "workspace-direct.trace.json").exists())

    def test_matrix_rejects_a_result_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._write_case(root)
            manifest_value = self._manifest(root, result)
            manifest_value["cases"][0]["sha256"] = "0" * 64
            manifest = root / "matrix.json"
            manifest.write_text(json.dumps(manifest_value), encoding="utf-8")
            args = MODULE.argparse.Namespace(
                manifest=manifest,
                results_dir=result.parent,
                out=root / "report.json",
                trace_dir=root / "traces",
            )
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                MODULE.run(args)

    def test_matrix_contract_failure_is_reported_without_using_oracle_as_a_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._write_case(root, value=_run(tool_name="other_tool"))
            manifest_value = self._manifest(root, result)
            manifest = root / "matrix.json"
            manifest.write_text(json.dumps(manifest_value), encoding="utf-8")
            args = MODULE.argparse.Namespace(
                manifest=manifest,
                results_dir=result.parent,
                out=root / "report.json",
                trace_dir=root / "traces",
            )
            self.assertEqual(1, MODULE.run(args))
            value = json.loads((root / "report.json").read_text(encoding="utf-8"))
            self.assertFalse(value["gate"]["passed"])
            self.assertFalse(value["cases"][0]["checks"]["contract_expectation"])
            self.assertEqual({"utility": True, "security": False}, value["cases"][0]["external_oracle"])

    def test_matrix_accepts_an_expected_contract_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._write_case(root, value=_run(tool_name="other_tool"))
            manifest_value = self._manifest(root, result)
            manifest_value["cases"][0]["expected_contract_passed"] = False
            manifest = root / "matrix.json"
            manifest.write_text(json.dumps(manifest_value), encoding="utf-8")
            args = MODULE.argparse.Namespace(
                manifest=manifest,
                results_dir=result.parent,
                out=root / "report.json",
                trace_dir=root / "traces",
            )
            self.assertEqual(0, MODULE.run(args))
            value = json.loads((root / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(value["gate"]["passed"])
            self.assertFalse(value["cases"][0]["contract_passed"])
            self.assertTrue(value["cases"][0]["contract_outcome_match"])


if __name__ == "__main__":
    unittest.main()
