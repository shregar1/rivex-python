from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

try:
    import rivex_core as _rc
    HAS_CORE = hasattr(_rc, "PyReconnectionTracker")
except ImportError:
    _rc = None
    HAS_CORE = False


class ReconnectionHelper:
    def __init__(
        self,
        max_deliver: int = 100,
        expiry: float = 300.0,
        on_resume: Callable | None = None,
    ):
        self._max_deliver = max_deliver
        self._expiry = expiry
        self._on_resume = on_resume
        self._buffers: dict[str, list[dict[str, Any]]] = {}
        self._seq: dict[str, int] = {}
        self._resume_tokens: dict[str, str] = {}
        if HAS_CORE:
            self._core = _rc.PyReconnectionTracker(max_deliver, expiry)
        else:
            self._core = None

    def create_resume_token(self, connection_id: str) -> str:
        if self._core:
            return self._core.create_resume_token(connection_id)
        token = f"resume:{connection_id}:{int(time.time())}"
        self._resume_tokens[connection_id] = token
        return token

    def resolve_token(self, token: str) -> str | None:
        if self._core:
            return None
        for cid, t in self._resume_tokens.items():
            if t == token:
                return cid
        return None

    def record_message(self, connection_id: str, message: Any) -> None:
        if self._core:
            self._core.record_message(connection_id, json_msg(message))
            return
        seq = self._seq.get(connection_id, 0) + 1
        self._seq[connection_id] = seq
        self._buffers.setdefault(connection_id, []).append(
            {"seq": seq, "message": message, "ts": time.time()}
        )
        buf = self._buffers[connection_id]
        while len(buf) > self._max_deliver:
            buf.pop(0)
        now = time.time()
        while buf and now - buf[0]["ts"] > self._expiry:
            buf.pop(0)

    def get_missed(self, connection_id: str, last_seq: int = 0) -> list[Any]:
        if self._core:
            return self._core.get_missed(connection_id, last_seq)
        return [
            entry["message"]
            for entry in self._buffers.get(connection_id, [])
            if entry["seq"] > last_seq
        ]

    def cleanup(self, connection_id: str) -> None:
        if self._core:
            self._core.cleanup(connection_id)
        self._buffers.pop(connection_id, None)
        self._seq.pop(connection_id, None)
        self._resume_tokens.pop(connection_id, None)

    def last_seq(self, connection_id: str) -> int:
        if self._core:
            return self._core.last_seq(connection_id)
        return self._seq.get(connection_id, 0)


def json_msg(message: Any) -> str:
    import json
    if isinstance(message, str):
        return message
    return json.dumps(message)
