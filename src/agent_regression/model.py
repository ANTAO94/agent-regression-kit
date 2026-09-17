from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping


SUPPORTED_SCHEMA_VERSION = "0.1"
EVENT_TYPES = {"tool_call", "tool_result", "final_answer"}


class TraceValidationError(ValueError):
    """Raised when evidence does not satisfy AgentTrace v0.1."""


@dataclass(frozen=True)
class AgentTrace:
    schema_version: str
    run_id: str
    agent: Dict[str, Any]
    events: List[Dict[str, Any]]
    metadata: Dict[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AgentTrace":
        trace = cls(
            schema_version=value.get("schema_version", ""),
            run_id=value.get("run_id", ""),
            agent=dict(value.get("agent", {})),
            events=[dict(event) for event in value.get("events", [])],
            metadata=dict(value.get("metadata", {})),
        )
        trace.validate()
        return trace

    def validate(self) -> None:
        if self.schema_version != SUPPORTED_SCHEMA_VERSION:
            raise TraceValidationError(
                f"unsupported schema_version {self.schema_version!r}; expected {SUPPORTED_SCHEMA_VERSION!r}"
            )
        if not self.run_id:
            raise TraceValidationError("run_id must be a non-empty string")
        if not isinstance(self.agent.get("name"), str) or not self.agent["name"]:
            raise TraceValidationError("agent.name must be a non-empty string")
        if not self.events:
            raise TraceValidationError("events must not be empty")

        pending_calls: Dict[str, str] = {}
        final_count = 0
        for expected_sequence, event in enumerate(self.events, start=1):
            if event.get("sequence") != expected_sequence:
                raise TraceValidationError(
                    f"event sequence must be contiguous from 1; got {event.get('sequence')!r} at position {expected_sequence}"
                )
            event_type = event.get("type")
            if event_type not in EVENT_TYPES:
                raise TraceValidationError(f"unsupported event type {event_type!r}")
            if event_type == "tool_call":
                call_id = event.get("call_id")
                if not call_id or call_id in pending_calls:
                    raise TraceValidationError("tool_call.call_id must be unique and non-empty")
                if not event.get("tool") or not isinstance(event.get("arguments"), dict):
                    raise TraceValidationError("tool_call requires tool and object arguments")
                pending_calls[call_id] = event["tool"]
            elif event_type == "tool_result":
                call_id = event.get("call_id")
                if call_id not in pending_calls:
                    raise TraceValidationError(f"tool_result references unknown call_id {call_id!r}")
                if not isinstance(event.get("is_error"), bool):
                    raise TraceValidationError("tool_result.is_error must be a boolean")
                if "result" not in event:
                    raise TraceValidationError("tool_result.result is required")
                del pending_calls[call_id]
            else:
                final_count += 1
                if not isinstance(event.get("text"), str):
                    raise TraceValidationError("final_answer.text must be a string")
                if "claims" in event and not isinstance(event["claims"], dict):
                    raise TraceValidationError("final_answer.claims must be an object when present")

        if pending_calls:
            raise TraceValidationError(f"tool calls without results: {sorted(pending_calls)}")
        if final_count != 1 or self.events[-1].get("type") != "final_answer":
            raise TraceValidationError("trace must end with exactly one final_answer")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "agent": self.agent,
            "events": self.events,
            "metadata": self.metadata,
        }
