from __future__ import annotations

import json
from typing import Any

try:
    import rivex_core as _rc
    HAS_CORE = hasattr(_rc, "PyMessageAckTracker")
except ImportError:
    _rc = None
    HAS_CORE = False


class MessageAckTracker:
    def __init__(self, max_retries: int = 3, retry_timeout: float = 30.0):
        self._max_retries = max_retries
        self._retry_timeout = retry_timeout
        if HAS_CORE:
            self._core = _rc.PyMessageAckTracker(max_retries, retry_timeout)
        else:
            self._core = None
        self._store: dict[str, dict[str, Any]] = {}

    def send(self, msg_id: str, message: str | dict[str, Any]) -> None:
        if self._core:
            payload = json.dumps(message) if isinstance(message, dict) else message
            self._core.send(msg_id, payload)
            return
        self._store[msg_id] = {
            "message": message,
            "retries": 0,
            "status": "pending",
        }

    def ack(self, msg_id: str) -> str | None:
        if self._core:
            return self._core.ack(msg_id)
        entry = self._store.pop(msg_id, None)
        return str(entry) if entry else None

    def nack(self, msg_id: str) -> str | None:
        if self._core:
            return self._core.nack(msg_id)
        entry = self._store.get(msg_id)
        if entry is None:
            return None
        entry["retries"] += 1
        if entry["retries"] >= self._max_retries:
            self._store.pop(msg_id, None)
            return f"failed after {self._max_retries} retries: {entry['message']}"
        return None

    def pending_messages(self) -> list[str]:
        if self._core:
            return list(self._core.pending_messages())
        return list(self._store.keys())

    def is_delivered(self, msg_id: str) -> bool:
        if self._core:
            return self._core.is_delivered(msg_id)
        return msg_id not in self._store

    def check_timeouts(self) -> list[str]:
        if self._core:
            return list(self._core.check_timeouts())
        return []

    def clear(self) -> None:
        if self._core:
            self._core.clear()
        self._store.clear()
