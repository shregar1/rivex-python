"""``rivex.constants.auth.token`` — authentication token type constants.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.auth.abstraction import IAuthConstant


class AuthTokenConstant(IAuthConstant):
    """Token type string constants."""

    BEARER: Final[str] = "Bearer"
    API_KEY: Final[str] = "APIKey"
    REFRESH: Final[str] = "Refresh"


__all__ = ["AuthTokenConstant"]
