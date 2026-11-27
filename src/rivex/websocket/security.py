from __future__ import annotations

from rivex.exceptions.http.exceptions import WebSocketDisconnect

try:
    import rivex_core as _rc
    HAS_CORE = hasattr(_rc, "PyOriginValidator")
except ImportError:
    _rc = None
    HAS_CORE = False


class OriginValidator:
    def __init__(self, allowed_origins: list[str] | None = None, allow_missing: bool = False):
        self._allowed = allowed_origins or []
        self._allow_missing = allow_missing
        if HAS_CORE:
            self._core = _rc.PyOriginValidator(self._allowed, allow_missing)
        else:
            self._core = None

    def validate(self, headers: dict[str, str]) -> None:
        """Reject the handshake when ``Origin`` is missing or disallowed.

        Looks up the ``Origin`` / ``Sec-WebSocket-Origin`` header from the
        handshake request and compares it against the configured allow-list.
        Delegates to the native core when available; otherwise runs the
        equivalent pure-Python check, raising :class:`WebSocketDisconnect`
        with code ``1008`` on any failure.

        Args:
            headers: Mapping of normalised handshake headers. Missing-origin
                handling is controlled by ``allow_missing``; unknown origins
                are always rejected when an allow-list is configured.

        Raises:
            WebSocketDisconnect: When the origin is missing and ``allow_missing``
                is ``False``, or when it is present but not in
                :attr:`allowed_origins`.
        """
        if self._core:
            self._core.validate(list(headers.items()))
            return
        origin = headers.get("origin") or headers.get("sec-websocket-origin") or headers.get("Origin")
        if not origin:
            if self._allow_missing:
                return
            raise WebSocketDisconnect(code=1008, reason="missing origin header")
        if self._allowed and origin not in self._allowed:
            raise WebSocketDisconnect(code=1008, reason=f"origin {origin} not allowed")

    @property
    def allowed_origins(self) -> list[str]:
        """Return the configured allow-list as a defensive copy.

        Reads from the native core when present; otherwise returns a new list
        built from the in-memory ``_allowed`` store so callers cannot mutate
        the validator's internal state.

        Returns:
            A list of origin strings the validator will accept. May be empty
            when no origins have been configured (which then allows any
            origin, provided ``allow_missing`` is respected).
        """
        if self._core:
            return self._core.allowed_origins()
        return list(self._allowed)
