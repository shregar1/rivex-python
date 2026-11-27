"""``rivex.dtos.response.streaming_response`` — Streaming response DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.dtos.response.abstraction import IResponseDTO
from rivex.serialization.serialization import serialize


@dataclass
class StreamingResponse(IResponseDTO):
    """Streaming Response DTO for async/sync iterator payloads."""

    content: Any
    status_code: int = HTTPStatus.OK
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = MediaType.APPLICATION_OCTET_STREAM

    def to_dict(self) -> dict[str, Any]:
        """Return the response status and media type as a plain dict.

        Returns:
            A dict with ``status_code`` and ``media_type`` keys. The
            iterator body and headers are intentionally omitted.
        """
        return {"status_code": self.status_code, "media_type": self.media_type}

    def to_json(self) -> bytes:
        """Serialize :meth:`to_dict` to JSON bytes.

        Returns:
            The JSON encoding of ``{"status_code": ..., "media_type": ...}``.
        """
        return serialize(self.to_dict())

    def to_headers(self) -> dict[str, str]:
        """Build the response header map for this streaming response.

        The ``Content-Type`` header is always set to :attr:`media_type`,
        and any caller-supplied headers override that single value.

        Returns:
            A new dict including ``Content-Type`` plus every entry
            from :attr:`headers`.
        """
        return {Header.CONTENT_TYPE: self.media_type, **self.headers}


__all__ = ["StreamingResponse"]
