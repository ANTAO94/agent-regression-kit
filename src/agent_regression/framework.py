"""Framework callback event ingestion for real Agent integrations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, Mapping

from .model import AgentTrace, SUPPORTED_SCHEMA_VERSION
from .record import ToolExecutionResult
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


class FrameworkTraceRecorder:
    """Turn framework lifecycle callbacks into one validated AgentTrace.

    Frameworks commonly expose separate callbacks for tool start, tool end and
    final output. This recorder keeps the framework-specific callback adapter
    small while preserving call_id association even when tool results arrive
    out of order.
    """

    def __init__(
        self,
        identity: Mapping[str, Any],
        *,
        run_id: str,
        request: Any = None,
        metadata: Mapping[str, Any] | None = None,
        redaction_policy: RedactionPolicy | None = None,
    ) -> None:
        self._identity = dict(identity)
        self._run_id = run_id
        self._request = deepcopy(request)
        self._metadata = dict(metadata or {})
        self._redaction = redaction_policy or DEFAULT_REDACTION_POLICY
        self._events: list[Dict[str, Any]] = []
        self._pending: Dict[str, str] = {}
        self._seen_call_ids: set[str] = set()
        self._call_counter = 0
        self._final_seen = False

    @property
    def identity(self) -> Mapping[str, Any]:
        return self._identity

    @property
    def events(self) -> list[Dict[str, Any]]:
        return deepcopy(self._events)

    def _append(self, event: Dict[str, Any]) -> None:
        event["sequence"] = len(self._events) + 1
        self._events.append(self._redaction.redact(event))

    def on_tool_start(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        call_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        if self._final_seen:
            raise ValueError("tool start cannot occur after final_answer")
        if not isinstance(tool, str) or not tool:
            raise ValueError("framework tool name must be a non-empty string")
        if not isinstance(arguments, Mapping):
            raise ValueError("framework tool arguments must be an object")
        if call_id is None:
            self._call_counter += 1
            call_id = f"call-{self._call_counter}"
        if not isinstance(call_id, str) or not call_id or call_id in self._seen_call_ids:
            raise ValueError("framework call_id must be unique and non-empty")
        self._seen_call_ids.add(call_id)
        self._pending[call_id] = tool
        event: Dict[str, Any] = {
            "type": "tool_call",
            "call_id": call_id,
            "tool": tool,
            "arguments": deepcopy(dict(arguments)),
        }
        if metadata:
            event["metadata"] = deepcopy(dict(metadata))
        self._append(event)
        return call_id

    def on_tool_end(
        self,
        call_id: str,
        result: Any,
        *,
        is_error: bool = False,
        error: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if call_id not in self._pending:
            raise ValueError(f"framework tool result references unknown call_id {call_id!r}")
        if not isinstance(is_error, bool):
            raise ValueError("framework tool result is_error must be a boolean")
        del self._pending[call_id]
        if isinstance(result, ToolExecutionResult):
            is_error = result.is_error
            error = result.error
            result_value = result.result
            combined_metadata = dict(result.metadata or {})
            combined_metadata.update(dict(metadata or {}))
            metadata = combined_metadata
        else:
            result_value = result
        event: Dict[str, Any] = {
            "type": "tool_result",
            "call_id": call_id,
            "result": deepcopy(result_value),
            "is_error": is_error,
        }
        if error:
            event["error"] = error
        if metadata:
            event["metadata"] = deepcopy(dict(metadata))
        self._append(event)

    def on_final_answer(
        self,
        text: str,
        claims: Mapping[str, Any] | None = None,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if self._final_seen:
            raise ValueError("framework emitted more than one final_answer")
        if self._pending:
            raise ValueError(
                "framework final_answer arrived before tool results: "
                + ", ".join(sorted(self._pending))
            )
        if not isinstance(text, str):
            raise ValueError("framework final answer text must be a string")
        event: Dict[str, Any] = {"type": "final_answer", "text": text}
        if claims is not None:
            if not isinstance(claims, Mapping):
                raise ValueError("framework final answer claims must be an object")
            event["claims"] = deepcopy(dict(claims))
        if metadata:
            event["metadata"] = deepcopy(dict(metadata))
        self._append(event)
        self._final_seen = True

    def finish(self) -> AgentTrace:
        if self._pending:
            raise ValueError(
                "framework run ended with pending tool calls: "
                + ", ".join(sorted(self._pending))
            )
        if not self._final_seen:
            raise ValueError("framework run did not emit final_answer")
        trace = AgentTrace(
            schema_version=SUPPORTED_SCHEMA_VERSION,
            run_id=self._run_id,
            agent=self._redaction.redact(self._identity),
            events=self.events,
            metadata=self._redaction.redact(
                {"input": self._request, **self._metadata}
            ),
        )
        trace.validate()
        return trace

    # Short aliases make adapters read naturally inside framework callbacks.
    tool_start = on_tool_start
    tool_end = on_tool_end
    final_answer = on_final_answer


def record_framework_run(
    identity: Mapping[str, Any],
    runner: Callable[[Any, FrameworkTraceRecorder], Any],
    request: Any,
    *,
    run_id: str,
    metadata: Mapping[str, Any] | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> AgentTrace:
    """Run a framework callback and convert its lifecycle events to a Trace."""

    recorder = FrameworkTraceRecorder(
        identity,
        run_id=run_id,
        request=request,
        metadata=metadata,
        redaction_policy=redaction_policy,
    )
    runner(request, recorder)
    return recorder.finish()
