"""Bind one in-process Agent invocation to a redacted, immutable Trace and record.

The callback and its returned Trace are trusted inputs.  A hash detects later
changes to the published bytes; neither a local recording nor CI metadata
authenticates the caller, runner, code revision, or actual Agent behavior.
"""

from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping
import uuid

from .incidents import IncidentValidationError, canonical_sha256, resolve_reference, safe_input_path, safe_output_path
from .model import AgentTrace, TraceValidationError
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


EXECUTION_SCHEMA_VERSION = "0.1"
RECORDER_VERSION = "0.1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CI_PRODUCER_FIELDS = ("runner", "repository", "commit", "job_id", "run_id")
_CURRENT_EXECUTION_ID: ContextVar[str | None] = ContextVar("execution_record_id", default=None)


class ExecutionValidationError(ValueError):
    """An execution record or its linked evidence is invalid."""


def current_execution_id() -> str | None:
    """Return the ID allocated before the active callback was invoked, if any."""
    return _CURRENT_EXECUTION_ID.get()


def _timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ExecutionValidationError(f"{label} must be an ISO-8601 timestamp with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionValidationError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionValidationError(f"{label} must include a timezone")
    return parsed


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionValidationError(f"{label} must be a JSON object")
    return value


def _digest(value: Any, label: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ExecutionValidationError(f"{label} must be a SHA-256 hex digest")


def _nonempty(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionValidationError(f"{label} must be a non-empty string")


def _fingerprint(value: Any, policy: RedactionPolicy) -> str | None:
    if value is None:
        return None
    safe = policy.redact(deepcopy(value))
    # This also rejects values that cannot be preserved as portable JSON.
    return canonical_sha256(safe)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _stage(path: Path, data: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


def _publish_pair(trace_path: Path, trace_bytes: bytes, record_path: Path, record_bytes: bytes) -> None:
    trace_stage = record_stage = None
    trace_published = False
    try:
        trace_stage = _stage(trace_path, trace_bytes)
        record_stage = _stage(record_path, record_bytes)
        # Exclusive links reject a competing writer without replacing either file.
        os.link(trace_stage, trace_path)
        trace_published = True
        os.link(record_stage, record_path)
    except BaseException:
        if trace_published:
            trace_path.unlink()
        raise
    finally:
        if trace_stage is not None:
            trace_stage.unlink(missing_ok=True)
        if record_stage is not None:
            record_stage.unlink(missing_ok=True)


def _validate_shape(record: dict[str, Any]) -> None:
    required = {
        "schema_version", "execution_id", "trace_ref", "trace_run_id", "agent_revision",
        "dirty", "input_sha256", "environment_sha256", "recorder_version",
        "started_at", "finished_at", "producer", "provenance_level",
        "recording_mode", "callback_binding", "trust_boundary",
    }
    if set(record) != required:
        raise ExecutionValidationError(f"execution record fields differ from schema: {sorted(set(record) ^ required)}")
    if record["schema_version"] != EXECUTION_SCHEMA_VERSION:
        raise ExecutionValidationError("unsupported execution record schema_version")
    for key in ("execution_id", "trace_run_id", "agent_revision", "recorder_version"):
        _nonempty(record[key], key)
    try:
        uuid.UUID(record["execution_id"])
    except (ValueError, AttributeError) as exc:
        raise ExecutionValidationError("execution_id must be a UUID") from exc
    if record["dirty"] is not None and type(record["dirty"]) is not bool:
        raise ExecutionValidationError("dirty must be boolean or null")
    _digest(record["input_sha256"], "input_sha256", optional=True)
    _digest(record["environment_sha256"], "environment_sha256", optional=True)
    started = _timestamp(record["started_at"], "started_at")
    finished = _timestamp(record["finished_at"], "finished_at")
    if finished < started:
        raise ExecutionValidationError("finished_at precedes started_at")
    ref = _object(record["trace_ref"], "trace_ref")
    if set(ref) != {"path", "sha256"}:
        raise ExecutionValidationError("trace_ref requires path and sha256")
    _nonempty(ref["path"], "trace_ref.path")
    _digest(ref["sha256"], "trace_ref.sha256")
    producer = _object(record["producer"], "producer")
    if record["provenance_level"] not in {"declared", "ci_correlated"}:
        raise ExecutionValidationError("invalid provenance_level")
    has_ci_metadata = any(key in producer for key in _CI_PRODUCER_FIELDS)
    if has_ci_metadata != (record["provenance_level"] == "ci_correlated"):
        raise ExecutionValidationError("producer CI metadata and provenance_level disagree")
    if record["provenance_level"] == "ci_correlated":
        for key in _CI_PRODUCER_FIELDS:
            _nonempty(producer.get(key), f"producer.{key}")
        if producer["commit"] != record["agent_revision"]:
            raise ExecutionValidationError("producer.commit differs from agent_revision")
    if record["recording_mode"] not in {"recorded", "imported"}:
        raise ExecutionValidationError("invalid recording_mode")
    if record["recording_mode"] == "recorded":
        if record["callback_binding"] != "in_process_callback":
            raise ExecutionValidationError("recorded mode requires in_process_callback binding")
    elif record["callback_binding"] != "unverified_import":
        raise ExecutionValidationError("imported mode requires unverified_import binding")
    if record["trust_boundary"] != "caller_supplied_callback_and_trace_not_authenticated":
        raise ExecutionValidationError("unsupported trust_boundary declaration")


def record_execution(
    *, root: str | Path, trace_path: str | Path, out_path: str | Path,
    invoke: Callable[[], AgentTrace], agent_revision: str = "unknown",
    dirty: bool | None = None, input_data: Any = None, environment: Any = None,
    producer: Mapping[str, Any] | None = None, redaction_policy: RedactionPolicy | None = None,
) -> dict[str, Any]:
    """Call invoke once and publish its Trace and record together, without overwrite.

    The wrapper allocates an ID and sets :func:`current_execution_id` before
    invoking the callback. The callback must return a Trace already carrying
    this ID in metadata.execution_id; an old, unbound Trace is rejected. The
    caller controls the callback and Trace, so this is not authentication and
    cannot prevent a malicious callback from fabricating fresh-looking evidence.
    """
    if not callable(invoke):
        raise ExecutionValidationError("invoke must be a zero-argument callback")
    _nonempty(agent_revision, "agent_revision")
    if dirty is not None and type(dirty) is not bool:
        raise ExecutionValidationError("dirty must be boolean or null")
    if producer is not None and not isinstance(producer, Mapping):
        raise ExecutionValidationError("producer must be an object")
    policy = redaction_policy or DEFAULT_REDACTION_POLICY
    try:
        trace_file = safe_output_path(root, trace_path)
        record_file = safe_output_path(root, out_path)
    except (IncidentValidationError, OSError) as exc:
        raise ExecutionValidationError(f"invalid execution output path: {exc}") from exc
    if trace_file == record_file:
        raise ExecutionValidationError("Trace and record paths must differ")
    if trace_file.exists() or record_file.exists():
        raise ExecutionValidationError("refusing to overwrite existing execution output")
    execution_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    token = _CURRENT_EXECUTION_ID.set(execution_id)
    try:
        trace = invoke()
    finally:
        _CURRENT_EXECUTION_ID.reset(token)
    finished_at = datetime.now(timezone.utc).isoformat()
    if not isinstance(trace, AgentTrace):
        raise ExecutionValidationError("invoke must return AgentTrace")
    try:
        trace.validate()
        raw = deepcopy(trace.to_dict())
        source_commit = raw["agent"].get("source_commit")
        if source_commit is not None and source_commit != agent_revision:
            raise ExecutionValidationError("Trace agent.source_commit differs from agent_revision")
        metadata = _object(raw["metadata"], "Trace metadata")
        if metadata.get("execution_id") != execution_id:
            raise ExecutionValidationError("callback Trace must already carry current metadata.execution_id")
        if "agent_revision" in metadata and metadata["agent_revision"] != agent_revision:
            raise ExecutionValidationError("callback Trace has a conflicting metadata.agent_revision")
        input_hash = _fingerprint(input_data, policy)
        environment_hash = _fingerprint(environment, policy)
        for key, expected in (("input_sha256", input_hash), ("environment_sha256", environment_hash)):
            if key in metadata and metadata[key] != expected:
                raise ExecutionValidationError(f"callback Trace has a conflicting metadata.{key}")
        metadata.update({"agent_revision": agent_revision, "input_sha256": input_hash,
                         "environment_sha256": environment_hash})
        safe_trace = policy.redact(raw)
        AgentTrace.from_dict(safe_trace)
        if (safe_trace["run_id"] != trace.run_id or
                safe_trace["metadata"]["execution_id"] != execution_id or
                safe_trace["metadata"]["agent_revision"] != agent_revision):
            raise ExecutionValidationError("redaction changed an execution identity field")
        safe_producer = policy.redact(dict(producer or {}))
        provenance = "ci_correlated" if any(key in safe_producer for key in _CI_PRODUCER_FIELDS) else "declared"
        trace_bytes = _json_bytes(safe_trace)
        record = {
            "schema_version": EXECUTION_SCHEMA_VERSION,
            "execution_id": execution_id,
            "trace_ref": {"path": trace_file.relative_to(Path(root).expanduser().resolve()).as_posix(),
                          "sha256": hashlib.sha256(trace_bytes).hexdigest()},
            "trace_run_id": trace.run_id,
            "agent_revision": agent_revision,
            "dirty": dirty,
            "input_sha256": input_hash,
            "environment_sha256": environment_hash,
            "recorder_version": RECORDER_VERSION,
            "started_at": started_at,
            "finished_at": finished_at,
            "producer": safe_producer,
            "provenance_level": provenance,
            "recording_mode": "recorded",
            "callback_binding": "in_process_callback",
            "trust_boundary": "caller_supplied_callback_and_trace_not_authenticated",
        }
        _validate_shape(record)
        record_bytes = _json_bytes(record)
    except (TraceValidationError, TypeError, ValueError, OverflowError) as exc:
        if isinstance(exc, ExecutionValidationError):
            raise
        raise ExecutionValidationError(f"invalid callback evidence: {exc}") from exc
    try:
        _publish_pair(trace_file, trace_bytes, record_file, record_bytes)
    except OSError as exc:
        raise ExecutionValidationError(f"cannot publish execution outputs: {exc}") from exc
    return record


def validate_execution_record(
    *, root: str | Path, record_path: str | Path,
    candidate_path: str | Path | None = None, require_recorded: bool = False,
) -> dict[str, Any]:
    """Validate a record and its Trace; strict mode requires recorded provenance.

    recorded means produced through a local callback. It is not authentication.
    Imported records remain useful for comparison when require_recorded=False.
    """
    try:
        record_file = safe_input_path(root, record_path)
        record = _object(json.loads(record_file.read_text(encoding="utf-8")), "execution record")
        _validate_shape(record)
        trace_file = resolve_reference(root, record["trace_ref"])
        if candidate_path is not None and safe_input_path(root, candidate_path) != trace_file:
            raise ExecutionValidationError("candidate_path differs from trace_ref.path")
        trace = AgentTrace.from_dict(json.loads(trace_file.read_text(encoding="utf-8")))
        if trace.run_id != record["trace_run_id"]:
            raise ExecutionValidationError("trace_run_id differs from Trace.run_id")
        source_commit = trace.agent.get("source_commit")
        if source_commit is not None and source_commit != record["agent_revision"]:
            raise ExecutionValidationError("Trace agent.source_commit differs from agent_revision")
        for key, expected in (
            ("execution_id", record["execution_id"]),
            ("agent_revision", record["agent_revision"]),
            ("input_sha256", record["input_sha256"]),
            ("environment_sha256", record["environment_sha256"]),
        ):
            if trace.metadata.get(key) != expected or key not in trace.metadata:
                raise ExecutionValidationError(f"Trace metadata.{key} differs from execution record")
        if require_recorded and record["recording_mode"] != "recorded":
            raise ExecutionValidationError("strict validation requires a newly recorded callback execution")
        return record
    except (IncidentValidationError, TraceValidationError, OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise ExecutionValidationError(f"invalid execution evidence: {exc}") from exc
