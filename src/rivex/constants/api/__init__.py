"""``rivex.constants.api`` — HTTP API constants sub-package.

Usage::

    from rivex.constants.api import IAPIConstant, HTTPMethod, MediaType, Header, HTTPStatus
    from rivex.constants.api import RequestEntity, ResponseEntity
"""
from rivex.constants.api.abstraction import IAPIConstant
from rivex.constants.api.header import Header as HTTPHeader
from rivex.constants.api.header import Header
from rivex.constants.api.http_method import HTTPMethod
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.constants.api.request_entity import RequestEntity
from rivex.constants.api.response_entity import ResponseEntity

__all__ = [
    "IAPIConstant",
    "HTTPHeader",
    "Header",
    "HTTPMethod",
    "HTTPStatus",
    "MediaType",
    "RequestEntity",
    "ResponseEntity",
]
