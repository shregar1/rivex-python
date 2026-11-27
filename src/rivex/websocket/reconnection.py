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
        """Issue a fresh resume token that a client can present on reconnect.

        Delegates to the native ``PyReconnectionTracker`` when the Rust core is
        available; otherwise mints a ``"resume:<id>:<unix-ts>"`` string, stores
        it in the in-memory ``_resume_tokens`` map, and returns it. Tokens are
        the only handle a reconnecting client has to recover their buffered
        messages via :meth:`get_missed`.

        Args:
            connection_id: Stable identifier of the connection that is about
                to disconnect.

        Returns:
            A token string the client can send back on reconnect.
        """
        if self._core:
            return self._core.create_resume_token(connection_id)
        token = f"resume:{connection_id}:{int(time.time())}"
        self._resume_tokens[connection_id] = token
        return token

    def resolve_token(self, token: str) -> str | None:
        """Map a resume token back to the connection it was issued for.

        When the Rust core is available the lookup happens there; this helper
        returns ``None`` in that branch so the Rust implementation is the sole
        source of truth. In the pure-Python fallback the token map is scanned
        for an exact match and the corresponding connection id is returned.

        Args:
            token: The token string returned by :meth:`create_resume_token`
                and presented by the reconnecting client.

        Returns:
            The original ``connection_id`` if the token is known, otherwise
            ``None``.
        """
        if self._core:
            return None
        for cid, t in self._resume_tokens.items():
            if t == token:
                return cid
        return None

    def record_message(self, connection_id: str, message: Any) -> None:
        """Append a message to the per-connection replay buffer.

        Assigns a monotonically increasing sequence number and keeps at most
        ``_max_deliver`` entries in the buffer. Entries older than ``_expiry``
        seconds are pruned from the head of the buffer so reconnecting clients
        do not receive stale data on :meth:`get_missed`. When the Rust core is
        available this is delegated entirely to it.

        Args:
            connection_id: Identifier of the connection that produced the
                message.
            message: The message payload to retain for replay; stored verbatim
                and returned later by :meth:`get_missed`.
        """
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
        """Return messages buffered after the caller's last acknowledged sequence.

        Used during a resume handshake to replay messages the server emitted
        while the client was disconnected. Filtering is done by sequence
        number; only entries with ``seq > last_seq`` are returned, in order.
        The Rust core, when present, performs the same lookup natively.

        Args:
            connection_id: Identifier of the reconnecting client.
            last_seq: Highest sequence the client has already acknowledged.
                Pass ``0`` to receive every buffered message.

        Returns:
            A list of the buffered message payloads the client missed, in
            order. Empty when nothing matches or when no buffer exists for
            ``connection_id``.
        """
        if self._core:
            return self._core.get_missed(connection_id, last_seq)
        return [
            entry["message"]
            for entry in self._buffers.get(connection_id, [])
            if entry["seq"] > last_seq
        ]

    def cleanup(self, connection_id: str) -> None:
        """Drop all buffered state for a finished connection.

        Removes the replay buffer, the per-connection sequence counter, and
        any resume token associated with ``connection_id``. Safe to call on
        unknown ids: missing keys are ignored. Used during connection
        teardown so memory does not leak for connections that never reconnect.

        Args:
            connection_id: Identifier of the connection that is now closed
                and whose state should be discarded.
        """
        if self._core:
            self._core.cleanup(connection_id)
        self._buffers.pop(connection_id, None)
        self._seq.pop(connection_id, None)
        self._resume_tokens.pop(connection_id, None)

    def last_seq(self, connection_id: str) -> int:
        """Return the most recent sequence number recorded for a connection.

        Delegates to the Rust core when available; otherwise reads from the
        in-memory ``_seq`` map and returns ``0`` if no messages have ever
        been recorded for the connection. Used by resume handshakes to seed
        the ``last_seq`` argument of :meth:`get_missed`.

        Args:
            connection_id: Identifier of the connection to look up.

        Returns:
            The highest sequence number recorded so far, or ``0`` when the
            connection is unknown.
        """
        if self._core:
            return self._core.last_seq(connection_id)
        return self._seq.get(connection_id, 0)


def json_msg(message: Any) -> str:
        """Serialise ``message`` to JSON, leaving strings untouched.

        Convenience helper used by the pure-Python fallback path so callers
        do not have to repeat the ``isinstance(message, str)`` short-circuit.
        Strings round-trip unchanged; everything else is encoded with the
        standard-library ``json`` module.

        Args:
            message: Either a pre-serialised string or any JSON-encodable
                object.

        Returns:
            A JSON-encoded string suitable for handing to the Rust core via
            :meth:`record_message`.
        """
        import json
        if isinstance(message, str):
            return message
        return json.dumps(message)
