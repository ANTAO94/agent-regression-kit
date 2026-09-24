"""Evidence checks for the repository's own historical HelpPilot adapter defect."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/reproduce_helppilot_history.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("reproduce_helppilot_history", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load historical reproduction script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


class HistoricalAdapterEvidenceTests(unittest.TestCase):
    def test_exact_historical_sources_same_fixture_and_reviewed_case(self):
        reproduction = _load_script()
        missing = []
        for revision in (reproduction.FIX_COMMIT + "^", reproduction.FIX_COMMIT):
            try:
                result = subprocess.run(
                    ["git", "-C", str(REPO), "cat-file", "-e", f"{revision}^{{commit}}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
            except OSError:
                self.skipTest("Git unavailable; exact historical commits cannot be verified")
            if result.returncode != 0:
                missing.append(revision)
        if missing:
            self.skipTest(
                "exact historical Git commits unavailable: " + ", ".join(missing)
                + "; fetch full history to run this reproduction"
            )
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "evidence"
            manifest = reproduction.reproduce(out, repo=REPO)

            self.assertEqual(manifest, _read(out, "manifest.json"))
            self.assertIn("framework HelpPilot adapter", manifest["scope"])
            self.assertIn("not upstream or production", manifest["scope"])
            self.assertEqual("evidence_compare only; no fresh HelpPilot execution or ExecutionRecord",
                             manifest["execution_provenance"])
            for label, revision in (("before", reproduction.FIX_COMMIT + "^"),
                                    ("after", reproduction.FIX_COMMIT)):
                commit = subprocess.check_output(
                    ["git", "-C", str(REPO), "rev-parse", "--verify", f"{revision}^{{commit}}"]
                ).decode().strip()
                source = subprocess.check_output(
                    ["git", "-C", str(REPO), "show", f"{commit}:{reproduction.ADAPTER_PATH}"]
                )
                self.assertEqual(commit, manifest["versions"][label]["commit"])
                blob = subprocess.check_output(
                    ["git", "-C", str(REPO), "rev-parse", f"{commit}:{reproduction.ADAPTER_PATH}"]
                ).decode().strip()
                self.assertEqual(blob, manifest["versions"][label]["git_blob_sha"])
                self.assertEqual(hashlib.sha256(source).hexdigest(),
                                 manifest["versions"][label]["source_sha256"])

            scenario = _read(out, "input.json")
            self.assertEqual(reproduction.ACTUAL_REPLY, scenario["actual_reply"])
            self.assertEqual("none", scenario["mutation"])
            self.assertEqual(hashlib.sha256((out / "input.json").read_bytes()).hexdigest(),
                             manifest["same_input_sha256"])
            self.assertEqual(hashlib.sha256((out / "policy.json").read_bytes()).hexdigest(),
                             manifest["same_policy_sha256"])
            self.assertEqual(reproduction.CONTRACT, _read(out, "policy.json")["contract"])

            before = _read(out, "before.trace.json")
            after = _read(out, "after.trace.json")
            self.assertEqual(before["events"][-1]["text"], after["events"][-1]["text"])
            self.assertEqual("lost", before["events"][-1]["claims"]["order_status"])
            self.assertEqual("delivered", after["events"][-1]["claims"]["order_status"])
            self.assertEqual(before["run_id"], after["run_id"])
            self.assertEqual(before["metadata"]["mutation"], after["metadata"]["mutation"])
            self.assertEqual(
                [event for event in before["events"] if event["type"] != "final_answer"],
                [event for event in after["events"] if event["type"] != "final_answer"],
            )

            old_report = _read(out, "before.compare.json")
            fixed_report = _read(out, "after.compare.json")
            self.assertTrue(old_report["passed"])
            self.assertEqual(0, old_report["blocking_difference_count"])
            self.assertFalse(fixed_report["passed"])
            self.assertTrue(any(
                "order_status" in difference["path"] and not difference["allowed"]
                for difference in fixed_report["differences"]
            ))

            case = _read(out, "case.json")
            old_run = _read(out, "before.case-run.json")
            fixed_run = _read(out, "after.case-run.json")
            self.assertEqual("approved", case["status"])
            self.assertEqual({"pass", "fail"},
                             {run["outcome"] for run in case["review"]["validation_runs"]})
            self.assertEqual("pass", old_run["outcome"])
            self.assertEqual("fail", fixed_run["outcome"])
            self.assertEqual(old_run["definition_sha256"], fixed_run["definition_sha256"])
            self.assertEqual(case["review"]["definition_sha256"], old_run["definition_sha256"])
            self.assertNotIn("execution_ref", old_run)
            self.assertNotIn("execution_ref", fixed_run)

            with self.assertRaises(FileExistsError):
                reproduction.reproduce(out, repo=REPO)


if __name__ == "__main__":
    unittest.main()
