"""``rivex.websockets`` — async ``WebSocket`` wrapper + ``@app.websocket`` decorator.

The Rust side (``rivex_core.PyWebSocket``) gives us sync ``recv``,
``send_text``, ``send_bytes``, and ``close`` methods that block the
calling thread while waiting on a Tokio ``mpsc``. Those blocks release
the GIL — so other Python work (other connections, HTTP handlers) keeps
running concurrently despite the GIL.

This module wraps those sync methods in an async surface using
``loop.run_in_executor`` so user handlers look like

.. code-block:: python

    @app.websocket("/ws")
    async def echo(ws: WebSocket):
        while True:
            msg = await ws.receive_text()
            if msg is None:
                break
            await ws.send_text(f"echo: {msg}")

with normal ``await`` semantics. Each connection runs in its own
dedicated thread (spawned by the Rust handler), with its own asyncio
event loop — so this executor is the loop's default thread pool and
the blocking call runs there.
"""

from __future__ import annotations

import asyncio
from typing import Any


class WebSocket:
    """Async wrapper over ``rivex_core.PyWebSocket``."""

    __slots__ = ("_raw", "_loop")

    def __init__(self, raw: Any) -> None:
        self._raw = raw
        # Pin the loop here — the Rust handler thread runs a freshly
        # created loop, so getting it once and re-using is fine.
        self._loop = asyncio.get_event_loop()

    async def receive(self) -> tuple[str, str | bytes] | None:
        """Receive the next message.

        Returns ``("text", str)`` or ``("binary", bytes)``, or ``None``
        if the peer has closed. Ping/Pong frames are handled on the
        Rust side and never surface here.
        """
        return await self._loop.run_in_executor(None, self._raw.recv)

    async def receive_text(self) -> str | None:
        """Convenience: receive and assert the message is text.

        Returns the text payload, or ``None`` on close. Raises
        ``TypeError`` if the next frame is binary — call
        :meth:`receive` if you want to handle either.
        """
        msg = await self.receive()
        if msg is None:
            return None
        kind, data = msg
        if kind != "text":
            raise TypeError(f"expected text frame, got {kind!r}")
        return data  # type: ignore[return-value]

    async def receive_bytes(self) -> bytes | None:
        """Convenience: receive and assert the message is binary."""
        msg = await self.receive()
        if msg is None:
            return None
        kind, data = msg
        if kind != "binary":
            raise TypeError(f"expected binary frame, got {kind!r}")
        return data  # type: ignore[return-value]

    async def receive_json(self) -> Any:
        """Receive a text frame and parse it as JSON."""
        text = await self.receive_text()
        if text is None:
            return None
        from rivex import _json

        return _json.loads(text)

    async def send_text(self, data: str) -> None:
        await self._loop.run_in_executor(None, self._raw.send_text, data)

    async def send_bytes(self, data: bytes) -> None:
        await self._loop.run_in_executor(None, self._raw.send_bytes, data)

    async def send_json(self, data: Any) -> None:
        """Send ``data`` as a JSON text frame.

        Uses our Rust JSON serialiser (no ``serde_json::Value``
        intermediate, ~2× faster than stdlib).
        """
        from rivex import _json

        await self.send_text(_json.dumps(data).decode("utf-8"))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Send a Close frame and shut the connection down."""
        await self._loop.run_in_executor(None, self._raw.close, code, reason)

    async def __aiter__(self):
        """Async iteration yields ``(kind, payload)`` until close."""
        while True:
            msg = await self.receive()
            if msg is None:
                return
            yield msg
