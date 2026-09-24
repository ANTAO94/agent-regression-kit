"""Lifecycle acceptance checks. Kept separate from legacy compare CLI tests."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path

from agent_regression import (
    AgentTrace, CaseValidationError, approve_case, compare_case,
    compare_case_suite, create_case_draft, revise_case, validate_case,
)
from agent_regression.cli import main
from agent_regression.cases import save_case
from agent_regression.compare import compare_traces
from agent_regression.incidents import IncidentValidationError, safe_input_path, safe_output_path


SOURCE = Path(__file__).resolve().parents[1] / "examples/external-pilot/helppilot/baseline.trace.json"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class CaseLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        original = json.loads(SOURCE.read_text(encoding="utf-8"))
        original["metadata"]["fixture_version"] = "v1"
        negative = deepcopy(original)
        negative["run_id"] = "known-bad"
        negative["events"][-1]["claims"]["reply_refund_issued"] = False
        missing = deepcopy(original)
        missing["run_id"] = "missing-evidence"
        del missing["metadata"]["fixture_version"]
        for name, content in (("baseline.json", original), ("positive.json", original),
                              ("negative.json", negative), ("missing.json", missing)):
            write_json(self.root / name, content)
        write_json(self.root / "policy.json", {
            "final_answer_mode": "claims-only",
            "evidence_requirements": [{"path": "metadata.fixture_version", "exists": True}],
        })

    def draft(self):
        case = create_case_draft(
            root=self.root, baseline_path="baseline.json", policy_path="policy.json",
            title="Refund answer", expected_behavior="Reply follows the observed result",
        )
        save_case(case, root=self.root, out_path="cases/refund.json")
        return case

    def test_review_requires_discriminating_samples_and_draft_cannot_gate(self):
        case = self.draft()
        with self.assertRaisesRegex(CaseValidationError, "draft"):
            compare_case(root=self.root, case_path="cases/refund.json",
                         candidate_path="positive.json", out_path="draft.run.json")
        with self.assertRaisesRegex(CaseValidationError, "negative sample"):
            approve_case(root=self.root, case_path="cases/refund.json", positive_path="positive.json",
                         negative_path="positive.json", reviewer="antao", reason="checked")
        with self.assertRaisesRegex(CaseValidationError, "positive sample"):
            approve_case(root=self.root, case_path="cases/refund.json", positive_path="missing.json",
                         negative_path="negative.json", reviewer="antao", reason="checked")

    def test_approved_case_pass_fail_inconclusive_and_fingerprint(self):
        self.draft()
        case = approve_case(root=self.root, case_path="cases/refund.json", positive_path="positive.json",
                            negative_path="negative.json", reviewer="antao", reason="checked")
        passed, pass_code = compare_case(root=self.root, case_path="cases/refund.json",
                                         candidate_path="positive.json", out_path="pass.run.json")
        self.assertEqual(("pass", 0), (passed["outcome"], pass_code))
        failed, fail_code = compare_case(root=self.root, case_path="cases/refund.json",
                                         candidate_path="negative.json", out_path="fail.run.json")
        self.assertEqual(("fail", 1), (failed["outcome"], fail_code))
        self.assertFalse(json.loads((self.root / failed["report_ref"]["path"]).read_text())["passed"])
        uncertain, uncertain_code = compare_case(root=self.root, case_path="cases/refund.json",
                                                  candidate_path="missing.json", out_path="uncertain.run.json")
        self.assertEqual(("inconclusive", 2), (uncertain["outcome"], uncertain_code))
        write_json(self.root / "policy.json", {"final_answer_mode": "exact"})
        with self.assertRaisesRegex(CaseValidationError, "SHA-256"):
            validate_case(case, self.root, require_approved=True)

    def test_suite_maps_explicit_candidates_and_keeps_failures(self):
        self.draft()
        approve_case(root=self.root, case_path="cases/refund.json", positive_path="positive.json",
                     negative_path="negative.json", reviewer="antao", reason="checked")
        write_json(self.root / "suite.json", {"schema_version": "0.1", "cases": [
            {"case": "cases/refund.json", "candidate": "negative.json"},
            {"case": "cases/refund.json", "candidate": "missing.json"},
        ]})
        suite, code = compare_case_suite(root=self.root, manifest_path="suite.json", out_path="suite.report.json")
        self.assertEqual(2, code)
        self.assertEqual(1, suite["failed_count"])
        self.assertEqual(1, suite["error_count"])
        self.assertIsNotNone(suite["case_runs"][0]["report"])

    def test_revise_keeps_the_old_approval_and_requires_a_new_review(self):
        self.draft()
        old = approve_case(root=self.root, case_path="cases/refund.json",
                           positive_path="positive.json", negative_path="negative.json",
                           reviewer="antao", reason="initial review")
        write_json(self.root / "policy-v2.json", {
            "final_answer_mode": "claims-only",
            "evidence_requirements": [{"path": "metadata.fixture_version", "exists": True}],
            "allow_paths": [],
        })
        revised = revise_case(root=self.root, case_path="cases/refund.json",
                              policy_path="policy-v2.json")
        save_case(revised, root=self.root, out_path="cases/refund-r2.json")
        self.assertEqual(old.case_id, revised.case_id)
        self.assertEqual((1, "approved"), (old.revision, old.status))
        self.assertEqual((2, "draft"), (revised.revision, revised.status))
        self.assertEqual("approved", json.loads((self.root / "cases/refund.json").read_text())["status"])
        with self.assertRaisesRegex(CaseValidationError, "not approved"):
            compare_case(root=self.root, case_path="cases/refund-r2.json",
                         candidate_path="positive.json", out_path="draft-r2.run.json")

    def test_cli_review_validation_and_explicit_upgrade(self):
        self.draft()
        approve_case(root=self.root, case_path="cases/refund.json",
                     positive_path="positive.json", negative_path="negative.json",
                     reviewer="reviewer", reason="known samples discriminate")
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["case", "validate", "--root", str(self.root),
                         "--case", "cases/refund.json", "--review-evidence"])
        self.assertEqual(code, 0, output.getvalue())
        with redirect_stdout(io.StringIO()):
            code = main(["case", "upgrade", "--root", str(self.root),
                         "--case", "cases/refund.json", "--out", "cases/upgraded.json"])
        self.assertEqual(code, 0)
        upgraded = json.loads((self.root / "cases/upgraded.json").read_text())
        self.assertEqual((upgraded["revision"], upgraded["status"]), (2, "draft"))
        self.assertIsNone(upgraded["review"])
        self.assertEqual(json.loads((self.root / "cases/refund.json").read_text())["status"], "approved")

    def test_business_assertion_cannot_be_downgraded_to_missing_evidence(self):
        write_json(self.root / "conflicting-policy.json", {
            "contract": {"assertions": [{"path": "metadata.fixture_version", "exists": True}]},
            "evidence_requirements": [{"path": "metadata.fixture_version", "exists": True}],
        })
        with self.assertRaisesRegex(CaseValidationError, "conflicts with a Contract"):
            create_case_draft(
                root=self.root, baseline_path="baseline.json", policy_path="conflicting-policy.json",
                title="Conflicting rule", expected_behavior="Missing fixture version is a violation",
            )

    def test_import_redacts_and_rejects_symlink_escape(self):
        trace = json.loads((self.root / "negative.json").read_text())
        trace["metadata"]["api_key"] = "secret-value"
        write_json(self.root / "negative.json", trace)
        report = compare_traces(
            AgentTrace.from_dict(json.loads((self.root / "baseline.json").read_text())),
            AgentTrace.from_dict(trace),
        )
        write_json(self.root / "report.json", report)
        with redirect_stdout(io.StringIO()):
            code = main(["incident", "import", "--root", str(self.root),
                         "--trace", "negative.json", "--report", "report.json",
                         "--out", "incident.json"])
        self.assertEqual(0, code)
        incident = json.loads((self.root / "incident.json").read_text())
        imported = self.root / incident["evidence_refs"][0]["path"]
        self.assertNotIn("secret-value", imported.read_text())
        commands = [
            (["case", "draft", "--root", str(self.root), "--incident", "incident.json",
              "--baseline", "baseline.json", "--policy", "policy.json",
              "--expected-behavior", "Refund reply reflects observed result",
              "--out", "cases/cli.json"], 0),
            (["case", "validate", "--root", str(self.root), "--case", "cases/cli.json"], 0),
            (["case", "approve", "--root", str(self.root), "--case", "cases/cli.json",
              "--positive", "positive.json", "--negative", "negative.json",
              "--reviewer", "antao", "--reason", "known defect must fail"], 0),
            (["case", "compare", "--root", str(self.root), "--case", "cases/cli.json",
              "--candidate", "positive.json", "--out", "cli.run.json"], 0),
        ]
        for arguments, expected in commands:
            with self.subTest(arguments=arguments[:2]), redirect_stdout(io.StringIO()):
                self.assertEqual(expected, main(arguments))
        self.assertEqual("pass", json.loads((self.root / "cli.run.json").read_text())["outcome"])
        outside = self.root.parent / (self.root.name + "-outside")
        (self.root / "escape").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(IncidentValidationError):
            safe_output_path(self.root, "escape/file.json")
        with self.assertRaises(IncidentValidationError):
            safe_input_path(self.root, "../outside.json")


if __name__ == "__main__":
    unittest.main()
