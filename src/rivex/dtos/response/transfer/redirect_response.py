"""``rivex.dtos.response.redirect_response`` — Redirect response DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.dtos.response.abstraction import IResponseDTO
from rivex.serialization.serialization import serialize


@dataclass
class RedirectResponse(IResponseDTO):
    """Redirect Response DTO for issuing HTTP redirects."""

    url: str
    status_code: int = HTTPStatus.TEMPORARY_REDIRECT
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the redirect target and status code as a plain dict.

        Returns:
            A dict with ``url`` and ``status_code`` keys.
        """
        return {"url": self.url, "status_code": self.status_code}

    def to_json(self) -> bytes:
        """Serialize :meth:`to_dict` to JSON bytes.

        Returns:
            The JSON encoding of ``{"url": ..., "status_code": ...}``.
        """
        return serialize(self.to_dict())

    def to_headers(self) -> dict[str, str]:
        """Build the header map for this redirect response.

        The ``Location`` header is always set to :attr:`url`; any
        caller-supplied headers override that single value.

        Returns:
            A new dict including ``Location`` plus every entry from
            :attr:`headers`.
        """
        return {Header.LOCATION: self.url, **self.headers}


__all__ = ["RedirectResponse"]
