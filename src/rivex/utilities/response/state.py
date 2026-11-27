"""``rivex.utilities.response.state`` — response-side state bag.

Middleware occasionally wants to attach metadata to the
response itself (audit-log correlation ids, request → response
timing breakdown, cache keys) without polluting the response
headers. The convention is ``response["state"]`` — a free-form
``dict`` that mirrors the request-side state bag.

These helpers keep that bag consistent with the request-side
:mod:`rivex.utilities.request.state` API so the two read like
twins.
"""

from __future__ import annotations

from typing import Any


class ResponseStateUtility:
    """Static helpers for reading and mutating ``response["state"]``."""

    @staticmethod
    def get_response_state(response: dict[str, Any], key: str, default: Any = None) -> Any:
        """Return ``response["state"][key]`` (or ``default`` when absent)."""
        state = response.get("state")
        if not isinstance(state, dict):
            return default
        return state.get(key, default)

    @staticmethod
    def set_response_state(response: dict[str, Any], key: str, value: Any) -> None:
        """Store ``value`` under ``state[key]``, creating the ``state`` dict if needed."""
        state = response.setdefault("state", {})
        if not isinstance(state, dict):
            new_state: dict[str, Any] = {}
            response["state"] = new_state
            state = new_state
        state[key] = value

    @staticmethod
    def update_response_state(response: dict[str, Any], **values: Any) -> None:
        """Bulk-merge ``values`` into ``state`` in a single call."""
        state = response.setdefault("state", {})
        if not isinstance(state, dict):
            state = {}
            response["state"] = state
        state.update(values)

    @staticmethod
    def pop_response_state(response: dict[str, Any], key: str, default: Any = None) -> Any:
        """Remove and return ``state[key]`` (or ``default`` when absent)."""
        state = response.get("state")
        if not isinstance(state, dict):
            return default
        return state.pop(key, default)

    @staticmethod
    def has_response_state(response: dict[str, Any], key: str) -> bool:
        """Return ``True`` when ``state[key]`` exists."""
        state = response.get("state")
        return isinstance(state, dict) and key in state

    @staticmethod
    def clear_response_state(response: dict[str, Any]) -> None:
        """Drop every key from the state bag (the dict itself stays in place)."""
        state = response.get("state")
        if isinstance(state, dict):
            state.clear()


__all__ = ["ResponseStateUtility"]
