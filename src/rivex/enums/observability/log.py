"""``rivex.enums.observability.log`` — log level enum.
"""

from __future__ import annotations

from rivex.constants.observability.log import LogLevelConstant
from rivex.enums.observability.abstraction import IObservabilityEnum


class LogLevel(str, IObservabilityEnum):
    """Log level Enum built from ``LogLevelConstant`` constants."""

    TRACE = LogLevelConstant.TRACE
    DEBUG = LogLevelConstant.DEBUG
    INFO = LogLevelConstant.INFO
    WARN = LogLevelConstant.WARN
    ERROR = LogLevelConstant.ERROR
    FATAL = LogLevelConstant.FATAL


__all__ = ["LogLevel"]
