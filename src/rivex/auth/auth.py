"""``@authenticated`` / ``@admin_only`` decorators + ``@jwt_required()``.

Quick start (resolver-based):

    from rivex import authenticated, set_user_resolver
    from rivex.core.context import current_user

    async def resolve_user(request):
        token = request.cookies.get("session")
        if not token:
            return None
        return await users.find_by_session(token)

    set_user_resolver(resolve_user)

    class WidgetsController(Controller):
        @post("/{widget_id}/archive")
        @authenticated
        async def archive(self, request, widget_id: int = Path()):
            user = current_user()
            return {"archived_by": user.email}

Quick start (JWT):

    from rivex.auth.auth import jwt_required
    from rivex.middleware.middleware_auth import JWTAuthMiddleware

    app.add_middleware(JWTAuthMiddleware, secret="my-secret")

    @app.get("/profile")
    @jwt_required(secret="my-secret")
    async def get_profile(auth: dict):
        return {"user_id": auth.get("sub")}
"""

from __future__ import annotations

import asyncio
import base64
import functools
import hashlib
import hmac
import json
import time
from typing import Any, Awaitable, Callable, TypeVar

from rivex.core._compat import HAS_CORE
from rivex.core._compat import rc as _rc
from rivex.core.context import bind_user, request_context
from rivex.core.exceptions import HTTPException
from rivex.core.requests import Request

_UserResolver = Callable[[Request], Awaitable[Any] | Any]
_USER_RESOLVER: _UserResolver | None = None


def _extract_auth_from_request_data(request_data: dict) -> str | None:
    """Extract ``Bearer`` token from the internal ``request_data`` dict."""
    hdrs = request_data.get("headers")
    if isinstance(hdrs, dict):
        return hdrs.get("Authorization")
    if isinstance(hdrs, list):
        for k, v in hdrs:
            if isinstance(k, bytes):
                k = k.decode("latin-1")
            if k.lower() == "authorization":
                if isinstance(v, bytes):
                    return v.decode("latin-1")
                return v
    return None


def _build_jwt_wrapper(handler: Callable, jwt_config: dict) -> Callable:
    """Wrap an existing ``(request_data) -> dict`` handler with JWT verification.

    Used by :meth:`Rivex._build` and :class:`ASGIAdapter._build` so routes
    decorated with ``@jwt_required`` enforce authentication even when the
    Rust middleware pipeline is not active.
    """
    verify = jwt_config["verify"]

    async def jwt_wrapper(request_data: dict) -> dict:
        auth_header = _extract_auth_from_request_data(request_data)
        if not auth_header:
            from rivex.core._injection import _http_exception_response
            return _http_exception_response(HTTPException(401, "Missing authorization header"))

        prefix = "Bearer "
        if not auth_header.startswith(prefix):
            from rivex.core._injection import _http_exception_response
            return _http_exception_response(HTTPException(401, "Invalid authorization scheme"))

        token = auth_header[len(prefix):].strip()
        claims = verify(token)
        if claims is None:
            from rivex.core._injection import _http_exception_response
            return _http_exception_response(HTTPException(401, "Invalid token"))

        _stash_user(claims)
        ctx = request_context()
        if ctx is not None:
            ctx.extras["auth"] = claims

        return await handler(request_data)

    return jwt_wrapper


def set_user_resolver(resolver: _UserResolver) -> None:
    """Register an async/sync callable that resolves a user from a request.

    The resolver receives a :class:`rivex.requests.Request` and should
    return the user object (or ``None`` to reject). It is called by
    ``@authenticated`` / ``@admin_only`` **before** the handler body.
    """
    global _USER_RESOLVER
    _USER_RESOLVER = resolver


def get_user_resolver() -> _UserResolver | None:
    """Return the currently installed user resolver (or ``None``)."""
    return _USER_RESOLVER


def current_user() -> Any | None:
    """Return the user object for the current request, or ``None``.

    Must be called inside a request context (after the middleware has
    stamped the user via ``@authenticated``).
    """
    ctx = request_context()
    if ctx is None:
        return None
    return ctx.extras.get("user")


def _find_request(args: tuple, kwargs: dict) -> Any:
    for arg in args:
        if isinstance(arg, Request):
            return arg
    for v in kwargs.values():
        if isinstance(v, Request):
            return v
    req = kwargs.get("request")
    if req is not None:
        return req
    if args:
        first = args[0]
        if isinstance(first, Request):
            return first
    return None


def _stash_user(user: Any) -> None:
    ctx = request_context()
    if ctx is not None:
        ctx.extras["user"] = user
        uid = getattr(user, "id", None)
        if uid is not None:
            bind_user(uid)


def authenticated(
    fn: Callable | None = None,
    *,
    roles: list[str] | None = None,
    resolver: _UserResolver | None = None,
    inject: bool = False,
) -> Callable:
    """Decorator that requires the user to be logged in.

    Uses the registered user resolver (``set_user_resolver``) to
    fetch the user. Raises ``401`` when no user is resolved, or
    ``403`` when role requirements are not met.

    Can be used bare (``@authenticated``) or with args
    (``@authenticated(roles=["admin"])``).  Pass a ``resolver``
    to override the global resolver for a single handler::

        @authenticated(resolver=my_resolver)
        async def handler(request):
            ...

    When ``inject=True`` the resolved user object is passed as the
    ``user`` keyword argument to the handler.
    """

    def _decorator(fn: Callable) -> Callable:
        effective_resolver = resolver if resolver is not None else _USER_RESOLVER

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal effective_resolver
            if effective_resolver is None:
                effective_resolver = resolver if resolver is not None else _USER_RESOLVER
            if effective_resolver is None:
                raise RuntimeError(
                    "No user resolver registered. Call set_user_resolver()."
                )

            request = _find_request(args, kwargs)
            if request is None:
                raise RuntimeError(
                    "Could not find a Request object among arguments. "
                    "Add a ``request: Request`` parameter to the handler."
                )

            result = effective_resolver(request)
            if asyncio.iscoroutine(result):
                user = await result
            else:
                user = result

            if user is None:
                raise HTTPException(401, "Not authenticated")

            if roles:
                user_roles = getattr(user, "roles", None) or getattr(user, "role", None)
                if user_roles is None:
                    user_roles = []
                elif isinstance(user_roles, str):
                    user_roles = [user_roles]
                if not any(r in user_roles for r in roles):
                    raise HTTPException(
                        403,
                        f"Requires one of: {', '.join(roles)}",
                    )

            _stash_user(user)
            if inject:
                kwargs.setdefault("user", user)
            return await fn(*args, **kwargs)

        return wrapper

    if fn is not None:
        return _decorator(fn)
    return _decorator


def admin_only(
    fn: Callable | None = None,
    *,
    resolver: _UserResolver | None = None,
) -> Callable:
    """Decorator that requires the user to be an admin.

    Equivalent to ``@authenticated(roles=["admin"])``.
    """
    if fn is not None:
        return authenticated(roles=["admin"], resolver=resolver)(fn)
    return authenticated(roles=["admin"], resolver=resolver)


def get_jwt_claims() -> dict[str, Any] | None:
    """Return the decoded JWT claims for the current request, or ``None``.

    Must be called inside a request context after ``@jwt_required`` has
    run.  Handlers access claims this way instead of via a parameter:

        @app.get("/profile")
        @jwt_required(secret="my-secret")
        async def get_profile():
            auth = get_jwt_claims()
            return {"user_id": auth.get("sub")}
    """
    ctx = request_context()
    if ctx is None:
        return None
    return ctx.extras.get("auth")


def _b64_decode(s: str) -> bytes:
    padded = s + "=" * (4 - len(s) % 4) if len(s) % 4 else s
    return base64.urlsafe_b64decode(padded)


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode the payload of a JWT **without** verifying the signature."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = _b64_decode(parts[1])
        return json.loads(payload)
    except (ValueError, json.JSONDecodeError, IndexError):
        return None


F = TypeVar("F", bound=Callable)

def jwt_required(
    *,
    algorithm: str = "HS256",
    secret: str | None = None,
) -> Callable[[F], F]:
    """Decorator that requires a valid JWT and stores claims in request context.

    Access claims via :func:`get_jwt_claims` inside the handler::

        @app.get("/profile")
        @jwt_required(secret="my-secret")
        async def get_profile():
            auth = get_jwt_claims()
            return {"user_id": auth.get("sub")}

    The **signature is verified** using the provided ``secret``, so this
    works on both the Rust pipeline (where the middleware also validates)
    and the ASGI/uvicorn path.

    Parameters
    ----------
    algorithm:
        JWT algorithm (default ``"HS256"``).
    secret:
        HMAC secret for signature verification.  Required.
    """

    def _verify(token: str) -> dict[str, Any] | None:
        alg = algorithm.upper()
        if HAS_CORE and alg in ("HS256", "HS384", "HS512"):
            try:
                payload_str: str = _rc.jwt_decode_alg(token, secret or "", alg, True)
            except (ValueError, TypeError):
                return None
            decoded: dict[str, Any] = json.loads(payload_str)
            exp = decoded.get("exp")
            if exp is not None and time.time() > exp:
                return None
            return decoded

        payload = _decode_jwt_payload(token)
        if payload is None:
            return None

        parts = token.split(".")
        if algorithm.upper().startswith("HS"):
            if secret is None:
                return None
            signing_input = f"{parts[0]}.{parts[1]}".encode()
            sig_size = {
                "HS256": 32,
                "HS384": 48,
                "HS512": 64,
            }.get(algorithm.upper(), 32)
            hash_algo = {
                "HS256": hashlib.sha256,
                "HS384": hashlib.sha384,
                "HS512": hashlib.sha512,
            }.get(algorithm.upper(), hashlib.sha256)
            expected = hmac.new(secret.encode(), signing_input, hash_algo).digest()
            actual = _b64_decode(parts[2])
            if not hmac.compare_digest(expected[:sig_size], actual):
                return None
        exp = payload.get("exp")
        if exp is not None:
            if time.time() > exp:
                return None

        return payload

    def decorator(func: F) -> F:
        # Store JWT config so applications.py can build the handler correctly
        func._rivex_jwt_config = {"secret": secret, "algorithm": algorithm, "verify": _verify}
        return func

    return decorator
