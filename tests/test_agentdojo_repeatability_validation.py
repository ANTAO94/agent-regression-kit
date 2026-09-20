import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "agentdojo_repeatability_validation.py"
SPEC = importlib.util.spec_from_file_location("agentdojo_repeatability_validation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _run():
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
                    {"function": {"name": "get_current_day", "args": {}}, "id": "call-1"}
                ],
            },
            {"role": "tool", "content": "ok", "tool_call_id": "call-1", "error": None},
            {"role": "assistant", "content": "done", "tool_calls": None},
        ],
        "utility": True,
        "security": False,
    }


class AgentDojoRepeatabilityValidationTests(unittest.TestCase):
    def test_repeated_pinned_decisions_have_stable_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            results.mkdir()
            result = results / "case.json"
            result.write_text(json.dumps(_run()), encoding="utf-8")
            contract = {"must_call": [{"tool": "get_current_day"}], "max_steps": 1}
            manifest = root / "matrix.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "repository": "https://example.invalid/agentdojo",
                        "revision": "abc123",
                        "contract_provenance": {
                            "scheme": "sha256-canonical-json",
                            "frozen_before_oracle": True,
                        },
                        "cases": [
                            {
                                "case_id": "workspace-direct",
                                "suite_name": "workspace",
                                "user_task_id": "user_task_0",
                                "injection_task_id": "injection_task_0",
                                "attack_type": "direct",
                                "dataset_path": "fixture.json",
                                "download_url": "https://example.invalid/abc123/fixture.json",
                                "result_file": "case.json",
                                "sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
                                "expected_oracle": {"utility": True, "security": False},
                                "contract": contract,
                                "contract_sha256": hashlib.sha256(
                                    json.dumps(
                                        contract, sort_keys=True, separators=(",", ":")
                                    ).encode("utf-8")
                                ).hexdigest(),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = root / "repeatability.json"
            args = MODULE.argparse.Namespace(
                manifest=manifest,
                results_dir=results,
                out=report,
                repeats=3,
            )
            self.assertEqual(0, MODULE.run(args))
            value = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(value["stable"])
            self.assertTrue(value["gate"]["passed"])
            self.assertEqual(3, value["run_count"])
            self.assertTrue(value["gate"]["checks"]["traces_stable"])

    def test_repeatability_requires_two_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            args = MODULE.argparse.Namespace(
                manifest=Path(directory) / "matrix.json",
                results_dir=Path(directory) / "results",
                out=Path(directory) / "report.json",
                repeats=1,
            )
            with self.assertRaisesRegex(ValueError, "at least 2"):
                MODULE.run(args)


if __name__ == "__main__":
    unittest.main()
