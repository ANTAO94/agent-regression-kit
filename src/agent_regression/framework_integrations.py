"""Optional framework result adapters with no mandatory framework dependencies."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .framework import FrameworkTraceRecorder
from .model import AgentTrace
from .redaction import RedactionPolicy


ClaimsExtractor = Callable[[Any], Mapping[str, Any]]


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    dumper = getattr(value, "model_dump", None)
    return dumper(mode="json") if callable(dumper) else value


def _arguments(part: Any) -> dict[str, Any]:
    converter = getattr(part, "args_as_dict", None)
    value = converter() if callable(converter) else _field(part, "args", _field(part, "arguments", {}))
    value = _json_value(value)
    if not isinstance(value, Mapping):
        raise ValueError("framework tool arguments must decode to an object")
    return dict(value)


def _answer(output: Any, claims_extractor: ClaimsExtractor | None) -> tuple[str, Mapping[str, Any]]:
    serialized = _json_value(output)
    claims = claims_extractor(output) if claims_extractor else (
        dict(serialized) if isinstance(serialized, Mapping) else {}
    )
    if not isinstance(claims, Mapping):
        raise ValueError("claims_extractor must return a mapping")
    text = output if isinstance(output, str) else json.dumps(serialized, ensure_ascii=False, sort_keys=True)
    return text, dict(claims)


def trace_from_pydantic_ai_result(
    result: Any,
    request: Any,
    *,
    run_id: str,
    identity: Mapping[str, Any] | None = None,
    claims_extractor: ClaimsExtractor | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> AgentTrace:
    """Convert a completed PydanticAI ``AgentRunResult`` into AgentTrace."""
    recorder = FrameworkTraceRecorder(
        identity or {"name": "pydantic-ai-agent", "version": "unknown", "framework": "pydantic-ai"},
        run_id=run_id,
        request=request,
        redaction_policy=redaction_policy,
    )
    messages = result.all_messages() if callable(getattr(result, "all_messages", None)) else []
    for message in messages:
        for part in _field(message, "parts", ()):
            kind = type(part).__name__
            call_id = _field(part, "tool_call_id")
            if kind == "ToolCallPart":
                recorder.tool_start(
                    _field(part, "tool_name"),
                    _arguments(part),
                    call_id=call_id,
                )
            elif kind == "ToolReturnPart":
                recorder.tool_end(call_id, _json_value(_field(part, "content")))
    output = _field(result, "output")
    text, claims = _answer(output, claims_extractor)
    recorder.final_answer(text, claims)
    return recorder.finish()


def trace_from_openai_agents_result(
    result: Any,
    request: Any,
    *,
    run_id: str,
    identity: Mapping[str, Any] | None = None,
    claims_extractor: ClaimsExtractor | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> AgentTrace:
    """Convert a completed OpenAI Agents SDK ``RunResult`` into AgentTrace."""
    recorder = FrameworkTraceRecorder(
        identity or {"name": "openai-agents-agent", "version": "unknown", "framework": "openai-agents"},
        run_id=run_id,
        request=request,
        redaction_policy=redaction_policy,
    )
    for item in _field(result, "new_items", ()):
        kind = type(item).__name__
        raw = _field(item, "raw_item", {})
        if kind == "ToolCallItem":
            recorder.tool_start(
                _field(raw, "name"),
                _arguments(raw),
                call_id=_field(raw, "call_id", _field(raw, "id")),
            )
        elif kind == "ToolCallOutputItem":
            recorder.tool_end(
                _field(raw, "call_id"),
                _json_value(_field(item, "output", _field(raw, "output"))),
            )
    output = _field(result, "final_output")
    text, claims = _answer(output, claims_extractor)
    recorder.final_answer(text, claims)
    return recorder.finish()


def trace_from_langgraph_result(
    result: Mapping[str, Any],
    request: Any,
    *,
    run_id: str,
    identity: Mapping[str, Any] | None = None,
    claims_extractor: ClaimsExtractor | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> AgentTrace:
    """Convert a completed LangGraph message state into AgentTrace."""
    messages: Sequence[Any] = result.get("messages", ())
    recorder = FrameworkTraceRecorder(
        identity or {"name": "langgraph-agent", "version": "unknown", "framework": "langgraph"},
        run_id=run_id,
        request=request,
        redaction_policy=redaction_policy,
    )
    final_output: Any = result.get("structured_response")
    for message in messages:
        tool_calls = _field(message, "tool_calls", ()) or ()
        for call in tool_calls:
            recorder.tool_start(
                _field(call, "name"),
                dict(_field(call, "args", {}) or {}),
                call_id=_field(call, "id"),
            )
        if type(message).__name__ == "ToolMessage":
            recorder.tool_end(
                _field(message, "tool_call_id"),
                _json_value(_field(message, "content")),
            )
        elif type(message).__name__ in {"AIMessage", "AIMessageChunk"} and not tool_calls:
            final_output = _field(message, "content")
    text, claims = _answer(final_output, claims_extractor)
    recorder.final_answer(text, claims)
    return recorder.finish()
