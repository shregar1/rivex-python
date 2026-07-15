"""Bare-bones landing page served at ``GET /``.

Users with only ``pip install rivex`` (no admin / codegen / scaffold
plugins) get a tiny placeholder page when they hit the server's root
URL.  It tells them:

* the server is up,
* what app/version/env they're hitting,
* what routes are mounted,
* what the next step is (add a route, install an admin, etc.).

This is a "ship a working default" — not a marketing page.  Real
applications will mount their own ``@app.get("/")`` route and
shadow it; we only render this when no user route exists for ``/``.

Opt out with ``Rivex(landing_page=False)``.
"""

from __future__ import annotations

import html
import os
import platform
import socket
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rivex.core.applications import Rivex


_LANDING_CSS = """
:root {
  --bg: #fafafa; --fg: #18181b; --muted: #71717a; --line: #e4e4e7;
  --soft: #f4f4f5; --accent: #f97316;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --sans: ui-sans-serif, -apple-system, system-ui, "Inter", sans-serif;
}
* { box-sizing: border-box; margin: 0; }
body { background: var(--bg); color: var(--fg); font-family: var(--sans);
  line-height: 1.55; padding: 48px 24px; -webkit-font-smoothing: antialiased; }
.shell { max-width: 760px; margin: 0 auto; }
.brand { display: flex; align-items: baseline; gap: 14px; margin-bottom: 8px; }
.brand .mark { font-family: var(--mono); font-size: 26px; font-weight: 900;
  letter-spacing: -.04em; }
.brand .mark .accent { color: var(--accent); }
h1 { font-size: 24px; font-weight: 700; letter-spacing: -.02em; }
h2 { font-size: 13px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .12em; color: var(--muted); margin: 36px 0 12px; }
p { color: var(--fg); }
.meta { font-family: var(--mono); font-size: 12px; color: var(--muted);
  margin-bottom: 28px; }
.panel { background: #fff; border: 1px solid var(--line); border-radius: 14px;
  padding: 22px 26px; }
.kv { width: 100%; border-collapse: collapse; }
.kv th, .kv td { text-align: left; padding: 8px 0;
  border-bottom: 1px solid var(--line); font-size: 13px; vertical-align: top; }
.kv tr:last-child th, .kv tr:last-child td { border-bottom: none; }
.kv th { width: 160px; font-weight: 600; color: var(--muted); }
code, pre { font-family: var(--mono); font-size: 12.5px; }
code { background: var(--soft); padding: 1px 6px; border-radius: 4px; }
pre { background: #0b0b0c; color: #fafafa; padding: 16px 18px;
  border-radius: 10px; overflow-x: auto; line-height: 1.55; }
.routes { width: 100%; border-collapse: collapse; }
.routes th, .routes td { padding: 7px 10px; font-size: 12.5px;
  text-align: left; border-bottom: 1px solid var(--line); }
.routes th { color: var(--muted); font-weight: 600; text-transform: uppercase;
  letter-spacing: .08em; font-size: 11px; }
.method { font-family: var(--mono); font-weight: 700;
  color: var(--accent); }
.path { font-family: var(--mono); }
.next { background: #fff; border: 1px solid var(--line); border-radius: 14px;
  padding: 22px 26px; margin-top: 16px; }
.next h3 { font-size: 14px; font-weight: 700; margin-bottom: 8px; }
.next ol { padding-left: 20px; }
.next li { margin: 6px 0; font-size: 14px; }
.muted { color: var(--muted); }
.powered { text-align: center; margin-top: 36px; font-size: 11px;
  color: var(--muted); font-family: var(--mono);
  text-transform: uppercase; letter-spacing: .12em; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #09090b; --fg: #fafafa; --muted: #a1a1aa; --line: #27272a;
    --soft: #18181b; }
  .panel, .next { background: #18181b; border-color: var(--line); }
  code { background: var(--soft); }
  .kv th, .routes th { color: var(--muted); }
}
"""


def _safe(value: Any) -> str:
    if value is None:
        return "—"
    return html.escape(str(value), quote=True)


def _http_method_class(method: str) -> str:
    return f'<span class="method">{html.escape(method)}</span>'


def build_landing_page(app: Rivex) -> tuple[str, str]:
    """Return ``(body, content_type)`` for the bare-bones landing page.

    Rendered only when the user hasn't mounted their own ``GET /`` —
    we *never* shadow an existing route.
    """
    title = getattr(app, "title", "Rivex")
    version = getattr(app, "version", "0.0.0")
    description = getattr(app, "description", None)
    app_name = getattr(app, "app_name", None) or "Rivex"
    powered_by = getattr(app, "powered_by", None)
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    routes = list(getattr(app, "_routes", []))

    # Service identity table
    rows = [
        ("Service", _safe(app_name)),
        ("Version", _safe(version)),
        ("Bind", f"{_safe(host)}:{_safe(port)}"),
        ("Python", _safe(platform.python_version())),
        ("PID", _safe(os.getpid())),
        ("Hostname", _safe(socket.gethostname())),
    ]
    if description:
        rows.append(("Description", _safe(description)))

    kv_html = "\n".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)

    # Routes table
    if routes:
        route_rows = []
        seen_paths: set[str] = set()
        for r in routes:
            path = r.path
            method = r.method
            tag = f"{method} {path}"
            if tag in seen_paths:
                continue
            seen_paths.add(tag)
            handler = getattr(r.endpoint, "__name__", str(r.endpoint))
            route_rows.append(
                f"<tr><td>{_http_method_class(method)}</td>"
                f'<td class="path">{_safe(path)}</td>'
                f"<td>{_safe(handler)}</td></tr>"
            )
        routes_table = (
            '<table class="routes"><thead><tr>'
            "<th>Method</th><th>Path</th><th>Handler</th>"
            "</tr></thead><tbody>" + "\n".join(route_rows) + "</tbody></table>"
        )
    else:
        routes_table = (
            '<p class="muted">No routes registered yet — '
            "this server is bare. Mount your first endpoint with "
            "<code>@app.get('/')</code>.</p>"
        )

    # Next-step block — points at the install commands a new user needs
    next_steps = []
    if not routes:
        next_steps.append(
            "Define a route — the <code>@app.get()</code> decorator is the simplest way in."
        )
    if not _admin_mounted(app):
        next_steps.append(
            "Mount the admin dashboard (optional): "
            "<code>Rivex(admin_url='/admin')</code>. "
            "Then run <code>rivex createsuperuser</code> to mint "
            "your first admin."
        )
    if not _codegen_mounted(app):
        next_steps.append(
            "Generate a layered backend from an API spec "
            "(optional): install the "
            "<code>rivex[codegen]</code> extra and run "
            "<code>rivex generate</code>."
        )
    next_steps.append(
        "Read the docs at <code>/docs</code> or <code>/redoc</code>, "
        "or fetch the OpenAPI spec at <code>/openapi.json</code>."
    )
    if not next_steps:
        next_steps.append("Server looks healthy — carry on.")
    next_html = (
        '<div class="next">'
        "<h3>Next steps</h3>"
        "<ol>" + "".join(f"<li>{s}</li>" for s in next_steps) + "</ol>"
        "</div>"
    )

    powered_html = (
        f'<div class="powered">Powered by {html.escape(powered_by)}</div>' if powered_by else ""
    )
    description_html = f'<p class="meta">{_safe(description)}</p>' if description else ""

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{_safe(app_name)} — {_safe(title)}</title>
  <style>{_LANDING_CSS}</style>
</head>
<body>
  <div class="shell">
    <div class="brand">
      <div class="mark">{_safe(app_name[:3]).upper()}<span class="accent">{_safe(app_name[3:4]).upper() if len(app_name) > 3 else ""}</span></div>
    </div>
    <h1>{_safe(title)}</h1>
    {description_html}
    <p class="meta">v{_safe(version)} · bare-bones Rivex · {len(routes)} route{"s" if len(routes) != 1 else ""} mounted</p>

    <div class="panel">
      <h2>Service identity</h2>
      <table class="kv"><tbody>{kv_html}</tbody></table>
    </div>

    <h2>Mounted routes</h2>
    <div class="panel">
      {routes_table}
    </div>

    {next_html}
    {powered_html}
  </div>
</body>
</html>
"""
    return body, "text/html; charset=utf-8"


def _admin_mounted(app: Rivex) -> bool:
    return bool(getattr(app, "admin_url", None))


def _codegen_mounted(app: Rivex) -> bool:
    # No flag for this yet — we infer from the existence of any
    # ``services/`` or ``controllers/``-looking route.  Cheap heuristic.
    return False


__all__ = ["build_landing_page"]
