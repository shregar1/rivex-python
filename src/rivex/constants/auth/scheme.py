"""``rivex.constants.auth.scheme`` — authentication scheme constants.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.auth.abstraction import IAuthConstant


class AuthSchemeConstant(IAuthConstant):
    """Authentication scheme string constants."""

    BEARER: Final[str] = "bearer"
    BASIC: Final[str] = "basic"
    API_KEY: Final[str] = "api_key"
    OAUTH2: Final[str] = "oauth2"


__all__ = ["AuthSchemeConstant"]
