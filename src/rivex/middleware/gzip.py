"""``rivex.middleware.gzip`` — GZip response compression middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.header import Header
from rivex.native._compat import RC_V2, apply_compressed_headers, get_request_header, rc as _rc
from rivex.middleware.abstraction import IMiddleware


class GZipMiddleware(IMiddleware):
    """Compresses responses with GZip when the client advertises ``accept-encoding: gzip``.

    Parameters:
        minimum_size: Responses smaller than this (bytes) are not compressed.
    """

    def __init__(self, minimum_size: int = 500):
        self.minimum_size = minimum_size

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and GZip-compress the response when appropriate.

        Invokes ``call_next`` to obtain the downstream response, then negotiates
        GZip compression against the incoming ``Accept-Encoding`` header and the
        configured size threshold. The body is compressed via the native Rust
        core when available and falls back to the standard-library ``gzip``
        module otherwise. Responses that would grow under compression, or whose
        body is below ``minimum_size``, are returned unchanged.

        Args:
            request_data: The in-flight request envelope as carried by the
                middleware chain. Only its ``Accept-Encoding`` header is read.
            call_next: Awaitable that invokes the next middleware/handler and
                returns the downstream response dict.

        Returns:
            The downstream response dict, with ``body`` replaced by the
            compressed bytes and ``Content-Encoding`` / ``Vary`` headers set
            when compression is actually applied. Unchanged otherwise.

        Note:
            Compression is skipped if the body is shorter than
            ``self.minimum_size`` or if the compressed output is not smaller
            than the original body — both cases return the response untouched
            so callers do not need to special-case the output.
        """
        response: dict = await call_next(request_data)
        body = response.get("body", b"")
        if len(body) < self.minimum_size:
            return response

        accept = get_request_header(request_data, Header.ACCEPT_ENCODING) or ""
        if "gzip" not in accept.lower():
            return response

        if RC_V2:
            compressed = _rc.gzip_compress(body)
        else:
            import gzip
            compressed = gzip.compress(body)

        if len(compressed) >= len(body):
            return response

        response["body"] = compressed
        apply_compressed_headers(response, "gzip")
        return response


__all__ = ["GZipMiddleware"]
