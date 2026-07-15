from __future__ import annotations

from rivex.core.exceptions import WebSocketDisconnect

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
        if self._core:
            return self._core.allowed_origins()
        return list(self._allowed)
