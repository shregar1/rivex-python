"""``rivex.constants.observability.abstraction`` — base observability constant interface.
"""

from __future__ import annotations

from rivex.constants.abstraction import IConstant


class IObservabilityConstant(IConstant):
    """Base interface for observability constant groups."""

    pass


__all__ = ["IObservabilityConstant"]
