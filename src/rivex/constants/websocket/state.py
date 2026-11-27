"""``rivex.constants.websocket.state`` — WebSocket connection state integer constants.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.websocket.abstraction import IWebSocketConstant


class WebSocketStateConstant(IWebSocketConstant):
    """WebSocket connection state integer constants."""

    CONNECTING: Final[int] = 0
    OPEN: Final[int] = 1
    CLOSING: Final[int] = 2
    CLOSED: Final[int] = 3


__all__ = ["WebSocketStateConstant"]
