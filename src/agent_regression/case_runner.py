"""Approved Trace case validation, evidence comparison, and explicit suite execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from typing import Any, Mapping

from .cases import (
    CASE_SCHEMA_VERSION,
    CaseValidationError,
    EvaluationCase,
    case_definition_sha256,
    load_case,
    save_case,
    validate_case,
)
from .compare import ComparisonPolicy, compare_traces
from .contracts import ContractPolicy
from .incidents import (
    IncidentValidationError,
    atomic_write_json,
    make_reference,
    safe_input_path,
    safe_output_path,
    sha256_file,
)
from .model import AgentTrace
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


CASE_RUN_SCHEMA_VERSION = "0.1"


@dataclass(frozen=True)
class CaseRun:
    schema_version: str
    case_run_id: str
    case_id: str
    case_revision: int
    definition_sha256: str
    execution_mode: str
    candidate_ref: dict[str, str]
    agent_revision: str
    outcome: str
    started_at: str
    finished_at: str
    compare_report: dict[str, Any] | None = None
    report_ref: dict[str, str] | None = None
    execution_ref: dict[str, str] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "case_run_id": self.case_run_id,
            "case_id": self.case_id,
            "case_revision": self.case_revision,
            "definition_sha256": self.definition_sha256,
            "execution_mode": self.execution_mode,
            "candidate_ref": self.candidate_ref,
            "agent_revision": self.agent_revision,
            "report_ref": self.report_ref,
            "outcome": self.outcome,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        if self.execution_ref is not None:
            result["execution_ref"] = self.execution_ref
        if self.compare_report is not None:
            result["report"] = self.compare_report
        if self.error is not None:
            result["error"] = self.error
        return result


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseValidationError(f"cannot read {label} JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CaseValidationError(f"{label} must be a JSON object")
    return value


def _case_file(root: str | Path, value: str | Path) -> Path:
    try:
        return safe_input_path(root, value)
    except IncidentValidationError as exc:
        raise CaseValidationError(str(exc)) from exc


def _output_file(root: str | Path, value: str | Path) -> Path:
    try:
        return safe_output_path(root, value)
    except IncidentValidationError as exc:
        raise CaseValidationError(str(exc)) from exc


def _make_path_reference(root: str | Path, path: str | Path, *, role: str) -> dict[str, str]:
    root_path = Path(root).expanduser().resolve()
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        relative = resolved.relative_to(root_path).as_posix()
    except ValueError as exc:
        raise CaseValidationError(f"evidence path escapes bundle root: {path}") from exc
    try:
        return make_reference(root_path, relative, role=role)
    except IncidentValidationError as exc:
        raise CaseValidationError(str(exc)) from exc


def _comparison_policy(raw: Mapping[str, Any]) -> ComparisonPolicy:
    contract_raw = raw.get("contract", {})
    try:
        contract = ContractPolicy.from_dict(contract_raw)
        return ComparisonPolicy(
            allowed_categories=set(raw.get("allow_categories", [])),
            allowed_paths=set(raw.get("allow_paths", [])),
            final_answer_mode=raw.get("final_answer_mode", "exact"),
            result_alignment=raw.get("result_alignment", "call_id"),
            contract=contract,
        )
    except (TypeError, ValueError) as exc:
        raise CaseValidationError(f"invalid comparison policy: {exc}") from exc


def _lookup(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    for token in path.replace("[", ".").replace("]", "").split("."):
        if not token:
            continue
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError):
                return False, None
        else:
            return False, None
    return True, current


def _actual_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _evidence_gaps(trace: AgentTrace, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw = trace.to_dict()
    gaps = []
    for requirement in requirements:
        path = requirement["path"]
        found, value = _lookup(raw, path)
        should_exist = requirement.get("exists", True)
        if should_exist and not found:
            gaps.append({"path": path, "reason": "required evidence is missing"})
            continue
        if not should_exist and found:
            gaps.append({"path": path, "reason": "evidence was required to be absent"})
            continue
        expected_type = requirement.get("type")
        if found and expected_type and _actual_type(value) != expected_type:
            gaps.append(
                {
                    "path": path,
                    "reason": "evidence has the wrong type",
                    "expected_type": expected_type,
                    "actual_type": _actual_type(value),
                }
            )
    return gaps


def _independent_of_gaps(path: str, gaps: list[dict[str, Any]]) -> bool:
    """Only promote a difference when its evidence is demonstrably separate."""
    if not isinstance(path, str) or not path:
        return False

    def tokens(value: str) -> tuple[str, ...]:
        return tuple(part for part in value.replace("[", ".").replace("]", "").split(".") if part)

    difference = tokens(path)
    if not difference:
        return False
    for gap in gaps:
        missing = tokens(gap["path"])
        if not missing:
            return False
        # The comparator projects raw events into several logical paths. A
        # missing event field can affect tool, answer, and contract judgments.
        if missing[0] == "events" and difference[0] != "metadata":
            return False
        if difference[:len(missing)] == missing or missing[:len(difference)] == difference:
            return False
    return True


def _load_inputs(
    case: EvaluationCase,
    root: str | Path,
    candidate_path: str | Path,
) -> tuple[dict[str, Path], AgentTrace, AgentTrace, dict[str, Any], ComparisonPolicy, dict[str, Any]]:
    paths = validate_case(case, root, require_approved=case.status != "draft")
    candidate_file = _case_file(root, candidate_path)
    baseline_data = _read_json(paths["baseline_ref"], "baseline Trace")
    candidate_data = _read_json(candidate_file, "candidate Trace")
    baseline = AgentTrace.from_dict(baseline_data)
    candidate = AgentTrace.from_dict(candidate_data)
    policy_raw = _read_json(paths["policy_ref"], "comparison policy")
    policy = _comparison_policy(policy_raw)
    requirements = [*case.evidence_requirements, *policy_raw.get("evidence_requirements", [])]
    return paths, baseline, candidate, policy_raw, policy, {"requirements": requirements, "candidate_file": candidate_file}


def _compare(
    case: EvaluationCase,
    root: str | Path,
    candidate_path: str | Path,
    *,
    redaction_policy: RedactionPolicy | None = None,
) -> tuple[dict[str, Any], AgentTrace, Path]:
    _, baseline, candidate, _, policy, details = _load_inputs(case, root, candidate_path)
    gaps = _evidence_gaps(candidate, details["requirements"])
    report = compare_traces(
        baseline, candidate, policy, redaction_policy or DEFAULT_REDACTION_POLICY,
    )
    report["report_type"] = "agent_case_compare"
    if gaps:
        report.update(outcome="inconclusive", passed=None,
                      reason="candidate does not satisfy declared evidence requirements",
                      evidence_gaps=gaps)
        report["violations"] = [
            item for item in report["differences"]
            if not item["allowed"] and _independent_of_gaps(item.get("path"), gaps)
        ]
    else:
        report["outcome"] = "pass" if report["passed"] else "fail"
    return report, candidate, details["candidate_file"]


def _case_storage_key(case_id: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", case_id).strip("._-")
    return token[:80] or "case"


def approve_case(
    case_or_path: EvaluationCase | str | Path | None = None, *, root: str | Path,
    case_path: str | Path | None = None, positive_path: str | Path,
    negative_path: str | Path, reviewer: str, reason: str,
    redaction_policy: RedactionPolicy | None = None,
) -> EvaluationCase:
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise CaseValidationError("reviewer must be a non-empty string")
    if not isinstance(reason, str) or not reason.strip():
        raise CaseValidationError("review reason must be a non-empty string")
    if case_or_path is not None and case_path is not None:
        raise CaseValidationError("provide either a case object or case_path, not both")
    target = case_path if case_path is not None else case_or_path
    if target is None:
        raise CaseValidationError("approve_case requires a case or case_path")
    persist = not isinstance(target, EvaluationCase)
    case = target if isinstance(target, EvaluationCase) else load_case(_case_file(root, target))
    if case.status != "draft":
        raise CaseValidationError("only a draft case can be approved; create a new revision to re-review")
    validate_case(case, root)
    positive_report, positive_trace, positive_file = _compare(
        case, root, positive_path, redaction_policy=redaction_policy
    )
    negative_report, negative_trace, negative_file = _compare(
        case, root, negative_path, redaction_policy=redaction_policy
    )
    if positive_report.get("outcome") != "pass":
        raise CaseValidationError(
            "approval rejected: positive sample or its evidence requirements failed; observed "
            + str(positive_report.get("outcome"))
        )
    if negative_report.get("outcome") != "fail":
        raise CaseValidationError(
            "approval rejected: negative sample passes or is inconclusive; a weak rule cannot be approved"
        )

    root_path = Path(root).expanduser().resolve()
    directory = Path("evidence/case-approvals") / _case_storage_key(case.case_id) / f"r{case.revision}"
    positive_report_rel = directory / "positive.compare.json"
    negative_report_rel = directory / "negative.compare.json"
    positive_report_file = _output_file(root_path, positive_report_rel)
    negative_report_file = _output_file(root_path, negative_report_rel)
    if positive_report_file.exists() or negative_report_file.exists():
        raise CaseValidationError("approval report already exists; refusing to overwrite an existing file")
    protected = {positive_file, negative_file, *validate_case(case, root_path).values()}
    if persist:
        protected.add(_case_file(root_path, target))
    if positive_report_file in protected or negative_report_file in protected:
        raise CaseValidationError("approval report path overlaps case or evidence input")
    with tempfile.TemporaryDirectory(prefix=".case-approval-", dir=root_path) as stage_dir:
        staged_positive = Path(stage_dir) / "positive.compare.json"
        staged_negative = Path(stage_dir) / "negative.compare.json"
        atomic_write_json(staged_positive, positive_report)
        atomic_write_json(staged_negative, negative_report)
        staged = [(staged_positive, positive_report_file), (staged_negative, negative_report_file)]
        created: list[tuple[Path, Path]] = []
        try:
            for source, destination in staged:
                os.link(source, destination)
                created.append((source, destination))
            approved = _build_approved_case(
                case, reviewer, reason, positive_trace, negative_trace,
                positive_report, negative_report,
                positive_file, negative_file, positive_report_rel, negative_report_rel,
                staged_positive, staged_negative, root_path,
            )
            validate_case(approved, root_path, require_approved=True)
            if persist:
                save_case(approved, root=root, out_path=target, overwrite=True)
            return approved
        except BaseException:
            for source, destination in reversed(created):
                if destination.exists() and os.path.samefile(source, destination):
                    destination.unlink()
            raise


def _build_approved_case(
    case: EvaluationCase, reviewer: str, reason: str,
    positive_trace: AgentTrace, negative_trace: AgentTrace,
    positive_report: dict[str, Any], negative_report: dict[str, Any],
    positive_file: Path, negative_file: Path,
    positive_report_rel: Path, negative_report_rel: Path,
    positive_report_file: Path, negative_report_file: Path, root_path: Path,
) -> EvaluationCase:
    positive_candidate_ref = _make_path_reference(root_path, positive_file, role="positive_candidate")
    negative_candidate_ref = _make_path_reference(root_path, negative_file, role="negative_candidate")
    validation_runs = [
        {
            "role": "positive",
            "candidate_ref": {"path": positive_candidate_ref["path"], "sha256": positive_candidate_ref["sha256"]},
            "run_id": positive_trace.run_id,
            "outcome": positive_report["outcome"],
            "report_ref": {
                "path": positive_report_rel.as_posix(),
                "sha256": sha256_file(positive_report_file),
            },
        },
        {
            "role": "negative",
            "candidate_ref": {"path": negative_candidate_ref["path"], "sha256": negative_candidate_ref["sha256"]},
            "run_id": negative_trace.run_id,
            "outcome": negative_report["outcome"],
            "report_ref": {
                "path": negative_report_rel.as_posix(),
                "sha256": sha256_file(negative_report_file),
            },
        },
    ]
    approved = replace(
        case,
        status="approved",
        review={
            "reviewer": reviewer.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason.strip(),
            "definition_sha256": case_definition_sha256(case),
            "validation_runs": validation_runs,
        },
    )
    return approved


def _case_run(
    *, case: EvaluationCase, root: str | Path, candidate_path: str | Path,
    agent_revision: str | None, redaction_policy: RedactionPolicy | None,
    execution_path: str | Path | None,
) -> CaseRun:
    if case.status != "approved":
        raise CaseValidationError("case is not approved; draft cases cannot be used as CI gates")
    started_at = datetime.now(timezone.utc).isoformat()
    report, candidate, candidate_file = _compare(
        case, root, candidate_path, redaction_policy=redaction_policy
    )
    finished_at = datetime.now(timezone.utc).isoformat()
    execution_ref = None
    revision = candidate.agent.get("source_commit") or agent_revision or candidate.agent.get("version") or "unknown"
    if execution_path is not None:
        from .execution_records import validate_execution_record
        record = validate_execution_record(root=root, record_path=execution_path,
                                           candidate_path=candidate_path, require_recorded=False)
        revision = record["agent_revision"]
        if agent_revision is not None and agent_revision != revision:
            raise CaseValidationError(
                "explicit agent_revision conflicts with ExecutionRecord.agent_revision"
            )
        full_ref = _make_path_reference(root, _case_file(root, execution_path), role="execution")
        execution_ref = {"path": full_ref["path"], "sha256": full_ref["sha256"]}
    candidate_ref_full = _make_path_reference(root, candidate_file, role="candidate")
    outcome = report.get("outcome")
    return CaseRun(
        schema_version=CASE_RUN_SCHEMA_VERSION,
        case_run_id="case-run-" + uuid.uuid4().hex[:12],
        case_id=case.case_id,
        case_revision=case.revision,
        definition_sha256=case.review["definition_sha256"],
        execution_mode="evidence_compare",
        candidate_ref={"path": candidate_ref_full["path"], "sha256": candidate_ref_full["sha256"]},
        agent_revision=revision,
        outcome=outcome,
        started_at=started_at,
        finished_at=finished_at,
        compare_report=report,
        execution_ref=execution_ref,
    )


def validate_case_definition(case_or_path: EvaluationCase | str | Path, root: str | Path) -> dict[str, Any]:
    case = (
        case_or_path
        if isinstance(case_or_path, EvaluationCase)
        else load_case(_case_file(root, case_or_path))
    )
    paths = validate_case(case, root, require_approved=case.status == "approved")
    return {
        "ok": True,
        "case_id": case.case_id,
        "revision": case.revision,
        "status": case.status,
        "definition_sha256": case_definition_sha256(case),
        "verified_references": sorted(paths),
        "gate_eligible": case.status == "approved",
    }


def compare_case(
    case_or_path: EvaluationCase | str | Path | None = None, *, root: str | Path,
    case_path: str | Path | None = None,
    candidate_path: str | Path, agent_revision: str | None = None,
    execution_path: str | Path | None = None,
    redaction_policy: RedactionPolicy | None = None, out_path: str | Path | None = None,
    report_path: str | Path | None = None,
) -> CaseRun | tuple[dict[str, Any], int]:
    if case_or_path is not None and case_path is not None:
        raise CaseValidationError("provide either a case object or case_path, not both")
    target = case_path if case_path is not None else case_or_path
    if target is None:
        raise CaseValidationError("compare_case requires a case or case_path")
    case = target if isinstance(target, EvaluationCase) else load_case(_case_file(root, target))
    run = _case_run(
        case=case,
        root=root,
        candidate_path=candidate_path,
        agent_revision=agent_revision,
        execution_path=execution_path,
        redaction_policy=redaction_policy,
    )
    if out_path is None:
        return run

    root_path = Path(root).expanduser().resolve()
    run_file = _output_file(root_path, out_path)
    if report_path is None:
        out_relative = Path(out_path)
        report_relative = out_relative.with_name(out_relative.stem + ".compare.json")
    else:
        report_relative = Path(report_path)
    report_file = _output_file(root_path, report_relative)
    case_file = _case_file(root_path, case_path if case_path is not None else target) if not isinstance(target, EvaluationCase) else None
    candidate_file = _case_file(root_path, candidate_path)
    protected = {candidate_file}
    if case_file is not None:
        protected.add(case_file)
    protected.update(validate_case(case, root_path).values())
    if run_file == report_file or run_file in protected or report_file in protected:
        raise CaseValidationError("CaseRun/report output must differ from case, candidate, baseline, policy, input, and environment")
    if run_file.exists() or report_file.exists():
        raise CaseValidationError("refusing to overwrite an existing CaseRun or comparison report")
    atomic_write_json(report_file, run.compare_report or {})
    report_ref = _make_path_reference(root_path, report_file, role="compare_report")
    completed = replace(run, report_ref=report_ref)
    atomic_write_json(run_file, completed.to_dict())
    exit_code = {"pass": 0, "fail": 1, "inconclusive": 2, "error": 2}.get(completed.outcome, 2)
    return completed.to_dict(), exit_code


def compare_case_suite(
    manifest_path: str | Path | None = None, *, root: str | Path = ".",
    redaction_policy: RedactionPolicy | None = None,
    out_path: str | Path | None = None,
) -> dict[str, Any] | tuple[dict[str, Any], int]:
    if manifest_path is None:
        raise CaseValidationError("case suite requires a manifest path")
    root_path = Path(root).expanduser().resolve()
    manifest_file = _case_file(root_path, manifest_path)
    manifest = _read_json(manifest_file, "case suite manifest")
    if set(manifest) - {"schema_version", "cases"}:
        raise CaseValidationError("unsupported suite manifest fields")
    if manifest.get("schema_version", "0.1") != "0.1":
        raise CaseValidationError("unsupported suite manifest schema_version")
    entries = manifest.get("cases")
    if not isinstance(entries, list) or not entries:
        raise CaseValidationError("case suite must contain at least one explicit case mapping")
    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) - {"case", "candidate", "agent_revision", "execution"}:
            raise CaseValidationError(f"suite entry {index} has unsupported fields")
        if not isinstance(entry.get("case"), str) or not isinstance(entry.get("candidate"), str):
            raise CaseValidationError(f"suite entry {index} must explicitly map case and candidate paths")
        try:
            case = load_case(_case_file(root_path, entry["case"]))
            if case.case_id in seen_ids:
                raise CaseValidationError(f"duplicate case_id in suite: {case.case_id}")
            seen_ids.add(case.case_id)
            run = compare_case(
                case,
                root=root_path,
                candidate_path=entry["candidate"],
                agent_revision=entry.get("agent_revision"),
                execution_path=entry.get("execution"),
                redaction_policy=redaction_policy,
            )
            if not isinstance(run, CaseRun):
                raise CaseValidationError("internal suite comparison returned an invalid CaseRun")
            run_value = run.to_dict()
            # Keep the intuitive compare_report alias in suite rows while the
            # standalone CaseRun document follows case-run-v0.1.schema.json.
            run_value["compare_report"] = run.compare_report
            results.append(run_value)
        except (CaseValidationError, IncidentValidationError, OSError, ValueError) as exc:
            results.append(
                {
                    "schema_version": CASE_RUN_SCHEMA_VERSION,
                    "case_run_id": "case-run-" + uuid.uuid4().hex[:12],
                    "case_path": entry.get("case"),
                    "candidate_path": entry.get("candidate"),
                    "execution_mode": "evidence_compare",
                    "outcome": "error",
                    "error": str(exc),
                }
            )
    outcomes = {item.get("outcome") for item in results}
    if outcomes & {"error", "inconclusive"}:
        outcome, exit_code = "error", 2
    elif "fail" in outcomes:
        outcome, exit_code = "fail", 1
    else:
        outcome, exit_code = "pass", 0
    suite = {
        "schema_version": "0.1",
        "report_type": "agent_case_suite",
        "outcome": outcome,
        "case_count": len(results),
        "passed_count": sum(item.get("outcome") == "pass" for item in results),
        "failed_count": sum(item.get("outcome") == "fail" for item in results),
        "inconclusive_count": sum(item.get("outcome") == "inconclusive" for item in results),
        "error_count": sum(item.get("outcome") == "error" for item in results),
        "counts": {
            "pass": sum(item.get("outcome") == "pass" for item in results),
            "fail": sum(item.get("outcome") == "fail" for item in results),
            "inconclusive": sum(item.get("outcome") == "inconclusive" for item in results),
            "error": sum(item.get("outcome") == "error" for item in results),
        },
        "runs": results,
        "case_runs": results,
        "exit_code": exit_code,
    }
    if out_path is None:
        return suite
    output = _output_file(root_path, out_path)
    if output == manifest_file:
        raise CaseValidationError("suite report must not replace its manifest")
    if output.exists():
        raise CaseValidationError(f"refusing to overwrite existing suite report: {output}")
    atomic_write_json(output, suite)
    return suite, exit_code


def render_case_run_markdown(run: Mapping[str, Any], report: Mapping[str, Any] | None = None) -> str:
    report = report or {}
    outcome = str(run.get("outcome", "error")).upper()
    lines = [
        "# Agent Regression Case Run",
        "",
        f"**Outcome:** `{outcome}`",
        "",
        f"- Case: `{run.get('case_id', 'unknown')}` (revision `{run.get('case_revision', 'unknown')}`)",
        f"- Candidate: `{run.get('candidate_ref', {}).get('path', 'unknown')}`",
        f"- Agent revision: `{run.get('agent_revision', 'unknown')}`",
        f"- Mode: `{run.get('execution_mode', 'evidence_compare')}`",
        "",
    ]
    if report.get("evidence_gaps"):
        lines.extend(["## Evidence gaps", ""])
        lines.extend(f"- `{item.get('path')}`: {item.get('reason')}" for item in report["evidence_gaps"])
    if report.get("differences"):
        lines.extend(["## Differences", ""])
        for item in report["differences"]:
            status = "allowed" if item.get("allowed") else "blocking"
            lines.append(f"- {status}: `{item.get('category')}` at `{item.get('path')}` — {item.get('message', '')}")
    if run.get("error"):
        lines.extend(["## Error", "", str(run["error"]), ""])
    return "\n".join(lines).rstrip() + "\n"
