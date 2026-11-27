"""``rivex.constants.observability.log`` — log level string constants.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.observability.abstraction import IObservabilityConstant


class LogLevelConstant(IObservabilityConstant):
    """Standard log level string constants."""

    TRACE: Final[str] = "TRACE"
    DEBUG: Final[str] = "DEBUG"
    INFO: Final[str] = "INFO"
    WARN: Final[str] = "WARN"
    ERROR: Final[str] = "ERROR"
    FATAL: Final[str] = "FATAL"


__all__ = ["LogLevelConstant"]
