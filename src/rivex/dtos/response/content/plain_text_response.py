"""``rivex.dtos.response.plain_text_response`` — Plain text response DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.dtos.response.abstraction import IResponseDTO
from rivex.serialization.serialization import serialize


@dataclass
class PlainTextResponse(IResponseDTO):
    """Plain Text Response DTO for raw text content."""

    content: str
    status_code: int = HTTPStatus.OK
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = MediaType.TEXT_PLAIN

    def to_dict(self) -> dict[str, Any]:
        return {"content": self.content}

    def to_json(self) -> bytes:
        return serialize(self.to_dict())

    def to_body(self) -> bytes:
        return self.content.encode("utf-8")

    def to_headers(self) -> dict[str, str]:
        return {Header.CONTENT_TYPE: self.media_type, **self.headers}


__all__ = ["PlainTextResponse"]
