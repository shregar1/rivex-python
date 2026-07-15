from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, NamedTuple
from urllib.parse import parse_qs

from rivex.core._compat import HAS_CORE, RC_V2, parse_cookies
from rivex.core._compat import rc as _rc
from rivex.datastructures import Headers


class ClientInfo(NamedTuple):
    host: str | None
    port: int | None


class Request:
    __slots__ = (
        "method",
        "path",
        "_headers",
        "_body",
        "query_string",
        "path_params",
        "client_host",
        "client_port",
        "state",
        "session",
        "_htmx",
    )

    def __init__(
        self,
        method: str,
        path: str,
        headers: list[tuple[str, str]],
        body: bytes,
        query_string: str = "",
        path_params: dict[str, str] | None = None,
        client_host: str | None = None,
        client_port: int | None = None,
        session: dict[str, Any] | None = None,
    ):
        self.method = method
        self.path = path
        self._headers = Headers(headers)
        self._body = body
        self.query_string = query_string
        self.path_params = path_params or {}
        self.client_host = client_host
        self.client_port = client_port
        self.state = _State()
        self.session = session if session is not None else {}
        self._htmx = None

    @classmethod
    def _from_raw(cls, data: dict) -> Request:
        return cls(
            method=data["method"],
            path=data["path"],
            headers=[(k, v) for k, v in data.get("headers", [])],
            body=data.get("body", b""),
            query_string=data.get("query_string", ""),
            path_params=dict(data.get("path_params", {})),
            client_host=data.get("client_host"),
            client_port=data.get("client_port"),
            session=data.get("session"),
        )

    @property
    def headers(self) -> Headers:
        return self._headers

    def header(self, name: str, default: str | None = None) -> str | None:
        return self._headers.get(name, default)

    @property
    def url(self) -> str:
        if self.query_string:
            return f"{self.path}?{self.query_string}"
        return self.path

    @property
    def content_type(self) -> str | None:
        return self._headers.get("content-type")

    @property
    def body(self) -> bytes:
        return self._body

    def body_json(self) -> Any:
        """Parse JSON body synchronously.

        Raises :class:`RequestBodyError` on invalid input. The
        underlying ``json.JSONDecodeError`` is chained via
        ``__cause__`` for full traceback context.
        """
        if not self._body:
            return None
        try:
            if HAS_CORE:
                return _rc.json_deserialize(self._body)
            return json.loads(self._body)
        except Exception as exc:
            # Wrap the raw JSON / Rust error in a request-aware
            # exception so the user can see the method, path, and
            # a body preview alongside the parse failure.
            from rivex.core.exceptions import RequestBodyError

            preview = self._body[:200]
            try:
                preview_str = preview.decode("utf-8", errors="replace")
            except Exception:
                preview_str = repr(preview)
            raise RequestBodyError(
                method=self.method,
                path=self.path,
                body_preview=preview_str,
                reason=f"{type(exc).__name__}: {exc}",
            ) from exc

    async def json(self) -> Any:
        """Parse JSON body (FastAPI-compatible async API)."""
        return self.body_json()

    def form(self) -> dict[str, str]:
        if RC_V2:
            result = _rc.parse_query_string(self._body.decode("utf-8"))
            return {k: (v if isinstance(v, str) else v[0]) for k, v in result.items()}
        parsed = parse_qs(self._body.decode("utf-8"), keep_blank_values=True)
        return {k: v[0] for k, v in parsed.items()}

    def text(self, errors: str = "strict") -> str:
        return self._body.decode("utf-8", errors=errors)

    @property
    def query_params(self) -> dict[str, str | list[str]]:
        if RC_V2:
            result: dict[str, str | list[str]] = _rc.parse_query_string(self.query_string)
            return result
        parsed = parse_qs(self.query_string, keep_blank_values=True)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    @property
    def cookies(self) -> dict[str, str]:
        cookie_header = self._headers.get("cookie", "")
        if not cookie_header:
            return {}
        return parse_cookies(cookie_header)

    @property
    def client(self) -> ClientInfo:
        return ClientInfo(host=self.client_host, port=self.client_port)

    @property
    def base_url(self) -> str:
        scheme = "https" if self._headers.get("x-forwarded-proto") == "https" else "http"
        host = self._headers.get("host", "localhost")
        return f"{scheme}://{host}"

    async def stream(self) -> AsyncIterator[bytes]:
        if self._body:
            yield self._body

    @property
    def htmx(self) -> Any:
        """HTMX request details (or ``None`` if ``HX-Request`` is absent).

        Usage::

            if request.htmx and request.htmx.target:
                # respond with just the partial
                return app.template("partial.html", context)
            # full page render
            return app.template("page.html", context)
        """
        if self._htmx is None:
            from rivex.web.htmx import HtmxDetails

            self._htmx = HtmxDetails(self)
        if not self._htmx.request:
            return None
        return self._htmx


class _State:
    """Arbitrary attribute storage for per-request state."""

    pass
