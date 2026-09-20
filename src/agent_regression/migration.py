"""Compatibility checks and explicit migration helpers for v4 releases."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .contracts import ContractPolicy
from .model import AgentTrace
from .public_api import (
    LEGACY_PUBLIC_API_VERSIONS,
    PUBLIC_API_VERSION,
    SUPPORTED_CONTRACT_SCHEMA_VERSIONS,
    SUPPORTED_REPORT_SCHEMA_VERSIONS,
    SUPPORTED_SESSION_SCHEMA_VERSIONS,
    SUPPORTED_TRACE_SCHEMA_VERSIONS,
    public_api_manifest,
)
from .session import AgentSession


COMPATIBILITY_REPORT_SCHEMA_VERSION = "0.1"

# Report types emitted by the package. Keeping this allow-list explicit is
# important: a non-empty arbitrary ``report_type`` must not make an unknown
# document look compatible merely because its schema version is familiar.
SUPPORTED_REPORT_TYPES = frozenset(
    {
        "agent_compare",
        "agent_batch",
        "agent_scenario_batch",
        "agent_coverage",
        "agent_stability",
        "agent_session_compare",
        "agent_history",
        "agent_report_index",
        "agent_workspace_manifest",
        "agent_compatibility",
        "agent_migration",
    }
)


def _schema_check(name: str, actual: Any, supported: tuple[str, ...]) -> Dict[str, Any]:
    passed = actual in supported
    return {
        "name": name,
        "ok": passed,
        "status": "passed" if passed else "incompatible",
        "actual": actual,
        "supported": list(supported),
    }


def _invalid(kind: str, error: str) -> Dict[str, Any]:
    return {
        "kind": kind,
        "ok": False,
        "status": "invalid",
        "migration_required": False,
        "checks": [],
        "error": error,
    }


def _result(kind: str, checks: list[Dict[str, Any]], migration_required: bool = False) -> Dict[str, Any]:
    return {
        "kind": kind,
        "ok": all(check.get("ok", False) for check in checks),
        "status": "passed" if all(check.get("ok", False) for check in checks) else "incompatible",
        "migration_required": migration_required,
        "checks": checks,
    }


def _detect_kind(value: Mapping[str, Any]) -> str:
    if "events" in value and "run_id" in value:
        return "trace"
    if "turns" in value and "session_id" in value:
        return "session"
    if "report_type" in value:
        return "report"
    if "contract" in value or any(
        key in value
        for key in (
            "assertions",
            "ignore_paths",
            "normalizers",
            "must_call",
            "must_not_call",
            "path_rules",
            "side_effects",
            "relations",
            "required_claims",
            "tool_limits",
        )
    ):
        return "contract"
    return "unknown"


def check_public_api_version(version: str) -> Dict[str, Any]:
    """Check an integration's declared public API generation.

    v3 remains loadable as a deprecated generation so existing integrations can
    upgrade deliberately. It is reported as requiring migration, not silently
    treated as the current v4 contract.
    """

    if version == PUBLIC_API_VERSION:
        return {
            "name": "public_api_version",
            "ok": True,
            "status": "current",
            "actual": version,
            "expected": PUBLIC_API_VERSION,
            "migration_required": False,
        }
    if version in LEGACY_PUBLIC_API_VERSIONS:
        return {
            "name": "public_api_version",
            "ok": True,
            "status": "deprecated",
            "actual": version,
            "expected": PUBLIC_API_VERSION,
            "migration_required": True,
            "message": "public API generation is deprecated; update the integration before the next major release",
        }
    return {
        "name": "public_api_version",
        "ok": False,
        "status": "unsupported",
        "actual": version,
        "expected": PUBLIC_API_VERSION,
        "migration_required": True,
    }


def check_document_compatibility(
    value: Mapping[str, Any],
    kind: str = "auto",
) -> Dict[str, Any]:
    """Validate one Trace, Session, Contract/config, or Report boundary.

    The checker returns a JSON-serializable result instead of changing a file.
    A deprecated public API generation remains readable but is explicitly
    marked as requiring migration by :func:`check_public_api_version`.
    """

    if not isinstance(value, Mapping):
        return _invalid(kind, "document must be a JSON object")
    selected = _detect_kind(value) if kind == "auto" else kind
    if selected == "unknown":
        return _invalid(selected, "unable to detect a supported document kind")

    try:
        if selected == "trace":
            schema = value.get("schema_version")
            schema_check = _schema_check("trace_schema", schema, SUPPORTED_TRACE_SCHEMA_VERSIONS)
            if not schema_check["ok"]:
                return _result(selected, [schema_check], migration_required=True)
            AgentTrace.from_dict(value)
            return _result(selected, [schema_check])

        if selected == "session":
            schema = value.get("schema_version")
            schema_check = _schema_check("session_schema", schema, SUPPORTED_SESSION_SCHEMA_VERSIONS)
            if not schema_check["ok"]:
                return _result(selected, [schema_check], migration_required=True)
            AgentSession.from_dict(value)
            return _result(selected, [schema_check])

        if selected == "contract":
            contract_value = value.get("contract") if "contract" in value else value
            configured_schema = value.get("contract_schema_version", "0.1")
            schema_check = _schema_check(
                "contract_schema", configured_schema, SUPPORTED_CONTRACT_SCHEMA_VERSIONS
            )
            if not schema_check["ok"]:
                return _result(selected, [schema_check], migration_required=True)
            ContractPolicy.from_dict(contract_value)
            return _result(selected, [schema_check])

        if selected == "report":
            report_type = value.get("report_type")
            # v4.0.0 compare reports predated the explicit report_type field.
            # Recognize that one legacy shape while rejecting arbitrary types.
            if report_type is None and {
                "baseline_run_id",
                "candidate_run_id",
                "blocking_difference_count",
            }.issubset(value):
                report_type = "agent_compare"
            if not isinstance(report_type, str) or not report_type:
                return _invalid(selected, "report_type must be a non-empty string")
            if report_type not in SUPPORTED_REPORT_TYPES:
                return _invalid(selected, f"unsupported report_type {report_type!r}")
            schema_check = _schema_check(
                "report_schema", value.get("schema_version"), SUPPORTED_REPORT_SCHEMA_VERSIONS
            )
            return _result(selected, [schema_check], migration_required=not schema_check["ok"])

        return _invalid(selected, f"unsupported compatibility kind: {selected}")
    except (KeyError, TypeError, ValueError) as exc:
        return _invalid(selected, str(exc))


def build_compatibility_report(
    *,
    trace: Mapping[str, Any] | None = None,
    session: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
    report: Mapping[str, Any] | None = None,
    public_api_version: str | None = None,
) -> Dict[str, Any]:
    """Build the v4 release/integration compatibility report."""

    checks = [
        check_public_api_version(public_api_version or PUBLIC_API_VERSION),
    ]
    if trace is not None:
        checks.append(check_document_compatibility(trace, "trace"))
    if session is not None:
        checks.append(check_document_compatibility(session, "session"))
    if config is not None:
        checks.append(check_document_compatibility(config, "contract"))
    if report is not None:
        checks.append(check_document_compatibility(report, "report"))
    return {
        "schema_version": COMPATIBILITY_REPORT_SCHEMA_VERSION,
        "report_type": "agent_compatibility",
        "ok": all(check.get("ok", False) for check in checks),
        "migration_required": any(check.get("migration_required", False) for check in checks),
        "public_api": public_api_manifest(),
        "checks": checks,
    }


def migrate_trace(value: Mapping[str, Any]) -> Dict[str, Any]:
    """Canonicalize a supported Trace into the current v4 output shape.

    AgentTrace schema 0.1 is unchanged in v4, so migration is intentionally a
    validated no-op for normal traces. The explicit command still removes
    unknown top-level fields and gives future schema migrations one stable
    entry point.
    """

    # Migration is the one boundary allowed to accept legacy top-level noise;
    # normal loading and compatibility checks remain schema-strict.
    canonical = {
        key: value[key]
        for key in ("schema_version", "run_id", "agent", "events", "metadata")
        if key in value
    }
    compatibility = check_document_compatibility(canonical, "trace")
    if not compatibility["ok"]:
        raise ValueError(compatibility.get("error") or "Trace is not compatible")
    return AgentTrace.from_dict(canonical).to_dict()


def build_trace_migration_report(
    source: Mapping[str, Any], migrated: Mapping[str, Any]
) -> Dict[str, Any]:
    """Describe an explicit Trace migration without including its payload."""

    return {
        "schema_version": COMPATIBILITY_REPORT_SCHEMA_VERSION,
        "report_type": "agent_migration",
        "kind": "trace",
        "source_schema_version": source.get("schema_version"),
        "target_schema_version": migrated.get("schema_version"),
        "changed": dict(source) != dict(migrated),
        "migration_required": source.get("schema_version") != migrated.get("schema_version"),
        "status": "migrated" if dict(source) != dict(migrated) else "no-op",
    }
