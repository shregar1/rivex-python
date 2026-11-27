"""``@authenticated`` / ``@admin_only`` decorators + ``@jwt_required()``.

Quick start (resolver-based):

    from rivex import authenticated, set_user_resolver
    from rivex.context.context import current_user

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

from rivex.native._compat import HAS_CORE
from rivex.native._compat import rc as _rc
from rivex.context.context import bind_user, request_context
from rivex.exceptions.http.exceptions import HTTPException
from rivex.http.requests import Request

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
        """Verify a JWT and invoke the wrapped handler, returning the response.

        Pulls the ``Authorization`` header from ``request_data``, requires a
        ``Bearer`` token, and runs the configured ``verify`` callable to
        validate the signature and expiry. On failure, a 401 HTTP exception
        response is returned without ever touching the wrapped handler. On
        success, the claims are stashed on the active request context and the
        downstream handler is awaited.

        Args:
            request_data: The in-flight request envelope carried by the
                Rust/ASGI pipeline. Only its ``headers`` mapping is read.

        Returns:
            The downstream handler's response dict, or a 401 error response
            built from :class:`HTTPException` when authentication fails.
        """
        auth_header = _extract_auth_from_request_data(request_data)
        if not auth_header:
            from rivex.di._injection import _http_exception_response
            return _http_exception_response(HTTPException(401, "Missing authorization header"))

        prefix = "Bearer "
        if not auth_header.startswith(prefix):
            from rivex.di._injection import _http_exception_response
            return _http_exception_response(HTTPException(401, "Invalid authorization scheme"))

        token = auth_header[len(prefix):].strip()
        claims = verify(token)
        if claims is None:
            from rivex.di._injection import _http_exception_response
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
    """Locate the first :class:`Request` instance in a handler call's arguments.

    Inspects positional args first, then keyword values, then a ``request``
    keyword specifically, and finally falls back to the first positional arg
    if it is a request. Returns ``None`` when no request is found so the
    caller can raise an informative error.

    Args:
        args: Positional arguments the handler was invoked with.
        kwargs: Keyword arguments the handler was invoked with.

    Returns:
        The first :class:`Request` instance discovered, or ``None``.
    """
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
    """Bind the resolved user to the active request context, if any.

    Stashes ``user`` under the ``user`` key of the current request context's
    ``extras`` map, then also calls :func:`bind_user` with the user's
    ``id`` attribute (when present) so per-request logging/tracing can pick
    it up. A no-op when no request context is active.

    Args:
        user: The resolved user object. May be ``None`` for callers that
            only need the ``id``-based binding; both branches tolerate it.
    """
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
        """Build the async wrapper that enforces authentication around ``fn``.

        Resolves the per-call user via the registered or per-handler
        ``resolver``, raises :class:`HTTPException` 401 when no user is
        returned, enforces any required ``roles`` (else 403), stashes the
        user on the request context, and optionally injects it as the
        ``user`` kwarg before delegating to the wrapped coroutine.

        Args:
            fn: The async handler to wrap.

        Returns:
            A coroutine function that performs the auth checks and then
            awaits ``fn`` with the original arguments.
        """
        effective_resolver = resolver if resolver is not None else _USER_RESOLVER

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Authenticate the request, then delegate to the wrapped handler.

            Re-resolves the user resolver inside the coroutine to avoid
            binding issues across the event loop, locates the inbound
            :class:`Request`, runs the resolver, enforces any required
            roles, stashes the user, and finally awaits the wrapped
            handler with the original arguments (and ``user`` injected
            when ``inject=True``).

            Args:
                *args: Positional arguments forwarded to the handler.
                **kwargs: Keyword arguments forwarded to the handler;
                    ``user`` is added here when ``inject`` is set on
                    the outer decorator.

            Returns:
                Whatever the wrapped handler returns.

            Raises:
                RuntimeError: If no user resolver is registered or no
                    :class:`Request` is found among the arguments.
                HTTPException: 401 when authentication fails, 403 when
                    role requirements are not satisfied.
            """
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
    """Decode a URL-safe base64 string, restoring any missing ``=`` padding.

    JWT base64 segments are required to omit trailing ``=`` padding, so
    callers pass the raw segment directly. Padding is re-added before
    delegating to :func:`base64.urlsafe_b64decode`.

    Args:
        s: A URL-safe base64 string that may be missing trailing
            ``=`` padding.

    Returns:
        The decoded raw bytes.
    """
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
        """Verify a JWT and return its claims, or ``None`` if verification fails.

        Prefers the Rust core verifier for ``HS256``/``HS384``/``HS512`` when
        available, falling back to a pure-Python HMAC implementation. Always
        checks the ``exp`` claim against the current time and rejects
        expired tokens by returning ``None``.

        Args:
            token: The raw ``header.payload.signature`` JWT string.

        Returns:
            The decoded claims dict on success, or ``None`` if the
            signature does not match, the token is malformed, or the
            ``exp`` claim has elapsed.
        """
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
        """Attach the JWT configuration to the handler for the router to use.

        Stores the verification callable together with the secret and
        algorithm on a private attribute of ``func`` so
        :class:`Rivex._build` can wire up the same verifier in the Rust
        pipeline that runs the actual request.

        Args:
            func: The async handler to annotate.

        Returns:
            The same ``func``, mutated in place with a
            ``_rivex_jwt_config`` attribute.
        """
        # Store JWT config so applications.py can build the handler correctly
        func._rivex_jwt_config = {"secret": secret, "algorithm": algorithm, "verify": _verify}
        return func

    return decorator
