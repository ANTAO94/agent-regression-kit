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
        if not isinstance(value, Mapping):
            raise TraceValidationError("trace must be an object")
        unknown = sorted(set(value) - {"schema_version", "run_id", "agent", "events", "metadata"})
        if unknown:
            raise TraceValidationError(
                "unsupported trace fields: " + ", ".join(map(str, unknown))
            )
        if not isinstance(value.get("agent", {}), Mapping):
            raise TraceValidationError("agent must be an object")
        if not isinstance(value.get("events", []), list) or not all(
            isinstance(event, Mapping) for event in value.get("events", [])
        ):
            raise TraceValidationError("events must be an array of objects")
        if not isinstance(value.get("metadata", {}), Mapping):
            raise TraceValidationError("metadata must be an object")
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
        if not isinstance(self.run_id, str) or not self.run_id:
            raise TraceValidationError("run_id must be a non-empty string")
        if not isinstance(self.agent.get("name"), str) or not self.agent["name"]:
            raise TraceValidationError("agent.name must be a non-empty string")
        if not self.events:
            raise TraceValidationError("events must not be empty")

        pending_calls: Dict[str, str] = {}
        seen_call_ids: set[str] = set()
        final_count = 0
        for expected_sequence, event in enumerate(self.events, start=1):
            sequence = event.get("sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
                raise TraceValidationError("event sequence must be a positive integer")
            if event.get("sequence") != expected_sequence:
                raise TraceValidationError(
                    f"event sequence must be contiguous from 1; got {event.get('sequence')!r} at position {expected_sequence}"
                )
            event_type = event.get("type")
            if event_type not in EVENT_TYPES:
                raise TraceValidationError(f"unsupported event type {event_type!r}")
            allowed_fields = {
                "tool_call": {"sequence", "type", "call_id", "tool", "arguments", "metadata"},
                "tool_result": {"sequence", "type", "call_id", "result", "is_error", "error", "metadata"},
                "final_answer": {"sequence", "type", "text", "claims", "metadata"},
            }[event_type]
            unknown_fields = sorted(set(event) - allowed_fields)
            if unknown_fields:
                raise TraceValidationError(
                    f"unsupported {event_type} fields: " + ", ".join(map(str, unknown_fields))
                )
            if "metadata" in event and not isinstance(event["metadata"], dict):
                raise TraceValidationError(f"{event_type}.metadata must be an object")
            if event_type == "tool_call":
                call_id = event.get("call_id")
                if not isinstance(call_id, str) or not call_id or call_id in seen_call_ids:
                    raise TraceValidationError("tool_call.call_id must be unique and non-empty")
                if (
                    not isinstance(event.get("tool"), str)
                    or not event["tool"]
                    or not isinstance(event.get("arguments"), dict)
                ):
                    raise TraceValidationError("tool_call requires tool and object arguments")
                seen_call_ids.add(call_id)
                pending_calls[call_id] = event["tool"]
            elif event_type == "tool_result":
                call_id = event.get("call_id")
                if not isinstance(call_id, str) or not call_id:
                    raise TraceValidationError("tool_result.call_id must be a non-empty string")
                if call_id not in pending_calls:
                    raise TraceValidationError(f"tool_result references unknown call_id {call_id!r}")
                if not isinstance(event.get("is_error"), bool):
                    raise TraceValidationError("tool_result.is_error must be a boolean")
                if "result" not in event:
                    raise TraceValidationError("tool_result.result is required")
                if "error" in event and not isinstance(event["error"], str):
                    raise TraceValidationError("tool_result.error must be a string")
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
