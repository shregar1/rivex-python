from __future__ import annotations

import asyncio

from rivex.core._compat import get_request_header, json_error_response
from rivex.middleware.middleware import Middleware


class Guard:
    """Base guard. Override __call__(request_data) to implement.

    Return True to allow. Raise HTTPException to deny.
    Can be used as:
    1. Global: app.add_middleware(GuardMiddleware, guards=[IsAuthenticated()])
    2. Per-route via Depends: @app.get("/", dependencies=[Depends(IsAuthenticated())])
    """

    def __call__(self, request_data: dict) -> bool:
        raise NotImplementedError


class IsAuthenticated(Guard):
    """Requires Authorization header."""

    def __call__(self, request_data):
        from rivex.core.exceptions import HTTPException

        if not get_request_header(request_data, "authorization"):
            raise HTTPException(401, "Not authenticated")
        return True


class RequiresRoles(Guard):
    """Requires specific roles in x-user-roles header (comma-separated)."""

    def __init__(self, *roles: str):
        self.required = set(roles)

    def __call__(self, request_data):
        from rivex.core.exceptions import HTTPException

        roles_header = get_request_header(request_data, "x-user-roles") or ""
        user_roles = {r.strip() for r in roles_header.split(",") if r.strip()}
        if not self.required.intersection(user_roles):
            raise HTTPException(403, "Insufficient permissions")
        return True


class AllowAll(Guard):
    def __call__(self, request_data):
        return True


class DenyAll(Guard):
    def __call__(self, request_data):
        from rivex.core.exceptions import HTTPException

        raise HTTPException(403, "Access denied")


class GuardMiddleware(Middleware):
    """Applies guard checks to all requests passing through."""

    def __init__(self, guards: list[Guard | type]):
        self._guards = [g() if isinstance(g, type) else g for g in guards]

    async def process(self, request_data, call_next):
        from rivex.core.exceptions import HTTPException

        for g in self._guards:
            try:
                result = g(request_data)
                if asyncio.iscoroutine(result):
                    await result
            except HTTPException as exc:
                return json_error_response(exc.status_code, exc.detail)
        return await call_next(request_data)
