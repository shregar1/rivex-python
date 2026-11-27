"""``rivex.constants.context.abstraction`` — marker interface for context constants."""

from __future__ import annotations

from rivex.constants.abstraction import IConstant


class IContextConstant(IConstant):
    """Marker interface for classes that enumerate ``request_data["state"]`` keys."""

    pass


__all__ = ["IContextConstant"]
