from __future__ import annotations

from typing import Any, Dict, List, Mapping, Protocol


class RunContext(Protocol):
    def call_tool(self, tool: str, arguments: Dict[str, Any]) -> Any: ...

    def final_answer(self, text: str, claims: Dict[str, Any] | None = None) -> None: ...


class AgentAdapter(Protocol):
    """Framework boundary: translate one real agent run into RunContext calls."""

    @property
    def identity(self) -> Mapping[str, Any]: ...

    def run(self, request: Any, context: RunContext) -> None: ...


class ScriptedAgentAdapter:
    """Deterministic adapter for testing the recorder without a model or network."""

    def __init__(self, identity: Mapping[str, Any], plan: List[Mapping[str, Any]]):
        self._identity = dict(identity)
        self._plan = [dict(action) for action in plan]

    @property
    def identity(self) -> Mapping[str, Any]:
        return self._identity

    def run(self, request: Any, context: RunContext) -> None:
        del request
        for action in self._plan:
            action_type = action.get("type")
            if action_type == "tool_call":
                context.call_tool(action["tool"], dict(action.get("arguments", {})))
            elif action_type == "final_answer":
                context.final_answer(action.get("text", ""), dict(action.get("claims", {})))
            else:
                raise ValueError(f"unsupported scripted action: {action_type!r}")
