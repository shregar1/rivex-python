"""``rivex.enums.auth.scheme`` — authentication scheme enum.
"""

from __future__ import annotations

from rivex.constants.auth.scheme import AuthSchemeConstant
from rivex.enums.auth.abstraction import IAuthEnum


class AuthScheme(str, IAuthEnum):
    """Authentication scheme Enum built from ``AuthSchemeConstant`` constants."""

    BEARER = AuthSchemeConstant.BEARER
    BASIC = AuthSchemeConstant.BASIC
    API_KEY = AuthSchemeConstant.API_KEY
    OAUTH2 = AuthSchemeConstant.OAUTH2


__all__ = ["AuthScheme"]
