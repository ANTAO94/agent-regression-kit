from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Set

from .model import AgentTrace
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


@dataclass(frozen=True)
class ComparisonPolicy:
    """Controls which structural differences block a regression check."""

    allowed_categories: Set[str] = field(default_factory=set)
    allowed_paths: Set[str] = field(default_factory=set)

    def allows(self, difference: Dict[str, Any]) -> bool:
        return (
            difference["category"] in self.allowed_categories
            or difference["path"] in self.allowed_paths
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": "strict" if not self.allowed_categories and not self.allowed_paths else "allow_list",
            "allowed_categories": sorted(self.allowed_categories),
            "allowed_paths": sorted(self.allowed_paths),
        }


def _events(trace: AgentTrace, event_type: str) -> List[Dict[str, Any]]:
    return [event for event in trace.events if event["type"] == event_type]


def _add_diff(
    diffs: List[Dict[str, Any]], category: str, path: str, baseline: Any, candidate: Any
) -> None:
    if baseline != candidate:
        diffs.append(
            {"category": category, "path": path, "baseline": baseline, "candidate": candidate}
        )


def _compare_event_list(
    diffs: List[Dict[str, Any]],
    baseline: Iterable[Dict[str, Any]],
    candidate: Iterable[Dict[str, Any]],
    event_type: str,
) -> None:
    baseline_list = list(baseline)
    candidate_list = list(candidate)
    _add_diff(
        diffs,
        "event_count",
        f"events.{event_type}.count",
        len(baseline_list),
        len(candidate_list),
    )
    for index, (left, right) in enumerate(zip(baseline_list, candidate_list)):
        if event_type == "tool_call":
            _add_diff(diffs, "tool_name", f"tool_calls[{index}].tool", left["tool"], right["tool"])
            _add_diff(
                diffs,
                "tool_arguments",
                f"tool_calls[{index}].arguments",
                left["arguments"],
                right["arguments"],
            )
        elif event_type == "tool_result":
            _add_diff(
                diffs,
                "tool_result",
                f"tool_results[{index}].result",
                left.get("result"),
                right.get("result"),
            )
            _add_diff(
                diffs,
                "tool_error_state",
                f"tool_results[{index}].is_error",
                left.get("is_error", False),
                right.get("is_error", False),
            )


def compare_traces(
    baseline: AgentTrace,
    candidate: AgentTrace,
    policy: ComparisonPolicy | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> Dict[str, Any]:
    baseline.validate()
    candidate.validate()
    diffs: List[Dict[str, Any]] = []
    _compare_event_list(
        diffs, _events(baseline, "tool_call"), _events(candidate, "tool_call"), "tool_call"
    )
    _compare_event_list(
        diffs, _events(baseline, "tool_result"), _events(candidate, "tool_result"), "tool_result"
    )

    baseline_answer = _events(baseline, "final_answer")[0]
    candidate_answer = _events(candidate, "final_answer")[0]
    _add_diff(
        diffs,
        "result_interpretation",
        "final_answer.claims",
        baseline_answer.get("claims", {}),
        candidate_answer.get("claims", {}),
    )
    _add_diff(
        diffs,
        "final_answer",
        "final_answer.text",
        baseline_answer["text"],
        candidate_answer["text"],
    )
    active_policy = policy or ComparisonPolicy()
    diffs = (redaction_policy or DEFAULT_REDACTION_POLICY).redact(diffs)
    for difference in diffs:
        difference["allowed"] = active_policy.allows(difference)
    blocking_diffs = [difference for difference in diffs if not difference["allowed"]]
    return {
        "schema_version": "0.1",
        "baseline_run_id": baseline.run_id,
        "candidate_run_id": candidate.run_id,
        "passed": not blocking_diffs,
        "difference_count": len(diffs),
        "blocking_difference_count": len(blocking_diffs),
        "policy": active_policy.to_dict(),
        "differences": diffs,
    }
