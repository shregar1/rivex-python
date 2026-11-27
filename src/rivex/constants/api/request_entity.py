"""``rivex.constants.api.request_entity`` — keys for inbound request fields."""

from __future__ import annotations

from typing import Final

from rivex.constants.api.abstraction import IAPIConstant


class RequestEntity(IAPIConstant):
    """Field-name constants used to index the inbound request dict.

    Mirrors the :attr:`Request.body` / :attr:`Request.headers` /
    :attr:`Request.query_params` / etc. attribute names so middleware
    and utilities can reference them without string literals.
    """

    BODY: Final[str] = "body"
    HEADERS: Final[str] = "headers"
    METADATA: Final[str] = "metadata"
    QUERY_PARAMS: Final[str] = "query_params"
    PATH_PARAMS: Final[str] = "path_params"
    FORM_DATA: Final[str] = "form_data"
    FILE_DATA: Final[str] = "file_data"
    COOKIES: Final[str] = "cookies"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "RequestEntity"


__all__ = ["RequestEntity"]
