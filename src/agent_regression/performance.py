"""Deterministic local performance baselines for the regression engine.

The benchmark intentionally measures the framework boundary only: generating
valid traces, validating them and comparing identical evidence.  It never
calls a model, network service or user Agent.  This makes the result useful for
release engineering without pretending to measure model latency.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from copy import deepcopy
from typing import Any, Dict, Mapping

from .compare import compare_traces
from .model import AgentTrace, SUPPORTED_SCHEMA_VERSION
from .version import __version__


def _trace_payload(index: int, tool_calls: int) -> Dict[str, Any]:
    """Build one valid deterministic trace for the requested workload."""
    events: list[Dict[str, Any]] = []
    for call_index in range(tool_calls):
        call_id = f"call-{index}-{call_index}"
        order_id = str((index + call_index) % 1000).zfill(3)
        events.append(
            {
                "type": "tool_call",
                "call_id": call_id,
                "tool": "lookup_order",
                "arguments": {"order_id": order_id},
                "sequence": len(events) + 1,
            }
        )
        events.append(
            {
                "type": "tool_result",
                "call_id": call_id,
                "result": {"order_id": order_id, "status": "not_shipped"},
                "is_error": False,
                "sequence": len(events) + 1,
            }
        )
    events.append(
        {
            "type": "final_answer",
            "text": "The order is not shipped.",
            "claims": {"status": "not_shipped", "calls": tool_calls},
            "sequence": len(events) + 1,
        }
    )
    return {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "run_id": f"performance-{index}",
        "agent": {"name": "performance-fixture", "version": "1.0.0"},
        "events": events,
        "metadata": {"input": {"case": index}},
    }


def _peak_rss_bytes() -> int | None:
    """Return process peak RSS in bytes where the host exposes it."""
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, OSError, ValueError):
        return None
    # macOS reports bytes; Linux and most BSD implementations report KiB.
    return value if sys.platform == "darwin" else value * 1024


def _run_workload(name: str, count: int, tool_calls: int) -> Dict[str, Any]:
    if count <= 0:
        raise ValueError("performance workload count must be positive")
    if tool_calls <= 0:
        raise ValueError("performance workload tool_calls must be positive")
    started = time.perf_counter()
    for index in range(count):
        payload = _trace_payload(index, tool_calls)
        baseline = AgentTrace.from_dict(payload)
        candidate = AgentTrace.from_dict(deepcopy(payload))
        report = compare_traces(baseline, candidate)
        if not report["passed"]:
            raise AssertionError(f"performance fixture unexpectedly failed: {name}")
    elapsed = max(time.perf_counter() - started, 1e-9)
    return {
        "name": name,
        "trace_count": count,
        "tool_calls_per_trace": tool_calls,
        "events_per_trace": tool_calls * 2 + 1,
        "elapsed_seconds": round(elapsed, 6),
        "traces_per_second": round(count / elapsed, 3),
    }


def run_performance_benchmark(
    *,
    small_count: int = 10_000,
    medium_count: int = 1_000,
    medium_tool_calls: int = 10,
) -> Dict[str, Any]:
    """Run the fixed small and medium workloads and return JSON evidence."""
    started = time.perf_counter()
    workloads = [
        _run_workload("small", small_count, 2),
        _run_workload("medium", medium_count, medium_tool_calls),
    ]
    elapsed = max(time.perf_counter() - started, 1e-9)
    return {
        "schema_version": "0.1",
        "report_type": "agent_performance",
        "passed": True,
        "workloads": workloads,
        "environment": {
            "package_version": __version__,
            "commit": os.environ.get("GITHUB_SHA") or os.environ.get("AGENT_REGRESSION_COMMIT"),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "os": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "peak_rss_bytes": _peak_rss_bytes(),
        },
        "total_elapsed_seconds": round(elapsed, 6),
    }


def _workloads(report: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    value = report.get("workloads")
    if not isinstance(value, list) or not value:
        raise ValueError("performance report workloads must be a non-empty array")
    result: Dict[str, Mapping[str, Any]] = {}
    for workload in value:
        if not isinstance(workload, Mapping) or not isinstance(workload.get("name"), str):
            raise ValueError("performance workload must contain a name")
        result[str(workload["name"])] = workload
    return result


def evaluate_performance_gate(
    current: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    warn_ratio: float = 0.20,
    block_ratio: float = 0.40,
) -> Dict[str, Any]:
    """Compare elapsed-time regressions against a stored release baseline."""
    if not 0 <= warn_ratio <= block_ratio:
        raise ValueError("performance ratios must satisfy 0 <= warn_ratio <= block_ratio")
    current_workloads = _workloads(current)
    baseline_workloads = _workloads(baseline)
    comparisons = []
    blocked = False
    for name, previous in baseline_workloads.items():
        actual = current_workloads.get(name)
        if actual is None:
            comparisons.append({"name": name, "status": "missing_current"})
            blocked = True
            continue
        previous_seconds = float(previous.get("elapsed_seconds", 0))
        current_seconds = float(actual.get("elapsed_seconds", 0))
        if previous_seconds <= 0 or current_seconds < 0:
            raise ValueError(f"invalid elapsed_seconds for workload {name!r}")
        ratio = (current_seconds / previous_seconds) - 1 if previous_seconds else 0.0
        status = "blocked" if ratio > block_ratio else "warning" if ratio > warn_ratio else "passed"
        blocked = blocked or status == "blocked"
        comparisons.append(
            {
                "name": name,
                "status": status,
                "baseline_seconds": previous_seconds,
                "current_seconds": current_seconds,
                "delta_ratio": round(ratio, 6),
                "warn_ratio": warn_ratio,
                "block_ratio": block_ratio,
            }
        )
    for name in sorted(set(current_workloads) - set(baseline_workloads)):
        comparisons.append({"name": name, "status": "new_workload"})
    return {
        "schema_version": "0.1",
        "report_type": "agent_performance_gate",
        "passed": not blocked,
        "thresholds": {"warn_ratio": warn_ratio, "block_ratio": block_ratio},
        "comparisons": comparisons,
    }
