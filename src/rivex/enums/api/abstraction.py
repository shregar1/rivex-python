"""``rivex.enums.api.abstraction`` — base API enum interface.
"""

from __future__ import annotations

from rivex.enums.abstraction import IEnum


class IAPIEnum(IEnum):
    """Base interface for API domain enums."""

    pass


__all__ = ["IAPIEnum"]
