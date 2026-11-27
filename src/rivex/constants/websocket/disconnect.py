"""``rivex.constants.websocket.disconnect`` — WebSocket disconnect status code constants (RFC 6455).
"""

from __future__ import annotations

from typing import Final

from rivex.constants.websocket.abstraction import IWebSocketConstant


class WebSocketDisconnectConstant(IWebSocketConstant):
    """WebSocket disconnect status code integer constants."""

    NORMAL: Final[int] = 1000
    GOING_AWAY: Final[int] = 1001
    PROTOCOL_ERROR: Final[int] = 1002
    UNSUPPORTED_DATA: Final[int] = 1003
    POLICY_VIOLATION: Final[int] = 1008
    TOO_BIG: Final[int] = 1009
    SERVER_ERROR: Final[int] = 1011


__all__ = ["WebSocketDisconnectConstant"]
