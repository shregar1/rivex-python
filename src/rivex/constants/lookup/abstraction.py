"""``rivex.constants.lookup.abstraction`` — base interface for lookup-table seed constants."""

from __future__ import annotations

from rivex.constants.abstraction import IConstant


class ILookupConstant(IConstant):
    """Marker interface for classes that enumerate seed values for a DB lookup table."""

    pass


__all__ = ["ILookupConstant"]
