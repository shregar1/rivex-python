"""``rivex.middleware.trailing_slash`` — trailing slash normalisation middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.constants.api.header import Header
from rivex.constants.api.http_status import HTTPStatus
from rivex.middleware.abstraction import IMiddleware


class TrailingSlashMiddleware(IMiddleware):
    """Normalises trailing slashes via redirect or in-place path rewrite.

    Parameters:
        redirect: Issue a 307 redirect when ``True``; rewrite the path in-place
                  when ``False``.
        action:   ``"strip"`` removes a trailing slash; ``"append"`` adds one.
    """

    def __init__(self, redirect: bool = True, action: str = "strip"):
        self.redirect = redirect
        self.action = action

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        path = request_data.get("path", "/")
        new_path: str | None = None

        if path != "/" and len(path) > 1:
            if self.action == "strip" and path.endswith("/"):
                new_path = path.rstrip("/")
            elif self.action == "append" and not path.endswith("/"):
                new_path = path + "/"

        if new_path and new_path != path:
            if self.redirect:
                qs = request_data.get("query_string", "")
                location = new_path + ("?" + qs if qs else "")
                return {"status": HTTPStatus.TEMPORARY_REDIRECT, "headers": [(Header.LOCATION, location)], "body": b""}
            request_data = dict(request_data)
            request_data["path"] = new_path

        return await call_next(request_data)


__all__ = ["TrailingSlashMiddleware"]
