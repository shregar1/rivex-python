from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

_DISABLED = object()


class DebugToolbarMiddleware:
    """Injects a collapsible debug toolbar panel into HTML responses.

    Shows:
    - Request info (method, path, status, duration)
    - SQL queries (when a probe is installed via ``set_pool_probe``)
    - Cache hits/misses
    - Template rendering time
    - Registered signals
    - Session data

    Toggle via ``?debug`` query parameter or ``rivex_debug`` cookie.
    """

    def __init__(self, app: Any = None):
        self._app = app
        self._queries: list[dict] = []
        self._cache_stats: dict = {"hits": 0, "misses": 0}
        self._template_time: float = 0.0
        self._start_time: float = 0.0

    def _should_show(self, request_data: dict) -> bool:
        """Decide whether the debug toolbar should be injected for this request.

        The toolbar is shown when either the request's query string
        contains ``debug`` (e.g. ``?debug``) or the ``rivex_debug=1``
        cookie is set.

        Args:
            request_data: The in-flight request envelope. ``query_string``
                and ``cookies`` are read.

        Returns:
            ``True`` when the toolbar should be injected, ``False``
            otherwise.
        """
        query = request_data.get("query_string", "")
        if query and "debug" in query:
            return True
        cookies = request_data.get("cookies", "")
        if isinstance(cookies, str) and "rivex_debug=1" in cookies:
            return True
        return False

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Time the request and inject a debug panel into HTML responses.

        Resets per-request stats, decides whether to instrument the
        request via :meth:`_should_show`, installs a SQL probe on the
        database pool when one is reachable from request state, and
        otherwise passes through unchanged. For HTML responses with a
        ``</body>`` terminator, the rendered panel is inserted just
        before it and ``Content-Length`` is updated.

        Args:
            request_data: The in-flight request envelope as carried by
                the middleware chain.
            call_next: Awaitable returning the downstream response
                dict.

        Returns:
            The downstream response dict, with the toolbar HTML
            inserted when the toolbar is enabled and the response is
            HTML. Otherwise the response is returned untouched.
        """
        self._start_time = time.time()
        self._queries = []
        self._cache_stats = {"hits": 0, "misses": 0}
        self._template_time = 0.0

        show = self._should_show(request_data)
        if not show:
            return await call_next(request_data)

        # Install probe on pool if available
        state = request_data.get("state", {})
        if isinstance(state, dict):
            db = state.get("db")
            if db and hasattr(db, "_set_probe"):
                db._set_probe(self._record_query)

        result: dict = await call_next(request_data)

        duration = (time.time() - self._start_time) * 1000

        body = result.get("body", "")
        headers = result.get("headers", {})
        content_type = ""
        if isinstance(headers, dict):
            content_type = headers.get("content-type", headers.get("Content-Type", ""))

        if "text/html" not in content_type or not body:
            return result

        panel = self._render_panel(result, duration)
        if isinstance(body, str) and "</body>" in body:
            body = body.replace("</body>", panel + "</body>")
        elif isinstance(body, bytes) and b"</body>" in body:
            body = body.replace(b"</body>", panel.encode() + b"</body>")

        result["body"] = body
        if isinstance(headers, dict):
            headers["Content-Length"] = str(len(body) if isinstance(body, bytes) else len(body.encode()))
        return result

    def _record_query(self, sql: str, duration: float) -> None:
        """Capture one SQL statement for the toolbar's SQL panel.

        The statement is truncated to 200 characters and the duration
        is formatted with a millisecond suffix for display.

        Args:
            sql: The SQL statement that was executed.
            duration: How long the statement took, in seconds.
        """
        self._queries.append({"sql": sql[:200], "duration": f"{duration:.2f}ms"})

    def _render_panel(self, result: dict, duration: float) -> str:
        """Build the HTML snippet for the debug toolbar panel.

        Combines the recorded SQL queries, cache hit/miss counts, and
        request meta (method, path, status, duration) into a single
        fixed-position ``<div>`` that callers inject just before the
        page's closing ``</body>`` tag.

        Args:
            result: The downstream response dict; ``status``, ``method``
                and ``path`` are read for the panel header.
            duration: Total request duration in milliseconds.

        Returns:
            The HTML snippet for the toolbar panel.
        """
        status = result.get("status", 200)
        method = result.get("method", "GET")
        path = result.get("path", "/")

        queries_html = ""
        if self._queries:
            for q in self._queries:
                queries_html += (
                    f'<tr><td style="font-size:11px;font-family:monospace;'
                    f'border-bottom:1px solid #eee;padding:2px 4px;">'
                    f'{q["sql"]}</td>'
                    f'<td style="font-size:11px;border-bottom:1px solid #eee;'
                    f'padding:2px 4px;color:#666;">{q["duration"]}</td></tr>'
                )
            queries_html = (
                f'<table style="width:100%;border-collapse:collapse;">{queries_html}</table>'
            )
        else:
            queries_html = '<p style="font-size:11px;color:#999;padding:4px;">No queries recorded.</p>'

        cache_html = (
            f'Hits: {self._cache_stats["hits"]} | '
            f'Misses: {self._cache_stats["misses"]}'
        )

        panel = f"""
<div id="rivex-debug-toolbar" style="position:fixed;bottom:0;left:0;right:0;
z-index:99999;background:#1a1a2e;color:#e0e0e0;font-family:-apple-system,
BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:12px;
border-top:3px solid #e94560;box-shadow:0 -2px 10px rgba(0,0,0,0.3);
max-height:40vh;overflow-y:auto;transition:max-height 0.3s ease;">
<div style="display:flex;align-items:center;padding:6px 12px;
background:#16213e;cursor:pointer;" onclick="(function(e){{
var p=e.target.closest('#rivex-debug-toolbar');
p.style.maxHeight=p.style.maxHeight==='40vh'?'40px':'40vh';
}})(event)">
<span style="font-weight:bold;color:#e94560;margin-right:8px;">Rivex Debug</span>
<span style="color:#aaa;margin-right:12px;">{method} {path}</span>
<span style="color:#aaa;margin-right:12px;">Status: {status}</span>
<span style="color:#aaa;margin-right:12px;">{duration:.1f}ms</span>
<span style="color:#aaa;margin-right:12px;">SQL: {len(self._queries)}</span>
<span style="color:#aaa;font-size:10px;">&#x25BC; toggle</span>
</div>
<div style="padding:8px 12px;">
<div style="display:flex;gap:16px;flex-wrap:wrap;">
<div style="flex:1;min-width:200px;">
<h4 style="margin:0 0 4px;color:#e94560;font-size:12px;">SQL Queries</h4>
{queries_html}
</div>
<div style="flex:1;min-width:150px;">
<h4 style="margin:0 0 4px;color:#e94560;font-size:12px;">Cache</h4>
<p style="font-size:11px;padding:4px;">{cache_html}</p>
</div>
</div>
</div>
</div>
"""
        return panel
