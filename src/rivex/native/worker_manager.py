"""``rivex.native.worker_manager`` — multi-process worker management & shared in-memory state."""

from __future__ import annotations

from typing import Any, Callable

__all__ = ["SharedState", "WorkerManager"]


class SharedState:
    """In-memory key-value store for cross-worker state sharing."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def set_str(self, key: str, value: str) -> None:
        """Store ``value`` as a string under ``key``, coercing non-strings.

        Args:
            key: The key to associate the value with.
            value: The value to store; passed through :func:`str` so
                integers, floats, and other primitives are stored as
                their canonical string form.
        """
        self._store[key] = str(value)

    def set_int(self, key: str, value: int) -> None:
        """Store ``value`` as an integer under ``key``, coercing numeric inputs.

        Args:
            key: The key to associate the value with.
            value: The value to store; passed through :func:`int` so
                string-encoded numbers and booleans are normalised.
        """
        self._store[key] = int(value)

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value stored under ``key`` or ``default`` if absent.

        Args:
            key: The key to look up.
            default: Value to return when ``key`` is not present.

        Returns:
            The stored value, or ``default`` when the key is missing.
        """
        return self._store.get(key, default)

    def contains(self, key: str) -> bool:
        """Return whether ``key`` is currently set in the store.

        Args:
            key: The key to test for membership.

        Returns:
            ``True`` when ``key`` has an entry, ``False`` otherwise.
        """
        return key in self._store

    def increment(self, key: str, amount: int = 1) -> int:
        """Atomically (within this process) add ``amount`` to the value at ``key``.

        Treats a missing or non-numeric entry as ``0`` before adding,
        so the call can be used for both first-time and accumulated
        counters. The result is stored back as an integer.

        Args:
            key: The counter key to update.
            amount: How much to add to the current value; defaults to
                ``1`` for a typical counter increment.

        Returns:
            The new counter value after the increment.
        """
        val = int(self._store.get(key, 0)) + amount
        self._store[key] = val
        return val


class WorkerManager:
    """Manages worker processes, background tasks, and shared state."""

    def __init__(self, app: Any) -> None:
        self._app = app
        self.shared_state = SharedState()
        self._background_processes: list[Callable] = []
        self._custom_processes: list[Callable] = []

    def background_process(self, fn: Callable) -> Callable:
        """Register ``fn`` as a background process and return it unchanged.

        Used as a decorator so that callers can mark a function as a
        long-running background task: ``@worker_manager.background_process``.

        Args:
            fn: The callable to register as a background process.

        Returns:
            ``fn`` itself, so the call can be used as a decorator.
        """
        self._background_processes.append(fn)
        return fn

    def custom_process(self, fn: Callable) -> Callable:
        """Register ``fn`` as a custom process and return it unchanged.

        Used as a decorator to mark a function as a one-off custom
        process handled outside the standard background loop.

        Args:
            fn: The callable to register as a custom process.

        Returns:
            ``fn`` itself, so the call can be used as a decorator.
        """
        self._custom_processes.append(fn)
        return fn
