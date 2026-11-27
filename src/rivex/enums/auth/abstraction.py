"""``rivex.enums.auth.abstraction`` — base auth enum interface.
"""

from __future__ import annotations

from rivex.enums.abstraction import IEnum


class IAuthEnum(IEnum):
    """Base interface for authentication and authorization enums."""

    pass


__all__ = ["IAuthEnum"]
