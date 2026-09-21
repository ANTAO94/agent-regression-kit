"""Release-readiness audits for the maturity plan.

The readiness manifest is deliberately evidence-first.  It verifies the
bytes referenced by a report, checks the final-v4 quantitative gates, and
keeps external requirements such as a real first-user study explicit.  A
pending external item is never silently converted into a passing maturity
claim.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


READINESS_SCHEMA_VERSION = "0.1"
FINAL_PROFILE = "final-v4"
FINAL_THRESHOLDS = {
    "min_evaluated_samples": 300,
    "min_failure_samples": 50,
    "min_failure_recall": 0.99,
    "max_false_alarm_rate": 0.05,
    "min_small_trace_count": 10_000,
    "max_small_elapsed_seconds": 60.0,
    "max_peak_rss_bytes": 512 * 1024 * 1024,
}
_HASH_LENGTH = 64
_CHECK_KINDS = {"benchmark", "performance", "evidence", "external"}
_STATUSES = {"passed", "failed", "pending"}


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path, label: str) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc


def _canonical_digest(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(rendered)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _sha256_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != _HASH_LENGTH:
        raise ValueError(f"{label} must be a 64-character SHA-256 hex string")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be a 64-character SHA-256 hex string") from exc
    return value.lower()


def _resolve_relative(base: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError(f"{label} must be relative to the readiness manifest")
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes the readiness manifest directory") from exc
    return resolved


def _verify_file_descriptor(
    base: Path,
    descriptor: Any,
    label: str,
) -> Dict[str, str]:
    value = _object(descriptor, label)
    relative_path = value.get("path")
    expected = _sha256_value(value.get("sha256"), f"{label}.sha256")
    path = _resolve_relative(base, relative_path, f"{label}.path")
    observed = _sha256_file(path, label)
    if observed != expected:
        raise ValueError(
            f"{label} SHA-256 mismatch: expected {expected}, observed {observed}"
        )
    return {"path": str(relative_path), "sha256": observed}


def _thresholds(raw: Any) -> Dict[str, float | int]:
    value = {} if raw is None else dict(_object(raw, "readiness thresholds"))
    result: Dict[str, float | int] = dict(FINAL_THRESHOLDS)
    for key, expected in value.items():
        if key not in FINAL_THRESHOLDS:
            raise ValueError(f"unsupported readiness threshold: {key}")
        if not isinstance(expected, (int, float)) or isinstance(expected, bool):
            raise ValueError(f"readiness threshold {key} must be numeric")
        default = FINAL_THRESHOLDS[key]
        # The final-v4 profile may be made stricter, never weaker.  This keeps
        # a locally edited manifest from producing a misleading READY result.
        if key.startswith("min_") and expected < default:
            raise ValueError(f"readiness threshold {key} cannot be weaker than {default}")
        if key.startswith("max_") and expected > default:
            raise ValueError(f"readiness threshold {key} cannot be weaker than {default}")
        result[key] = expected
    return result


def _status_result(
    check: Mapping[str, Any],
    *,
    status: str,
    reasons: Iterable[str] = (),
    observed: Mapping[str, Any] | None = None,
    evidence: Iterable[Mapping[str, str]] = (),
) -> Dict[str, Any]:
    check_id = check.get("id")
    kind = check.get("kind")
    required = bool(check.get("required", True))
    return {
        "id": check_id,
        "kind": kind,
        "required": required,
        "status": status,
        "verified": status == "passed",
        "reasons": list(reasons),
        "observed": dict(observed or {}),
        "evidence": [dict(item) for item in evidence],
    }


def _evaluate_benchmark(
    base: Path,
    check: Mapping[str, Any],
    thresholds: Mapping[str, float | int],
) -> Dict[str, Any]:
    evidence = _verify_file_descriptor(base, check.get("report"), f"check {check['id']} report")
    report = _object(_read_json(base / evidence["path"], f"check {check['id']} report"), "benchmark report")
    if report.get("report_type") != "benchmark_score":
        raise ValueError(f"check {check['id']} report must be a benchmark_score report")
    scope = _object(report.get("scope"), f"check {check['id']} report.scope")
    matrix = _object(report.get("confusion_matrix"), f"check {check['id']} report.confusion_matrix")
    metrics = _object(report.get("metrics"), f"check {check['id']} report.metrics")
    evaluated = int(scope.get("evaluated_samples", 0))
    failures = int(matrix.get("true_block", 0)) + int(matrix.get("missed_failure", 0))
    recall = metrics.get("failure_recall")
    false_alarm = metrics.get("false_alarm_rate")
    observed = {
        "evaluated_samples": evaluated,
        "failure_samples": failures,
        "failure_recall": recall,
        "false_alarm_rate": false_alarm,
        "unsupported_samples": int(scope.get("unsupported", 0)),
    }
    reasons: list[str] = []
    if evaluated < int(thresholds["min_evaluated_samples"]):
        reasons.append(
            f"evaluated samples {evaluated} < required {int(thresholds['min_evaluated_samples'])}"
        )
    if failures < int(thresholds["min_failure_samples"]):
        reasons.append(
            f"failure samples {failures} < required {int(thresholds['min_failure_samples'])}"
        )
    if recall is None or float(recall) < float(thresholds["min_failure_recall"]):
        reasons.append(
            f"failure recall {recall!r} < required {float(thresholds['min_failure_recall'])}"
        )
    if false_alarm is None or float(false_alarm) > float(thresholds["max_false_alarm_rate"]):
        reasons.append(
            f"false-alarm rate {false_alarm!r} > allowed {float(thresholds['max_false_alarm_rate'])}"
        )
    if observed["unsupported_samples"]:
        reasons.append("unsupported samples must be counted separately before claiming readiness")
    return _status_result(
        check,
        status="passed" if not reasons else "failed",
        reasons=reasons,
        observed=observed,
        evidence=[evidence],
    )


def _evaluate_performance(
    base: Path,
    check: Mapping[str, Any],
    thresholds: Mapping[str, float | int],
) -> Dict[str, Any]:
    evidence = _verify_file_descriptor(base, check.get("report"), f"check {check['id']} report")
    report = _object(_read_json(base / evidence["path"], f"check {check['id']} report"), "performance report")
    if report.get("report_type") != "agent_performance":
        raise ValueError(f"check {check['id']} report must be an agent_performance report")
    workloads = _array(report.get("workloads"), f"check {check['id']} report.workloads")
    small = next(
        (
            _object(item, f"check {check['id']} report.workloads")
            for item in workloads
            if isinstance(item, Mapping) and item.get("name") == "small"
        ),
        None,
    )
    if small is None:
        raise ValueError(f"check {check['id']} performance report has no small workload")
    environment = _object(report.get("environment"), f"check {check['id']} report.environment")
    trace_count = int(small.get("trace_count", 0))
    elapsed = float(small.get("elapsed_seconds", -1))
    peak_rss = environment.get("peak_rss_bytes")
    observed = {
        "small_trace_count": trace_count,
        "small_elapsed_seconds": elapsed,
        "peak_rss_bytes": peak_rss,
    }
    reasons: list[str] = []
    if trace_count < int(thresholds["min_small_trace_count"]):
        reasons.append(
            f"small workload count {trace_count} < required {int(thresholds['min_small_trace_count'])}"
        )
    if elapsed < 0 or elapsed > float(thresholds["max_small_elapsed_seconds"]):
        reasons.append(
            f"small workload time {elapsed} > allowed {float(thresholds['max_small_elapsed_seconds'])} seconds"
        )
    if not isinstance(peak_rss, (int, float)) or isinstance(peak_rss, bool):
        reasons.append("performance report does not contain a measurable peak RSS")
    elif peak_rss >= int(thresholds["max_peak_rss_bytes"]):
        reasons.append(
            f"peak RSS {int(peak_rss)} must be below {int(thresholds['max_peak_rss_bytes'])} bytes"
        )
    return _status_result(
        check,
        status="passed" if not reasons else "failed",
        reasons=reasons,
        observed=observed,
        evidence=[evidence],
    )


def _evaluate_evidence(base: Path, check: Mapping[str, Any]) -> Dict[str, Any]:
    descriptors = _array(check.get("files"), f"check {check['id']} files")
    verified = [
        _verify_file_descriptor(base, descriptor, f"check {check['id']} files[{index}]")
        for index, descriptor in enumerate(descriptors)
    ]
    if not verified:
        raise ValueError(f"check {check['id']} files must not be empty")
    return _status_result(check, status="passed", evidence=verified)


def _evaluate_external(base: Path, check: Mapping[str, Any]) -> Dict[str, Any]:
    status = check.get("status")
    if status not in _STATUSES:
        raise ValueError(
            f"check {check['id']} external status must be one of: {', '.join(sorted(_STATUSES))}"
        )
    descriptors = check.get("evidence", [])
    verified = [
        _verify_file_descriptor(base, descriptor, f"check {check['id']} evidence[{index}]")
        for index, descriptor in enumerate(_array(descriptors, f"check {check['id']} evidence"))
    ]
    reasons = []
    if isinstance(check.get("reason"), str) and check["reason"].strip():
        reasons.append(check["reason"].strip())
    if status == "passed" and not verified:
        raise ValueError(f"check {check['id']} passed external checks require evidence")
    return _status_result(check, status=status, reasons=reasons, evidence=verified)


def evaluate_readiness(manifest_path: str | Path) -> Dict[str, Any]:
    """Evaluate a final-v4 readiness manifest without embedding evidence contents."""
    manifest_file = Path(manifest_path).expanduser().resolve()
    raw = _object(_read_json(manifest_file, "readiness manifest"), "readiness manifest")
    if raw.get("schema_version") != READINESS_SCHEMA_VERSION:
        raise ValueError(
            f"readiness manifest schema_version must be {READINESS_SCHEMA_VERSION!r}"
        )
    profile = raw.get("profile", FINAL_PROFILE)
    if profile != FINAL_PROFILE:
        raise ValueError(f"readiness profile must be {FINAL_PROFILE!r}")
    thresholds = _thresholds(raw.get("thresholds"))
    raw_checks = _array(raw.get("checks"), "readiness checks")
    if not raw_checks:
        raise ValueError("readiness checks must not be empty")

    checks: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_check in enumerate(raw_checks):
        check = _object(raw_check, f"readiness checks[{index}]")
        check_id = check.get("id")
        kind = check.get("kind")
        if not isinstance(check_id, str) or not check_id.strip():
            raise ValueError(f"readiness checks[{index}].id must be a non-empty string")
        if check_id in seen:
            raise ValueError(f"duplicate readiness check id: {check_id}")
        seen.add(check_id)
        if kind not in _CHECK_KINDS:
            raise ValueError(f"readiness check {check_id} has unsupported kind: {kind!r}")
        if kind == "benchmark":
            result = _evaluate_benchmark(manifest_file.parent, check, thresholds)
        elif kind == "performance":
            result = _evaluate_performance(manifest_file.parent, check, thresholds)
        elif kind == "evidence":
            result = _evaluate_evidence(manifest_file.parent, check)
        else:
            result = _evaluate_external(manifest_file.parent, check)
        checks.append(result)

    summary = {
        "required": sum(1 for check in checks if check["required"]),
        "passed": sum(1 for check in checks if check["status"] == "passed"),
        "failed": sum(1 for check in checks if check["status"] == "failed"),
        "pending": sum(1 for check in checks if check["status"] == "pending"),
        "optional_not_passed": sum(
            1 for check in checks if not check["required"] and check["status"] != "passed"
        ),
    }
    required_ready = all(
        check["status"] == "passed" for check in checks if check["required"]
    )
    result: Dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "report_type": "readiness_audit",
        "ok": True,
        "ready": required_ready,
        "profile": profile,
        "target_version": raw.get("target_version"),
        "manifest_sha256": _sha256_file(manifest_file, "readiness manifest"),
        "thresholds": thresholds,
        "summary": summary,
        "checks": checks,
        "decision_boundary": (
            "readiness verifies declared evidence bytes and final-v4 thresholds; "
            "external checks remain pending until an independently recorded artifact exists"
        ),
    }
    result["report_digest"] = _canonical_digest(result)
    return result


__all__ = [
    "FINAL_PROFILE",
    "FINAL_THRESHOLDS",
    "READINESS_SCHEMA_VERSION",
    "evaluate_readiness",
]
