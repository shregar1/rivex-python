"""``rivex.dtos.response.xml_response`` — XML response DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.dtos.response.abstraction import IResponseDTO
from rivex.serialization.serialization import serialize


@dataclass
class XmlResponse(IResponseDTO):
    """XML Response DTO for XML content."""

    content: str | bytes
    status_code: int = HTTPStatus.OK
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = MediaType.APPLICATION_XML

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content if isinstance(self.content, str) else self.content.decode("utf-8", errors="replace")
        }

    def to_json(self) -> bytes:
        return serialize(self.to_dict())

    def to_body(self) -> bytes:
        return self.content if isinstance(self.content, bytes) else self.content.encode("utf-8")

    def to_headers(self) -> dict[str, str]:
        return {Header.CONTENT_TYPE: self.media_type, **self.headers}


__all__ = ["XmlResponse"]
