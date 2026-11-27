"""``rivex.enums.observability.trace`` — trace state enum.
"""

from __future__ import annotations

from rivex.constants.observability.trace import TraceStateConstant
from rivex.enums.observability.abstraction import IObservabilityEnum


class TraceState(str, IObservabilityEnum):
    """Trace state Enum built from ``TraceStateConstant`` constants."""

    RECORDING = TraceStateConstant.RECORDING
    SAMPLED = TraceStateConstant.SAMPLED
    DROPPED = TraceStateConstant.DROPPED


__all__ = ["TraceState"]
