"""Batch comparison for a directory of AgentTrace cases."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from .compare import ComparisonPolicy, compare_traces
from .model import AgentTrace
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


def _trace_files(root: Path) -> Dict[str, Path]:
    return {
        str(path.relative_to(root)): path
        for path in root.rglob("*.trace.json")
        if path.is_file()
    }


def _load_trace(path: Path) -> AgentTrace:
    import json

    return AgentTrace.from_dict(json.loads(path.read_text(encoding="utf-8")))


def compare_trace_batch(
    baseline_dir: str | Path,
    candidate_dir: str | Path,
    *,
    policy: ComparisonPolicy | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> Dict[str, Any]:
    """Compare matching ``*.trace.json`` files under two directories."""
    baseline_root = Path(baseline_dir)
    candidate_root = Path(candidate_dir)
    baseline_files = _trace_files(baseline_root)
    candidate_files = _trace_files(candidate_root)
    names = sorted(set(baseline_files) | set(candidate_files))
    cases = []
    missing_baselines = []
    missing_candidates = []
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY

    for name in names:
        baseline_path = baseline_files.get(name)
        candidate_path = candidate_files.get(name)
        if baseline_path is None:
            missing_baselines.append(name)
            continue
        if candidate_path is None:
            missing_candidates.append(name)
            continue
        comparison = compare_traces(
            _load_trace(baseline_path),
            _load_trace(candidate_path),
            policy,
            redaction_policy,
        )
        cases.append({"case": name, **comparison})

    missing = [
        {"case": name, "reason": "missing_baseline", "passed": False}
        for name in missing_baselines
    ] + [
        {"case": name, "reason": "missing_candidate", "passed": False}
        for name in missing_candidates
    ]
    all_cases = cases + missing
    failed_count = sum(1 for case in all_cases if not case["passed"])
    return active_redaction.redact(
        {
            "schema_version": "0.1",
            "report_type": "agent_batch",
            "passed": failed_count == 0,
            "case_count": len(all_cases),
            "passed_case_count": len(all_cases) - failed_count,
            "failed_case_count": failed_count,
            "missing_baselines": missing_baselines,
            "missing_candidates": missing_candidates,
            "policy": (policy or ComparisonPolicy()).to_dict(),
            "cases": all_cases,
        }
    )
