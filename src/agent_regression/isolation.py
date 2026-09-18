"""Snapshot/restore boundaries for isolated Agent scenarios."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol


class SnapshotBackend(Protocol):
    """Small boundary an external database/cache fixture can implement."""

    def snapshot(self) -> Any: ...

    def restore(self, snapshot: Any) -> None: ...


class StateIsolation:
    """Context manager that restores a backend after one scenario.

    The backend may be an in-memory ``StatefulFixtureTools`` instance or an
    adapter around a test database, cache, or service emulator. Snapshots are
    detached before the scenario starts and before restore is called.
    """

    def __init__(self, backend: SnapshotBackend):
        self.backend = backend
        self._snapshot: Any = None
        self._entered = False

    def __enter__(self) -> "StateIsolation":
        if not callable(getattr(self.backend, "snapshot", None)):
            raise TypeError("state backend must provide snapshot()")
        if not callable(getattr(self.backend, "restore", None)):
            raise TypeError("state backend must provide restore(snapshot)")
        self._snapshot = deepcopy(self.backend.snapshot())
        self._entered = True
        return self

    def restore(self) -> None:
        if not self._entered:
            raise RuntimeError("state isolation has not been entered")
        self.backend.restore(deepcopy(self._snapshot))

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.restore()
        self._entered = False
        return False
