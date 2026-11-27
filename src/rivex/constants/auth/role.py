"""``rivex.constants.auth.role`` — authentication role level constants.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.auth.abstraction import IAuthConstant


class AuthRoleConstant(IAuthConstant):
    """Role level string constants."""

    GUEST: Final[str] = "guest"
    USER: Final[str] = "user"
    ADMIN: Final[str] = "admin"
    SYSTEM: Final[str] = "system"


__all__ = ["AuthRoleConstant"]
