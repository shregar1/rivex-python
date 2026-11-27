"""``rivex.dtos.response.file_response`` — File response DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.dtos.response.abstraction import IResponseDTO
from rivex.serialization.serialization import serialize


@dataclass
class FileResponse(IResponseDTO):
    """File Response DTO for serving files."""

    path: str
    filename: str | None = None
    status_code: int = HTTPStatus.OK
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = MediaType.APPLICATION_OCTET_STREAM

    def to_dict(self) -> dict[str, Any]:
        """Return the file metadata as a plain dict.

        Returns:
            A dict with ``path``, ``filename``, ``status_code`` and
            ``media_type`` keys.
        """
        return {
            "path": self.path,
            "filename": self.filename,
            "status_code": self.status_code,
            "media_type": self.media_type,
        }

    def to_json(self) -> bytes:
        """Serialize :meth:`to_dict` to JSON bytes.

        Returns:
            The JSON encoding of the metadata dict.
        """
        return serialize(self.to_dict())

    def to_headers(self) -> dict[str, str]:
        """Build the header map for this file response.

        ``Content-Type`` is always set to :attr:`media_type`; when
        :attr:`filename` is set, a ``Content-Disposition`` header is
        added suggesting the filename as an attachment. Any
        caller-supplied headers from :attr:`headers` override the
        default ``Content-Type`` (last-wins).

        Returns:
            The merged header dict ready to attach to the response.
        """
        h = {Header.CONTENT_TYPE: self.media_type, **self.headers}
        if self.filename:
            h["content-disposition"] = f'attachment; filename="{self.filename}"'
        return h


__all__ = ["FileResponse"]
