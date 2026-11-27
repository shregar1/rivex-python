"""``rivex.constants.api.http_method`` — HTTP verb constants.

Backed directly by the native Rust ``RivexHTTPMethod`` PyO3 class.
"""

from __future__ import annotations

from typing import Final

from rivex.constants._rust import RivexHTTPMethod
from rivex.constants.api.abstraction import IAPIConstant


class HTTPMethod(IAPIConstant):
    """Canonical HTTP verb strings, backed directly by the Rust core."""

    GET: Final[str] = "GET"
    POST: Final[str] = "POST"
    PUT: Final[str] = "PUT"
    PATCH: Final[str] = "PATCH"
    DELETE: Final[str] = "DELETE"
    HEAD: Final[str] = "HEAD"
    OPTIONS: Final[str] = "OPTIONS"
    QUERY: Final[str] = "QUERY"
    TRACE: Final[str] = "TRACE"
    CONNECT: Final[str] = "CONNECT"

    _MUTATING: Final[frozenset[str]] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    Native = RivexHTTPMethod

    @classmethod
    def all_methods(cls) -> list[str]:
        """Return all supported HTTP verb strings."""
        return RivexHTTPMethod.all_methods()

    @classmethod
    def parse(cls, name: str) -> str | None:
        """Return the canonical uppercase verb or ``None`` if unknown."""
        if name not in {
            cls.GET, cls.POST, cls.PUT, cls.PATCH, cls.DELETE,
            cls.HEAD, cls.OPTIONS, cls.QUERY, cls.TRACE, cls.CONNECT,
        }:
            return None
        return RivexHTTPMethod.parse(name)

    @classmethod
    def is_mutating(cls, name: str) -> bool:
        """True for verbs that conventionally carry a mutating request body."""
        return RivexHTTPMethod.is_mutating(name)


__all__ = ["HTTPMethod"]
