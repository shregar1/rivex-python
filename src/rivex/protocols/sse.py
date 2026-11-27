"""Server-Sent Events (SSE) — Tier 3 real-time feature.

Usage::

    from rivex.protocols.sse import SSEEvent, sse

    @sse("/events")
    async def event_stream():
        yield SSEEvent(data="hello")
        await asyncio.sleep(1)
        yield SSEEvent(data="world", event="update", id="42")

Or on an existing Rivex app instance::

    @app.sse("/events")
    async def event_stream():
        yield SSEEvent(data="ping")
"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Generator

from rivex.http.responses import EventSourceResponse


@dataclass
class SSEEvent:
    """A single Server-Sent Event.

    Fields correspond to the SSE spec (https://html.spec.whatwg.org/#server-sent-events):

    * ``data`` — the event payload (a string or JSON-serialisable object).
    * ``event`` — optional event type (default ``None`` → ``message``).
    * ``id`` — optional event ID (browser tracks ``Last-Event-ID``).
    * ``retry`` — optional reconnection time in milliseconds.
    * ``json`` — if ``True``, the ``data`` is JSON-encoded automatically
      before formatting.
    """
    data: str | Any
    event: str | None = None
    id: str | None = None
    retry: int | None = None
    json: bool = False

    def _format(self) -> str:
        """Render this event as a wire-level Server-Sent Event string.

        When ``json`` is true the ``data`` payload is JSON-encoded via
        the package's Rust serialiser; otherwise it is coerced to
        ``str``. Formatting itself is delegated to
        :meth:`EventSourceResponse.format_event` so the multi-line
        ``data:`` expansion and the optional ``event:`` / ``id:`` /
        ``retry:`` fields are emitted consistently with the rest of the
        package.

        Returns:
            The serialized SSE frame, including the trailing blank
            line that separates events on the wire.
        """
        payload = _json.dumps(self.data) if self.json else str(self.data)
        return EventSourceResponse.format_event(
            data=payload,
            event=self.event,
            id=self.id,
            retry=self.retry,
        )


# Re-export EventSourceResponse so users can type-annotate their handlers.
__all__ = [
    "EventSourceResponse",
    "SSEEvent",
    "sse",
]
