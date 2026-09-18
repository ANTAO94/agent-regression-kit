from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Protocol


class RunContext(Protocol):
    def call_tool(self, tool: str, arguments: Dict[str, Any]) -> Any: ...

    def final_answer(self, text: str, claims: Dict[str, Any] | None = None) -> None: ...


class AgentAdapter(Protocol):
    """Framework boundary: translate one real agent run into RunContext calls."""

    @property
    def identity(self) -> Mapping[str, Any]: ...

    def run(self, request: Any, context: RunContext) -> None: ...


class AsyncRunContext(Protocol):
    """Context used by an Agent that awaits parallel tool calls."""

    def call_tool(
        self,
        tool: str,
        arguments: Dict[str, Any],
        *,
        parallel_group: str | None = None,
    ) -> Awaitable[Any]: ...

    def final_answer(self, text: str, claims: Dict[str, Any] | None = None) -> None: ...


class AsyncAgentAdapter(Protocol):
    """Framework boundary for an asynchronous Agent run."""

    @property
    def identity(self) -> Mapping[str, Any]: ...

    async def run(self, request: Any, context: AsyncRunContext) -> None: ...


class CallableAgentAdapter:
    """Adapt a framework-owned callable to the stable AgentAdapter boundary.

    The callable receives the framework request and the kit's ``RunContext``.
    A real integration can therefore keep its framework-specific ``invoke``
    code in one function without re-implementing the recorder protocol for
    every test case.
    """

    def __init__(self, identity: Mapping[str, Any], runner: Callable[[Any, RunContext], None]):
        if not callable(runner):
            raise TypeError("Agent runner must be callable")
        self._identity = dict(identity)
        self._runner = runner

    @property
    def identity(self) -> Mapping[str, Any]:
        return self._identity

    def run(self, request: Any, context: RunContext) -> None:
        self._runner(request, context)


class AsyncCallableAgentAdapter:
    """Adapt an async framework callback to the async recording boundary."""

    def __init__(
        self,
        identity: Mapping[str, Any],
        runner: Callable[[Any, AsyncRunContext], Awaitable[None]],
    ):
        if not callable(runner):
            raise TypeError("Agent runner must be callable")
        self._identity = dict(identity)
        self._runner = runner

    @property
    def identity(self) -> Mapping[str, Any]:
        return self._identity

    async def run(self, request: Any, context: AsyncRunContext) -> None:
        result = self._runner(request, context)
        if not hasattr(result, "__await__"):
            raise TypeError("Async Agent runner must return an awaitable")
        await result


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


class AsyncScriptedAgentAdapter:
    """Deterministic async adapter with explicit parallel tool-call groups."""

    def __init__(
        self,
        identity: Mapping[str, Any],
        parallel_plan: List[List[Mapping[str, Any]]],
        final_answer: Mapping[str, Any],
    ):
        self._identity = dict(identity)
        self._parallel_plan = [
            [dict(action) for action in group] for group in parallel_plan
        ]
        self._final_answer = dict(final_answer)

    @property
    def identity(self) -> Mapping[str, Any]:
        return self._identity

    async def run(self, request: Any, context: AsyncRunContext) -> None:
        del request
        for index, group in enumerate(self._parallel_plan, start=1):
            if not group:
                raise ValueError("async parallel groups must not be empty")
            results = await asyncio.gather(
                *[
                    context.call_tool(
                        action["tool"],
                        dict(action.get("arguments", {})),
                        parallel_group=f"group-{index}",
                    )
                    for action in group
                ]
            )
            del results
        if self._final_answer.get("type", "final_answer") != "final_answer":
            raise ValueError("async final_answer must have type 'final_answer'")
        context.final_answer(
            str(self._final_answer.get("text", "")),
            dict(self._final_answer.get("claims", {})),
        )


class ScriptedSessionAdapter:
    """Deterministic multi-turn adapter with one plan per user turn."""

    def __init__(self, identity: Mapping[str, Any], plans: List[List[Mapping[str, Any]]]):
        self._identity = dict(identity)
        self._plans = [[dict(action) for action in plan] for plan in plans]
        self._turn = 0

    @property
    def identity(self) -> Mapping[str, Any]:
        return self._identity

    def run(self, request: Any, context: RunContext) -> None:
        if self._turn >= len(self._plans):
            raise ValueError("scripted session received more turns than configured plans")
        ScriptedAgentAdapter(self._identity, self._plans[self._turn]).run(request, context)
        self._turn += 1
