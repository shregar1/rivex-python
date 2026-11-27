"""``rivex.middleware.content_type`` — Content-Type header validation middleware."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Iterable

from rivex.constants.api.header import Header
from rivex.constants.api.http_method import HTTPMethod
from rivex.constants.api.http_status import HTTPStatus
from rivex.constants.api.media_type import MediaType
from rivex.middleware.abstraction import IMiddleware


class ContentTypeValidationMiddleware(IMiddleware):
    """Reject requests whose ``Content-Type`` doesn't match the expected type.

    Default behaviour: ``POST`` / ``PUT`` / ``PATCH`` requests must
    carry ``application/json``; ``GET`` / ``HEAD`` / ``DELETE`` / ``OPTIONS``
    requests are unchecked.

    Parameters:
        required_content_type: The expected ``Content-Type`` value
            (default ``application/json``). Comparison is case-insensitive
            substring (``"application/json" in header_value``).
        mutating_methods: HTTP methods that require the header. Default:
            ``{"POST", "PUT", "PATCH"}``.
        excluded_paths: Paths to skip (e.g. ``{"/health", "/docs"}``). Exact
            match plus ``"*"`` suffix glob (``"/admin*"`` matches ``/admin``,
            ``/admin/users``, ...).
        error_message: Override for the 415 error envelope.
    """

    def __init__(
        self,
        required_content_type: str = MediaType.APPLICATION_JSON,
        mutating_methods: Iterable[str] | None = None,
        excluded_paths: Iterable[str] | None = None,
        error_message: str | None = None,
    ) -> None:
        self.required_content_type = required_content_type.lower()
        self.mutating_methods = set(
            (m.value if hasattr(m, "value") else str(m)).upper()
            for m in (mutating_methods or (HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH))
        )
        self.excluded_paths = list(excluded_paths or ())
        self.error_message = error_message

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Validate the ``Content-Type`` header before forwarding the request.

        Non-mutating methods are passed straight through to ``call_next``
        because they do not need a body content type. Mutating methods
        on an excluded path are also passed through. Otherwise the
        ``Content-Type`` header is read and compared (case-insensitive
        substring) to :attr:`required_content_type`; if it matches the
        request is forwarded, and if not, a ``415 UNSUPPORTED_MEDIA_TYPE``
        response carrying an ``UNSUPPORTED_MEDIA_TYPE`` error envelope is
        returned.

        Args:
            request_data: The in-flight request envelope. The
                ``method``, ``path``, and ``headers`` fields are read.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            Either the downstream response produced by ``call_next``, or
            a 415 response with a JSON error envelope when the
            Content-Type is missing or does not match.
        """
        method = (request_data.get("method") or "").upper()
        path = request_data.get("path") or ""

        if method not in self.mutating_methods:
            return await call_next(request_data)
        if self._is_excluded(path):
            return await call_next(request_data)

        content_type = self._read_header(request_data, Header.CONTENT_TYPE)
        if content_type and self.required_content_type in content_type.lower():
            return await call_next(request_data)

        envelope = {
            "api_status": "FAILURE",
            "errors": [
                {
                    "code": "UNSUPPORTED_MEDIA_TYPE",
                    "message": self.error_message
                    or (
                        f"Method {method} requires '{Header.CONTENT_TYPE}: "
                        f"{self.required_content_type}'. Got '{content_type}'."
                    ),
                }
            ],
        }
        return {
            "status": HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "headers": [(Header.CONTENT_TYPE, MediaType.APPLICATION_JSON)],
            "body": json.dumps(envelope).encode("utf-8"),
        }

    @staticmethod
    def _read_header(request_data: dict, name: str) -> str | None:
        """Look up a header in ``request_data`` with case-insensitive matching.

        Args:
            request_data: The in-flight request envelope. Its
                ``headers`` list is searched.
            name: Header name to look up; matched case-insensitively.

        Returns:
            The header value as a string when found, otherwise
            ``None``. Non-string keys in the headers list are skipped.
        """
        headers = request_data.get("headers") or []
        lowered = name.lower()
        for key, value in headers:
            if isinstance(key, str) and key.lower() == lowered:
                return value
        return None

    def _is_excluded(self, path: str) -> bool:
        """Return ``True`` when ``path`` is in :attr:`excluded_paths`.

        Each entry is tested as either an exact match or as a prefix
        glob (entries ending in ``"*"`` match every ``path`` that
        starts with the preceding characters).

        Args:
            path: The request path string.

        Returns:
            ``True`` when ``path`` matches any entry in the exclude
            list, ``False`` otherwise.
        """
        for excluded in self.excluded_paths:
            if excluded.endswith("*") and path.startswith(excluded[:-1]):
                return True
            if path == excluded:
                return True
        return False


__all__ = ["ContentTypeValidationMiddleware"]
