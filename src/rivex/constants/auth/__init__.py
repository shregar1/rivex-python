"""``rivex.constants.auth`` — authentication & authorization constant groups package.
"""

from __future__ import annotations

from rivex.constants.auth.abstraction import IAuthConstant
from rivex.constants.auth.config import AuthConfigConstant
from rivex.constants.auth.role import AuthRoleConstant
from rivex.constants.auth.scheme import AuthSchemeConstant
from rivex.constants.auth.token import AuthTokenConstant

__all__ = [
    "IAuthConstant",
    "AuthConfigConstant",
    "AuthTokenConstant",
    "AuthSchemeConstant",
    "AuthRoleConstant",
]
