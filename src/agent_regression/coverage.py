"""Scenario-suite tool-path coverage for AgentTrace evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .model import AgentTrace
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


PathSignature = Tuple[str, ...]


def trace_tool_path(trace: AgentTrace) -> PathSignature:
    """Return the ordered tool names observed in one AgentTrace."""
    trace.validate()
    return tuple(
        event["tool"] for event in trace.events if event["type"] == "tool_call"
    )


def trace_outcome_path(trace: AgentTrace) -> PathSignature:
    """Return tool names annotated with the matching result outcome."""
    trace.validate()
    outcomes = {
        event["call_id"]: "error" if event.get("is_error") else "ok"
        for event in trace.events
        if event["type"] == "tool_result"
    }
    return tuple(
        f"{event['tool']}[{outcomes.get(event['call_id'], 'unknown')}]"
        for event in trace.events
        if event["type"] == "tool_call"
    )


def _lookup(value: Any, path: Sequence[str]) -> List[Any]:
    if not path:
        return [value]
    token, *rest = path
    if isinstance(value, dict):
        if token not in value:
            return []
        return _lookup(value[token], rest)
    if isinstance(value, list):
        try:
            index = int(token)
        except ValueError:
            return []
        if index < 0 or index >= len(value):
            return []
        return _lookup(value[index], rest)
    return []


def trace_business_branch(
    trace: AgentTrace, branch_paths: Sequence[str]
) -> Dict[str, Any]:
    """Project selected structured claims into one business branch identity."""
    trace.validate()
    data = trace.to_dict()
    data["final_answer"] = next(
        event for event in trace.events if event["type"] == "final_answer"
    )
    result: Dict[str, Any] = {}
    for path in branch_paths:
        values = _lookup(data, tuple(path.split(".")))
        result[path] = values[0] if len(values) == 1 else (values if values else None)
    return result


def path_to_string(path: Sequence[str]) -> str:
    return " -> ".join(path) if path else "(no tool calls)"


def parse_path(value: str | Sequence[str]) -> PathSignature:
    """Parse ``get_order -> cancel_order`` or an explicit tool-name sequence."""
    if isinstance(value, str):
        parts = tuple(item.strip() for item in value.split("->") if item.strip())
    else:
        parts = tuple(str(item).strip() for item in value if str(item).strip())
    if not parts:
        raise ValueError("expected path must contain at least one tool name")
    return parts


def _trace_files(root: Path) -> Dict[str, Path]:
    if not root.exists():
        raise ValueError(f"trace directory not found: {root}")
    return {
        str(path.relative_to(root)): path
        for path in root.rglob("*.trace.json")
        if path.is_file()
    }


def _load_trace(path: Path) -> AgentTrace:
    import json

    return AgentTrace.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _path_entry(path: PathSignature, cases: Iterable[str]) -> Dict[str, Any]:
    case_list = sorted(cases)
    return {
        "path": list(path),
        "signature": path_to_string(path),
        "case_count": len(case_list),
        "cases": case_list,
    }


def compare_trace_coverage(
    trace_dir: str | Path,
    *,
    expected_paths: Iterable[str | Sequence[str]] = (),
    include_outcomes: bool = False,
    branch_paths: Sequence[str] = (),
    expected_branches: Iterable[Mapping[str, Any]] = (),
    redaction_policy: RedactionPolicy | None = None,
) -> Dict[str, Any]:
    """Aggregate tool paths and report missing expected scenario branches.

    Coverage is intentionally based on recorded evidence, not on model
    internals. Two cases that reach the same ordered tool path count as one
    covered path and retain both case names in the report.
    """
    root = Path(trace_dir).resolve()
    files = _trace_files(root)
    path_cases: Dict[PathSignature, List[str]] = {}
    branch_cases: Dict[str, Dict[str, Any]] = {}
    for name, path in sorted(files.items()):
        trace = _load_trace(path)
        trace_path = (
            trace_outcome_path(trace)
            if include_outcomes
            else trace_tool_path(trace)
        )
        path_cases.setdefault(trace_path, []).append(name)
        if branch_paths:
            branch_values = trace_business_branch(trace, branch_paths)
            branch_signature = json.dumps(
                branch_values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            branch_cases.setdefault(
                branch_signature,
                {"values": branch_values, "cases": []},
            )["cases"].append(name)

    expected = sorted({parse_path(path) for path in expected_paths})
    actual = sorted(path_cases)
    missing = [path for path in expected if path not in path_cases]
    expected_branch_list = [dict(branch) for branch in expected_branches]
    missing_branches = [
        branch
        for branch in expected_branch_list
        if not any(
            all(entry["values"].get(path) == value for path, value in branch.items())
            for entry in branch_cases.values()
        )
    ]
    branch_entries = [
        {
            "values": entry["values"],
            "signature": signature,
            "case_count": len(entry["cases"]),
            "cases": sorted(entry["cases"]),
        }
        for signature, entry in sorted(branch_cases.items())
    ]
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    report = {
        "schema_version": "0.1",
        "report_type": "agent_coverage",
        # Zero discovered traces is missing evidence, not 100% coverage.
        "passed": bool(files) and not missing and not missing_branches,
        "trace_dir": str(root),
        "path_mode": "tool_outcome" if include_outcomes else "tool",
        "branch_paths": list(branch_paths),
        "case_count": len(files),
        "unique_path_count": len(actual),
        "expected_path_count": len(expected),
        "covered_expected_path_count": len(expected) - len(missing),
        "coverage_percent": (
            round((len(expected) - len(missing)) / len(expected) * 100, 2)
            if expected
            else (100.0 if files else 0.0)
        ),
        "paths": [_path_entry(path, path_cases[path]) for path in actual],
        "expected_paths": [list(path) for path in expected],
        "missing_paths": [list(path) for path in missing],
        "business_branch_count": len(branch_entries),
        "expected_branch_count": len(expected_branch_list),
        "covered_expected_branch_count": len(expected_branch_list) - len(missing_branches),
        "business_branch_coverage_percent": (
            round(
                (len(expected_branch_list) - len(missing_branches))
                / len(expected_branch_list)
                * 100,
                2,
            )
            if expected_branch_list
            else (100.0 if files else 0.0)
        ),
        "business_branches": branch_entries,
        "expected_branches": expected_branch_list,
        "missing_branches": missing_branches,
    }
    return active_redaction.redact(report)
