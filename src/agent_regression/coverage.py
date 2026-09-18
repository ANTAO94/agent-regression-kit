"""Scenario-suite tool-path coverage for AgentTrace evidence."""

from __future__ import annotations

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
    for name, path in sorted(files.items()):
        trace_path = trace_tool_path(_load_trace(path))
        path_cases.setdefault(trace_path, []).append(name)

    expected = sorted({parse_path(path) for path in expected_paths})
    actual = sorted(path_cases)
    missing = [path for path in expected if path not in path_cases]
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    report = {
        "schema_version": "0.1",
        "passed": not missing,
        "trace_dir": str(root),
        "case_count": len(files),
        "unique_path_count": len(actual),
        "expected_path_count": len(expected),
        "covered_expected_path_count": len(expected) - len(missing),
        "coverage_percent": (
            round((len(expected) - len(missing)) / len(expected) * 100, 2)
            if expected
            else 100.0
        ),
        "paths": [_path_entry(path, path_cases[path]) for path in actual],
        "expected_paths": [list(path) for path in expected],
        "missing_paths": [list(path) for path in missing],
    }
    return active_redaction.redact(report)
