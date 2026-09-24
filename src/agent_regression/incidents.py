"""Incident records and safe, redacted evidence import for case lifecycle workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import uuid
from typing import Any, Mapping

from .model import AgentTrace
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


INCIDENT_SCHEMA_VERSION = "0.1"
INCIDENT_SOURCES = {"injected", "historical_bug", "user_feedback", "ci_failure"}
INCIDENT_STATUSES = {"open", "triaged", "resolved"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class IncidentValidationError(ValueError):
    """Raised when an incident document or its evidence is invalid."""


def canonical_sha256(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise IncidentValidationError("evidence path must be a non-empty POSIX relative path")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or any(
        part in {"", ".", ".."} for part in value.split("/")
    ):
        raise IncidentValidationError(f"evidence path must stay inside the bundle: {value!r}")
    return posix


def resolve_reference(root: str | Path, reference: Mapping[str, Any], *, verify_hash: bool = True) -> Path:
    if not isinstance(reference, Mapping):
        raise IncidentValidationError("evidence reference must be an object")
    relative = _validate_relative_path(reference.get("path"))
    root_path = Path(root).expanduser().resolve()
    resolved = (root_path / Path(*relative.parts)).resolve(strict=True)
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise IncidentValidationError(f"evidence path escapes bundle root: {relative}") from exc
    if not resolved.is_file():
        raise IncidentValidationError(f"evidence is not a file: {relative}")
    expected = reference.get("sha256")
    if not isinstance(expected, str) or not _SHA256_RE.fullmatch(expected):
        raise IncidentValidationError(f"evidence reference has an invalid SHA-256: {relative}")
    if verify_hash and sha256_file(resolved) != expected:
        raise IncidentValidationError(f"evidence SHA-256 mismatch: {relative}")
    return resolved


def make_reference(root: str | Path, path: str | Path, *, role: str) -> dict[str, str]:
    root_path = Path(root).expanduser().resolve()
    relative = _validate_relative_path(str(path))
    resolved = safe_input_path(root_path, relative.as_posix())
    if not resolved.is_file():
        raise IncidentValidationError(f"evidence is not a file: {path}")
    try:
        relative = resolved.relative_to(root_path).as_posix()
    except ValueError as exc:
        raise IncidentValidationError(f"evidence must be inside bundle root: {path}") from exc
    return {"role": role, "path": relative, "sha256": sha256_file(resolved)}


def safe_output_path(root: str | Path, value: str | Path) -> Path:
    raw = str(value)
    relative = _validate_relative_path(raw)
    root_path = Path(root).expanduser().resolve()
    destination = root_path.joinpath(*relative.parts)
    # Check every existing parent before mkdir, so a symlink cannot create
    # directories outside the bundle as a side effect of validation.
    cursor = root_path
    for part in relative.parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink() or (cursor.exists() and not cursor.is_dir()):
            raise IncidentValidationError(f"unsafe output parent: {value}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    parent = destination.parent.resolve(strict=True)
    try:
        parent.relative_to(root_path)
    except ValueError as exc:
        raise IncidentValidationError(f"output path escapes bundle root: {value}") from exc
    if destination.is_symlink():
        raise IncidentValidationError(f"output symlink is not allowed: {value}")
    return destination


def safe_input_path(root: str | Path, value: str | Path) -> Path:
    relative = _validate_relative_path(str(value))
    root_path = Path(root).expanduser().resolve()
    resolved = root_path.joinpath(*relative.parts).resolve(strict=True)
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise IncidentValidationError(f"input path escapes bundle root: {value}") from exc
    if not resolved.is_file():
        raise IncidentValidationError(f"input is not a file: {value}")
    return resolved


def atomic_write_json(path: Path, value: Mapping[str, Any], *, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise IncidentValidationError(f"refusing to overwrite existing file: {path}")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if overwrite:
            temporary.replace(path)
        else:
            # link() is atomic and fails if another process created the destination meanwhile.
            os.link(temporary, path)
            temporary.unlink()
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class Incident:
    schema_version: str
    incident_id: str
    title: str
    source_kind: str
    summary: str
    evidence_refs: list[dict[str, str]]
    reported_at: str
    status: str = "open"
    case_refs: list[str] = field(default_factory=list)
    resolution: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Incident":
        if not isinstance(value, Mapping):
            raise IncidentValidationError("incident must be an object")
        allowed = {
            "schema_version", "incident_id", "title", "source_kind", "summary",
            "evidence_refs", "reported_at", "status", "case_refs", "resolution",
        }
        unknown = set(value) - allowed
        if unknown:
            raise IncidentValidationError("unsupported incident fields: " + ", ".join(sorted(unknown)))
        incident = cls(
            schema_version=value.get("schema_version", ""),
            incident_id=value.get("incident_id", ""),
            title=value.get("title", ""),
            source_kind=value.get("source_kind", ""),
            summary=value.get("summary", ""),
            evidence_refs=[dict(item) for item in value.get("evidence_refs", [])],
            reported_at=value.get("reported_at", ""),
            status=value.get("status", "open"),
            case_refs=list(value.get("case_refs", [])),
            resolution=dict(value["resolution"]) if isinstance(value.get("resolution"), Mapping) else value.get("resolution"),
        )
        incident.validate()
        return incident

    def validate(self) -> None:
        if self.schema_version != INCIDENT_SCHEMA_VERSION:
            raise IncidentValidationError(f"unsupported incident schema_version {self.schema_version!r}")
        for name in ("incident_id", "title", "summary", "reported_at"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise IncidentValidationError(f"incident.{name} must be a non-empty string")
        if not isinstance(self.source_kind, str) or self.source_kind not in INCIDENT_SOURCES:
            raise IncidentValidationError("incident.source_kind must be one of: " + ", ".join(sorted(INCIDENT_SOURCES)))
        if not isinstance(self.status, str) or self.status not in INCIDENT_STATUSES:
            raise IncidentValidationError("incident.status must be open, triaged, or resolved")
        if not self.evidence_refs or not all(isinstance(ref, dict) for ref in self.evidence_refs):
            raise IncidentValidationError("incident.evidence_refs must contain evidence objects")
        for ref in self.evidence_refs:
            if not isinstance(ref.get("role"), str) or not ref["role"].strip():
                raise IncidentValidationError("incident evidence role must be a non-empty string")
            _validate_relative_path(ref.get("path"))
            if not isinstance(ref.get("sha256"), str) or not _SHA256_RE.fullmatch(ref["sha256"]):
                raise IncidentValidationError("incident evidence sha256 must be a SHA-256 hex digest")
        if not isinstance(self.case_refs, list) or not all(isinstance(item, str) and item for item in self.case_refs):
            raise IncidentValidationError("incident.case_refs must be an array of case IDs")
        if self.status == "resolved" and not isinstance(self.resolution, dict):
            raise IncidentValidationError("resolved incidents require a resolution object")
        # Legacy declarations remain readable. Strict closure is checked by
        # validate_incident/validate_resolution against a separate record.

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_incident(path: str | Path) -> Incident:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IncidentValidationError(f"cannot read incident {path}: {exc}") from exc
    return Incident.from_dict(raw)


def import_incident(
    *, trace_path: str | Path, report_path: str | Path, out_path: str | Path,
    root: str | Path, source_kind: str = "ci_failure", title: str | None = None,
    summary: str | None = None, redaction_policy: RedactionPolicy | None = None,
) -> Incident:
    """Import compare evidence into a self-contained, redacted incident bundle."""
    if source_kind not in INCIDENT_SOURCES:
        raise IncidentValidationError("unsupported incident source_kind")
    root_path = Path(root).expanduser().resolve()
    try:
        trace_source = safe_input_path(root_path, trace_path)
        report_source = safe_input_path(root_path, report_path)
        trace_raw = json.loads(trace_source.read_text(encoding="utf-8"))
        report_raw = json.loads(report_source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IncidentValidationError(f"cannot read incident evidence: {exc}") from exc
    if not isinstance(trace_raw, dict) or not isinstance(report_raw, dict):
        raise IncidentValidationError("trace and compare report must be JSON objects")
    policy = redaction_policy or DEFAULT_REDACTION_POLICY
    trace_data = policy.redact(trace_raw)
    report_data = policy.redact(report_raw)
    trace = AgentTrace.from_dict(trace_data)
    if report_data.get("report_type") != "agent_compare":
        raise IncidentValidationError("report must be an agent_compare report")
    if report_data.get("candidate_run_id") != trace.run_id:
        raise IncidentValidationError("compare report candidate_run_id does not match imported Trace run_id")
    if not isinstance(report_data.get("passed"), bool):
        raise IncidentValidationError("compare report must contain a boolean passed field")
    if report_data["passed"]:
        raise IncidentValidationError("incident import requires a failed comparison report")

    incident_id = "inc-" + uuid.uuid4().hex[:12]
    out = safe_output_path(root_path, out_path)
    trace_ref_path = Path("evidence/incidents") / incident_id / "candidate.trace.json"
    report_ref_path = Path("evidence/incidents") / incident_id / "compare.report.json"
    trace_out = safe_output_path(root_path, trace_ref_path)
    report_out = safe_output_path(root_path, report_ref_path)
    if out.exists():
        raise IncidentValidationError(f"refusing to overwrite existing file: {out}")
    atomic_write_json(trace_out, trace_data)
    atomic_write_json(report_out, report_data)
    refs = [
        {"role": "candidate_trace", "path": trace_ref_path.as_posix(), "sha256": sha256_file(trace_out)},
        {"role": "compare_report", "path": report_ref_path.as_posix(), "sha256": sha256_file(report_out)},
    ]
    detail = summary or (
        f"Imported {source_kind} evidence for candidate run {trace.run_id}; "
        f"comparison passed={str(report_data['passed']).lower()} with "
        f"{report_data.get('blocking_difference_count', 0)} blocking difference(s)."
    )
    incident = Incident(
        schema_version=INCIDENT_SCHEMA_VERSION,
        incident_id=incident_id,
        title=policy.redact(title or f"Regression evidence for run {trace.run_id}"),
        source_kind=source_kind,
        summary=policy.redact(detail),
        evidence_refs=refs,
        reported_at=datetime.now(timezone.utc).isoformat(),
    )
    incident.validate()
    atomic_write_json(out, incident.to_dict())
    return incident
