"""``rivex.exceptions.http.abstraction`` — base HTTP exception interface.

Provides ``IHTTPException``, the base interface for all HTTP status exceptions.
"""

from __future__ import annotations

from abc import ABC

from rivex.exceptions.base import RivexException


class IHTTPException(RivexException, ABC):
    """Base interface for HTTP status-bound exception classes."""

    pass


__all__ = ["IHTTPException"]
