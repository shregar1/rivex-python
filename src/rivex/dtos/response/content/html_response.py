"""``rivex.dtos.response.html_response`` — HTML response DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.dtos.response.abstraction import IResponseDTO
from rivex.serialization.serialization import serialize


@dataclass
class HtmlResponse(IResponseDTO):
    """HTML Response DTO for returning rendered HTML strings."""

    content: str
    status_code: int = HTTPStatus.OK
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = MediaType.TEXT_HTML

    def to_dict(self) -> dict[str, Any]:
        """Return the response content as a plain dict.

        Returns:
            A dict with a single ``content`` key holding the raw HTML
            string.
        """
        return {"content": self.content}

    def to_json(self) -> bytes:
        """Serialize :meth:`to_dict` to JSON bytes.

        Returns:
            The JSON encoding of ``{"content": ...}``.
        """
        return serialize(self.to_dict())

    def to_body(self) -> bytes:
        """Encode the HTML content as UTF-8 bytes for the response body.

        Returns:
            The HTML string from :attr:`content`, encoded as UTF-8.
        """
        return self.content.encode("utf-8")

    def to_headers(self) -> dict[str, str]:
        """Build the response header map for this HTML response.

        The ``Content-Type`` header is always set to
        :attr:`media_type`; any caller-supplied headers override that
        single value.

        Returns:
            A new dict including ``Content-Type`` plus every entry
            from :attr:`headers`.
        """
        return {Header.CONTENT_TYPE: self.media_type, **self.headers}


__all__ = ["HtmlResponse"]
