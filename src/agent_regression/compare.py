from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Set

from .contracts import ContractPolicy, _IGNORED
from .model import AgentTrace
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


@dataclass(frozen=True)
class ComparisonPolicy:
    """Controls which structural differences block a regression check."""

    allowed_categories: Set[str] = field(default_factory=set)
    allowed_paths: Set[str] = field(default_factory=set)
    final_answer_mode: str = "exact"
    contract: ContractPolicy | None = None

    def __post_init__(self) -> None:
        if self.final_answer_mode not in {"exact", "claims-only"}:
            raise ValueError("final_answer_mode must be 'exact' or 'claims-only'")

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
            "final_answer_mode": self.final_answer_mode,
            "contract": self.contract.to_dict() if self.contract else {},
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
    contract: ContractPolicy | None = None,
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
            path = f"tool_calls[{index}].arguments"
            left_arguments = contract.sanitize(left["arguments"], path) if contract else left["arguments"]
            right_arguments = contract.sanitize(right["arguments"], path) if contract else right["arguments"]
            if left_arguments is not _IGNORED and right_arguments is not _IGNORED:
                _add_diff(diffs, "tool_arguments", path, left_arguments, right_arguments)
        elif event_type == "tool_result":
            path = f"tool_results[{index}].result"
            left_result = contract.sanitize(left.get("result"), path) if contract else left.get("result")
            right_result = contract.sanitize(right.get("result"), path) if contract else right.get("result")
            if left_result is not _IGNORED and right_result is not _IGNORED:
                _add_diff(diffs, "tool_result", path, left_result, right_result)
            _add_diff(
                diffs,
                "tool_error_state",
                f"tool_results[{index}].is_error",
                left.get("is_error", False),
                right.get("is_error", False),
            )


def _compare_nested(
    diffs: List[Dict[str, Any]],
    baseline: Any,
    candidate: Any,
    path: str,
) -> None:
    """Emit field-level state changes instead of one opaque JSON mismatch."""
    if isinstance(baseline, dict) and isinstance(candidate, dict):
        for key in sorted(set(baseline) | set(candidate)):
            child_path = f"{path}.{key}"
            if key not in baseline or key not in candidate:
                _add_diff(diffs, "state_change", child_path, baseline.get(key), candidate.get(key))
            else:
                _compare_nested(diffs, baseline[key], candidate[key], child_path)
        return
    if isinstance(baseline, list) and isinstance(candidate, list):
        if len(baseline) != len(candidate):
            _add_diff(diffs, "state_change", f"{path}.count", len(baseline), len(candidate))
        for index, (left, right) in enumerate(zip(baseline, candidate)):
            _compare_nested(diffs, left, right, f"{path}[{index}]")
        return
    _add_diff(diffs, "state_change", path, baseline, candidate)


def compare_traces(
    baseline: AgentTrace,
    candidate: AgentTrace,
    policy: ComparisonPolicy | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> Dict[str, Any]:
    baseline.validate()
    candidate.validate()
    diffs: List[Dict[str, Any]] = []
    active_policy = policy or ComparisonPolicy()
    contract = active_policy.contract
    baseline_calls = _events(baseline, "tool_call")
    candidate_calls = _events(candidate, "tool_call")
    same_call_shape = [event.get("tool") for event in baseline_calls] == [
        event.get("tool") for event in candidate_calls
    ]
    # An explicit path contract owns the allowed tool sequence.  Do not make
    # an alternative valid path fail merely because its event counts differ.
    if not contract or not contract.has_path_rules:
        _compare_event_list(diffs, baseline_calls, candidate_calls, "tool_call", contract)
        _compare_event_list(
            diffs,
            _events(baseline, "tool_result"),
            _events(candidate, "tool_result"),
            "tool_result",
            contract,
        )
    elif same_call_shape:
        _compare_event_list(
            diffs,
            _events(baseline, "tool_result"),
            _events(candidate, "tool_result"),
            "tool_result",
            contract,
        )

    baseline_answer = _events(baseline, "final_answer")[0]
    candidate_answer = _events(candidate, "final_answer")[0]
    claims_path = "final_answer.claims"
    baseline_claims = contract.sanitize(baseline_answer.get("claims", {}), claims_path) if contract else baseline_answer.get("claims", {})
    candidate_claims = contract.sanitize(candidate_answer.get("claims", {}), claims_path) if contract else candidate_answer.get("claims", {})
    if baseline_claims is not _IGNORED and candidate_claims is not _IGNORED:
        _add_diff(diffs, "result_interpretation", claims_path, baseline_claims, candidate_claims)
    if active_policy.final_answer_mode == "exact":
        text_path = "final_answer.text"
        baseline_text = contract.sanitize(baseline_answer["text"], text_path) if contract else baseline_answer["text"]
        candidate_text = contract.sanitize(candidate_answer["text"], text_path) if contract else candidate_answer["text"]
        if baseline_text is not _IGNORED and candidate_text is not _IGNORED:
            _add_diff(diffs, "final_answer", text_path, baseline_text, candidate_text)
    if contract:
        diffs.extend(contract.check(baseline, candidate))
    baseline_world = baseline.metadata.get("world_state")
    candidate_world = candidate.metadata.get("world_state")
    if baseline_world is not None or candidate_world is not None:
        left_world = baseline_world or {}
        right_world = candidate_world or {}
        if contract:
            left_world = contract.sanitize(left_world, "world_state")
            right_world = contract.sanitize(right_world, "world_state")
        if left_world is not _IGNORED and right_world is not _IGNORED:
            _compare_nested(diffs, left_world, right_world, "world_state")
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
