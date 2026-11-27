"""``rivex.constants.api.abstraction`` — base API constant interface.

Provides ``IAPIConstant``, the base class for all API-level constant groups.
"""

from __future__ import annotations

from rivex.constants.abstraction import IConstant


class IAPIConstant(IConstant):
    """Base interface for API constants (HTTPMethod, MediaType, Header)."""

    pass


__all__ = ["IAPIConstant"]
