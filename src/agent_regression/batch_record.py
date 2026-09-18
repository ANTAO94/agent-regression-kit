"""Parallel, deterministic recording of independent Agent scenarios."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Sequence

from .adapters import AgentAdapter
from .isolation import SnapshotBackend
from .model import AgentTrace
from .record import ToolExecutor, isolated_record_run, record_run
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


AdapterFactory = Callable[[], AgentAdapter]
ToolExecutorFactory = Callable[[], ToolExecutor]
StateBackendFactory = Callable[[], SnapshotBackend]


@dataclass(frozen=True)
class ScenarioCase:
    """A self-contained case that can be executed without shared state.

    Factories are intentional: each worker gets a fresh Agent and tool
    executor. Set ``isolate=True`` when the executor or the supplied backend
    implements snapshot/restore and the case should roll back after recording.
    """

    case_id: str
    request: Any
    run_id: str
    adapter_factory: AdapterFactory
    tools_factory: ToolExecutorFactory
    state_backend_factory: StateBackendFactory | None = None
    metadata: Mapping[str, Any] | None = None
    isolate: bool = False

    def record(self, redaction_policy: RedactionPolicy) -> AgentTrace:
        adapter = self.adapter_factory()
        tools = self.tools_factory()
        state_backend = (
            self.state_backend_factory() if self.state_backend_factory is not None else None
        )
        if self.isolate or state_backend is not None:
            return isolated_record_run(
                adapter,
                self.request,
                tools,
                run_id=self.run_id,
                state_backend=state_backend,
                metadata=self.metadata,
                redaction_policy=redaction_policy,
            )
        return record_run(
            adapter,
            self.request,
            tools,
            run_id=self.run_id,
            metadata=self.metadata,
            redaction_policy=redaction_policy,
        )


@dataclass(frozen=True)
class ScenarioResult:
    """One stable, sorted result from a parallel scenario batch."""

    case_id: str
    run_id: str
    trace: AgentTrace | None = None
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.trace is not None and self.error is None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "case_id": self.case_id,
            "run_id": self.run_id,
            "passed": self.passed,
        }
        if self.trace is not None:
            value["event_count"] = len(self.trace.events)
        if self.error is not None:
            value["error"] = self.error
        return value


@dataclass(frozen=True)
class ScenarioBatchResult:
    """Aggregate result whose case order is independent of thread timing."""

    results: List[ScenarioResult]
    max_workers: int

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        failed_count = sum(1 for result in self.results if not result.passed)
        return {
            "schema_version": "0.1",
            "passed": self.passed,
            "parallel": True,
            "max_workers": self.max_workers,
            "case_count": len(self.results),
            "passed_case_count": len(self.results) - failed_count,
            "failed_case_count": failed_count,
            "cases": [result.to_dict() for result in self.results],
        }


def record_scenario_batch(
    cases: Sequence[ScenarioCase],
    *,
    max_workers: int = 4,
    redaction_policy: RedactionPolicy | None = None,
) -> ScenarioBatchResult:
    """Record independent cases concurrently and return deterministic results.

    Every case owns its adapter and tools through factories. A worker failure is
    captured as a case result so the caller can inspect all failures at once;
    one broken scenario does not hide failures in other scenarios.
    """

    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")
    case_list = list(cases)
    case_ids = [case.case_id for case in case_list]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("scenario case_id values must be unique")
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY

    def run_case(case: ScenarioCase) -> ScenarioResult:
        try:
            return ScenarioResult(
                case_id=case.case_id,
                run_id=case.run_id,
                trace=case.record(active_redaction),
            )
        except Exception as exc:
            return ScenarioResult(
                case_id=case.case_id,
                run_id=case.run_id,
                error=active_redaction.redact(str(exc)),
            )

    if not case_list:
        return ScenarioBatchResult(results=[], max_workers=max_workers)

    worker_count = min(max_workers, len(case_list))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(run_case, case) for case in case_list]
        results = [future.result() for future in as_completed(futures)]
    results.sort(key=lambda result: result.case_id)
    return ScenarioBatchResult(results=results, max_workers=worker_count)
