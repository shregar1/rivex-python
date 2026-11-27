"""``rivex.enums.api.method`` — HTTP method enum.
"""

from __future__ import annotations

from rivex.constants.api.http_method import HTTPMethod
from rivex.enums.api.abstraction import IAPIEnum


class HTTPMethodEnum(str, IAPIEnum):
    """HTTP verb Enum built from ``HTTPMethod`` constants."""

    GET = HTTPMethod.GET
    POST = HTTPMethod.POST
    PUT = HTTPMethod.PUT
    PATCH = HTTPMethod.PATCH
    DELETE = HTTPMethod.DELETE
    HEAD = HTTPMethod.HEAD
    OPTIONS = HTTPMethod.OPTIONS
    QUERY = HTTPMethod.QUERY
    TRACE = HTTPMethod.TRACE
    CONNECT = HTTPMethod.CONNECT


__all__ = ["HTTPMethodEnum"]
