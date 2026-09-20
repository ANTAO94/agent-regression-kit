"""Side-effect-free project preflight checks for CLI and CI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

from .config import contract_diagnostics, load_batch_compare_config, load_compare_config
from .model import AgentTrace


def _read_trace(path: str | Path, role: str) -> Dict[str, Any]:
    trace_path = Path(path)
    if not trace_path.is_file():
        raise ValueError(f"{role} trace not found: {trace_path}")
    try:
        value = json.loads(trace_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{role} trace is not valid JSON: {trace_path}") from exc
    trace = AgentTrace.from_dict(value)
    return {
        "role": role,
        "path": str(trace_path),
        "run_id": trace.run_id,
        "agent": trace.agent,
        "event_count": len(trace.events),
        "tool_call_count": sum(event["type"] == "tool_call" for event in trace.events),
        "has_world_state": isinstance(trace.metadata.get("world_state"), dict),
    }


def _trace_files(directory: str | Path) -> Iterable[Path]:
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"trace directory not found: {root}")
    return sorted(root.rglob("*.trace.json"))


def _guidance(
    config: Dict[str, Any], traces: list[Dict[str, Any]], config_path: str | Path
) -> list[Dict[str, str]]:
    """Return non-blocking, actionable advice for a first-time integration."""
    guidance: list[Dict[str, str]] = []
    contract = config.get("contract") or {}
    if not contract:
        guidance.append(
            {
                "level": "warning",
                "code": "missing_contract",
                "message": "no Contract is configured; structural differences alone may miss business regressions",
                "action": "add contract.required_claims, assertions and must_call, then rerun check",
            }
        )
    elif not (
        contract.get("required_claims")
        or contract.get("assertions")
        or contract.get("relations")
    ):
        guidance.append(
            {
                "level": "warning",
                "code": "claims_unconstrained",
                "message": "the Contract does not constrain a business claim or relation",
                "action": "declare the structured claim that proves the business outcome",
            }
        )
    if config.get("allow_categories") or config.get("allow_paths"):
        guidance.append(
            {
                "level": "warning",
                "code": "allow_list_review",
                "message": "allow_categories/allow_paths relax the default blocking policy",
                "action": "add a negative regression test for every allowed category or path",
            }
        )
    path_rules = contract.get("path_rules") or {}
    if path_rules and path_rules.get("mode", "exact") != "exact":
        guidance.append(
            {
                "level": "warning",
                "code": "tolerant_path_review",
                "message": "a tolerant path mode accepts more than one tool path",
                "action": "review extra_calls and keep forbidden tools explicitly denied",
            }
        )
    state_equivalence = contract.get("state_equivalence") or {}
    if state_equivalence.get("paths") and any(
        not trace.get("has_world_state") for trace in traces
    ):
        guidance.append(
            {
                "level": "warning",
                "code": "state_evidence_missing",
                "message": "state_equivalence is configured but at least one Trace has no world_state snapshot",
                "action": "record initial/final state through a SnapshotBackend or remove the state rule",
            }
        )
    guidance.append(
        {
            "level": "info",
            "code": "compare_next",
            "message": "preflight passed; the next step is the actual baseline/candidate comparison",
            "action": f"run agent-regression compare --config {config_path}",
        }
    )
    return guidance


def check_single_config(path: str | Path) -> Dict[str, Any]:
    """Validate config and both configured Trace files without comparing them."""
    config = load_compare_config(path)
    traces = [
        _read_trace(config["baseline"], "baseline"),
        _read_trace(config["candidate"], "candidate"),
    ]
    guidance = _guidance(config, traces, path)
    return {
        "ok": True,
        "kind": "single",
        "config": config,
        "diagnostics": contract_diagnostics(config),
        "guidance": guidance,
        "next_actions": [item["action"] for item in guidance],
        "traces": traces,
    }


def check_batch_config(path: str | Path) -> Dict[str, Any]:
    """Validate batch config and every Trace file in both configured dirs."""
    config = load_batch_compare_config(path)
    baseline_files = list(_trace_files(config["baseline_dir"]))
    candidate_files = list(_trace_files(config["candidate_dir"]))
    if not baseline_files:
        raise ValueError(f"baseline directory contains no *.trace.json files: {config['baseline_dir']}")
    if not candidate_files:
        raise ValueError(f"candidate directory contains no *.trace.json files: {config['candidate_dir']}")
    baseline_root = Path(config["baseline_dir"])
    candidate_root = Path(config["candidate_dir"])
    baseline_names = {str(path.relative_to(baseline_root)) for path in baseline_files}
    candidate_names = {str(path.relative_to(candidate_root)) for path in candidate_files}
    missing_candidate = sorted(baseline_names - candidate_names)
    missing_baseline = sorted(candidate_names - baseline_names)
    if missing_candidate or missing_baseline:
        details = []
        if missing_candidate:
            details.append("missing candidate: " + ", ".join(missing_candidate))
        if missing_baseline:
            details.append("missing baseline: " + ", ".join(missing_baseline))
        raise ValueError("batch trace sets do not match; " + "; ".join(details))
    summaries = []
    for trace_path in baseline_files:
        summaries.append(_read_trace(trace_path, f"baseline:{trace_path.relative_to(baseline_root)}"))
    for trace_path in candidate_files:
        summaries.append(_read_trace(trace_path, f"candidate:{trace_path.relative_to(candidate_root)}"))
    guidance = _guidance(config, summaries, path)
    return {
        "ok": True,
        "kind": "batch",
        "config": config,
        "diagnostics": contract_diagnostics(config),
        "guidance": guidance,
        "next_actions": [item["action"] for item in guidance],
        "trace_count": len(summaries),
        "traces": summaries,
    }
