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
        """Register *receiver* as a listener for this signal.

        Args:
            receiver: Callable to invoke when the signal is sent. May be a
                regular function or a coroutine function — coroutine
                receivers are only awaited by :meth:`send_async`.
            sender: Optional sender object the receiver is bound to. When
                not ``None`` the receiver fires only for dispatches whose
                ``sender`` matches; ``None`` means "respond to any sender".
        """
        self._receivers.append((receiver, sender))

    def disconnect(self, receiver: Callable, sender: Any = None) -> None:
        """Remove every registration of *receiver* paired with *sender*.

        Both arguments are matched together: a *receiver* registered with a
        different ``sender`` is left in place. Removing a non-existent
        registration is a no-op.

        Args:
            receiver: The callable previously passed to :meth:`connect`.
            sender: The sender value the registration was stored under.
        """
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
            """Connect *func* to the signal and return it unchanged.

            Args:
                func: The callable to register as a receiver.

            Returns:
                The original *func* so the decorator is transparent at
                runtime and introspection still sees the function's own
                name and docstring.
            """
            self.connect(func, sender)
            return func

        return decorator


# Pre-defined framework signals
request_started = Signal("request_started")
request_finished = Signal("request_finished")
request_failed = Signal("request_failed")
server_startup = Signal("server_startup")
server_shutdown = Signal("server_shutdown")
