"""``rivex.enums.websocket.abstraction`` — base WebSocket enum interface.
"""

from __future__ import annotations

from rivex.enums.abstraction import IEnum


class IWebSocketEnum(IEnum):
    """Base interface for WebSocket domain enums."""

    pass


__all__ = ["IWebSocketEnum"]
