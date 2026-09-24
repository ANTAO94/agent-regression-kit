"""Strict incident closure checks using actual compare and callback recording APIs."""

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from agent_regression.case_runner import approve_case, compare_case
from agent_regression.cases import create_case_draft, save_case
from agent_regression.cli import main
from agent_regression.compare import compare_traces
from agent_regression.execution_records import current_execution_id, record_execution
from agent_regression.incident_resolution import (
    ResolutionValidationError, render_incident_report, resolve_incident,
    validate_incident, validate_resolution,
)
from agent_regression.incidents import import_incident, sha256_file
from agent_regression.model import AgentTrace


SOURCE = Path(__file__).resolve().parents[1] / "examples/external-pilot/helppilot/baseline.trace.json"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class IncidentResolutionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        normal = json.loads(SOURCE.read_text(encoding="utf-8"))
        normal["run_id"] = "approval-good"
        broken = deepcopy(normal)
        broken["run_id"] = "imported-bad"
        broken["events"][-1]["claims"]["reply_refund_issued"] = False
        write_json(self.root / "baseline.json", normal)
        write_json(self.root / "negative.json", broken)
        write_json(self.root / "policy.json", {"final_answer_mode": "claims-only"})
        write_json(self.root / "input.json", normal["metadata"]["input"])
        write_json(self.root / "environment.json", {"fixture": "v1"})
        report = compare_traces(AgentTrace.from_dict(normal), AgentTrace.from_dict(broken))
        write_json(self.root / "import-report.json", report)
        self.incident = import_incident(root=self.root, trace_path="negative.json",
                                        report_path="import-report.json", out_path="incident.json",
                                        source_kind="injected")
        draft = create_case_draft(root=self.root, baseline_path="baseline.json",
                                  policy_path="policy.json", title="Refund",
                                  expected_behavior="Refund claim must agree with result",
                                  incident_refs=[self.incident.incident_id],
                                  input_path="input.json", environment_path="environment.json")
        save_case(draft, root=self.root, out_path="case.json")
        approve_case(root=self.root, case_path="case.json", positive_path="baseline.json",
                     negative_path="negative.json", reviewer="reviewer", reason="known error fails")
        before, code = compare_case(root=self.root, case_path="case.json",
                                    candidate_path="negative.json", out_path="before.json")
        self.assertEqual(("fail", 1), (before["outcome"], code))

        def invoke():
            candidate = deepcopy(normal)
            candidate["run_id"] = "fresh-good"
            candidate["metadata"]["execution_id"] = current_execution_id()
            return AgentTrace.from_dict(candidate)

        record_execution(root=self.root, trace_path="after.trace.json", out_path="after.execution.json",
                         invoke=invoke, agent_revision=normal["agent"]["source_commit"],
                         input_data=normal["metadata"]["input"], environment={"fixture": "v1"})
        after, code = compare_case(root=self.root, case_path="case.json",
                                   candidate_path="after.trace.json", execution_path="after.execution.json",
                                   out_path="after.json")
        self.assertEqual(("pass", 0), (after["outcome"], code))

    def resolve(self, **changes):
        arguments = dict(root=self.root, incident_path="incident.json", case_path="case.json",
                         before_path="before.json", after_path="after.json",
                         kind="injected_recovery", reviewer="reviewer", reason="fresh run passed",
                         out_path="resolution.json")
        arguments.update(changes)
        return resolve_incident(**arguments)

    def test_closure_is_immutable_and_revalidated(self):
        self.assertEqual("open", validate_incident(root=self.root, incident_path="incident.json")["status"])
        result = self.resolve()
        self.assertEqual("resolved", validate_resolution(root=self.root, resolution_path="resolution.json")["status"])
        report = render_incident_report(root=self.root, incident_path="incident.json",
                                        resolution_path="resolution.json")
        self.assertIn("injected_recovery", report)
        self.assertIn("Before: `imported-bad` (fail)", report)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.resolve()
        self.assertEqual(result, json.loads((self.root / "resolution.json").read_text()))
        after_trace = json.loads((self.root / "after.trace.json").read_text())
        after_trace["events"][-1]["claims"]["reply_refund_issued"] = False
        write_json(self.root / "after.trace.json", after_trace)
        with self.assertRaisesRegex(ResolutionValidationError, "SHA-256"):
            validate_resolution(root=self.root, resolution_path="resolution.json")

    def test_cli_execution_incident_closure_and_tampered_input(self):
        def invoke(*arguments):
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(list(arguments))
            return code, output.getvalue()

        root = ("--root", str(self.root))
        code, output = invoke("execution", "validate", *root, "--record", "after.execution.json",
                              "--candidate", "after.trace.json", "--require-recorded")
        self.assertEqual(0, code)
        self.assertEqual("recorded", json.loads(output)["recording_mode"])

        code, output = invoke("incident", "validate", *root, "--incident", "incident.json")
        self.assertEqual(0, code)
        self.assertEqual(self.incident.incident_id, json.loads(output)["incident_id"])

        code, output = invoke("incident", "resolve", *root, "--incident", "incident.json",
                              "--case", "case.json", "--before", "before.json", "--after", "after.json",
                              "--kind", "injected_recovery", "--reviewer", "reviewer",
                              "--reason", "fresh run passed", "--out", "resolution.json")
        self.assertEqual(0, code)
        self.assertEqual("injected_recovery", json.loads(output)["resolution_kind"])

        report_args = ("incident", "report", *root, "--incident", "incident.json",
                       "--resolution", "resolution.json")
        code, output = invoke(*report_args, "--format", "json")
        self.assertEqual(0, code)
        self.assertEqual("resolved", json.loads(output)["status"])
        code, output = invoke(*report_args, "--format", "markdown")
        self.assertEqual(0, code)
        self.assertIn("# Incident report", output)
        self.assertIn("injected_recovery", output)

        write_json(self.root / "input.json", {"query": "tampered"})
        code, output = invoke(*report_args, "--format", "json")
        self.assertEqual(2, code)
        self.assertFalse(json.loads(output)["ok"])
        self.assertIn("SHA-256", json.loads(output)["error"])

    def test_legacy_resolved_empty_dict_does_not_close(self):
        incident = json.loads((self.root / "incident.json").read_text())
        incident["status"] = "resolved"
        incident["resolution"] = {}
        write_json(self.root / "incident.json", incident)
        with self.assertRaisesRegex(ResolutionValidationError, "legacy resolved"):
            validate_incident(root=self.root, incident_path="incident.json")

    def test_incident_roles_hash_and_run_id_are_checked(self):
        original = json.loads((self.root / "incident.json").read_text())
        for change in ("role", "hash", "run_id"):
            with self.subTest(change=change):
                value = deepcopy(original)
                if change == "role":
                    value["evidence_refs"][0]["role"] = "unrelated"
                elif change == "hash":
                    value["evidence_refs"][0]["sha256"] = "0" * 64
                else:
                    report = json.loads((self.root / value["evidence_refs"][1]["path"]).read_text())
                    report["candidate_run_id"] = "other-run"
                    write_json(self.root / value["evidence_refs"][1]["path"], report)
                    value["evidence_refs"][1]["sha256"] = sha256_file(
                        self.root / value["evidence_refs"][1]["path"])
                write_json(self.root / "incident.changed.json", value)
                with self.assertRaises(ResolutionValidationError):
                    validate_incident(root=self.root, incident_path="incident.changed.json")

    def test_forged_outcome_and_unrelated_before_are_rejected(self):
        before = json.loads((self.root / "before.json").read_text())
        before["outcome"] = "pass"
        write_json(self.root / "forged-before.json", before)
        with self.assertRaisesRegex(ResolutionValidationError, "outcome"):
            self.resolve(before_path="forged-before.json")
        different = json.loads((self.root / "negative.json").read_text())
        different["run_id"] = "unrelated-error"
        write_json(self.root / "unrelated.trace.json", different)
        compare_case(root=self.root, case_path="case.json", candidate_path="unrelated.trace.json",
                     out_path="unrelated.run.json")
        with self.assertRaisesRegex(ResolutionValidationError, "imported redacted Trace"):
            self.resolve(before_path="unrelated.run.json")

    def test_unrelated_case_and_bug_fix_disguise_are_rejected(self):
        case = json.loads((self.root / "case.json").read_text())
        case["incident_refs"] = []
        write_json(self.root / "unrelated.case.json", case)
        with self.assertRaises(ResolutionValidationError):
            self.resolve(case_path="unrelated.case.json")
        with self.assertRaisesRegex(ResolutionValidationError, "historical_bug"):
            self.resolve(kind="bug_fix", change_ref="commit-123")

    def test_missing_execution_and_reused_run_are_rejected(self):
        after = json.loads((self.root / "after.json").read_text())
        del after["execution_ref"]
        write_json(self.root / "unrecorded.run.json", after)
        with self.assertRaisesRegex(ResolutionValidationError, "execution_ref"):
            self.resolve(after_path="unrecorded.run.json")
        after["execution_ref"] = json.loads((self.root / "after.json").read_text())["execution_ref"]
        after["candidate_ref"] = json.loads((self.root / "before.json").read_text())["candidate_ref"]
        write_json(self.root / "reused.run.json", after)
        with self.assertRaises(ResolutionValidationError):
            self.resolve(after_path="reused.run.json")

    def test_forged_report_and_changed_revision_are_rejected(self):
        after = json.loads((self.root / "after.json").read_text())
        after["case_revision"] += 1
        write_json(self.root / "wrong-revision.run.json", after)
        with self.assertRaisesRegex(ResolutionValidationError, "revision"):
            self.resolve(after_path="wrong-revision.run.json")
        after = json.loads((self.root / "after.json").read_text())
        forged = deepcopy(after["report"])
        forged["blocking_difference_count"] = 999
        write_json(self.root / "forged-report.json", forged)
        after["report"] = forged
        after["report_ref"] = {"role": "compare_report", "path": "forged-report.json",
                               "sha256": sha256_file(self.root / "forged-report.json")}
        write_json(self.root / "forged-report.run.json", after)
        with self.assertRaisesRegex(ResolutionValidationError, "recomputed compare_case"):
            self.resolve(after_path="forged-report.run.json")

    def test_case_run_report_ref_requires_compare_report_role(self):
        after = json.loads((self.root / "after.json").read_text())
        self.assertEqual("compare_report", after["report_ref"]["role"])
        after["report_ref"]["role"] = "candidate_trace"
        write_json(self.root / "wrong-report-role.run.json", after)
        with self.assertRaisesRegex(ResolutionValidationError, "compare_report role"):
            self.resolve(after_path="wrong-report-role.run.json")

    def test_imported_execution_is_not_new_recorded_evidence(self):
        record = json.loads((self.root / "after.execution.json").read_text())
        record["recording_mode"] = "imported"
        record["callback_binding"] = "unverified_import"
        write_json(self.root / "imported.execution.json", record)
        after = json.loads((self.root / "after.json").read_text())
        after["execution_ref"] = {"path": "imported.execution.json",
                                  "sha256": sha256_file(self.root / "imported.execution.json")}
        write_json(self.root / "imported.run.json", after)
        with self.assertRaisesRegex(ResolutionValidationError, "newly recorded"):
            self.resolve(after_path="imported.run.json")

    def test_recorded_input_and_environment_must_match_case_fixed_refs(self):
        write_json(self.root / "fixed-input.json", {"query": "refund"})
        write_json(self.root / "fixed-environment.json", {"fixture": "v1"})
        fixed = create_case_draft(root=self.root, baseline_path="baseline.json",
                                  policy_path="policy.json", title="Fixed premises",
                                  expected_behavior="Refund claim agrees with result",
                                  incident_refs=[self.incident.incident_id],
                                  input_path="fixed-input.json",
                                  environment_path="fixed-environment.json")
        save_case(fixed, root=self.root, out_path="fixed.case.json")
        approve_case(root=self.root, case_path="fixed.case.json", positive_path="baseline.json",
                     negative_path="negative.json", reviewer="reviewer", reason="checked")
        compare_case(root=self.root, case_path="fixed.case.json", candidate_path="negative.json",
                     out_path="fixed-before.run.json")
        compare_case(root=self.root, case_path="fixed.case.json", candidate_path="after.trace.json",
                     execution_path="after.execution.json", out_path="fixed-after.run.json")
        with self.assertRaisesRegex(ResolutionValidationError, "input_sha256"):
            self.resolve(case_path="fixed.case.json", before_path="fixed-before.run.json",
                         after_path="fixed-after.run.json")

    def test_missing_before_record_requires_fixed_case_premises(self):
        loose = create_case_draft(root=self.root, baseline_path="baseline.json",
                                  policy_path="policy.json", title="Unfixed premises",
                                  expected_behavior="Refund claim agrees with result",
                                  incident_refs=[self.incident.incident_id])
        save_case(loose, root=self.root, out_path="loose.case.json")
        approve_case(root=self.root, case_path="loose.case.json", positive_path="baseline.json",
                     negative_path="negative.json", reviewer="reviewer", reason="checked")
        compare_case(root=self.root, case_path="loose.case.json", candidate_path="negative.json",
                     out_path="loose-before.run.json")
        compare_case(root=self.root, case_path="loose.case.json", candidate_path="after.trace.json",
                     execution_path="after.execution.json", out_path="loose-after.run.json")
        with self.assertRaisesRegex(ResolutionValidationError, "must fix both input_ref and environment_ref"):
            self.resolve(case_path="loose.case.json", before_path="loose-before.run.json",
                         after_path="loose-after.run.json")

    def recorded_before_bundle(self, *, input_data, environment):
        broken = json.loads((self.root / "negative.json").read_text())
        commit = broken["agent"]["source_commit"]

        def invoke_broken():
            trace = deepcopy(broken)
            trace["run_id"] = "recorded-bad"
            trace["metadata"]["execution_id"] = current_execution_id()
            return AgentTrace.from_dict(trace)

        record_execution(root=self.root, trace_path="recorded-bad.trace.json",
                         out_path="recorded-bad.execution.json", invoke=invoke_broken,
                         agent_revision=commit, input_data=input_data,
                         environment=environment)
        baseline = AgentTrace.from_dict(json.loads((self.root / "baseline.json").read_text()))
        recorded_bad = AgentTrace.from_dict(json.loads((self.root / "recorded-bad.trace.json").read_text()))
        write_json(self.root / "recorded-bad.report.json", compare_traces(baseline, recorded_bad))
        incident = import_incident(root=self.root, trace_path="recorded-bad.trace.json",
                                   report_path="recorded-bad.report.json",
                                   out_path="recorded-incident.json", source_kind="injected")
        case = create_case_draft(root=self.root, baseline_path="baseline.json",
                                 policy_path="policy.json", title="Recorded contrast",
                                 expected_behavior="Refund claim agrees with result",
                                 incident_refs=[incident.incident_id])
        save_case(case, root=self.root, out_path="recorded.case.json")
        approve_case(root=self.root, case_path="recorded.case.json", positive_path="baseline.json",
                     negative_path="recorded-bad.trace.json", reviewer="reviewer", reason="checked")
        compare_case(root=self.root, case_path="recorded.case.json",
                     candidate_path="recorded-bad.trace.json",
                     execution_path="recorded-bad.execution.json",
                     out_path="recorded-before.run.json")
        compare_case(root=self.root, case_path="recorded.case.json",
                     candidate_path="after.trace.json", execution_path="after.execution.json",
                     out_path="recorded-after.run.json")
        return {"incident_path": "recorded-incident.json", "case_path": "recorded.case.json",
                "before_path": "recorded-before.run.json", "after_path": "recorded-after.run.json"}

    def test_before_and_after_record_digests_must_match_without_case_refs(self):
        paths = self.recorded_before_bundle(input_data={"query": "different"},
                                            environment={"fixture": "v2"})
        with self.assertRaisesRegex(ResolutionValidationError, "before/after ExecutionRecord input_sha256"):
            self.resolve(**paths)

    def test_older_after_execution_cannot_prove_recovery(self):
        input_data = json.loads((self.root / "input.json").read_text())
        paths = self.recorded_before_bundle(input_data=input_data, environment={"fixture": "v1"})
        before_record = json.loads((self.root / "recorded-bad.execution.json").read_text())
        after_record = json.loads((self.root / "after.execution.json").read_text())
        self.assertEqual(before_record["input_sha256"], after_record["input_sha256"])
        self.assertEqual(before_record["environment_sha256"], after_record["environment_sha256"])
        with self.assertRaisesRegex(ResolutionValidationError, "started_at precedes before"):
            self.resolve(**paths)

    def test_resolution_reviewed_at_requires_iso_timezone(self):
        self.resolve()
        original = json.loads((self.root / "resolution.json").read_text())
        for value in ("yesterday", "2026-09-23T12:34:56", "2026-13-23T12:34:56+08:00"):
            with self.subTest(reviewed_at=value):
                changed = deepcopy(original)
                changed["reviewed_at"] = value
                write_json(self.root / "bad-time.resolution.json", changed)
                with self.assertRaisesRegex(ResolutionValidationError, "reviewed_at"):
                    validate_resolution(root=self.root, resolution_path="bad-time.resolution.json")

    def test_resolution_identity_and_requested_incident_are_rechecked(self):
        self.resolve()
        raw = json.loads((self.root / "resolution.json").read_text())
        raw["case_id"] = "unrelated-case"
        write_json(self.root / "forged-resolution.json", raw)
        with self.assertRaisesRegex(ResolutionValidationError, "case_id"):
            validate_resolution(root=self.root, resolution_path="forged-resolution.json")
        other = import_incident(root=self.root, trace_path="negative.json",
                                report_path="import-report.json", out_path="other-incident.json",
                                source_kind="injected")
        self.assertNotEqual(self.incident.incident_id, other.incident_id)
        with self.assertRaisesRegex(ResolutionValidationError, "different incident"):
            render_incident_report(root=self.root, incident_path="other-incident.json",
                                   resolution_path="resolution.json")

    def test_historical_bug_requires_change_reference(self):
        historical = import_incident(root=self.root, trace_path="negative.json",
                                     report_path="import-report.json", out_path="historical.json",
                                     source_kind="historical_bug")
        draft = create_case_draft(root=self.root, baseline_path="baseline.json",
                                  policy_path="policy.json", title="Historical refund error",
                                  expected_behavior="Refund claim agrees with result",
                                  incident_refs=[historical.incident_id], input_path="input.json",
                                  environment_path="environment.json")
        save_case(draft, root=self.root, out_path="historical.case.json")
        approve_case(root=self.root, case_path="historical.case.json", positive_path="baseline.json",
                     negative_path="negative.json", reviewer="reviewer", reason="checked")
        compare_case(root=self.root, case_path="historical.case.json", candidate_path="negative.json",
                     out_path="historical-before.run.json")
        compare_case(root=self.root, case_path="historical.case.json", candidate_path="after.trace.json",
                     execution_path="after.execution.json", out_path="historical-after.run.json")
        paths = {"incident_path": "historical.json", "case_path": "historical.case.json",
                 "before_path": "historical-before.run.json", "after_path": "historical-after.run.json",
                 "kind": "bug_fix"}
        with self.assertRaisesRegex(ResolutionValidationError, "change_ref"):
            self.resolve(**paths)
        result = self.resolve(change_ref="commit:abc123", **paths)
        self.assertEqual("commit:abc123", result["change_ref"])


if __name__ == "__main__":
    unittest.main()
