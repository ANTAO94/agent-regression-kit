"""Focused regression checks for reviewed evidence and CaseRun provenance."""

import json
import os
import tempfile
import types
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent_regression import (
    CaseValidationError, approve_case, compare_case, create_case_draft,
    load_case, revise_case, validate_case,
)
from agent_regression.cases import case_definition_sha256, save_case
from agent_regression.case_runner import _compare, _independent_of_gaps
from agent_regression.incidents import sha256_file


SOURCE = Path(__file__).resolve().parents[1] / "examples/external-pilot/helppilot/baseline.trace.json"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class CaseHardeningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        baseline = json.loads(SOURCE.read_text(encoding="utf-8"))
        negative = deepcopy(baseline)
        negative["run_id"] = "known-bad"
        negative["events"][-1]["claims"]["reply_refund_issued"] = False
        missing = deepcopy(negative)
        missing["run_id"] = "missing-and-bad"
        missing["metadata"].pop("fixture_version", None)
        for name, value in (("baseline.json", baseline), ("positive.json", baseline),
                            ("negative.json", negative), ("missing.json", missing)):
            write_json(self.root / name, value)
        write_json(self.root / "policy.json", {
            "final_answer_mode": "claims-only",
            "evidence_requirements": [{"path": "metadata.fixture_version", "exists": True}],
        })
        # The source fixture may omit fixture_version; positive and negative need it.
        for name in ("baseline.json", "positive.json", "negative.json"):
            value = json.loads((self.root / name).read_text())
            value["metadata"]["fixture_version"] = "v1"
            write_json(self.root / name, value)
        draft = create_case_draft(root=self.root, baseline_path="baseline.json",
                                  policy_path="policy.json", title="Refund",
                                  expected_behavior="Refund claim follows tool result")
        save_case(draft, root=self.root, out_path="cases/refund.json")

    def approve(self):
        return approve_case(root=self.root, case_path="cases/refund.json",
                            positive_path="positive.json", negative_path="negative.json",
                            reviewer="reviewer", reason="checked both samples")

    def test_strict_review_rechecks_roles_references_and_outcomes(self):
        approved = self.approve()
        self.assertIn("review_positive_report_ref", validate_case(approved, self.root, require_approved=True))
        for change in ("missing_runs", "duplicate_roles", "wrong_run_id", "wrong_outcome", "changed_report"):
            with self.subTest(change=change):
                altered = deepcopy(approved.to_dict())
                runs = altered["review"]["validation_runs"]
                if change == "missing_runs":
                    del altered["review"]["validation_runs"]
                elif change == "duplicate_roles":
                    runs[1]["role"] = "positive"
                elif change == "wrong_run_id":
                    runs[0]["run_id"] = "invented"
                elif change == "wrong_outcome":
                    runs[1]["outcome"] = "pass"
                else:
                    runs[0]["report_ref"]["sha256"] = "0" * 64
                tampered = replace(approved, review=altered["review"])
                with self.assertRaises(CaseValidationError):
                    validate_case(tampered, self.root, require_approved=True)

        legacy_review = deepcopy(approved.review)
        del legacy_review["validation_runs"]
        legacy = replace(approved, review=legacy_review)
        save_case(legacy, root=self.root, out_path="cases/legacy.json")
        self.assertEqual("approved", load_case(self.root / "cases/legacy.json").status)
        with self.assertRaisesRegex(CaseValidationError, "validation_runs"):
            validate_case(legacy, self.root, require_approved=True)
        revised = revise_case(root=self.root, case_path="cases/legacy.json")
        self.assertEqual((2, "draft"), (revised.revision, revised.status))

    def test_forged_approved_definition_hash_does_not_bypass_review(self):
        approved = self.approve()
        forged = replace(approved, expected_behavior="changed")
        forged = replace(forged, review={**forged.review,
                                         "definition_sha256": case_definition_sha256(forged),
                                         "validation_runs": []})
        with self.assertRaisesRegex(CaseValidationError, "validation_runs"):
            validate_case(forged, self.root, require_approved=True)

    def test_approval_publish_failure_cleans_only_its_outputs_and_retries(self):
        from agent_regression import case_runner
        real_link = os.link

        def fail_second_report(source, destination, *args, **kwargs):
            if "/evidence/case-approvals/" in str(destination) and str(destination).endswith("negative.compare.json"):
                raise OSError("injected publish failure")
            return real_link(source, destination, *args, **kwargs)

        with patch.object(case_runner.os, "link", side_effect=fail_second_report):
            with self.assertRaisesRegex(OSError, "injected publish failure"):
                self.approve()
        self.assertEqual("draft", load_case(self.root / "cases/refund.json").status)
        self.assertFalse(list((self.root / "evidence/case-approvals").rglob("*.compare.json")))
        self.approve()
        self.assertEqual("approved", load_case(self.root / "cases/refund.json").status)

    def test_missing_evidence_keeps_confirmed_violation_and_code_two(self):
        self.approve()
        run, code = compare_case(root=self.root, case_path="cases/refund.json",
                                 candidate_path="missing.json", out_path="runs/missing.json")
        self.assertEqual(("inconclusive", 2), (run["outcome"], code))
        report = run["report"]
        self.assertTrue(report["evidence_gaps"])
        self.assertTrue(report["violations"])
        self.assertIsNone(report["passed"])
        self.assertLess(run["started_at"], run["finished_at"])

    def test_event_gap_does_not_promote_tool_or_answer_differences(self):
        self.assertFalse(_independent_of_gaps("events.1.result", [{"path": "events[1].result"}]))
        self.assertFalse(_independent_of_gaps("tool_results[0].result", [{"path": "events[1].result"}]))
        self.assertFalse(_independent_of_gaps("final_answer.claims", [{"path": "events[1].result"}]))
        self.assertTrue(_independent_of_gaps("final_answer.claims", [{"path": "metadata.fixture_version"}]))

        write_json(self.root / "event-policy.json", {
            "final_answer_mode": "claims-only",
            "evidence_requirements": [{"path": "events[1].result.unrecorded", "exists": True}],
        })
        draft = create_case_draft(root=self.root, baseline_path="baseline.json",
                                  policy_path="event-policy.json", title="Event evidence",
                                  expected_behavior="Result is recorded")
        report, _, _ = _compare(draft, self.root, "negative.json")
        self.assertEqual("inconclusive", report["outcome"])
        self.assertTrue(report["evidence_gaps"])
        self.assertTrue(report["differences"])
        self.assertEqual([], report["violations"])

    def test_execution_record_is_validated_and_referenced(self):
        self.approve()
        write_json(self.root / "execution.json", {"execution_id": "e1"})
        calls = []
        module = types.ModuleType("agent_regression.execution_records")
        module.validate_execution_record = lambda **kwargs: calls.append(kwargs) or {"agent_revision": "record-commit"}
        with patch.dict("sys.modules", {module.__name__: module}):
            run = compare_case(root=self.root, case_path="cases/refund.json",
                               candidate_path="positive.json", execution_path="execution.json")
            with self.assertRaisesRegex(CaseValidationError, "conflicts with ExecutionRecord"):
                compare_case(root=self.root, case_path="cases/refund.json",
                             candidate_path="positive.json", execution_path="execution.json",
                             agent_revision="other-commit")
        self.assertEqual("execution.json", run.execution_ref["path"])
        self.assertEqual(sha256_file(self.root / "execution.json"), run.execution_ref["sha256"])
        self.assertEqual("record-commit", run.agent_revision)
        self.assertEqual(False, calls[0]["require_recorded"])

    def test_source_commit_precedes_semantic_version_without_record(self):
        self.approve()
        run = compare_case(root=self.root, case_path="cases/refund.json",
                           candidate_path="positive.json", agent_revision="declared-other")
        candidate = json.loads((self.root / "positive.json").read_text())
        self.assertEqual(candidate["agent"]["source_commit"], run.agent_revision)


if __name__ == "__main__":
    unittest.main()
