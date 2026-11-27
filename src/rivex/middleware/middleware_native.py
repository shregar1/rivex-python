"""Tier 5 — request-shape / security-headers middleware.

These classes mirror the Rust implementations in
``rivex-middleware::{security_headers, request_context,
request_timeout, request_validation}``. The Rust core is the
authoritative source of truth (its tests are the contract) and the
Python classes here provide ASGI-compatible behaviour so the same
configuration works under the TestClient, uvicorn, and (in a
forthcoming pyo3 bridge) the Rust server fast path.

Install them through the usual ``app.add_middleware(...)`` entry
point — no special wiring required::

    from rivex.middleware.middleware_native import (
        SecurityHeadersMiddleware,
        RequestContextMiddleware,
        RequestTimeoutMiddleware,
        RequestValidationMiddleware,
        AuditLoggerMiddleware,
        AuthorizationMiddleware,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuditLoggerMiddleware, subject_header="X-User-Id")
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from rivex.middleware.abstraction import IMiddleware


_logger = logging.getLogger("rivex.audit")


# ── Security headers ────────────────────────────────────────────────


class SecurityHeadersMiddleware(IMiddleware):
    """Add the standard browser-facing response headers.

    See ``rivex-middleware::security_headers`` for the full schema
    and the rationale behind the defaults.
    """

    _SAFETY_HEADER_NAMES = (
        "Content-Security-Policy",
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Cross-Origin-Opener-Policy",
        "Cross-Origin-Resource-Policy",
        "Cross-Origin-Embedder-Policy",
    )

    def __init__(
        self,
        content_security_policy: str = "default-src 'self'",
        x_frame_options: str | None = "DENY",
        x_content_type_options: str | None = "nosniff",
        referrer_policy: str | None = "strict-origin-when-cross-origin",
        permissions_policy: dict[str, list[str]] | None = None,
        coop: str | None = "same-origin",
        corp: str | None = "same-origin",
        coep: str | None = None,
    ) -> None:
        self.csp = content_security_policy
        self.x_frame_options = x_frame_options
        self.x_content_type_options = x_content_type_options
        self.referrer_policy = referrer_policy
        self.permissions_policy = permissions_policy or {}
        self.coop = coop
        self.corp = corp
        self.coep = coep

    def _apply(self, headers: list[tuple[str, str]]) -> list[tuple[str, str]]:
        def upsert(name: str, value: str | None) -> None:
            if value is None or value == "":
                return
            # Replace existing header rather than append duplicates.
            for i, (k, _) in enumerate(headers):
                if k.lower() == name.lower():
                    headers[i] = (name, value)
                    return
            headers.append((name, value))

        upsert("Content-Security-Policy", self.csp or None)
        upsert("X-Frame-Options", self.x_frame_options)
        upsert("X-Content-Type-Options", self.x_content_type_options)
        upsert("Referrer-Policy", self.referrer_policy)
        if self.permissions_policy:
            rendered = ", ".join(
                f"{feat}=()" if not allow else f"{feat}=(" + " ".join(allow) + ")"
                for feat, allow in sorted(self.permissions_policy.items())
            )
            upsert("Permissions-Policy", rendered)
        upsert("Cross-Origin-Opener-Policy", self.coop)
        upsert("Cross-Origin-Resource-Policy", self.corp)
        upsert("Cross-Origin-Embedder-Policy", self.coep)
        return headers

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        response = call_next(request_data)
        if asyncio.iscoroutine(response):
            response = await response
        headers = list(response.get("headers", []) or [])
        self._apply(headers)
        response["headers"] = headers
        return response


# ── Request context ─────────────────────────────────────────────────


class RequestContextMiddleware(IMiddleware):
    """Propagate a request id and tenant id through the request lifecycle.

    The request id is read from ``X-Request-Id`` (configurable); if
    missing it is minted. The chosen id is echoed on the response so
    clients can correlate.
    """

    def __init__(
        self,
        request_id_header: str = "X-Request-Id",
        tenant_id_header: str = "X-Tenant-Id",
    ) -> None:
        self.request_id_header = request_id_header
        self.tenant_id_header = tenant_id_header

    @staticmethod
    def _new_request_id() -> str:
        return f"req-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        headers = list(request_data.get("headers", []) or [])
        rid = next(
            (v for k, v in headers if k.lower() == self.request_id_header.lower()),
            None,
        )
        if not rid or len(rid) > 128:
            rid = self._new_request_id()
        tenant = next(
            (v for k, v in headers if k.lower() == self.tenant_id_header.lower()),
            None,
        )

        request_data["extensions"] = {
            **(request_data.get("extensions") or {}),
            "request_id": rid,
            "tenant_id": tenant,
            "started_at": time.perf_counter(),
        }

        response = call_next(request_data)
        if asyncio.iscoroutine(response):
            response = await response
        response_headers = list(response.get("headers", []) or [])
        response_headers.append((self.request_id_header, rid))
        response["headers"] = response_headers
        return response


# ── Request timeout ─────────────────────────────────────────────────


class RequestTimeoutMiddleware(IMiddleware):
    """Enforce a wall-clock budget per request.

    If the downstream call does not complete within ``timeout_ms``
    the middleware short-circuits with ``503 Service Unavailable``
    (configurable) and the inner future is allowed to keep running
    (cancellation is best-effort and depends on handler tolerance).
    """

    def __init__(
        self,
        timeout_ms: int = 30_000,
        status_on_timeout: int = 503,
        message: str = "Request timed out",
    ) -> None:
        self.timeout_ms = timeout_ms
        self.status_on_timeout = status_on_timeout
        self.message = message

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        fut = asyncio.ensure_future(call_next(request_data))
        try:
            return await asyncio.wait_for(fut, timeout=self.timeout_ms / 1000.0)
        except asyncio.TimeoutError:
            return {
                "status": self.status_on_timeout,
                "headers": [("content-type", "text/plain; charset=utf-8")],
                "body": self.message.encode("utf-8"),
            }


# ── Request validation ──────────────────────────────────────────────


class RequestValidationMiddleware(IMiddleware):
    """Reject malformed requests at the boundary.

    The three independent gates — content-type allow-list on
    mutating methods, required-headers, and a body-size limit —
    mirror ``rivex-middleware::request_validation``.
    """

    _MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
    _ALLOWED_CT = frozenset(
        {
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
            "text/plain",
        }
    )

    def __init__(
        self,
        allowed_content_types: list[str] | None = None,
        required_headers: list[str] | None = None,
        max_body_size: int | None = None,
    ) -> None:
        self.allowed_content_types = (
            frozenset(allowed_content_types)
            if allowed_content_types is not None
            else self._ALLOWED_CT
        )
        self.required_headers = [h.lower() for h in (required_headers or [])]
        self.max_body_size = max_body_size

    def _violation(self, status: int, detail: str) -> dict:
        return {
            "status": status,
            "headers": [("content-type", "text/plain; charset=utf-8")],
            "body": detail.encode("utf-8"),
        }

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        headers = dict(
            (k.lower(), v) for k, v in (request_data.get("headers", []) or [])
        )

        for name in self.required_headers:
            if name not in headers:
                return self._violation(400, f"Missing required header: {name}")

        body = request_data.get("body", b"") or b""
        if isinstance(body, str):
            body = body.encode("utf-8")
        if self.max_body_size is not None and len(body) > self.max_body_size:
            return self._violation(
                413, f"Request body too large: {len(body)} > {self.max_body_size}"
            )

        method = (request_data.get("method") or "GET").upper()
        if method in self._MUTATING and body and self.allowed_content_types:
            ct = headers.get("content-type", "").split(";")[0].strip().lower()
            if ct not in self.allowed_content_types:
                return self._violation(
                    415,
                    f"Unsupported media type: {ct or '<missing>'}",
                )

        return await call_next(request_data) if asyncio.iscoroutinefunction(
            call_next
        ) else call_next(request_data)


# ── Idempotency middleware ──────────────────────────────────────────


class IdempotencyMiddleware(IMiddleware):
    """Middleware equivalent of ``Idempotency-Key`` dedup.

    Reads ``Idempotency-Key`` header on mutating requests
    (POST/PUT/PATCH/DELETE). First request with a given key
    runs normally and the response is cached for ``ttl_ms``.
    Subsequent requests with the same key replay the cached
    response (same status + headers + body) and stamp
    ``idempotency-replayed: true`` so the client knows.

    The default backend is the in-process cache; an
    application with multiple workers should swap
    :attr:`cache` for a Redis-backed dict at startup.
    """

    _DEFAULT_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def __init__(
        self,
        key_header: str = "Idempotency-Key",
        ttl_ms: int = 86_400 * 1000,
        max_body_size: int = 1_048_576,
    ) -> None:
        self.key_header = key_header
        self.ttl_ms = ttl_ms
        self.max_body_size = max_body_size
        self.cache: dict[str, dict] = {}

    async def process(self, request_data: dict, call_next):
        method = (request_data.get("method") or "GET").upper()
        if method not in self._DEFAULT_MUTATING:
            return await call_next(request_data) if asyncio.iscoroutinefunction(
                call_next
            ) else call_next(request_data)

        headers = {
            k.lower(): v for k, v in (request_data.get("headers", []) or [])
        }
        key = headers.get(self.key_header.lower(), "").strip()
        if not key or len(key) > 200:
            return await call_next(request_data) if asyncio.iscoroutinefunction(
                call_next
            ) else call_next(request_data)

        cached = self.cache.get(key)
        if cached is not None:
            replay = dict(cached)
            replay["headers"] = list(cached.get("headers", [])) + [
                ("idempotency-replayed", "true")
            ]
            return replay

        response = await call_next(request_data) if asyncio.iscoroutinefunction(
            call_next
        ) else call_next(request_data)

        if not isinstance(response, dict):
            return response
        status = int(response.get("status", 0))
        if 500 <= status < 600:
            return response

        body = response.get("body", b"")
        if isinstance(body, str):
            body = body.encode("utf-8")
        if len(body) > self.max_body_size:
            return response

        self.cache[key] = response
        return response


# ── Exception handler ─────────────────────────────────────────────


class ExceptionHandlerMiddleware(IMiddleware):
    """Catch every raised exception and convert it to the
    standardised envelope.

    Behaviour:

    - ``RivexException`` subclasses (from ``rivex.exceptions``)
      are flattened via :meth:`to_response` and the dict
      returned to the inner response - ``status`` becomes a
      ``FAILURE`` envelope and the typed status code is
      carried in the HTTP status code.
    - All other exceptions (``ValueError``, ``KeyError``, ...)
      produce a generic 500 envelope with a fresh URN so the
      audit log + observability tooling can correlate by URN.
    - Plain Rivex exceptions raised by handlers (which already
      carry a status code) override anything the caller sets
      on the response.

    The middleware passes through normal returns unchanged.
    """

    def __init__(
        self,
        default_internal_status: int = 500,
        propagate_exceptions: bool = False,
    ) -> None:
        self.default_internal_status = default_internal_status
        # When True (debug mode) the wrapper re-raises after
        # rendering the envelope. Default False so production
        # never exposes the original traceback to the client.
        self.propagate_exceptions = propagate_exceptions

    @staticmethod
    def _envelope_from_exception(exc: BaseException, *, default_status: int) -> dict:
        """Best-effort conversion of an arbitrary Python
        exception into the lattice envelope. Returns a dict
        that ``ExceptionHandlerMiddleware.process`` serialises
        back into a response.
        """
        from rivex.exceptions import ExceptionUtils

        if ExceptionUtils.is_rivex_exception(exc):
            payload = exc.to_response()
            payload["transactionUrn"] = payload["transactionUrn"]  # already minted
            payload["responseKey"] = exc.code
            return {
                "status": getattr(exc, "status_code", default_status),
                "headers": [("content-type", "application/json")],
                "body": _json.dumps(payload).encode("utf-8"),
            }

        # Non-RivexException: produce a generic envelope with a
        # freshly minted URN so the audit log + observability
        # tooling can correlate by URN.
        from rivex.utilities.response import ResponseUtility

        urn = ResponseUtility.mint_urn()
        payload = {
            "transactionUrn": urn,
            "referenceUrn": "",
            "status": "FAILURE",
            "responseMessage": str(exc) or exc.__class__.__name__,
            "responseKey": "INTERNAL_ERROR",
            "errors": [],
            "timestamp": _log_audit_now(),
            "metadata": {"exception_class": exc.__class__.__name__},
            "data": None,
        }
        return {
            "status": default_status,
            "headers": [("content-type", "application/json")],
            "body": _json.dumps(payload).encode("utf-8"),
        }

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        try:
            return await call_next(request_data) if asyncio.iscoroutinefunction(
                call_next
            ) else call_next(request_data)
        except BaseException as exc:  # noqa: BLE001 — converter catches all
            resp = self._envelope_from_exception(
                exc, default_status=self.default_internal_status
            )
            if self.propagate_exceptions:
                raise
            return resp


def _log_audit_now() -> str:
    from rivex.utilities.response import ResponseUtility

    return ResponseUtility.iso8601_now()


# ── Audit logger ────────────────────────────────────────────────────


class AuditLoggerMiddleware(IMiddleware):
    """Emit one structured JSON line per request.

    Output schema matches ``rivex-middleware::audit``::

        {"ts": <unix_seconds>, "request_id": "...",
         "subject": "user-123", "method": "POST",
         "path": "/api/orders", "status": 201,
         "duration_ms": 12, "tenant_id": "acme",
         "remote": "10.0.0.1", "outcome": "allow"}
    """

    def __init__(self, subject_header: str = "X-Subject-Id") -> None:
        self.subject_header = subject_header

    @staticmethod
    def _classify(status: int) -> str:
        if 200 <= status < 300:
            return "allow"
        if status in (401, 403):
            return "deny"
        return "error"

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        started = time.perf_counter()
        headers = dict(
            (k.lower(), v) for k, v in (request_data.get("headers", []) or [])
        )
        subject = headers.get(self.subject_header.lower())
        extensions = request_data.get("extensions") or {}
        request_id = extensions.get("request_id")
        tenant_id = extensions.get("tenant_id")
        method = (request_data.get("method") or "GET").upper()
        path = request_data.get("path") or "/"
        remote = (
            request_data.get("client") or ""
        )  # populated when behind a load balancer

        response = call_next(request_data)
        if asyncio.iscoroutine(response):
            response = await response

        status = int(response.get("status", 0))
        record = {
            "ts": int(time.time()),
            "subject": subject or "anonymous",
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "remote": remote,
            "outcome": self._classify(status),
        }
        if request_id:
            record["request_id"] = request_id
        if tenant_id:
            record["tenant_id"] = tenant_id

        try:
            _logger.info("audit: %s", _json.dumps(record))
        except Exception:
            # Audit must never crash a request.
            pass
        return response


# ── Authorization ──────────────────────────────────────────────────


class AuthorizationMiddleware(IMiddleware):
    """Declarative permission gate that runs after JWT authentication.

    Policies mirror ``rivex-middleware::authorization``:

    - ``"require_roles"`` — request must carry ALL listed roles.
    - ``"require_any_role"`` — request must carry AT LEAST ONE role.
    - ``"require_scope"`` — request scope claim must contain the value.
    - ``"predicate"`` — a custom callable ``(claims) -> bool``.
    """

    def __init__(
        self,
        policy: str = "require_roles",
        roles: list[str] | None = None,
        scope: str | None = None,
        predicate: Callable[[dict], bool] | None = None,
        required: bool = True,
        message: str = "Forbidden",
    ) -> None:
        self.policy = policy
        self.roles = list(roles or [])
        self.scope = scope
        self.predicate = predicate
        self.required = required
        self.message = message

    @staticmethod
    def _claim_roles(claims: dict) -> list[str]:
        for key in ("roles", "role", "groups", "permissions"):
            val = claims.get(key)
            if isinstance(val, list):
                return [str(v) for v in val]
            if isinstance(val, str):
                return [val]
        return []

    @staticmethod
    def _claim_scopes(claims: dict) -> list[str]:
        for key in ("scope", "scp"):
            val = claims.get(key)
            if isinstance(val, list):
                return [str(v) for v in val]
            if isinstance(val, str):
                return val.split()
        return []

    def _evaluate(self, claims: dict) -> bool:
        if self.policy == "require_roles":
            roles = self._claim_roles(claims)
            return all(r in roles for r in self.roles)
        if self.policy == "require_any_role":
            roles = self._claim_roles(claims)
            return any(r in roles for r in self.roles)
        if self.policy == "require_scope":
            if not self.scope:
                return True
            return self.scope in self._claim_scopes(claims)
        if self.policy == "predicate":
            return bool(self.predicate and self.predicate(claims))
        return False

    def _forbidden(self) -> dict:
        return {
            "status": 403,
            "headers": [("content-type", "text/plain; charset=utf-8")],
            "body": self.message.encode("utf-8"),
        }

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        # Pull claims from extensions (installed by the JWT auth
        # middleware) under several conventional keys so the Python
        # tier works without a custom extension contract.
        extensions = request_data.get("extensions") or {}
        claims = extensions.get("claims") or extensions.get("jwt_claims") or {}
        if not claims and self.required:
            return self._forbidden()
        if claims and not self._evaluate(claims):
            return self._forbidden()
        return await call_next(request_data) if asyncio.iscoroutinefunction(
            call_next
        ) else call_next(request_data)


__all__ = [
    "SecurityHeadersMiddleware",
    "RequestContextMiddleware",
    "RequestTimeoutMiddleware",
    "RequestValidationMiddleware",
    "AuditLoggerMiddleware",
    "AuthorizationMiddleware",
    "ExceptionHandlerMiddleware",
    "IdempotencyMiddleware",
]
