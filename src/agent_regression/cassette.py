"""Controlled tool replay from an already reviewed AgentTrace."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

from .model import AgentTrace
from .record import ToolExecutionResult


@dataclass(frozen=True)
class CassetteEntry:
    """One expected tool call and its recorded result."""

    call_id: str
    tool: str
    arguments: Dict[str, Any]
    result: Any
    is_error: bool = False
    error: str | None = None
    metadata: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        value: Dict[str, Any] = {
            "call_id": self.call_id,
            "tool": self.tool,
            "arguments": deepcopy(self.arguments),
            "result": deepcopy(self.result),
            "is_error": self.is_error,
        }
        if self.error is not None:
            value["error"] = self.error
        if self.metadata:
            value["metadata"] = deepcopy(self.metadata)
        return value


class ReplayMismatchError(RuntimeError):
    """Raised when an Agent does not follow the recorded tool interaction."""

    def __init__(
        self,
        *,
        index: int,
        reason: str,
        expected: Mapping[str, Any] | None,
        actual: Mapping[str, Any] | None,
    ) -> None:
        self.index = index
        self.reason = reason
        self.expected = deepcopy(dict(expected)) if expected is not None else None
        self.actual = deepcopy(dict(actual)) if actual is not None else None
        detail = f"cassette replay mismatch at call {index + 1}: {reason}"
        super().__init__(detail)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": "replay_mismatch",
            "index": self.index,
            "reason": self.reason,
            "expected": deepcopy(self.expected),
            "actual": deepcopy(self.actual),
        }


class CassetteToolExecutor:
    """Serve recorded tool results while enforcing the recorded call contract.

    A cassette is intentionally strict. It matches the next recorded call by
    tool name and JSON arguments, returns the recorded result, and never calls
    a live executor. Call :meth:`assert_consumed` after the Agent finishes so
    an Agent that stops early also fails the replay.
    """

    def __init__(self, entries: List[CassetteEntry], *, source_run_id: str = ""):
        if not entries:
            raise ValueError("cassette must contain at least one tool call")
        self._entries = [deepcopy(entry) for entry in entries]
        self._source_run_id = source_run_id
        self._index = 0

    @classmethod
    def from_trace(cls, trace: AgentTrace) -> "CassetteToolExecutor":
        trace.validate()
        results = {
            event["call_id"]: event
            for event in trace.events
            if event["type"] == "tool_result"
        }
        entries = []
        for event in trace.events:
            if event["type"] != "tool_call":
                continue
            result = results.get(event["call_id"])
            if result is None:  # AgentTrace.validate already protects this.
                raise ValueError(f"missing result for cassette call {event['call_id']!r}")
            entries.append(
                CassetteEntry(
                    call_id=event["call_id"],
                    tool=event["tool"],
                    arguments=deepcopy(event["arguments"]),
                    result=deepcopy(result.get("result")),
                    is_error=bool(result.get("is_error", False)),
                    error=result.get("error"),
                    metadata=deepcopy(result.get("metadata", {})),
                )
            )
        return cls(entries, source_run_id=trace.run_id)

    @property
    def source_run_id(self) -> str:
        return self._source_run_id

    @property
    def consumed_count(self) -> int:
        return self._index

    @property
    def remaining_count(self) -> int:
        return len(self._entries) - self._index

    def call(self, tool: str, arguments: Dict[str, Any]) -> Any:
        actual = {"tool": tool, "arguments": deepcopy(arguments)}
        if self._index >= len(self._entries):
            raise ReplayMismatchError(
                index=self._index,
                reason="Agent made an extra tool call",
                expected=None,
                actual=actual,
            )
        expected_entry = self._entries[self._index]
        expected = {
            "call_id": expected_entry.call_id,
            "tool": expected_entry.tool,
            "arguments": deepcopy(expected_entry.arguments),
        }
        if expected_entry.tool != tool:
            raise ReplayMismatchError(
                index=self._index,
                reason="tool name changed",
                expected=expected,
                actual=actual,
            )
        if expected_entry.arguments != arguments:
            raise ReplayMismatchError(
                index=self._index,
                reason="tool arguments changed",
                expected=expected,
                actual=actual,
            )
        self._index += 1
        if expected_entry.is_error:
            return ToolExecutionResult(
                result=deepcopy(expected_entry.result),
                is_error=True,
                error=expected_entry.error,
                metadata=deepcopy(expected_entry.metadata or {}),
            )
        return deepcopy(expected_entry.result)

    def assert_consumed(self) -> None:
        if self._index == len(self._entries):
            return
        next_entry = self._entries[self._index]
        raise ReplayMismatchError(
            index=self._index,
            reason="Agent stopped before consuming the cassette",
            expected={
                "call_id": next_entry.call_id,
                "tool": next_entry.tool,
                "arguments": deepcopy(next_entry.arguments),
            },
            actual=None,
        )


def replay_agent_run(
    adapter: Any,
    request: Any,
    cassette: AgentTrace | CassetteToolExecutor,
    *,
    run_id: str,
    metadata: Mapping[str, Any] | None = None,
    redaction_policy: Any | None = None,
) -> AgentTrace:
    """Run an Agent against recorded tool results and return a new Trace."""

    from .record import record_run

    executor = (
        CassetteToolExecutor.from_trace(cassette)
        if isinstance(cassette, AgentTrace)
        else cassette
    )
    trace = record_run(
        adapter,
        request,
        executor,
        run_id=run_id,
        metadata=metadata,
        redaction_policy=redaction_policy,
    )
    executor.assert_consumed()
    trace.metadata["replay"] = {
        "source_run_id": executor.source_run_id,
        "consumed_call_count": executor.consumed_count,
        "strict": True,
    }
    trace.validate()
    return trace
