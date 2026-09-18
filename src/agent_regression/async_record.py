"""Async Agent recording with explicit, deterministic parallel groups."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from copy import deepcopy
from typing import Any, Awaitable, Dict, Mapping, Protocol

from .adapters import AsyncAgentAdapter, AsyncRunContext
from .isolation import SnapshotBackend
from .model import AgentTrace, SUPPORTED_SCHEMA_VERSION
from .record import ToolExecutionResult
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


class AsyncToolExecutor(Protocol):
    """Optional async boundary for tools used by ``async_record_run``."""

    async def call_async(self, tool: str, arguments: Dict[str, Any]) -> Any: ...


@dataclass
class _PendingResult:
    ordinal: int
    call_id: str
    event: Dict[str, Any] | None = None
    completed: bool = False
    emitted: bool = False


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _call_tool(tools: Any, tool: str, arguments: Dict[str, Any]) -> Any:
    call_async = getattr(tools, "call_async", None)
    if callable(call_async):
        return await _maybe_await(call_async(tool, arguments))
    # A synchronous fixture can still participate in a parallel group without
    # blocking the event loop. Real integrations should prefer call_async.
    return await asyncio.to_thread(tools.call, tool, arguments)


class _AsyncRecordingContext:
    def __init__(self, tools: Any, redaction_policy: RedactionPolicy):
        self.tools = tools
        self.redaction_policy = redaction_policy
        self.events: list[Dict[str, Any]] = []
        self._call_counter = 0
        self._pending: Dict[str, _PendingResult] = {}
        self._groups: Dict[str, Dict[str, Any]] = {}

    def _execution_metadata(self, ordinal: int, parallel_group: str | None) -> Dict[str, Any]:
        execution: Dict[str, Any] = {"mode": "async", "call_ordinal": ordinal}
        if parallel_group is not None:
            execution["parallel_group"] = parallel_group
        return {"execution": execution}

    def _flush_completed(self) -> None:
        for pending in sorted(self._pending.values(), key=lambda item: item.ordinal):
            if pending.completed and not pending.emitted and pending.event is not None:
                self.events.append(pending.event)
                pending.emitted = True

    def call_tool(
        self,
        tool: str,
        arguments: Dict[str, Any],
        *,
        parallel_group: str | None = None,
    ) -> Awaitable[Any]:
        # A new logical call starts after all completed results from an earlier
        # parallel group. This keeps event order stable even if task completion
        # order changes from run to run.
        self._flush_completed()
        self._call_counter += 1
        ordinal = self._call_counter
        call_id = f"call-{ordinal}"
        if parallel_group is not None:
            group = self._groups.setdefault(
                parallel_group,
                {"group_id": parallel_group, "call_ids": [], "call_count": 0},
            )
            group["call_ids"].append(call_id)
            group["call_count"] += 1
        self.events.append(
            {
                "type": "tool_call",
                "call_id": call_id,
                "tool": tool,
                "arguments": self.redaction_policy.redact(deepcopy(arguments)),
                "metadata": self.redaction_policy.redact(
                    self._execution_metadata(ordinal, parallel_group)
                ),
            }
        )
        pending = _PendingResult(ordinal=ordinal, call_id=call_id)
        self._pending[call_id] = pending
        return self._execute(pending, tool, arguments, parallel_group)

    async def _execute(
        self,
        pending: _PendingResult,
        tool: str,
        arguments: Dict[str, Any],
        parallel_group: str | None,
    ) -> Any:
        execution_metadata = self._execution_metadata(pending.ordinal, parallel_group)
        try:
            execution = await _call_tool(self.tools, tool, arguments)
        except Exception as exc:
            pending.event = {
                "type": "tool_result",
                "call_id": pending.call_id,
                "result": None,
                "is_error": True,
                "error": self.redaction_policy.redact(str(exc)),
                "metadata": self.redaction_policy.redact(execution_metadata),
            }
            pending.completed = True
            if parallel_group is None:
                self._flush_completed()
            raise

        if isinstance(execution, ToolExecutionResult):
            result = self.redaction_policy.redact(execution.result)
            is_error = execution.is_error
            error = self.redaction_policy.redact(execution.error)
            event_metadata = dict(execution.metadata or {})
        else:
            result = self.redaction_policy.redact(execution)
            is_error = False
            error = None
            event_metadata = {}
        event_metadata["execution"] = execution_metadata["execution"]
        result_event: Dict[str, Any] = {
            "type": "tool_result",
            "call_id": pending.call_id,
            "result": result,
            "is_error": is_error,
            "metadata": self.redaction_policy.redact(event_metadata),
        }
        if error:
            result_event["error"] = error
        pending.event = result_event
        pending.completed = True
        if parallel_group is None:
            self._flush_completed()
        return result

    def final_answer(self, text: str, claims: Dict[str, Any] | None = None) -> None:
        self._flush_completed()
        if any(not pending.emitted for pending in self._pending.values()):
            raise RuntimeError("final_answer called while async tool calls are pending")
        event: Dict[str, Any] = {
            "type": "final_answer",
            "text": self.redaction_policy.redact(text),
            "metadata": {"execution": {"mode": "async"}},
        }
        if claims:
            event["claims"] = self.redaction_policy.redact(deepcopy(claims))
        self.events.append(event)

    def execution_metadata(self) -> Dict[str, Any]:
        return {
            "mode": "async",
            "parallel_groups": [dict(group) for group in self._groups.values()],
        }


async def async_record_run(
    adapter: AsyncAgentAdapter,
    request: Any,
    tools: Any,
    *,
    run_id: str,
    metadata: Mapping[str, Any] | None = None,
    redaction_policy: RedactionPolicy | None = None,
    state_backend: SnapshotBackend | None = None,
) -> AgentTrace:
    """Record an async Agent run while preserving explicit parallel groups."""
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    snapshot_source = state_backend if state_backend is not None else tools
    snapshot = getattr(snapshot_source, "snapshot", None)
    initial_world = await _maybe_await(snapshot()) if callable(snapshot) else None
    context = _AsyncRecordingContext(tools, active_redaction)
    await adapter.run(request, context)
    final_world = await _maybe_await(snapshot()) if callable(snapshot) else None
    for sequence, event in enumerate(context.events, start=1):
        event["sequence"] = sequence
    run_metadata = {"input": deepcopy(request), **dict(metadata or {})}
    run_metadata["execution"] = context.execution_metadata()
    if initial_world is not None or final_world is not None:
        run_metadata["world_state"] = active_redaction.redact(
            {
                "initial": initial_world if initial_world is not None else {},
                "final": final_world if final_world is not None else {},
            }
        )
    trace = AgentTrace(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        run_id=run_id,
        agent=active_redaction.redact(dict(adapter.identity)),
        events=context.events,
        metadata=active_redaction.redact(run_metadata),
    )
    trace.validate()
    return trace


def record_async_run(
    adapter: AsyncAgentAdapter,
    request: Any,
    tools: Any,
    *,
    run_id: str,
    metadata: Mapping[str, Any] | None = None,
    redaction_policy: RedactionPolicy | None = None,
    state_backend: SnapshotBackend | None = None,
) -> AgentTrace:
    """Synchronous convenience wrapper around :func:`async_record_run`."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            async_record_run(
                adapter,
                request,
                tools,
                run_id=run_id,
                metadata=metadata,
                redaction_policy=redaction_policy,
                state_backend=state_backend,
            )
        )
    raise RuntimeError("record_async_run cannot run inside an event loop; await async_record_run")
