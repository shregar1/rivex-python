from __future__ import annotations

from collections.abc import Callable

from rivex.core._compat import get_request_header
from rivex.middleware.middleware import Middleware


class CSPMiddleware(Middleware):
    """Content Security Policy middleware.

    Sets the ``Content-Security-Policy`` header on every response.
    Supports per-route overrides via ``request.state.csp_directives``
    set in a ``before_request`` hook or earlier middleware.

    Usage::

        app.add_middleware(
            CSPMiddleware,
            default_src=["'self'"],
            script_src=["'self'", "'unsafe-inline'"],
            style_src=["'self'", "'unsafe-inline'"],
            img_src=["'self'", "data:", "https:"],
            font_src=["'self'"],
            connect_src=["'self'"],
            report_only=False,
            report_uri=None,
        )
    """

    def __init__(
        self,
        default_src: list[str] | None = None,
        script_src: list[str] | None = None,
        style_src: list[str] | None = None,
        img_src: list[str] | None = None,
        font_src: list[str] | None = None,
        connect_src: list[str] | None = None,
        media_src: list[str] | None = None,
        object_src: list[str] | None = None,
        frame_src: list[str] | None = None,
        frame_ancestors: list[str] | None = None,
        form_action: list[str] | None = None,
        base_uri: list[str] | None = None,
        manifest_src: list[str] | None = None,
        worker_src: list[str] | None = None,
        report_only: bool = False,
        report_uri: str | None = None,
        upgrade_insecure_requests: bool = False,
        block_all_mixed_content: bool = False,
    ):
        self._directives: dict[str, list[str]] = {}
        for name, values in [
            ("default-src", default_src),
            ("script-src", script_src),
            ("style-src", style_src),
            ("img-src", img_src),
            ("font-src", font_src),
            ("connect-src", connect_src),
            ("media-src", media_src),
            ("object-src", object_src),
            ("frame-src", frame_src),
            ("frame-ancestors", frame_ancestors),
            ("form-action", form_action),
            ("base-uri", base_uri),
            ("manifest-src", manifest_src),
            ("worker-src", worker_src),
        ]:
            if values is not None:
                self._directives[name] = values
        self._report_only = report_only
        self._report_uri = report_uri
        self._upgrade_insecure_requests = upgrade_insecure_requests
        self._block_all_mixed_content = block_all_mixed_content

    def _build_policy(self, overrides: dict[str, list[str]] | None = None) -> str:
        directives = dict(self._directives)
        if overrides:
            for name, values in overrides.items():
                if values is None:
                    directives.pop(name, None)
                else:
                    directives[name] = values
        if self._report_uri:
            directives["report-uri"] = [self._report_uri]
        if self._upgrade_insecure_requests:
            directives["upgrade-insecure-requests"] = []
        if self._block_all_mixed_content:
            directives["block-all-mixed-content"] = []
        parts: list[str] = []
        for name, values in directives.items():
            if not values:
                parts.append(name)
            else:
                parts.append(f"{name} {' '.join(values)}")
        return "; ".join(parts)

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        result: dict = await call_next(request_data)
        state = request_data.get("state", {})
        overrides = state.get("csp_directives") if isinstance(state, dict) else None
        policy = self._build_policy(overrides)
        header_name = "Content-Security-Policy-Report-Only" if self._report_only else "Content-Security-Policy"
        existing = result.get("headers", {})
        if isinstance(existing, dict):
            result = dict(result)
            result["headers"] = {**existing, header_name: policy}
        return result
