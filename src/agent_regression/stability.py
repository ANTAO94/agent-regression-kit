"""Repeated-run stability evaluation for non-deterministic Agents."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Mapping, Sequence

from .batch_record import ScenarioCase, record_scenario_batch
from .compare import ComparisonPolicy, compare_traces
from .coverage import trace_tool_path
from .contracts import _IGNORED
from .model import AgentTrace
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


@dataclass(frozen=True)
class StabilityPolicy:
    """Thresholds for repeated Agent behavior evaluation."""

    min_pass_rate: float = 1.0
    min_claims_match_rate: float = 1.0
    max_tool_error_rate: float = 0.0
    max_path_variants: int = 1

    def __post_init__(self) -> None:
        for name, value in (
            ("min_pass_rate", self.min_pass_rate),
            ("min_claims_match_rate", self.min_claims_match_rate),
            ("max_tool_error_rate", self.max_tool_error_rate),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.max_path_variants < 1:
            raise ValueError("max_path_variants must be at least 1")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_pass_rate": self.min_pass_rate,
            "min_claims_match_rate": self.min_claims_match_rate,
            "max_tool_error_rate": self.max_tool_error_rate,
            "max_path_variants": self.max_path_variants,
        }


def _final_claims(
    trace: AgentTrace,
    comparison_policy: ComparisonPolicy | None = None,
) -> Mapping[str, Any] | object:
    for event in reversed(trace.events):
        if event["type"] == "final_answer":
            claims = event.get("claims", {})
            contract = comparison_policy.contract if comparison_policy else None
            return contract.sanitize(claims, "final_answer.claims") if contract else claims
    return {}


def _claims_match(
    baseline: AgentTrace,
    candidate: AgentTrace,
    comparison_policy: ComparisonPolicy,
) -> bool:
    left = _final_claims(baseline, comparison_policy)
    right = _final_claims(candidate, comparison_policy)
    return (left is _IGNORED and right is _IGNORED) or left == right


def _tool_error_count(trace: AgentTrace) -> int:
    return sum(
        1
        for event in trace.events
        if event["type"] == "tool_result" and event.get("is_error", False)
    )


@dataclass(frozen=True)
class StabilityRun:
    """Evidence and comparison result for one repeated execution."""

    ordinal: int
    run_id: str
    trace: AgentTrace | None = None
    comparison: Dict[str, Any] | None = None
    error: str | None = None

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and self.trace is not None
            and bool(self.comparison and self.comparison.get("passed"))
        )

    def to_dict(
        self,
        baseline: AgentTrace,
        comparison_policy: ComparisonPolicy,
    ) -> Dict[str, Any]:
        trace = self.trace
        comparison = self.comparison or {}
        return {
            "ordinal": self.ordinal,
            "run_id": self.run_id,
            "passed": self.passed,
            "error": self.error,
            "difference_count": comparison.get("difference_count", 0),
            "blocking_difference_count": comparison.get("blocking_difference_count", 0),
            "tool_path": trace_tool_path(trace) if trace is not None else [],
            "tool_error_count": _tool_error_count(trace) if trace is not None else 0,
            "claims_match": (
                _claims_match(baseline, trace, comparison_policy)
                if trace is not None
                else False
            ),
        }


@dataclass(frozen=True)
class StabilityReport:
    """Aggregate repeated-run metrics and threshold decision."""

    baseline: AgentTrace
    runs: List[StabilityRun]
    policy: StabilityPolicy
    comparison_policy: ComparisonPolicy

    @property
    def run_count(self) -> int:
        return len(self.runs)

    @property
    def pass_count(self) -> int:
        return sum(1 for run in self.runs if run.passed)

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.run_count if self.run_count else 0.0

    @property
    def claims_match_count(self) -> int:
        return sum(
            1
            for run in self.runs
            if run.trace is not None
            and _claims_match(self.baseline, run.trace, self.comparison_policy)
        )

    @property
    def claims_match_rate(self) -> float:
        return self.claims_match_count / self.run_count if self.run_count else 0.0

    @property
    def tool_error_count(self) -> int:
        return sum(_tool_error_count(run.trace) for run in self.runs if run.trace is not None)

    @property
    def tool_result_count(self) -> int:
        return sum(
            sum(1 for event in run.trace.events if event["type"] == "tool_result")
            for run in self.runs
            if run.trace is not None
        )

    @property
    def tool_error_rate(self) -> float:
        return self.tool_error_count / self.tool_result_count if self.tool_result_count else 0.0

    @property
    def path_variants(self) -> List[List[str]]:
        paths = {tuple(trace_tool_path(self.baseline))}
        paths.update(
            tuple(trace_tool_path(run.trace))
            for run in self.runs
            if run.trace is not None
        )
        return [list(path) for path in sorted(paths)]

    @property
    def passed(self) -> bool:
        return (
            self.run_count > 0
            and self.pass_rate >= self.policy.min_pass_rate
            and self.claims_match_rate >= self.policy.min_claims_match_rate
            and self.tool_error_rate <= self.policy.max_tool_error_rate
            and len(self.path_variants) <= self.policy.max_path_variants
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "0.1",
            "report_type": "agent_stability",
            "passed": self.passed,
            "baseline_run_id": self.baseline.run_id,
            "policy": self.policy.to_dict(),
            "comparison_policy": self.comparison_policy.to_dict(),
            "run_count": self.run_count,
            "pass_count": self.pass_count,
            "pass_rate": self.pass_rate,
            "claims_match_count": self.claims_match_count,
            "claims_match_rate": self.claims_match_rate,
            "tool_error_count": self.tool_error_count,
            "tool_result_count": self.tool_result_count,
            "tool_error_rate": self.tool_error_rate,
            "path_variant_count": len(self.path_variants),
            "path_variants": self.path_variants,
            "runs": [
                run.to_dict(self.baseline, self.comparison_policy) for run in self.runs
            ],
        }


def evaluate_stability(
    baseline: AgentTrace,
    runs: Sequence[AgentTrace],
    *,
    comparison_policy: ComparisonPolicy | None = None,
    policy: StabilityPolicy | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> StabilityReport:
    """Compare already-recorded repeated runs against one baseline."""
    baseline.validate()
    active_comparison = comparison_policy or ComparisonPolicy()
    active_policy = policy or StabilityPolicy()
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    stability_runs = []
    for ordinal, trace in enumerate(runs, start=1):
        trace.validate()
        comparison = compare_traces(
            baseline,
            trace,
            active_comparison,
            active_redaction,
        )
        stability_runs.append(
            StabilityRun(
                ordinal=ordinal,
                run_id=trace.run_id,
                trace=trace,
                comparison=comparison,
            )
        )
    return StabilityReport(
        baseline=baseline,
        runs=stability_runs,
        policy=active_policy,
        comparison_policy=active_comparison,
    )


def record_stability(
    baseline: AgentTrace,
    case: ScenarioCase,
    *,
    repeats: int = 5,
    max_workers: int = 4,
    comparison_policy: ComparisonPolicy | None = None,
    policy: StabilityPolicy | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> StabilityReport:
    """Record one isolated case repeatedly, then evaluate its stability."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    repeated_cases = [
        replace(
            case,
            case_id=f"{case.case_id}::repeat-{ordinal:04d}",
            run_id=f"{case.run_id}-repeat-{ordinal}",
        )
        for ordinal in range(1, repeats + 1)
    ]
    batch = record_scenario_batch(
        repeated_cases,
        max_workers=max_workers,
        redaction_policy=redaction_policy,
    )
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    active_comparison = comparison_policy or ComparisonPolicy()
    active_policy = policy or StabilityPolicy()
    runs = []
    for ordinal, result in enumerate(batch.results, start=1):
        if result.trace is None:
            runs.append(
                StabilityRun(
                    ordinal=ordinal,
                    run_id=result.run_id,
                    error=active_redaction.redact(result.error or "scenario recording failed"),
                )
            )
            continue
        runs.append(
            StabilityRun(
                ordinal=ordinal,
                run_id=result.run_id,
                trace=result.trace,
                comparison=compare_traces(
                    baseline,
                    result.trace,
                    active_comparison,
                    active_redaction,
                ),
            )
        )
    runs.sort(key=lambda run: run.ordinal)
    return StabilityReport(
        baseline=baseline,
        runs=runs,
        policy=active_policy,
        comparison_policy=active_comparison,
    )
