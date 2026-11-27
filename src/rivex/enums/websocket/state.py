"""``rivex.enums.websocket.state`` — WebSocket connection state enum.
"""

from __future__ import annotations

from rivex.constants.websocket.state import WebSocketStateConstant
from rivex.enums.websocket.abstraction import IWebSocketEnum


class ConnectionState(int, IWebSocketEnum):
    """WebSocket connection state Enum built from ``WebSocketStateConstant`` constants."""

    CONNECTING = WebSocketStateConstant.CONNECTING
    OPEN = WebSocketStateConstant.OPEN
    CLOSING = WebSocketStateConstant.CLOSING
    CLOSED = WebSocketStateConstant.CLOSED


__all__ = ["ConnectionState"]
