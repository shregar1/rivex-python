"""``rivex.enums.auth`` — authentication and authorization enums package.
"""

from __future__ import annotations

from rivex.enums.auth.abstraction import IAuthEnum
from rivex.enums.auth.role import RoleLevel
from rivex.enums.auth.scheme import AuthScheme
from rivex.enums.auth.token import TokenType

__all__ = ["IAuthEnum", "TokenType", "AuthScheme", "RoleLevel"]
