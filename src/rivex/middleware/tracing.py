"""``rivex.middleware.tracing`` — W3C ``traceparent`` header middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.middleware.abstraction import IMiddleware


class TraceparentMiddleware(IMiddleware):
    """Propagate / mint a W3C ``traceparent`` header per request.

    The header is read from the incoming request; when absent, a fresh
    trace id / span id is generated (``00-<trace_id>-<span_id>-01``).
    The same value is appended to the response headers so downstream
    consumers can stitch their traces back to the originating request.

    Parameters:
        header_name: Override the request header name (default ``"traceparent"``).
        generate_ids: Callable that returns a ``(trace_id, span_id)`` tuple
            of 32-hex-char / 16-hex-char strings. Defaults to
            :func:`uuid.uuid4` x2 (cheap and good enough for dev).
        sample_flag: ``"00"`` (not sampled) or ``"01"`` (sampled). Default
            ``"01"``; flip when wiring up a sampler.
    """

    def __init__(
        self,
        header_name: str = "traceparent",
        generate_ids: Callable[[], tuple[str, str]] | None = None,
        sample_flag: str = "01",
    ) -> None:
        self.header_name = header_name
        self._generate_ids = generate_ids or self._default_generate
        self.sample_flag = sample_flag

    @staticmethod
    def _default_generate() -> tuple[str, str]:
        """Return a fresh ``(trace_id, span_id)`` pair from ``uuid4``.

    Used when the constructor is built without a ``generate_ids``
    callable. ``trace_id`` is the full 32-hex-char UUID4; ``span_id`` is
    the first 16 hex chars of another UUID4 — sufficient for the W3C
    trace-context ``traceparent`` format.

    Returns:
        A 2-tuple of ``(trace_id, span_id)`` hex strings.
    """
        import uuid

        return uuid.uuid4().hex, uuid.uuid4().hex[:16]

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Propagate or generate the W3C ``traceparent`` header.

        When the incoming request carries the configured traceparent
        header, the same value is forwarded. Otherwise a fresh
        ``00-<trace_id>-<span_id>-<sample_flag>`` value is generated
        using :attr:`_generate_ids`. After delegating to ``call_next``,
        the resolved value is appended to the response ``headers`` list
        unless a header of the same name is already present, in which
        case the existing value is preserved.

        Args:
            request_data: The in-flight request envelope. The
                ``headers`` list is read to look for an incoming
                ``traceparent`` value.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            The downstream response dict, with the ``headers`` list
            extended with the resolved traceparent when it was not
            already present.
    """
        incoming = self._read_header(request_data, self.header_name)
        if incoming:
            traceparent = incoming
        else:
            trace_id, span_id = self._generate_ids()
            traceparent = f"00-{trace_id}-{span_id}-{self.sample_flag}"

        response = await call_next(request_data)
        headers = list(response.get("headers") or [])
        if not any(k.lower() == self.header_name.lower() for k, _ in headers if isinstance(k, str)):
            headers.append((self.header_name, traceparent))
            response["headers"] = headers
        return response

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

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "TraceparentMiddleware"


__all__ = ["TraceparentMiddleware"]
