"""Boundary checks for callback-bound execution evidence."""

import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from agent_regression.execution_records import (
    ExecutionValidationError, current_execution_id, record_execution,
    validate_execution_record,
)
from agent_regression.model import AgentTrace


class ExecutionRecordTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def trace(self, *, run_id="run-1", commit="commit-1"):
        return AgentTrace.from_dict({
            "schema_version": "0.1", "run_id": run_id,
            "agent": {"name": "HelpPilot", "version": "0.1.0", "source_commit": commit},
            "events": [{"sequence": 1, "type": "final_answer", "text": "done"}],
            "metadata": {"execution_id": current_execution_id()},
        })

    def record(self, invoke=None, **kwargs):
        return record_execution(
            root=self.root, trace_path="executions/new.trace.json",
            out_path="executions/new.execution.json",
            invoke=invoke or (lambda: self.trace()), agent_revision="commit-1", **kwargs,
        )

    def test_callback_has_id_before_run_and_record_validates_strictly(self):
        seen = []

        def invoke():
            seen.append(current_execution_id())
            return self.trace()

        record = self.record(invoke, input_data={"prompt": "hi", "token": "secret"},
                             environment={"fixture": "v1"}, dirty=True,
                             producer={"runner": "GitHub Actions", "repository": "acme/helppilot",
                                       "commit": "commit-1", "job_id": "gate", "run_id": "42"})
        self.assertEqual([record["execution_id"]], seen)
        self.assertIsNone(current_execution_id())
        self.assertEqual("recorded", record["recording_mode"])
        self.assertEqual("ci_correlated", record["provenance_level"])
        self.assertEqual("0.1.0", self.trace().agent["version"])
        self.assertEqual(record, validate_execution_record(
            root=self.root, record_path="executions/new.execution.json",
            candidate_path="executions/new.trace.json", require_recorded=True,
        ))
        written = json.loads((self.root / "executions/new.trace.json").read_text())
        self.assertEqual(record["execution_id"], written["metadata"]["execution_id"])
        self.assertEqual(record["agent_revision"], written["agent"]["source_commit"])
        self.assertEqual(record["input_sha256"], written["metadata"]["input_sha256"])

    def test_existing_output_rejected_before_callback(self):
        self.record()
        called = []
        with self.assertRaisesRegex(ExecutionValidationError, "overwrite"):
            self.record(lambda: called.append(True))
        self.assertEqual([], called)

    def test_output_path_escape_rejected_before_callback(self):
        called = []
        with self.assertRaisesRegex(ExecutionValidationError, "output path"):
            record_execution(root=self.root, trace_path="../outside.trace.json",
                             out_path="executions/new.execution.json",
                             invoke=lambda: called.append(True))
        self.assertEqual([], called)

    def test_callback_failure_leaves_no_partial_files_or_context(self):
        def fail():
            self.assertIsNotNone(current_execution_id())
            raise RuntimeError("agent failed")

        with self.assertRaisesRegex(RuntimeError, "agent failed"):
            self.record(fail)
        self.assertIsNone(current_execution_id())
        self.assertFalse((self.root / "executions/new.trace.json").exists())
        self.assertFalse((self.root / "executions/new.execution.json").exists())

    def test_invalid_trace_and_commit_mismatch_leave_no_outputs(self):
        with self.assertRaisesRegex(ExecutionValidationError, "source_commit"):
            self.record(lambda: self.trace(commit="different"))
        self.assertFalse((self.root / "executions/new.trace.json").exists())
        with self.assertRaisesRegex(ExecutionValidationError, "AgentTrace"):
            self.record(lambda: {"run_id": "old"})
        self.assertFalse((self.root / "executions/new.execution.json").exists())

    def test_old_trace_created_before_callback_is_rejected(self):
        old_trace = self.trace(run_id="old-run")
        old_trace.metadata.pop("execution_id")
        self.assertNotIn("execution_id", old_trace.metadata)
        with self.assertRaisesRegex(ExecutionValidationError, "metadata.execution_id"):
            self.record(lambda: old_trace)
        self.assertFalse((self.root / "executions/new.trace.json").exists())
        self.assertFalse((self.root / "executions/new.execution.json").exists())

    def test_tampered_trace_candidate_and_record_are_rejected(self):
        self.record()
        record_file = self.root / "executions/new.execution.json"
        trace_file = self.root / "executions/new.trace.json"
        with self.assertRaisesRegex(ExecutionValidationError, "candidate_path"):
            validate_execution_record(root=self.root, record_path="executions/new.execution.json",
                                      candidate_path="executions/new.execution.json")
        trace = json.loads(trace_file.read_text())
        trace["run_id"] = "substituted"
        trace_file.write_text(json.dumps(trace))
        with self.assertRaisesRegex(ExecutionValidationError, "SHA-256"):
            validate_execution_record(root=self.root, record_path="executions/new.execution.json")
        trace_file.write_text(json.dumps(self.trace().to_dict()))
        record = json.loads(record_file.read_text())
        record["trace_ref"]["sha256"] = "0" * 64
        record_file.write_text(json.dumps(record))
        with self.assertRaisesRegex(ExecutionValidationError, "SHA-256"):
            validate_execution_record(root=self.root, record_path="executions/new.execution.json")

    def test_imported_record_is_comparable_but_not_strictly_recorded(self):
        record = self.record()
        imported = deepcopy(record)
        imported["recording_mode"] = "imported"
        imported["callback_binding"] = "unverified_import"
        (self.root / "executions/new.execution.json").write_text(json.dumps(imported))
        self.assertEqual(imported, validate_execution_record(
            root=self.root, record_path="executions/new.execution.json"))
        with self.assertRaisesRegex(ExecutionValidationError, "newly recorded"):
            validate_execution_record(root=self.root,
                                      record_path="executions/new.execution.json", require_recorded=True)

    def test_ci_claim_requires_complete_consistent_runner_metadata(self):
        fields = {"runner": "GitHub Actions", "repository": "acme/helppilot",
                  "commit": "commit-1", "job_id": "gate", "run_id": "42"}
        for key in fields:
            with self.subTest(missing=key):
                with self.assertRaisesRegex(ExecutionValidationError, f"producer.{key}"):
                    self.record(producer={name: value for name, value in fields.items() if name != key})
                self.assertFalse((self.root / "executions/new.trace.json").exists())
        with self.assertRaisesRegex(ExecutionValidationError, "producer.commit"):
            self.record(producer={**fields, "commit": "other-commit"})
        self.assertFalse((self.root / "executions/new.execution.json").exists())

    def test_empty_producer_is_local_declared_recording(self):
        record = self.record(producer={})
        self.assertEqual({}, record["producer"])
        self.assertEqual("declared", record["provenance_level"])
        self.assertEqual("recorded", record["recording_mode"])
        self.assertEqual(record, validate_execution_record(
            root=self.root, record_path="executions/new.execution.json", require_recorded=True))

    def test_metadata_and_source_commit_must_remain_consistent(self):
        def wrong_metadata():
            trace = self.trace()
            trace.metadata["execution_id"] = "old-execution"
            return trace

        with self.assertRaisesRegex(ExecutionValidationError, "metadata.execution_id"):
            self.record(wrong_metadata)
        self.record()
        record_file = self.root / "executions/new.execution.json"
        trace_file = self.root / "executions/new.trace.json"
        trace = json.loads(trace_file.read_text())
        trace["agent"]["source_commit"] = "different"
        trace_file.write_text(json.dumps(trace))
        record = json.loads(record_file.read_text())
        import hashlib
        record["trace_ref"]["sha256"] = hashlib.sha256(trace_file.read_bytes()).hexdigest()
        record_file.write_text(json.dumps(record))
        with self.assertRaisesRegex(ExecutionValidationError, "source_commit"):
            validate_execution_record(root=self.root, record_path="executions/new.execution.json")


if __name__ == "__main__":
    unittest.main()
