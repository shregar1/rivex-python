"""``rivex.middleware.compression`` — multi-algorithm response compression middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.header import Header
from rivex.native._compat import RC_V2, apply_compressed_headers, get_request_header, rc as _rc
from rivex.middleware.abstraction import IMiddleware


class CompressionMiddleware(IMiddleware):
    """Compresses responses using brotli, gzip, or deflate based on ``Accept-Encoding``.

    Prefers brotli → gzip → deflate. Skips compression if the response is
    already encoded or smaller than ``minimum_size``.

    Parameters:
        minimum_size: Skip compression for bodies smaller than this (bytes).
        level:        Compression level 1–9 (default 4).
    """

    def __init__(self, minimum_size: int = 500, level: int = 4):
        self.minimum_size = minimum_size
        self.level = level

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and compress the response when appropriate.

        Invokes ``call_next`` to obtain the downstream response, then
        negotiates a compression encoding from the incoming
        ``Accept-Encoding`` header in the order ``br`` → ``gzip`` →
        ``deflate`` (whichever the client advertises first is used). The
        body is compressed via the native Rust core when available, with
        stdlib fallbacks (``brotli``, ``gzip``, ``zlib``) otherwise.
        Responses that are already ``Content-Encoding``-tagged, whose body
        is below :attr:`minimum_size`, or whose compressed output is not
        smaller than the original body are returned unchanged.

        Args:
            request_data: The in-flight request envelope. Only its
                ``Accept-Encoding`` header is read.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            The downstream response dict, with ``body`` replaced by the
            compressed bytes and ``Content-Encoding`` / ``Vary`` headers
            set when compression is actually applied. Unchanged otherwise.
        """
        response: dict = await call_next(request_data)
        body = response.get("body", b"")
        if len(body) < self.minimum_size:
            return response

        for k, _v in response.get("headers", []):
            if k.lower() == Header.CONTENT_ENCODING:
                return response

        accept = (get_request_header(request_data, Header.ACCEPT_ENCODING) or "").lower()
        compressed: bytes | None = None
        encoding: str | None = None

        if "br" in accept:
            try:
                import brotli
                compressed = brotli.compress(body, quality=self.level)
                encoding = "br"
            except ImportError:
                pass

        if compressed is None and "gzip" in accept:
            if RC_V2:
                compressed = _rc.gzip_compress(body)
            else:
                import gzip
                compressed = gzip.compress(body, compresslevel=self.level)
            encoding = "gzip"

        if compressed is None and "deflate" in accept:
            import zlib
            compressed = zlib.compress(body, self.level)
            encoding = "deflate"

        if compressed is None or len(compressed) >= len(body):
            return response

        response["body"] = compressed
        assert encoding is not None
        apply_compressed_headers(response, encoding)
        return response


__all__ = ["CompressionMiddleware"]
