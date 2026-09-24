"""Strict, reproducible incident closure over immutable bundle evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
from typing import Any, Mapping

from .case_runner import CaseRun, compare_case
from .cases import case_definition_sha256, load_case, validate_case
from .incidents import (
    IncidentValidationError, atomic_write_json, canonical_sha256, load_incident, make_reference,
    resolve_reference, safe_input_path, safe_output_path,
)
from .model import AgentTrace
from .redaction import DEFAULT_REDACTION_POLICY


class ResolutionValidationError(ValueError):
    """An incident or closure evidence chain is incomplete or inconsistent."""


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_KINDS = {"injected_recovery", "bug_fix"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ResolutionValidationError(message)


def _read(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ResolutionValidationError(f"cannot read {label}: {path}: {exc}") from exc
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _file(root: str | Path, path: str | Path, label: str) -> Path:
    try:
        return safe_input_path(root, path)
    except (IncidentValidationError, OSError) as exc:
        raise ResolutionValidationError(f"{label}: {exc}") from exc


def _ref(root: str | Path, reference: Any, label: str) -> Path:
    _require(isinstance(reference, dict) and set(reference) == {"path", "sha256"},
             f"{label} must contain path and sha256")
    try:
        return resolve_reference(root, reference)
    except (IncidentValidationError, OSError) as exc:
        raise ResolutionValidationError(f"{label}: {exc}") from exc


def _plain_ref(root: str | Path, path: str | Path) -> dict[str, str]:
    try:
        reference = make_reference(root, path, role="record")
    except (IncidentValidationError, OSError) as exc:
        raise ResolutionValidationError(f"invalid record path {path}: {exc}") from exc
    return {key: reference[key] for key in ("path", "sha256")}


def _trace(path: Path, label: str) -> dict[str, Any]:
    data = _read(path, label)
    try:
        AgentTrace.from_dict(data)
    except ValueError as exc:
        raise ResolutionValidationError(f"{label}: {exc}") from exc
    return data


def validate_incident(*, root: str | Path, incident_path: str | Path) -> dict[str, Any]:
    """Verify imported roles, hashes, Trace and report identity; never trust legacy status."""
    incident_file = _file(root, incident_path, "incident")
    try:
        incident = load_incident(incident_file)
    except (IncidentValidationError, TypeError, ValueError) as exc:
        raise ResolutionValidationError(f"incident: {exc}") from exc
    refs: dict[str, Path] = {}
    for item in incident.evidence_refs:
        role = item.get("role")
        _require(role in {"candidate_trace", "compare_report"}, f"unsupported incident evidence role: {role!r}")
        _require(role not in refs, f"duplicate incident evidence role: {role}")
        refs[role] = _ref(root, {"path": item.get("path"), "sha256": item.get("sha256")}, role)
    _require(set(refs) == {"candidate_trace", "compare_report"},
             "incident requires candidate_trace and compare_report evidence")
    trace = _trace(refs["candidate_trace"], "imported Trace")
    report = _read(refs["compare_report"], "imported report")
    _require(report.get("report_type") == "agent_compare" and report.get("passed") is False,
             "incident compare report must be a failed agent_compare")
    _require(report.get("candidate_run_id") == trace["run_id"],
             "incident compare report candidate_run_id differs from Trace run_id")
    _require(incident.status != "resolved", "legacy resolved declaration needs a validated Resolution record")
    _require(incident.resolution is None, "legacy inline resolution cannot establish closure")
    return {
        "ok": True, "incident_id": incident.incident_id, "source_kind": incident.source_kind,
        "status": incident.status, "trace_run_id": trace["run_id"],
        "trace_ref": next(ref for ref in incident.evidence_refs if ref["role"] == "candidate_trace"),
        "report_ref": next(ref for ref in incident.evidence_refs if ref["role"] == "compare_report"),
    }


def _checked_run(*, root: str | Path, run_ref: Mapping[str, str], case: Any,
                 expected: str) -> tuple[dict[str, Any], dict[str, Any]]:
    run = _read(_ref(root, run_ref, f"{expected} CaseRun"), f"{expected} CaseRun")
    _require(run.get("schema_version") == "0.1" and isinstance(run.get("case_run_id"), str)
             and bool(run["case_run_id"].strip()), f"{expected} CaseRun identity is invalid")
    _require(run.get("case_id") == case.case_id and run.get("case_revision") == case.revision
             and run.get("definition_sha256") == case_definition_sha256(case),
             f"{expected} CaseRun case_id/revision/definition_sha256 differs from approved Case")
    _require(run.get("outcome") == expected, f"{expected} CaseRun outcome must be {expected}")
    candidate_path = _ref(root, run.get("candidate_ref"), f"{expected} candidate_ref")
    candidate = _trace(candidate_path, f"{expected} candidate Trace")
    report_ref = run.get("report_ref")
    _require(isinstance(report_ref, dict) and set(report_ref) == {"role", "path", "sha256"}
             and report_ref["role"] == "compare_report",
             f"{expected} report_ref must have compare_report role, path, and sha256")
    report_path = _ref(root, {"path": report_ref["path"], "sha256": report_ref["sha256"]},
                       f"{expected} report_ref")
    report = _read(report_path, f"{expected} comparison report")
    _require(report.get("report_type") == "agent_case_compare" and report.get("outcome") == expected
             and report.get("candidate_run_id") == candidate["run_id"]
             and report.get("passed") is (expected == "pass"),
             f"{expected} report outcome or candidate_run_id is invalid")
    _require(run.get("report") == report, f"{expected} embedded report differs from report_ref")
    recomputed = compare_case(case, root=root, candidate_path=run["candidate_ref"]["path"])
    _require(isinstance(recomputed, CaseRun) and recomputed.outcome == expected
             and recomputed.compare_report == report,
             f"{expected} report differs from recomputed compare_case result")
    return run, candidate


def _fixed_premise_digest(root: str | Path, reference: Any, label: str) -> str | None:
    if reference is None:
        return None
    path = _ref(root, reference, f"Case {label}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ResolutionValidationError(f"Case {label} must be JSON for execution comparison: {exc}") from exc
    return canonical_sha256(DEFAULT_REDACTION_POLICY.redact(value))


def _check_execution_premises(root: str | Path, case: Any, record: dict[str, Any], label: str) -> None:
    for ref_key, hash_key in (("input_ref", "input_sha256"),
                              ("environment_ref", "environment_sha256")):
        expected = _fixed_premise_digest(root, getattr(case, ref_key), ref_key)
        if expected is not None:
            _require(record.get(hash_key) == expected,
                     f"{label} ExecutionRecord {hash_key} differs from Case {ref_key}")


def _check_chain(*, root: str | Path, incident_ref: Mapping[str, str],
                 case_ref: Mapping[str, str], before_ref: Mapping[str, str],
                 after_ref: Mapping[str, str], kind: str, change_ref: str | None,
                 execution_ref: Mapping[str, str] | None = None) -> dict[str, Any]:
    incident_path = _ref(root, incident_ref, "incident_ref")
    incident_info = validate_incident(root=root, incident_path=incident_ref["path"])
    incident = load_incident(incident_path)
    case = load_case(_ref(root, case_ref, "case_ref"))
    validate_case(case, root, require_approved=True)
    _require(incident.incident_id in case.incident_refs, "approved Case does not reference incident_id")
    _require(kind in _KINDS, "resolution_kind must be injected_recovery or bug_fix")
    _require(change_ref is None or isinstance(change_ref, str), "change_ref must be a string or null")
    _require(kind != "injected_recovery" or incident.source_kind == "injected",
             "injected_recovery requires source_kind=injected")
    _require(kind != "bug_fix" or incident.source_kind == "historical_bug",
             "bug_fix requires source_kind=historical_bug")
    _require(kind != "bug_fix" or isinstance(change_ref, str) and bool(change_ref.strip()),
             "bug_fix requires change_ref")
    before, before_trace = _checked_run(root=root, run_ref=before_ref, case=case, expected="fail")
    after, after_trace = _checked_run(root=root, run_ref=after_ref, case=case, expected="pass")
    imported = _trace(_ref(root, {k: incident_info["trace_ref"][k] for k in ("path", "sha256")},
                           "incident Trace"), "incident Trace")
    _require(before_trace["run_id"] == imported["run_id"] and
             DEFAULT_REDACTION_POLICY.redact(before_trace) == imported,
             "before candidate does not match imported redacted Trace content/run_id")
    _require(before["candidate_ref"]["path"] != after["candidate_ref"]["path"],
             "after candidate must use a different path from before")
    _require(before_trace["run_id"] != after_trace["run_id"],
             "after candidate must have a new run_id")
    linked = after.get("execution_ref")
    _require(isinstance(linked, dict), "after CaseRun requires execution_ref")
    execution_path = _ref(root, linked, "after execution_ref")
    if execution_ref is not None:
        _require(dict(execution_ref) == linked, "resolution after_execution_ref differs from CaseRun execution_ref")
    record = _read(execution_path, "after ExecutionRecord")
    try:
        from .execution_records import validate_execution_record
    except ImportError as exc:
        raise ResolutionValidationError("execution_records validator is unavailable") from exc
    record = validate_execution_record(root=root, record_path=linked["path"],
                                       candidate_path=after["candidate_ref"]["path"],
                                       require_recorded=True)
    _check_execution_premises(root, case, record, "after")
    before_execution = before.get("execution_ref")
    if before_execution is not None:
        _ref(root, before_execution, "before execution_ref")
        before_record = validate_execution_record(
            root=root, record_path=before_execution["path"],
            candidate_path=before["candidate_ref"]["path"], require_recorded=False,
        )
        _check_execution_premises(root, case, before_record, "before")
        _require(before_record["execution_id"] != record["execution_id"],
                 "after execution_id reuses before ExecutionRecord")
        for name in ("input_sha256", "environment_sha256"):
            _require(isinstance(before_record[name], str) and isinstance(record[name], str),
                     f"before/after ExecutionRecord {name} must both be recorded")
            _require(before_record[name] == record[name],
                     f"before/after ExecutionRecord {name} differs; same-condition closure requires matching premises")
        before_finished = datetime.fromisoformat(before_record["finished_at"].replace("Z", "+00:00"))
        after_started = datetime.fromisoformat(record["started_at"].replace("Z", "+00:00"))
        _require(after_started >= before_finished,
                 "after ExecutionRecord started_at precedes before ExecutionRecord finished_at")
    else:
        _require(case.input_ref is not None and case.environment_ref is not None,
                 "before has no ExecutionRecord; Case must fix both input_ref and environment_ref")
    execution_id = record.get("execution_id")
    _require(isinstance(execution_id, str) and bool(execution_id.strip())
             and after_trace.get("metadata", {}).get("execution_id") == execution_id,
             "after Trace metadata.execution_id differs from ExecutionRecord")
    _require(record.get("trace_run_id") == after_trace["run_id"],
             "after ExecutionRecord trace_run_id differs from Trace")
    _require(execution_id != before_trace.get("metadata", {}).get("execution_id"),
             "after execution_id reuses the before execution")
    return {"incident_id": incident.incident_id, "case_id": case.case_id,
            "case_revision": case.revision, "definition_sha256": case_definition_sha256(case),
            "before_run_id": before_trace["run_id"], "after_run_id": after_trace["run_id"],
            "after_execution_id": execution_id, "source_kind": incident.source_kind,
            "before_execution_recorded": before_execution is not None}


def _validated_chain(**kwargs: Any) -> dict[str, Any]:
    try:
        return _check_chain(**kwargs)
    except ResolutionValidationError:
        raise
    except (ValueError, TypeError, OSError) as exc:
        raise ResolutionValidationError(f"invalid closure evidence: {exc}") from exc


def resolve_incident(*, root: str | Path, incident_path: str | Path,
                     case_path: str | Path, before_path: str | Path, after_path: str | Path,
                     kind: str, reviewer: str, reason: str, out_path: str | Path,
                     change_ref: str | None = None) -> dict[str, Any]:
    """Publish one immutable Resolution after checking the complete chain."""
    _require(isinstance(reviewer, str) and bool(reviewer.strip()), "reviewer is required")
    _require(isinstance(reason, str) and bool(reason.strip()), "reason is required")
    refs = [_plain_ref(root, path) for path in (incident_path, case_path, before_path, after_path)]
    after = _read(_ref(root, refs[3], "after CaseRun"), "after CaseRun")
    execution_ref = after.get("execution_ref")
    _require(isinstance(execution_ref, dict), "after CaseRun requires execution_ref")
    details = _validated_chain(root=root, incident_ref=refs[0], case_ref=refs[1],
                           before_ref=refs[2], after_ref=refs[3], kind=kind,
                           change_ref=change_ref, execution_ref=execution_ref)
    resolution = {
        "schema_version": "0.1", "resolution_id": "resolution-" + uuid.uuid4().hex,
        "incident_ref": refs[0], "incident_id": details["incident_id"],
        "case_ref": refs[1], "case_id": details["case_id"],
        "case_revision": details["case_revision"],
        "definition_sha256": details["definition_sha256"],
        "before_run_ref": refs[2], "after_run_ref": refs[3],
        "after_execution_ref": execution_ref, "resolution_kind": kind,
        "reviewer": reviewer.strip(), "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason.strip(), "change_ref": change_ref.strip() if isinstance(change_ref, str) else None,
    }
    try:
        output = safe_output_path(root, out_path)
    except (IncidentValidationError, OSError) as exc:
        raise ResolutionValidationError(f"invalid resolution output: {exc}") from exc
    inputs = {Path(root).expanduser().resolve() / ref["path"] for ref in (*refs, execution_ref)}
    _require(output not in inputs, "resolution output cannot replace evidence")
    try:
        atomic_write_json(output, resolution)
    except (IncidentValidationError, OSError) as exc:
        raise ResolutionValidationError(f"cannot publish Resolution: {exc}") from exc
    return resolution


def validate_resolution(*, root: str | Path, resolution_path: str | Path) -> dict[str, Any]:
    """Recheck all references and recompute both comparison reports."""
    raw = _read(_file(root, resolution_path, "Resolution"), "Resolution")
    fields = {"schema_version", "resolution_id", "incident_ref", "incident_id", "case_ref",
              "case_id", "case_revision", "definition_sha256", "before_run_ref",
              "after_run_ref", "after_execution_ref", "resolution_kind", "reviewer",
              "reviewed_at", "reason", "change_ref"}
    _require(set(raw) == fields and raw.get("schema_version") == "0.1", "invalid Resolution v0.1 fields")
    for name in ("resolution_id", "incident_id", "case_id", "reviewer", "reviewed_at", "reason"):
        _require(isinstance(raw[name], str) and bool(raw[name].strip()), f"Resolution {name} is required")
    reviewed_at = raw["reviewed_at"]
    _require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", reviewed_at)),
             "Resolution reviewed_at must be an ISO date-time with timezone")
    try:
        reviewed_time = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResolutionValidationError("Resolution reviewed_at must be a valid ISO date-time") from exc
    _require(reviewed_time.tzinfo is not None and reviewed_time.utcoffset() is not None,
             "Resolution reviewed_at must include timezone")
    _require(isinstance(raw["case_revision"], int) and not isinstance(raw["case_revision"], bool)
             and raw["case_revision"] > 0, "invalid Resolution case_revision")
    _require(isinstance(raw["definition_sha256"], str) and bool(_DIGEST.fullmatch(raw["definition_sha256"])),
             "invalid Resolution definition_sha256")
    details = _validated_chain(root=root, incident_ref=raw["incident_ref"], case_ref=raw["case_ref"],
                           before_ref=raw["before_run_ref"], after_ref=raw["after_run_ref"],
                           execution_ref=raw["after_execution_ref"],
                           kind=raw["resolution_kind"], change_ref=raw["change_ref"])
    for name in ("incident_id", "case_id", "case_revision", "definition_sha256"):
        _require(raw[name] == details[name], f"Resolution {name} differs from validated evidence")
    return {"ok": True, "status": "resolved", "resolution_id": raw["resolution_id"], **details}


def render_incident_report(*, root: str | Path, incident_path: str | Path,
                           resolution_path: str | Path | None = None) -> str:
    """Render verified evidence; a missing Resolution remains open or triaged."""
    info = validate_incident(root=root, incident_path=incident_path)
    incident = load_incident(_file(root, incident_path, "incident"))
    lines = ["# Incident report", "", f"- Incident: `{info['incident_id']}`",
             f"- Source: `{info['source_kind']}`", f"- Imported run: `{info['trace_run_id']}`"]
    if resolution_path is None:
        lines.append(f"- Status: `{info['status']}`")
    else:
        result = validate_resolution(root=root, resolution_path=resolution_path)
        _require(result["incident_id"] == incident.incident_id,
                 "Resolution belongs to a different incident")
        resolution = _read(_file(root, resolution_path, "Resolution"), "Resolution")
        lines.extend(["- Status: `resolved`", f"- Kind: `{result['source_kind']}` / "
                      f"`{resolution['resolution_kind']}`",
                      f"- Case: `{result['case_id']}` revision `{result['case_revision']}`",
                      f"- Definition SHA-256: `{result['definition_sha256']}`",
                      f"- Before: `{result['before_run_id']}` (fail)",
                      f"- After: `{result['after_run_id']}` (pass)",
                      f"- Execution: `{result['after_execution_id']}`",
                      f"- Reviewer: {resolution['reviewer']}",
                      f"- Reason: {resolution['reason']}"])
        if not result["before_execution_recorded"]:
            lines.append("- Before execution provenance: no ExecutionRecord; input and environment are fixed by Case references, but the old runtime conditions are not independently recorded.")
        if resolution["change_ref"]:
            lines.append(f"- Change: `{resolution['change_ref']}`")
    lines.extend(["", incident.summary, ""])
    return "\n".join(lines)
