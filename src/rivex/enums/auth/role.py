"""``rivex.enums.auth.role`` — role level enum.
"""

from __future__ import annotations

from rivex.constants.auth.role import AuthRoleConstant
from rivex.enums.auth.abstraction import IAuthEnum


class RoleLevel(str, IAuthEnum):
    """Role level Enum built from ``AuthRoleConstant`` constants."""

    GUEST = AuthRoleConstant.GUEST
    USER = AuthRoleConstant.USER
    ADMIN = AuthRoleConstant.ADMIN
    SYSTEM = AuthRoleConstant.SYSTEM


__all__ = ["RoleLevel"]
