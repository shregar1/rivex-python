"""``rivex.constants.exception.abstraction`` — base exception constant interface.

Provides ``IExceptionConstant``, the base class for all exception-level constant groups.
"""

from __future__ import annotations

from rivex.constants.abstraction import IConstant


class IExceptionConstant(IConstant):
    """Base interface for exception constants (Error, ExceptionCode, ExceptionMessage)."""

    pass


__all__ = ["IExceptionConstant"]
