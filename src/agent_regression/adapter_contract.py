"""Diagnostics for validating a framework adapter at its integration boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict

from .async_record import async_record_run
from .coverage import trace_tool_path
from .record import record_run
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


def _check(
    name: str,
    passed: bool,
    message: str,
    *,
    expected: Any = None,
    actual: Any = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"name": name, "passed": passed, "message": message}
    if expected is not None:
        result["expected"] = expected
    if actual is not None:
        result["actual"] = actual
    return result


def _identity(adapter: Any, redaction_policy: RedactionPolicy) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
    try:
        value = adapter.identity
    except Exception as exc:  # pragma: no cover - defensive integration boundary
        return None, {
            "ok": False,
            "error": {
                "type": type(exc).__name__,
                "message": redaction_policy.redact(str(exc)),
            },
        }
    if not isinstance(value, Mapping):
        return None, {
            "ok": False,
            "error": {
                "type": "AdapterContractError",
                "message": "adapter.identity must be a mapping",
            },
        }
    identity = redaction_policy.redact(dict(value))
    checks = []
    for field in ("name", "version"):
        valid = isinstance(identity.get(field), str) and bool(identity[field].strip())
        checks.append(
            _check(
                f"identity.{field}",
                valid,
                f"identity.{field} must be a non-empty string",
                actual=identity.get(field),
            )
        )
    return identity, {"ok": all(item["passed"] for item in checks), "checks": checks}


def _finish(
    identity: Dict[str, Any],
    identity_report: Dict[str, Any],
    trace: Any,
    *,
    expected_tool_path: tuple[str, ...] | None,
    expected_claims: Mapping[str, Any] | None,
    redaction_policy: RedactionPolicy,
) -> Dict[str, Any]:
    checks = list(identity_report.get("checks", []))
    if trace is not None:
        checks.append(_check("trace.valid", True, "recorded Trace satisfies AgentTrace invariants"))
        if expected_tool_path is not None:
            actual_path = trace_tool_path(trace)
            checks.append(
                _check(
                    "trace.tool_path",
                    actual_path == expected_tool_path,
                    "recorded tool path matches the adapter contract",
                    expected=list(expected_tool_path),
                    actual=list(actual_path),
                )
            )
        if expected_claims is not None:
            final_answer = trace.events[-1]
            claims = final_answer.get("claims", {})
            claims_match = isinstance(claims, dict) and all(
                claims.get(key) == value for key, value in expected_claims.items()
            )
            checks.append(
                _check(
                    "trace.final_answer.claims",
                    claims_match,
                    "required final-answer claims are present and equal",
                    expected=redaction_policy.redact(dict(expected_claims)),
                    actual=redaction_policy.redact(claims),
                )
            )
    return {
        "ok": bool(identity_report.get("ok")) and all(item["passed"] for item in checks),
        "adapter": identity,
        "checks": checks,
        **({"trace": trace.to_dict()} if trace is not None else {}),
    }


def _record_failure(
    identity: Dict[str, Any],
    identity_report: Dict[str, Any],
    exc: Exception,
    redaction_policy: RedactionPolicy,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "adapter": identity,
        "checks": identity_report.get("checks", []),
        "error": {
            "type": type(exc).__name__,
            "message": redaction_policy.redact(str(exc)),
        },
    }


def check_adapter_contract(
    adapter: Any,
    request: Any,
    tools: Any,
    *,
    run_id: str = "adapter-contract",
    expected_tool_path: tuple[str, ...] | list[str] | None = None,
    expected_claims: Mapping[str, Any] | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> Dict[str, Any]:
    """Run one deterministic adapter contract check and return diagnostics.

    The helper is intentionally a report-producing API rather than an assertion
    helper. Framework integrations can print or attach the returned JSON to CI,
    while their test runner decides whether ``ok`` should fail the build.
    """
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    identity, identity_report = _identity(adapter, active_redaction)
    if identity is None or not identity_report.get("ok"):
        return {
            "ok": False,
            "adapter": identity or {},
            "checks": identity_report.get("checks", []),
            "error": identity_report.get("error", {"type": "AdapterContractError"}),
        }
    try:
        trace = record_run(
            adapter,
            request,
            tools,
            run_id=run_id,
            redaction_policy=active_redaction,
        )
    except Exception as exc:
        return _record_failure(identity, identity_report, exc, active_redaction)
    return _finish(
        identity,
        identity_report,
        trace,
        expected_tool_path=tuple(expected_tool_path) if expected_tool_path is not None else None,
        expected_claims=expected_claims,
        redaction_policy=active_redaction,
    )


async def check_async_adapter_contract(
    adapter: Any,
    request: Any,
    tools: Any,
    *,
    run_id: str = "adapter-contract",
    expected_tool_path: tuple[str, ...] | list[str] | None = None,
    expected_claims: Mapping[str, Any] | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> Dict[str, Any]:
    """Async counterpart to :func:`check_adapter_contract`."""
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    identity, identity_report = _identity(adapter, active_redaction)
    if identity is None or not identity_report.get("ok"):
        return {
            "ok": False,
            "adapter": identity or {},
            "checks": identity_report.get("checks", []),
            "error": identity_report.get("error", {"type": "AdapterContractError"}),
        }
    try:
        trace = await async_record_run(
            adapter,
            request,
            tools,
            run_id=run_id,
            redaction_policy=active_redaction,
        )
    except Exception as exc:
        return _record_failure(identity, identity_report, exc, active_redaction)
    return _finish(
        identity,
        identity_report,
        trace,
        expected_tool_path=tuple(expected_tool_path) if expected_tool_path is not None else None,
        expected_claims=expected_claims,
        redaction_policy=active_redaction,
    )
