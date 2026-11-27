"""``rivex.constants.observability.trace`` — trace state string constants.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.observability.abstraction import IObservabilityConstant


class TraceStateConstant(IObservabilityConstant):
    """Trace state string constants."""

    RECORDING: Final[str] = "recording"
    SAMPLED: Final[str] = "sampled"
    DROPPED: Final[str] = "dropped"


__all__ = ["TraceStateConstant"]
