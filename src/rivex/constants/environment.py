"""``rivex.constants.environment`` — runtime environment name constants."""

from __future__ import annotations

from typing import Final

from rivex.constants.abstraction import IConstant


class Environment(IConstant):
    """Supported runtime environment names."""

    DEVELOPMENT: Final[str] = "DEVELOPMENT"
    STAGING: Final[str] = "STAGING"
    PRODUCTION: Final[str] = "PRODUCTION"
    TESTING: Final[str] = "TESTING"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "Environment"


__all__ = ["Environment"]
