from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Protocol

from .adapters import AgentAdapter
from .model import AgentTrace, SUPPORTED_SCHEMA_VERSION
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


@dataclass(frozen=True)
class ToolExecutionResult:
    """Normalized tool output for executors that expose explicit error state."""

    result: Any
    is_error: bool = False
    error: str | None = None
    metadata: Mapping[str, Any] | None = None


class ToolExecutor(Protocol):
    def call(self, tool: str, arguments: Dict[str, Any]) -> Any: ...


class FixtureTools:
    """Offline tool executor keyed by tool name."""

    def __init__(self, results: Mapping[str, Any]):
        self._results = deepcopy(dict(results))

    def call(self, tool: str, arguments: Dict[str, Any]) -> Any:
        del arguments
        if tool not in self._results:
            raise KeyError(f"no fixture result for tool {tool!r}")
        return deepcopy(self._results[tool])


class _RecordingContext:
    def __init__(self, tools: ToolExecutor, redaction_policy: RedactionPolicy):
        self.tools = tools
        self.redaction_policy = redaction_policy
        self.events: list[Dict[str, Any]] = []
        self._call_counter = 0

    def _append(self, event: Dict[str, Any]) -> None:
        event["sequence"] = len(self.events) + 1
        self.events.append(event)

    def call_tool(self, tool: str, arguments: Dict[str, Any]) -> Any:
        self._call_counter += 1
        call_id = f"call-{self._call_counter}"
        self._append(
            {
                "type": "tool_call",
                "call_id": call_id,
                "tool": tool,
                "arguments": self.redaction_policy.redact(deepcopy(arguments)),
            }
        )
        try:
            execution = self.tools.call(tool, arguments)
        except Exception as exc:
            self._append(
                {
                    "type": "tool_result",
                    "call_id": call_id,
                    "result": None,
                    "is_error": True,
                    "error": self.redaction_policy.redact(str(exc)),
                }
            )
            raise
        if isinstance(execution, ToolExecutionResult):
            result = self.redaction_policy.redact(execution.result)
            is_error = execution.is_error
            error = self.redaction_policy.redact(execution.error)
            event_metadata = self.redaction_policy.redact(dict(execution.metadata or {}))
        else:
            result = self.redaction_policy.redact(execution)
            is_error = False
            error = None
            event_metadata = {}
        event = {
            "type": "tool_result",
            "call_id": call_id,
            "result": result,
            "is_error": is_error,
        }
        if error:
            event["error"] = error
        if event_metadata:
            event["metadata"] = event_metadata
        self._append(event)
        return result

    def final_answer(self, text: str, claims: Dict[str, Any] | None = None) -> None:
        event: Dict[str, Any] = {
            "type": "final_answer",
            "text": self.redaction_policy.redact(text),
        }
        if claims:
            event["claims"] = self.redaction_policy.redact(deepcopy(claims))
        self._append(event)


def record_run(
    adapter: AgentAdapter,
    request: Any,
    tools: ToolExecutor,
    *,
    run_id: str,
    metadata: Mapping[str, Any] | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> AgentTrace:
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    context = _RecordingContext(tools, active_redaction)
    adapter.run(request, context)
    trace = AgentTrace(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        run_id=run_id,
        agent=active_redaction.redact(dict(adapter.identity)),
        events=context.events,
        metadata=active_redaction.redact(
            {"input": deepcopy(request), **dict(metadata or {})}
        ),
    )
    trace.validate()
    return trace
