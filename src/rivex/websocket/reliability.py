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
        """Register a message as in-flight under ``msg_id``.

        Records the message so a subsequent ``ack`` or ``nack`` from the
        recipient can settle it. When the native core is present, dicts are
        JSON-encoded before being handed off; the pure-Python fallback stores
        the payload verbatim alongside a ``pending`` marker.

        Args:
            msg_id: Unique identifier the recipient will echo back in its
                acknowledgement.
            message: The payload to track, either already-serialised or a
                dict that will be serialised by the native core.
        """
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
        """Mark ``msg_id`` as successfully delivered and return its payload.

        Removes the entry from the in-flight store (delegating to the native
        core when available). The return value lets callers log or post-process
        the payload that was just acknowledged.

        Args:
            msg_id: Identifier originally passed to :meth:`send`.

        Returns:
            A string representation of the acknowledged entry, or ``None``
            when ``msg_id`` was unknown and there was nothing to acknowledge.
        """
        if self._core:
            return self._core.ack(msg_id)
        entry = self._store.pop(msg_id, None)
        return str(entry) if entry else None

    def nack(self, msg_id: str) -> str | None:
        """Record a negative acknowledgement and bump the retry counter.

        Increments ``retries`` on the in-flight entry; once ``retries`` reaches
        ``max_retries`` the entry is evicted and a ``"failed after N retries"``
        diagnostic string is returned so the caller can surface a permanent
        failure. When the Rust core is present it owns the bookkeeping and
        returns the diagnostic directly.

        Args:
            msg_id: Identifier originally passed to :meth:`send`.

        Returns:
            A failure description if the message has exhausted its retry
            budget, otherwise ``None``.
        """
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
        """Return the ids of messages still awaiting acknowledgement.

        Reads from the native core when available; otherwise iterates over the
        in-flight ``_store`` and returns its current keys.

        Returns:
            A list of ``msg_id`` strings. Empty when nothing is pending.
        """
        if self._core:
            return list(self._core.pending_messages())
        return list(self._store.keys())

    def is_delivered(self, msg_id: str) -> bool:
        """Return whether ``msg_id`` is no longer in the pending store.

        A message is considered delivered when it has been removed from the
        in-flight store — either by an :meth:`ack`, an exhausted
        :meth:`nack`, or because it was never sent.

        Args:
            msg_id: Identifier originally passed to :meth:`send`.

        Returns:
            ``True`` when ``msg_id`` is no longer pending, ``False`` while
            it is still tracked.
        """
        if self._core:
            return self._core.is_delivered(msg_id)
        return msg_id not in self._store

    def check_timeouts(self) -> list[str]:
        """Return messages that exceeded the ``retry_timeout`` budget.

        The pure-Python fallback does not track per-message send timestamps,
        so it always returns an empty list. The native core owns the timeout
        logic and reports timed-out ids back through this method.

        Returns:
            A list of ``msg_id`` strings whose acknowledgement deadline has
            passed. Empty when the native core is absent or no timeouts are
            due.
        """
        if self._core:
            return list(self._core.check_timeouts())
        return []

    def clear(self) -> None:
        """Discard every in-flight message from the tracker.

        Resets both the native core (when present) and the in-memory ``_store``
        so the tracker behaves as if freshly constructed. Useful when tearing
        down a session and not wanting any pending entries to survive.

        Note:
            Acknowledgements for cleared ids will not be matched; callers that
            intend to reconnect should send them again with fresh ``msg_id``
            values.
        """
        if self._core:
            self._core.clear()
        self._store.clear()
