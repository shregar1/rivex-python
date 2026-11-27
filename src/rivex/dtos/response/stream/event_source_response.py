"""``rivex.dtos.response.event_source_response`` — SSE EventSource response DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.dtos.response.abstraction import IResponseDTO
from rivex.serialization.serialization import serialize


@dataclass
class EventSourceResponse(IResponseDTO):
    """Server-Sent Events (SSE) Response DTO."""

    content: Any
    status_code: int = HTTPStatus.OK
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = MediaType.TEXT_EVENT_STREAM

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
        """Build the SSE response header map for this DTO.

        Always sets ``Content-Type`` to :attr:`media_type` and
        ``Cache-Control: no-cache``; any caller-supplied headers
        override those defaults (last-wins).

        Returns:
            The merged header dict ready to attach to a response.
        """
        base_headers = {
            Header.CONTENT_TYPE: self.media_type,
            Header.CACHE_CONTROL: "no-cache",
        }
        return {**base_headers, **self.headers}


__all__ = ["EventSourceResponse"]
