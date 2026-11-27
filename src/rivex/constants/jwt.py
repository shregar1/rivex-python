"""``rivex.constants.jwt`` — JSON Web Token algorithm + claim type constants."""

from __future__ import annotations

from typing import Final

from rivex.constants.abstraction import IConstant


class JWT(IConstant):
    """JWT claim types, claim names, and signing algorithm identifiers."""

    ACCESS: Final[str] = "access"
    REFRESH: Final[str] = "refresh"
    JTI: Final[str] = "JTI"
    HS256: Final[str] = "HS256"
    HS384: Final[str] = "HS384"
    HS512: Final[str] = "HS512"
    RS256: Final[str] = "RS256"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "JWT"


__all__ = ["JWT"]
