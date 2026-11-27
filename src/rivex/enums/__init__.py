"""``rivex.enums`` — framework-wide enums package.

Provides typed Enums constructed directly from corresponding constants.
"""

from __future__ import annotations

from rivex.enums.abstraction import IEnum
from rivex.enums.api.status import APIResult, APIStatus
from rivex.enums.api.abstraction import IAPIEnum
from rivex.enums.api.cookie import SameSitePolicy
from rivex.enums.api.method import HTTPMethodEnum
from rivex.enums.auth import AuthScheme, IAuthEnum, RoleLevel, TokenType
from rivex.enums.observability import IObservabilityEnum, LogLevel, MetricType, TraceState
from rivex.enums.websocket import ConnectionState, DisconnectCode, FrameType, IWebSocketEnum

__all__ = [
    # Base interfaces
    "IEnum",
    "IAPIEnum",
    "IAuthEnum",
    "IObservabilityEnum",
    "IWebSocketEnum",
    # API
    "APIResult",
    "APIStatus",
    "HTTPMethodEnum",
    "SameSitePolicy",
    # Auth
    "TokenType",
    "AuthScheme",
    "RoleLevel",
    # Observability
    "LogLevel",
    "MetricType",
    "TraceState",
    # WebSocket
    "FrameType",
    "ConnectionState",
    "DisconnectCode",
]
