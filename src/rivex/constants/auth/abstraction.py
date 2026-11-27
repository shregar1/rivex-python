"""``rivex.constants.auth.abstraction`` — base auth constant interface.

Provides ``IAuthConstant``, the base class for all authentication constant groups.
"""

from __future__ import annotations

from rivex.constants.abstraction import IConstant


class IAuthConstant(IConstant):
    """Base interface for authentication constant groups."""

    pass


__all__ = ["IAuthConstant"]
