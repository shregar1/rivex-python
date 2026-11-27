"""``rivex.utilities.request.state`` — per-request state bag.

The ``request_data["state"]`` dict is the framework's standard place
to attach arbitrary metadata produced by middleware (e.g. URN,
tenant id, authenticated user id) and consumed by route handlers
and downstream services.

The corresponding Rust-side copy lives in ``Request._from_raw``,
which lifts every ``request_data["state"]`` entry onto
``request.state`` so handlers see ``request.state.<key>`` instead
of having to dig through the raw dict.
"""

from __future__ import annotations

from typing import Any


class RequestStateUtility:
    """Static helpers for reading and mutating ``request_data["state"]``."""

    @staticmethod
    def get_request_state(request_data: dict[str, Any], key: str, default: Any = None) -> Any:
        """Return the value stored under ``state[key]``, or ``default`` when absent."""
        state = request_data.get("state")
        if not isinstance(state, dict):
            return default
        return state.get(key, default)

    @staticmethod
    def set_request_state(request_data: dict[str, Any], key: str, value: Any) -> None:
        """Store ``value`` under ``state[key]``, creating the ``state`` dict if needed."""
        state = request_data.setdefault("state", {})
        if not isinstance(state, dict):
            new_state: dict[str, Any] = {}
            request_data["state"] = new_state
            state = new_state
        state[key] = value

    @staticmethod
    def update_request_state(request_data: dict[str, Any], **values: Any) -> None:
        """Bulk-merge ``values`` into ``state`` in a single call."""
        state = request_data.setdefault("state", {})
        if not isinstance(state, dict):
            state = {}
            request_data["state"] = state
        state.update(values)

    @staticmethod
    def pop_request_state(request_data: dict[str, Any], key: str, default: Any = None) -> Any:
        """Remove and return ``state[key]``, or ``default`` when absent."""
        state = request_data.get("state")
        if not isinstance(state, dict):
            return default
        return state.pop(key, default)

    @staticmethod
    def has_request_state(request_data: dict[str, Any], key: str) -> bool:
        """Return ``True`` when ``state[key]`` exists."""
        state = request_data.get("state")
        return isinstance(state, dict) and key in state

    @staticmethod
    def clear_request_state(request_data: dict[str, Any]) -> None:
        """Drop every key from the state bag (the dict itself stays in place)."""
        state = request_data.get("state")
        if isinstance(state, dict):
            state.clear()


__all__ = ["RequestStateUtility"]
