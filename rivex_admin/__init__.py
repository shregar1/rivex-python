"""Admin dashboard — React SPA + JSON API.

Public surface:
* :class:`AdminConfig` — declarative container for routes + hooks.
* :func:`register_admin_routes` — called by :class:`rivex.Rivex` to mount the
  admin shell + JSON API on the app.
* :func:`verify_admin_token` — constant-time token check for the auth middleware.
* :data:`ADMIN_NAMESPACE` — Python module with the partial builders and action
  handlers. Apps can extend it by registering new partials and actions.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from rivex.core.applications import Rivex

try:  # pragma: no cover
    from rivex_admin.db import default_db_path as _admin_default_db_path
except Exception:  # pragma: no cover

    def _admin_default_db_path() -> Path:  # type: ignore[no-redef]
        return Path("<admin DB unavailable — install rivex_admin>")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def verify_admin_token(provided: str | None, expected: str | None) -> bool:
    if not provided or not expected:
        return False
    if len(provided) != len(expected):
        hmac.compare_digest(provided, expected)
        return False
    return hmac.compare_digest(provided, expected)


def _extract_token(request_data: dict[str, Any]) -> str | None:
    cookie_name = "rivex_admin_token"
    for key, value in request_data.get("headers", []):
        kl = key.lower()
        if kl == "cookie" and value:
            for part in value.split(";"):
                name, _, val = part.strip().partition("=")
                if name == cookie_name and val:
                    return cast(str, val)
        elif kl == "x-admin-token" and value:
            return cast(str, value)
    query = request_data.get("query_string") or request_data.get("query") or ""
    if isinstance(query, bytes):
        query = query.decode("utf-8", errors="replace")
    for chunk in query.split("&"):
        if not chunk:
            continue
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            if k == "token" and v:
                return v
        elif chunk == "token":
            return ""
    return None


# ---------------------------------------------------------------------------
# Partial + action registry
# ---------------------------------------------------------------------------


@dataclass
class AdminContext:
    app: Any
    request_data: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.perf_counter)
    base_path: str = "/admin"


PartialHandler = Callable[[AdminContext], Awaitable[Any] | Any]
ActionHandler = Callable[[AdminContext], Awaitable[dict[str, Any]] | dict[str, Any]]


@dataclass
class _Registry:
    partials: dict[str, PartialHandler] = field(default_factory=dict)
    actions: dict[str, ActionHandler] = field(default_factory=dict)
    meta: dict[str, dict[str, str]] = field(default_factory=dict)


_REGISTRY = _Registry()


def admin_partial(
    name: str,
    *,
    title: str = "",
    description: str = "",
    icon: str = "",
) -> Callable[[PartialHandler], PartialHandler]:
    def decorator(fn: PartialHandler) -> PartialHandler:
        _REGISTRY.partials[name] = fn
        _REGISTRY.meta[name] = {
            "kind": "partial",
            "title": title or name.replace("_", " ").title(),
            "description": description,
            "icon": icon,
        }
        return fn

    return decorator


def admin_action(
    name: str,
    *,
    title: str = "",
    description: str = "",
    dangerous: bool = False,
) -> Callable[[ActionHandler], ActionHandler]:
    def decorator(fn: ActionHandler) -> ActionHandler:
        _REGISTRY.actions[name] = fn
        _REGISTRY.meta[name] = {
            "kind": "action",
            "title": title or name.replace("_", " ").title(),
            "description": description,
            "dangerous": "1" if dangerous else "0",
        }
        return fn

    return decorator


# ---------------------------------------------------------------------------
# Built-in partials
# ---------------------------------------------------------------------------


def _python_version() -> str:
    import platform

    return platform.python_version()


def _default_metrics() -> dict[str, dict[str, int]]:
    return {"counters": {}}


@admin_partial(
    "overview", title="Overview", icon="◉", description="Service identity and environment."
)
async def _partial_overview(ctx: AdminContext) -> dict[str, Any]:
    app = ctx.app
    settings = getattr(app, "_settings_snapshot", None) or {}
    env = settings.get("node_env", "unknown")
    host = settings.get("host", "0.0.0.0")
    port = settings.get("port", 8000)
    app_name = getattr(app, "app_name", "Rivex")
    version = getattr(app, "version", "0.0.0")
    started = getattr(app, "_started_at", None)
    uptime = time.time() - started if started else None

    return {
        "service": app_name,
        "version": version,
        "environment": env.upper(),
        "bind": f"{host}:{port}",
        "python": _python_version(),
        "started": started,
        "uptime": uptime,
    }


@admin_partial("runtime", title="Runtime", icon="▣", description="In-process request stats.")
async def _partial_runtime(ctx: AdminContext) -> dict[str, Any]:
    app = ctx.app
    metrics = getattr(app, "metrics", None) or _default_metrics()
    counters = metrics.get("counters", {})
    return {
        "requests_served": counters.get("requests", 0),
        "errors_5xx": counters.get("errors_5xx", 0),
        "errors_4xx": counters.get("errors_4xx", 0),
        "ws_connections": counters.get("ws_connections", 0),
        "mounted_routes": len(getattr(app, "_routes", [])),
        "middleware": len(getattr(app, "_middleware", [])),
        "controllers": len(getattr(app, "_controllers", [])),
    }


@admin_partial(
    "config", title="Config", icon="⚙", description="Active settings (secrets redacted)."
)
async def _partial_config(ctx: AdminContext) -> list[dict[str, Any]]:
    app = ctx.app
    settings = getattr(app, "_settings_snapshot", None) or {}
    redacted_keys = {
        "jwt_secret",
        "jwt_refresh_secret",
        "stripe_secret_key",
        "stripe_webhook_secret",
        "smtp_password",
        "sms_api_key",
        "persona_api_key",
        "persona_webhook_secret",
        "background_check_api_key",
        "background_check_webhook_secret",
        "azure_openai_api_key",
        "google_genai_api_key",
        "noonlight_api_key",
        "twilio_auth_token",
        "gcs_credentials_path",
    }

    rows = []
    for key in sorted(settings.keys()):
        value = settings[key]
        if key.lower() in redacted_keys:
            value = "••••••••" if value else "(unset)"
        elif isinstance(value, str) and len(value) > 80:
            value = value[:77] + "…"
        rows.append({"key": key, "value": value})

    if not rows:
        rows = [
            {
                "key": "—",
                "value": "(no settings snapshot available — call app.attach_settings(...))",
            }
        ]

    return rows


@admin_partial("setup", title="Setup", icon="+", description="Mint the first admin user.")
async def _partial_setup(ctx: AdminContext) -> dict[str, Any]:
    app = ctx.app
    store = getattr(app, "_admin_store", None)
    if store is not None:
        db_path = store.path
    else:
        db_path = getattr(app, "_admin_db", None) or _admin_default_db_path()
    return {
        "db_path": str(db_path),
        "schema": "ready",
    }


@admin_partial("logs", title="Logs", icon="≣", description="Tail of the structured log file.")
async def _partial_logs(ctx: AdminContext) -> dict[str, Any]:
    log_path = getattr(ctx.app, "_log_file", None)
    if not log_path or not os.path.isfile(log_path):
        return {"lines": [], "error": "No log file configured."}
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 65536))
            data = fh.read()
    except OSError as exc:
        return {"lines": [], "error": f"Failed to read log: {exc}"}

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()[-100:]
    return {"lines": lines, "error": None}


@admin_partial("actions", title="Actions", icon="▶", description="One-click operational actions.")
async def _partial_actions(ctx: AdminContext) -> list[dict[str, Any]]:
    cards = []
    for name, meta in _REGISTRY.meta.items():
        if meta["kind"] != "action":
            continue
        cards.append(
            {
                "name": name,
                "title": meta["title"],
                "description": meta["description"],
                "dangerous": meta.get("dangerous") == "1",
            }
        )
    return cards


# ---------------------------------------------------------------------------
# Built-in actions
# ---------------------------------------------------------------------------


@admin_action(
    "reload_config", title="Reload config", description="Re-read the .env and JSON config files."
)
async def _action_reload_config(ctx: AdminContext) -> dict[str, Any]:
    app = ctx.app
    reload_fn = getattr(app, "_reload_settings", None)
    if reload_fn is None:
        return {"ok": False, "message": "App does not expose reload_settings()."}
    try:
        result = reload_fn()
        return {"ok": True, "message": "Configuration reloaded.", "data": result}
    except Exception as exc:
        return {"ok": False, "message": f"Reload failed: {exc}"}


@admin_action(
    "ping_db", title="Ping database", description="Round-trip a SELECT 1 against the configured DB."
)
async def _action_ping_db(ctx: AdminContext) -> dict[str, Any]:
    ping_fn = getattr(ctx.app, "_ping_database", None)
    if ping_fn is None:
        return {"ok": False, "message": "App does not expose _ping_database()."}
    try:
        latency_ms = await ping_fn() if callable(ping_fn) else ping_fn
        return {"ok": True, "message": f"Database reachable ({latency_ms} ms)."}
    except Exception as exc:
        return {"ok": False, "message": f"DB ping failed: {exc}"}


@admin_action(
    "clear_caches",
    title="Clear in-memory caches",
    description="Drop any registered cache backends.",
)
async def _action_clear_caches(ctx: AdminContext) -> dict[str, Any]:
    app = ctx.app
    cleared = getattr(app, "_clear_caches", None)
    if cleared is None:
        return {"ok": True, "message": "No caches registered."}
    try:
        count = cleared()
        return {"ok": True, "message": f"Cleared {count} cache entries."}
    except Exception as exc:
        return {"ok": False, "message": f"Cache clear failed: {exc}"}


# ---------------------------------------------------------------------------
# Code-generation partial
# ---------------------------------------------------------------------------


@admin_partial(
    "generate",
    title="Generate resource",
    icon="+",
    description="Type an API spec, preview the layered code, apply to the repo.",
)
async def _partial_generate(ctx: AdminContext) -> dict[str, Any]:
    project_root = getattr(ctx.app, "project_root", None)
    if not project_root:
        return {"project_root": None}
    return {"project_root": str(project_root)}


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def _static_admin_path() -> Path:
    from pathlib import Path

    return Path(__file__).resolve().parent / "static" / "react_admin"


def register_admin_routes(
    app: Rivex,
    *,
    base_path: str = "/admin",
    token: str | None = None,
    admin_db: Path | str | None = None,
    _static_files: type | None = None,
) -> None:
    if admin_db is None:
        admin_db = getattr(app, "_admin_db", None)
    static_dir = _static_admin_path()

    # -- Set up the SQLite-backed admin store and eagerly initialize the schema
    # so that the DB file and tables exist the moment the server starts.
    # This means `pip install rivex[admin]` is truly sufficient — no manual
    # database creation or migration step required.
    store = None
    try:
        from rivex_admin.db import AdminStore

        store = AdminStore(admin_db)
        # Eagerly touch the connection to create the DB file + tables now,
        # not lazily on the first request.
        store._conn()
    except Exception:
        store = None

    has_static_token = bool(token)

    # Store the admin store on the app so it can be used by other components
    # (e.g. the `setup` partial to display the correct DB path).
    app._admin_store = store  # type: ignore[attr-defined]

    # ---------------------------------------------------------------------------
    # Auth — evaluated PER REQUEST so that newly minted tokens are honoured
    # immediately without restarting the server.
    # ---------------------------------------------------------------------------
    async def _auth(request_data: dict[str, Any]) -> bool:
        provided = _extract_token(request_data)
        # 1. DB-backed users take priority (multi-user, rotatable tokens).
        if store is not None:
            try:
                if store.has_any_users():
                    user = store.verify_token(provided or "")
                    if user is None:
                        return False
                    store.touch_used(user.username)
                    return True
            except Exception:
                pass
        # 2. Fall back to the static token (single-user back-compat).
        if has_static_token:
            return verify_admin_token(provided, token)
        # 3. No auth configured — allow all (setup mode).
        return True

    def _has_auth() -> bool:
        """Live check for whether any auth is configured at this moment."""
        if store is not None:
            try:
                if store.has_any_users():
                    return True
            except Exception:
                pass
        return has_static_token

    if _static_files is None:
        from rivex.web.staticfiles import StaticFiles as _static_files
    assert _static_files is not None

    base = base_path.rstrip("/")
    static_url = f"{base}/static"

    def _make_api_handler(name: str, registry_dict: dict) -> Any:
        handler = registry_dict[name]

        async def hndl(request_data: dict[str, Any]) -> dict[str, Any]:
            if not await _auth(request_data):
                return _unauthorized()
            ctx = AdminContext(app=app, request_data=request_data, base_path=base)
            result = handler(ctx)
            if hasattr(result, "__await__"):
                result = await result
            return _json_response(result)

        return hndl

    # Shell page
    async def shell(request_data: dict[str, Any]) -> dict[str, Any]:
        index_file = static_dir / "index.html"
        if not index_file.is_file():
            return {
                "status": 500,
                "headers": [("content-type", "text/html")],
                "body": b"<h1>500 - Admin React build not found</h1><p>Run <code>npm run build</code> in rivex_admin_react.</p>",
            }
        return {
            "status": 200,
            "headers": [("content-type", "text/html; charset=utf-8")],
            "body": index_file.read_bytes(),
        }

    # Meta endpoint for React to discover partials/actions.
    # has_auth is evaluated live so the React app immediately knows when
    # a user has been minted without requiring a server restart.
    async def meta_handler(request_data: dict[str, Any]) -> dict[str, Any]:
        return _json_response(
            {
                "partials": [
                    {
                        "name": n,
                        "title": m["title"],
                        "icon": m["icon"],
                        "description": m["description"],
                    }
                    for n, m in _REGISTRY.meta.items()
                    if m["kind"] == "partial"
                ],
                "actions": [
                    {
                        "name": n,
                        "title": m["title"],
                        "icon": m["icon"],
                        "description": m["description"],
                        "dangerous": m.get("dangerous") == "1",
                    }
                    for n, m in _REGISTRY.meta.items()
                    if m["kind"] == "action"
                ],
                "app_name": getattr(app, "app_name", "Rivex"),
                "powered_by": getattr(app, "powered_by", "Rivex Core"),
                "version": getattr(app, "version", "0.0.0"),
                "has_auth": _has_auth(),
            }
        )

    app._server.add_route("GET", base + "/", shell)
    app._server.add_route("GET", base, shell)
    app._server.add_route("GET", f"{base}/api/meta", meta_handler)

    for name in _REGISTRY.partials:
        app._server.add_route(
            "GET", f"{base}/api/partials/{name}", _make_api_handler(name, _REGISTRY.partials)
        )

    for name in _REGISTRY.actions:
        app._server.add_route(
            "POST", f"{base}/api/actions/{name}", _make_api_handler(name, _REGISTRY.actions)
        )

    app.mount(static_url, _static_files(directory=static_dir, check_dir=False))

    app._admin_mounted = True  # type: ignore[attr-defined]
    app._admin_token_hash = (  # type: ignore[attr-defined]
        hashlib.sha256(token.encode("utf-8")).hexdigest() if token else ""
    )
    app._admin_partials = list(_REGISTRY.partials)  # type: ignore[attr-defined]
    app._admin_actions = list(_REGISTRY.actions)  # type: ignore[attr-defined]

    # Code-generation routes
    try:
        from rivex_codegen import (  # type: ignore[import-not-found]
            apply_plan,
            generate_resource,
            parse_api_form,
            plan_to_summary,
        )

        _codegen = SimpleNamespace(
            apply_plan=apply_plan,
            generate_resource=generate_resource,
            parse_api_form=parse_api_form,
            plan_to_summary=plan_to_summary,
        )

        async def _parse_json_body(request_data: dict[str, Any]) -> dict[str, Any]:
            body = request_data.get("body") or request_data.get("body_bytes") or b"{}"
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")
            try:
                return cast(dict[str, Any], json.loads(body))
            except Exception:
                return {}

        def _project_root() -> Any:
            from pathlib import Path

            root = getattr(app, "project_root", None)
            return Path(root).resolve() if root else None

        async def _codegen_preview(request_data: dict[str, Any]) -> dict[str, Any]:
            if not await _auth(request_data):
                return _unauthorized()
            try:
                fields = await _parse_json_body(request_data)
                spec = _codegen.parse_api_form(
                    resource=fields.get("resource", ""),
                    description=fields.get("description", ""),
                    fields_text=fields.get("fields", ""),
                )
                root = _project_root()
                if root is None:
                    return _json_response(
                        {
                            "ok": False,
                            "error": "project_root not set. Configure app.project_root in main.py.",
                        }
                    )
                plan = _codegen.generate_resource(spec, project_root=root)
                _get_plan_store().put(plan)
                return _json_response(
                    {
                        "ok": True,
                        "plan_id": plan.plan_id,
                        "summary": _codegen.plan_to_summary(plan),
                        "creates": plan.creates,
                        "modifies": plan.modifies,
                        "preview": plan.preview_text
                        if hasattr(plan, "preview_text")
                        else str(plan),  # Simplify preview for React
                    }
                )
            except Exception as exc:
                return _json_response({"ok": False, "error": f"Parse error: {exc}"})

        async def _codegen_apply(request_data: dict[str, Any]) -> dict[str, Any]:
            plan_id = (request_data.get("path_params") or {}).get("plan_id", "")
            if not await _auth(request_data):
                return _unauthorized()
            plan = _get_plan_store().get(plan_id)
            if plan is None:
                return _json_response(
                    {"ok": False, "error": f"Plan {plan_id} not found or expired."}
                )
            root = _project_root()
            if root is None:
                return _json_response({"ok": False, "error": "project_root not set."})
            try:
                written = _codegen.apply_plan(plan, project_root=root)
                _get_plan_store().drop(plan_id)
                return _json_response({"ok": True, "written": written})
            except Exception as exc:
                return _json_response({"ok": False, "error": str(exc)})

        async def _codegen_cancel(request_data: dict[str, Any]) -> dict[str, Any]:
            plan_id = (request_data.get("path_params") or {}).get("plan_id", "")
            if not await _auth(request_data):
                return _unauthorized()
            plan = _get_plan_store().drop(plan_id)
            if plan is None:
                return _json_response({"ok": False, "error": f"Plan {plan_id} not found."})
            return _json_response({"ok": True, "message": f"Plan {plan_id} discarded."})

        app._server.add_route("POST", f"{base}/api/codegen/preview", _codegen_preview)
        app._server.add_route("POST", f"{base}/api/codegen/apply/{{plan_id}}", _codegen_apply)
        app._server.add_route("POST", f"{base}/api/codegen/cancel/{{plan_id}}", _codegen_cancel)
    except ImportError:
        pass


def _get_plan_store() -> Any:
    from rivex_codegen import get_plan_store

    return get_plan_store()


def _unauthorized() -> dict[str, Any]:
    return {
        "status": 401,
        "headers": [("content-type", "application/json; charset=utf-8")],
        "body": json.dumps({"error": "admin token required"}).encode("utf-8"),
    }


def _json_response(data: Any) -> dict[str, Any]:
    return {
        "status": 200,
        "headers": [
            ("content-type", "application/json; charset=utf-8"),
            ("cache-control", "no-store"),
        ],
        "body": json.dumps(data, default=str).encode("utf-8"),
    }


__all__ = [
    "ADMIN_NAMESPACE",
    "ActionHandler",
    "AdminContext",
    "PartialHandler",
    "admin_action",
    "admin_partial",
    "register_admin_routes",
    "verify_admin_token",
]

ADMIN_NAMESPACE = __name__
