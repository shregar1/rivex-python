"""``rivex.dtos.response.json_response`` — JSON response DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.dtos.response.abstraction import IResponseDTO
from rivex.serialization.serialization import serialize


@dataclass
class JsonResponse(IResponseDTO):
    """JSON Response DTO for returning arbitrary structured JSON data."""

    data: Any
    status_code: int = HTTPStatus.OK
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = MediaType.APPLICATION_JSON

    def to_dict(self) -> dict[str, Any]:
        if isinstance(self.data, dict):
            return self.data
        return {"data": self.data}

    def to_json(self) -> bytes:
        return serialize(self.data)

    def to_headers(self) -> dict[str, str]:
        return {Header.CONTENT_TYPE: self.media_type, **self.headers}


__all__ = ["JsonResponse"]
