"""``rivex.utilities.response.cookie`` — ``Set-Cookie`` header helpers.

Rivex writes cookies as raw ``Set-Cookie`` header entries — same
shape as every other header — so duplicates are preserved (the
browser applies them in order). These helpers build a single
``Set-Cookie`` value string from the usual ``name``, ``value``,
``max_age``, ``path``, ``domain``, ``secure``, ``httponly``,
``samesite`` arguments and append it through
:func:`ResponseHeaderUtility.add_response_header`.
"""

from __future__ import annotations

from typing import Any

from rivex.utilities.response.header import ResponseHeaderUtility


class ResponseCookieUtility:
    """Static helpers for writing ``Set-Cookie`` headers on the response."""

    SET_COOKIE: str = "set-cookie"

    @staticmethod
    def set_cookie(
        response: dict[str, Any],
        name: str,
        value: str,
        *,
        max_age: int | None = None,
        expires: str | None = None,
        path: str | None = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: str | None = None,
    ) -> None:
        """Append a ``Set-Cookie`` header built from the supplied attributes.

        ``max_age`` is rendered as ``Max-Age=<seconds>``; ``samesite``
        accepts the usual ``"Strict"``, ``"Lax"``, ``"None"`` values.
        """
        parts: list[str] = [f"{name}={value}"]
        if path:
            parts.append(f"Path={path}")
        if domain:
            parts.append(f"Domain={domain}")
        if max_age is not None:
            parts.append(f"Max-Age={int(max_age)}")
        if expires:
            parts.append(f"Expires={expires}")
        if secure:
            parts.append("Secure")
        if httponly:
            parts.append("HttpOnly")
        if samesite:
            parts.append(f"SameSite={samesite.capitalize()}")
        cookie_value = "; ".join(parts)
        ResponseHeaderUtility.add_response_header(response, ResponseCookieUtility.SET_COOKIE, cookie_value)

    @staticmethod
    def delete_cookie(
        response: dict[str, Any],
        name: str,
        *,
        path: str | None = "/",
        domain: str | None = None,
    ) -> None:
        """Append a ``Set-Cookie`` header that immediately expires the cookie on the client."""
        parts: list[str] = [f"{name}=", "Max-Age=0", "Expires=Thu, 01 Jan 1970 00:00:00 GMT"]
        if path:
            parts.append(f"Path={path}")
        if domain:
            parts.append(f"Domain={domain}")
        cookie_value = "; ".join(parts)
        ResponseHeaderUtility.add_response_header(response, ResponseCookieUtility.SET_COOKIE, cookie_value)

    @staticmethod
    def clear_all_cookies(response: dict[str, Any]) -> None:
        """Remove every ``Set-Cookie`` header on the response (the inverse of multiple ``set_cookie`` calls)."""
        ResponseHeaderUtility.remove_response_header(response, ResponseCookieUtility.SET_COOKIE)

    @staticmethod
    def has_cookie(response: dict[str, Any], name: str) -> bool:
        """Return ``True`` when any ``Set-Cookie`` header names ``name``."""
        for value in ResponseHeaderUtility.get_all_response_headers(response, ResponseCookieUtility.SET_COOKIE):
            cookie_name = value.split("=", 1)[0].strip()
            if cookie_name == name:
                return True
        return False


__all__ = ["ResponseCookieUtility"]
