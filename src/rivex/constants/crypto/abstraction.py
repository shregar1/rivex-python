"""``rivex.constants.crypto.abstraction`` — base interface for crypto constant groups."""

from __future__ import annotations

from rivex.constants.abstraction import IConstant


class ICryptoConstant(IConstant):
    """Marker interface for classes that enumerate hashing / encryption / cipher choices."""

    pass


__all__ = ["ICryptoConstant"]
