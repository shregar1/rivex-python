"""``rivex.enums.auth.token`` — token type enum.
"""

from __future__ import annotations

from rivex.constants.auth.token import AuthTokenConstant
from rivex.enums.auth.abstraction import IAuthEnum


class TokenType(str, IAuthEnum):
    """Token type Enum built from ``AuthTokenConstant`` constants."""

    BEARER = AuthTokenConstant.BEARER
    API_KEY = AuthTokenConstant.API_KEY
    REFRESH = AuthTokenConstant.REFRESH


__all__ = ["TokenType"]
