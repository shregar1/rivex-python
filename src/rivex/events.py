from __future__ import annotations

import asyncio
import inspect
import warnings
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
        """Send signal synchronously. Returns list of (receiver, response) tuples.

        .. note::
            Receivers registered with ``async def`` are NOT awaited
            here — they are called and the resulting coroutine
            object is stored. To dispatch to async receivers, use
            :meth:`send_async` instead. The mismatch is detected
            and a one-shot warning is emitted per receiver.
        """
        results = []
        for receiver, bound_sender in self._receivers:
            if bound_sender is not None and bound_sender is not sender:
                continue
            if inspect.iscoroutinefunction(receiver):
                warnings.warn(
                    f"Signal {self.name!r}: receiver {receiver!r} is a "
                    f"coroutine function; use send_async() to await it. "
                    f"send() will return the coroutine object without "
                    f"executing it.",
                    stacklevel=2,
                )
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
