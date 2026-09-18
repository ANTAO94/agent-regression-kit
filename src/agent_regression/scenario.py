"""Deterministic stateful fixtures for Agent scenario tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, Mapping

from .isolation import StateIsolation


class WorldState:
    """Mutable, snapshot-able state owned by one scenario execution.

    A new ``WorldState`` should be created for every case.  The class keeps
    the ownership rule explicit and makes it difficult for one test run to
    accidentally reuse another run's mutated data.
    """

    def __init__(self, initial: Mapping[str, Any] | None = None):
        self.data: Dict[str, Any] = deepcopy(dict(initial or {}))

    def snapshot(self) -> Dict[str, Any]:
        """Return a detached JSON-like copy suitable for a Trace."""
        return deepcopy(self.data)

    def reset(self, initial: Mapping[str, Any] | None = None) -> None:
        """Reset this state to a detached copy of ``initial``."""
        self.data = deepcopy(dict(initial or {}))

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        """Restore a previously captured snapshot."""
        self.data = deepcopy(dict(snapshot))


ToolHandler = Callable[[WorldState, Dict[str, Any]], Any]


class StatefulFixtureTools:
    """Offline tool executor whose calls can read and mutate ``WorldState``.

    ``handlers`` receive the current world and a detached argument object:

    .. code-block:: python

        def cancel_order(world, arguments):
            order = world.data["orders"][arguments["order_id"]]
            order["status"] = "cancelled"
            return order

    Use ``fresh()`` to create an isolated executor for another case.
    """

    def __init__(
        self,
        initial_state: Mapping[str, Any] | None = None,
        handlers: Mapping[str, ToolHandler] | None = None,
    ):
        self._initial_state = deepcopy(dict(initial_state or {}))
        self.world = WorldState(self._initial_state)
        self._handlers = dict(handlers or {})

    def call(self, tool: str, arguments: Dict[str, Any]) -> Any:
        if tool not in self._handlers:
            raise KeyError(f"no stateful fixture handler for tool {tool!r}")
        return deepcopy(self._handlers[tool](self.world, deepcopy(arguments)))

    def snapshot(self) -> Dict[str, Any]:
        return self.world.snapshot()

    def reset(self) -> None:
        self.world.reset(self._initial_state)

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        self.world.restore(snapshot)

    def isolation(self) -> StateIsolation:
        """Create a context manager that restores this fixture on exit."""
        return StateIsolation(self)

    def fresh(self) -> "StatefulFixtureTools":
        """Return a new executor with the original state and same handlers."""
        return StatefulFixtureTools(self._initial_state, self._handlers)
