"""``rivex.constants.api.response_entity`` — keys for outbound response fields."""

from __future__ import annotations

from typing import Final

from rivex.constants.api.abstraction import IAPIConstant


class ResponseEntity(IAPIConstant):
    """Field-name constants used to index the outbound response dict.

    Mirrors the :attr:`Response.status` / :attr:`Response.body` /
    :attr:`Response.headers` attribute names so middleware and
    utilities can reference them without string literals.
    """

    STATUS: Final[str] = "status"
    BODY: Final[str] = "body"
    HEADERS: Final[str] = "headers"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "ResponseEntity"


__all__ = ["ResponseEntity"]
