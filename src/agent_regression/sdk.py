"""Small SDK helpers for building framework-specific Agent adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping

from .adapters import (
    AsyncCallableAgentAdapter,
    AsyncRunContext,
    CallableAgentAdapter,
    RunContext,
)


@dataclass(frozen=True)
class AdapterSpec:
    """Reusable Agent identity and adapter factory for an integration project.

    The spec keeps framework-specific code in a callback while guaranteeing a
    consistent identity object for sync and async traces.
    """

    name: str
    version: str = "0.1.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("adapter name must not be empty")
        if not self.version.strip():
            raise ValueError("adapter version must not be empty")

    def identity(self) -> Dict[str, Any]:
        value = {"name": self.name, "version": self.version}
        value.update(dict(self.metadata))
        return value

    def build_sync(
        self,
        runner: Callable[[Any, RunContext], None],
    ) -> CallableAgentAdapter:
        """Build a synchronous adapter around a framework callback."""
        return CallableAgentAdapter(self.identity(), runner)

    def build_async(
        self,
        runner: Callable[[Any, AsyncRunContext], Any],
    ) -> AsyncCallableAgentAdapter:
        """Build an asynchronous adapter around a framework callback."""
        return AsyncCallableAgentAdapter(self.identity(), runner)
