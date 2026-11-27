"""``rivex.constants.websocket.abstraction`` — base WebSocket constant interface.
"""

from __future__ import annotations

from rivex.constants.abstraction import IConstant


class IWebSocketConstant(IConstant):
    """Base interface for WebSocket constant groups."""

    pass


__all__ = ["IWebSocketConstant"]
