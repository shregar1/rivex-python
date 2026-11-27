"""Redirect/rewrite handler via Rust const routes.

Registers HTTP redirect responses (301/302) as Rust const routes.
The redirect is served entirely from the Rust HashMap — no Python
involvement at request time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rivex.applications.applications import Rivex


def redirect(
    app: Rivex,
    from_path: str,
    to_path: str,
    *,
    permanent: bool = True,
    method: str = "GET",
) -> None:
    """Register an HTTP redirect as a Rust const route.

    Args:
        app: Rivex application instance.
        from_path: URL path to redirect from (e.g. ``"/old-page"``).
        to_path: Destination URL (e.g. ``"/new-page"`` or
            ``"https://example.com/new-page"``).
        permanent: ``True`` for 301 Moved Permanently (browsers cache
            indefinitely), ``False`` for 302 Found (temporary).
        method: HTTP method to match (default ``"GET"``).

    Note:
        301 redirects are cached aggressively by browsers. For
        time-limited redirects (A/B tests, maintenance), use
        ``permanent=False`` (302).
    """
    status = 301 if permanent else 302
    headers: list[tuple[str, str]] = [("location", to_path)]
    # Empty body — redirects don't need one
    body = b""

    app.add_const_route(method, from_path, status, body, headers)
