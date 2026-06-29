from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class Signal:
    """Django-style signal for decoupled event handling."""

    def __init__(self, name: str = ""):
        self.name = name
        self._receivers: list[tuple[Callable, Any]] = []

    def connect(self, receiver: Callable, sender: Any = None) -> None:
        self._receivers.append((receiver, sender))

    def disconnect(self, receiver: Callable, sender: Any = None) -> None:
        self._receivers = [
            (r, s) for r, s in self._receivers if not (r == receiver and s == sender)
        ]

    def send(self, sender: Any = None, **kwargs: Any) -> list:
        """Send signal synchronously. Returns list of (receiver, response) tuples."""
        results = []
        for receiver, bound_sender in self._receivers:
            if bound_sender is not None and bound_sender is not sender:
                continue
            result = receiver(sender=sender, **kwargs)
            results.append((receiver, result))
        return results

    async def send_async(self, sender: Any = None, **kwargs: Any) -> list:
        """Send signal asynchronously."""
        results = []
        for receiver, bound_sender in self._receivers:
            if bound_sender is not None and bound_sender is not sender:
                continue
            result = receiver(sender=sender, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            results.append((receiver, result))
        return results

    def receiver(self, sender: Any = None):
        """Decorator to connect a receiver."""

        def decorator(func):
            self.connect(func, sender)
            return func

        return decorator


# Pre-defined framework signals
request_started = Signal("request_started")
request_finished = Signal("request_finished")
request_failed = Signal("request_failed")
server_startup = Signal("server_startup")
server_shutdown = Signal("server_shutdown")
