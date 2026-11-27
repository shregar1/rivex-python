"""``rivex.lifecycle.signals`` — lightweight async signal/event bus.

Provides :class:`SignalBus` for decoupled publish/subscribe communication and
a module-level :data:`signal_bus` singleton for application-wide use.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from typing import Any, Callable

__all__ = ["SignalBus", "signal_bus"]

logger = logging.getLogger(__name__)


class SignalBus:
    """Async-first publish/subscribe signal bus.

    Example::

        bus = SignalBus()

        @bus.on("user.created")
        async def notify(user_id: int):
            ...

        await bus.emit("user.created", user_id=42)
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    # ── Registration ──────────────────────────────────────────────────────────

    def on(self, signal: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator that registers *handler* as a listener for *signal*."""

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            """Register *handler* in the listener list and return it unchanged.

            Subscribes the wrapped callable to *signal* via :meth:`subscribe` and
            returns it untouched so the original name and module remain
            accessible to introspection-based tools.

            Args:
                handler: The callable to register as a listener for *signal*.

            Returns:
                The same *handler* instance, allowing the decorator to be used
                as a transparent attribute-preserving wrapper.
            """
            self.subscribe(signal, handler)
            return handler

        return decorator

    def subscribe(self, signal: str, handler: Callable[..., Any]) -> None:
        """Imperatively subscribe *handler* to *signal*."""
        self._listeners[signal].append(handler)

    def unsubscribe(self, signal: str, handler: Callable[..., Any]) -> None:
        """Remove *handler* from *signal*'s listener list (no-op if absent)."""
        try:
            self._listeners[signal].remove(handler)
        except ValueError:
            pass

    # ── Emission ──────────────────────────────────────────────────────────────

    async def emit(self, signal: str, **kwargs: Any) -> None:
        """Emit *signal*, calling all registered listeners with *kwargs*.

        Listener errors are caught and logged individually so that remaining
        listeners are always executed.
        """
        for handler in list(self._listeners.get(signal, [])):
            try:
                result = handler(**kwargs)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception(
                    "Signal listener %r raised an error for signal %r",
                    getattr(handler, "__qualname__", handler),
                    signal,
                )

    # ── Introspection ─────────────────────────────────────────────────────────

    def listeners(self, signal: str) -> list[Callable[..., Any]]:
        """Return the list of listeners currently registered for *signal*."""
        return list(self._listeners.get(signal, []))

    def signals(self) -> list[str]:
        """Return all signal names that have at least one listener."""
        return [s for s, ls in self._listeners.items() if ls]

    def clear(self, signal: str) -> None:
        """Remove all listeners for *signal*."""
        self._listeners[signal] = []


#: Module-level singleton — use this for application-wide signals.
signal_bus: SignalBus = SignalBus()
