from __future__ import annotations

import inspect
from typing import Any, get_type_hints

from rivex.core._compat import HAS_CORE
from rivex.core._compat import rc as _rc


def generate_openapi(
    *,
    title: str,
    version: str,
    description: str | None = None,
    routes: list,
    openapi_tags: list[dict[str, Any]] | None = None,
    servers: list[dict[str, Any]] | None = None,
    terms_of_service: str | None = None,
    contact: dict[str, Any] | None = None,
    license_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": title, "version": version},
    }
    if description:
        spec["info"]["description"] = description
    if terms_of_service:
        spec["info"]["termsOfService"] = terms_of_service
    if contact:
        spec["info"]["contact"] = contact
    if license_info:
        spec["info"]["license"] = license_info
    if servers:
        spec["servers"] = servers

    paths: dict[str, dict] = {}
    all_tags: set[str] = set()
    components_schemas: dict[str, Any] = {}
    security_schemes: dict[str, Any] = {}

    for route in routes:
        if not route.include_in_schema:
            continue

        path_key = route.path
        method_key = route.method.lower()

        if path_key not in paths:
            paths[path_key] = {}

        operation = _build_operation(route, components_schemas, security_schemes)
        paths[path_key][method_key] = operation

        for tag in route.tags:
            all_tags.add(tag)

    if paths:
        spec["paths"] = paths

    if openapi_tags:
        spec["tags"] = openapi_tags
    elif all_tags:
        spec["tags"] = [{"name": t} for t in sorted(all_tags)]

    components: dict[str, Any] = {}
    if components_schemas:
        components["schemas"] = components_schemas
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        spec["components"] = components

    return spec


def _build_operation(
    route: Any,
    components_schemas: dict,
    security_schemes: dict[str, Any],
) -> dict[str, Any]:
    from rivex.core.dependencies import Depends

    op: dict[str, Any] = {}

    if route.summary:
        op["summary"] = route.summary
    elif route.endpoint.__doc__:
        op["summary"] = route.endpoint.__doc__.strip().split("\n")[0]

    if route.description:
        op["description"] = route.description

    if route.operation_id:
        op["operationId"] = route.operation_id
    else:
        path_slug = route.path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
        method_prefix = route.method.lower()
        if path_slug:
            op["operationId"] = f"{route.endpoint.__name__}_{path_slug}_{method_prefix}"
        else:
            op["operationId"] = f"{route.endpoint.__name__}_{method_prefix}"

    if route.tags:
        op["tags"] = list(route.tags)

    if route.deprecated:
        op["deprecated"] = True

    sig = inspect.signature(route.endpoint)
    try:
        hints = get_type_hints(route.endpoint)
    except Exception:
        hints = {}

    path_param_names = _extract_path_params(route.path)

    parameters: list[dict] = []
    request_body = None
    security_requirements: list[dict[str, list[str]]] = []

    from rivex.core.params import Body as BodyParam
    from rivex.core.params import Cookie as CookieParam
    from rivex.core.params import Header as HeaderParam
    from rivex.core.params import Path as PathParam
    from rivex.core.params import Query as QueryParam
    from rivex.core.params import _ParamBase

    for name, param in sig.parameters.items():
        hint = hints.get(name, str)

        if isinstance(param.default, Depends):
            _collect_security_requirement(
                param.default.dependency,
                security_schemes,
                security_requirements,
            )
            continue

        if _is_request_type(hint):
            continue

        if _is_internal_type(hint, param.default):
            continue

        if isinstance(param.default, _ParamBase):
            pm = param.default
            if isinstance(pm, PathParam):
                schema = {**_type_to_schema(hint), **pm.openapi_schema_extra()}
                p: dict[str, Any] = {
                    "name": pm.alias or name,
                    "in": "path",
                    "required": True,
                    "schema": schema,
                }
                if pm.description:
                    p["description"] = pm.description
                if pm.deprecated:
                    p["deprecated"] = True
                if pm.examples:
                    p["examples"] = pm.examples
                parameters.append(p)
            elif isinstance(pm, QueryParam):
                schema = {**_type_to_schema(hint), **pm.openapi_schema_extra()}
                if not pm.required and pm.default is not None:
                    schema["default"] = pm.default
                p = {
                    "name": pm.alias or name,
                    "in": "query",
                    "required": pm.required,
                    "schema": schema,
                }
                if pm.description:
                    p["description"] = pm.description
                if pm.deprecated:
                    p["deprecated"] = True
                if pm.examples:
                    p["examples"] = pm.examples
                parameters.append(p)
            elif isinstance(pm, HeaderParam):
                schema = {**_type_to_schema(hint), **pm.openapi_schema_extra()}
                if not pm.required and pm.default is not None:
                    schema["default"] = pm.default
                p = {
                    "name": pm.header_name(name),
                    "in": "header",
                    "required": pm.required,
                    "schema": schema,
                }
                if pm.description:
                    p["description"] = pm.description
                if pm.deprecated:
                    p["deprecated"] = True
                parameters.append(p)
            elif isinstance(pm, CookieParam):
                schema = {**_type_to_schema(hint), **pm.openapi_schema_extra()}
                if not pm.required and pm.default is not None:
                    schema["default"] = pm.default
                p = {
                    "name": pm.alias or name,
                    "in": "cookie",
                    "required": pm.required,
                    "schema": schema,
                }
                if pm.description:
                    p["description"] = pm.description
                parameters.append(p)
            elif isinstance(pm, BodyParam):
                schema = _type_to_schema(hint)
                schema.update(pm.openapi_schema_extra())
                request_body = {
                    "required": pm.required,
                    "content": {"application/json": {"schema": schema}},
                }
            continue

        if name in path_param_names:
            parameters.append(
                {
                    "name": name,
                    "in": "path",
                    "required": True,
                    "schema": _type_to_schema(hint),
                }
            )
        elif _is_body_model(hint):
            schema = _model_to_ref(hint, components_schemas)
            request_body = {
                "required": param.default is inspect.Parameter.empty,
                "content": {"application/json": {"schema": schema}},
            }
        elif _is_file_type(hint, param.default):
            if not request_body:
                request_body = {"required": True, "content": {}}
            request_body["content"].setdefault(  # type: ignore[index]
                "multipart/form-data",
                {"schema": {"type": "object", "properties": {}}},
            )
            props = request_body["content"]["multipart/form-data"]["schema"]["properties"]  # type: ignore[index]
            props[name] = {"type": "string", "format": "binary"}
        elif _is_form_type(param.default):
            if not request_body:
                request_body = {"required": True, "content": {}}
            request_body["content"].setdefault(  # type: ignore[index]
                "multipart/form-data",
                {"schema": {"type": "object", "properties": {}}},
            )
            props = request_body["content"]["multipart/form-data"]["schema"]["properties"]  # type: ignore[index]
            props[name] = _type_to_schema(hint)
        else:
            qp: dict[str, Any] = {
                "name": name,
                "in": "query",
                "required": param.default is inspect.Parameter.empty,
                "schema": _type_to_schema(hint),
            }
            if param.default is not inspect.Parameter.empty and param.default is not None:
                qp["schema"] = {**qp["schema"], "default": param.default}
            parameters.append(qp)

    if parameters:
        op["parameters"] = parameters

    if request_body:
        op["requestBody"] = request_body

    status_key = str(route.status_code)
    resp: dict[str, Any] = {"description": "Successful response"}

    if route.response_model:
        schema = _model_to_ref(route.response_model, components_schemas)
        resp["content"] = {"application/json": {"schema": schema}}

    op["responses"] = {status_key: resp}

    if route.responses:
        for status, resp_info in route.responses.items():
            extra_resp: dict[str, Any] = {"description": resp_info.get("description", "Response")}
            model = resp_info.get("model")
            if model:
                schema = _model_to_ref(model, components_schemas)
                extra_resp["content"] = {"application/json": {"schema": schema}}
            op["responses"][str(status)] = extra_resp

    if security_requirements:
        op["security"] = security_requirements
    if route.openapi_extra:
        op.update(route.openapi_extra)

    return op


def _collect_security_requirement(
    dependency: Any,
    security_schemes: dict[str, Any],
    requirements: list[dict[str, list[str]]],
) -> None:
    scheme = getattr(dependency, "openapi_scheme", None)
    if not scheme:
        return
    name = getattr(dependency, "scheme_name", dependency.__class__.__name__)
    security_schemes[name] = scheme
    requirements.append({name: []})


def _extract_path_params(path: str) -> set[str]:
    params: set[str] = set()
    for segment in path.split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            params.add(segment[1:-1])
    return params


def _type_to_schema(hint: Any) -> dict[str, Any]:
    if hint is int:
        return {"type": "integer"}
    if hint is float:
        return {"type": "number"}
    if hint is str:
        return {"type": "string"}
    if hint is bool:
        return {"type": "boolean"}
    if hint is list:
        return {"type": "array"}
    return {"type": "string"}


def _model_to_ref(model: Any, components: dict) -> dict[str, Any]:
    from typing import get_args, get_origin

    origin = get_origin(model)
    if origin in (list, set, frozenset, tuple):
        args = get_args(model)
        items = _model_to_ref(args[0], components) if args else {}
        return {"type": "array", "items": items}

    if hasattr(model, "model_json_schema"):
        name = model.__name__
        if name not in components:
            schema = model.model_json_schema()
            if "$defs" in schema:
                for def_name, def_schema in schema.pop("$defs").items():
                    components[def_name] = def_schema
            components[name] = schema
        return {"$ref": f"#/components/schemas/{name}"}
    return {"type": "object"}


def _is_request_type(hint: Any) -> bool:
    try:
        from rivex.core.requests import Request

        return hint is Request or (isinstance(hint, type) and issubclass(hint, Request))
    except (TypeError, ImportError):
        return False


def _is_body_model(hint: Any) -> bool:
    if hasattr(hint, "model_validate_json"):
        return True
    try:
        from pydantic import BaseModel

        return isinstance(hint, type) and issubclass(hint, BaseModel)
    except (TypeError, ImportError):
        return False


def _is_internal_type(hint: Any, default: Any) -> bool:
    try:
        from rivex.lifecycle.background import BackgroundTasks

        if hint is BackgroundTasks or (
            isinstance(hint, type) and issubclass(hint, BackgroundTasks)
        ):
            return True
    except (TypeError, ImportError):
        pass
    return False


def _is_file_type(hint: Any, default: Any) -> bool:
    try:
        from rivex.web.uploads import File, UploadFile

        if isinstance(default, File):
            return True
        if hint is UploadFile or (isinstance(hint, type) and issubclass(hint, UploadFile)):
            return True
    except (TypeError, ImportError):
        pass
    return False


def _is_form_type(default: Any) -> bool:
    try:
        from rivex.web.uploads import Form

        return isinstance(default, Form)
    except (TypeError, ImportError):
        return False


def build_docs_html(
    title: str,
    openapi_url: str,
    logo_url: str | None = None,
    description: str | None = None,
    favicon_url: str | None = None,
    app_name: str | None = None,
    powered_by: str | None = None,
) -> str:
    try:
        from rivex_react import render_react_docs

        return render_react_docs(
            openapi_url,
            title=title,
            description=description,
            favicon_url=favicon_url,
            logo_url=logo_url,
        )
    except ImportError:
        pass

    if HAS_CORE:
        result: str = _rc.render_docs_html(
            title,
            openapi_url,
            logo_url=logo_url,
            description=description,
            favicon_url=favicon_url,
        )
        return result
    return _fallback_docs_html(title, openapi_url, app_name=app_name, powered_by=powered_by)


def build_redoc_html(
    title: str,
    openapi_url: str,
    favicon_url: str | None = None,
    app_name: str | None = None,
    powered_by: str | None = None,
) -> str:
    if HAS_CORE:
        result: str = _rc.render_redoc_html(
            title,
            openapi_url,
            favicon_url=favicon_url,
        )
        return result
    return _fallback_redoc_html(title, openapi_url)


def build_health_html(
    title: str,
    version: str,
    docs_url: str | None = None,
    favicon_url: str | None = None,
    app_name: str | None = None,
    powered_by: str | None = None,
) -> str:
    if HAS_CORE:
        result: str = _rc.render_health_html(
            title,
            version,
            docs_url=docs_url,
            favicon_url=favicon_url,
        )
        return result
    return _fallback_health_html(
        title,
        version,
        docs_url,
        app_name=app_name,
        powered_by=powered_by,
    )


def build_admin_html(
    *,
    title: str,
    base_path: str,
    static_url: str,
    app_name: str,
    powered_by: str,
    version: str,
    partials: list[dict[str, str]],
) -> str:
    """Render the admin dashboard shell (HTMX + Alpine.js, server-rendered)."""
    return _fallback_admin_html(
        title=title,
        base_path=base_path,
        static_url=static_url,
        app_name=app_name,
        powered_by=powered_by,
        version=version,
        partials=partials,
    )


def _brand_mark(app_name: str, *, accent: bool = True) -> str:
    """Render the big brand mark used on the landing page.

    With ``accent=True`` (the default) the last character of
    ``app_name`` is wrapped in a ``.accent`` span so it picks up the
    orange brand colour, e.g. ``"Rivex"`` →
    ``"RIV<span class=\\\"accent\\\">E</span>X"``. With
    ``accent=False`` the whole wordmark renders in the foreground
    text colour (no orange) so it stays black-on-white (or
    white-on-black in dark mode). The supplied name is HTML-escaped
    before rendering.
    """
    from html import escape

    if not app_name:
        app_name = "Rivex"
    text = escape(app_name.upper())
    if not accent or len(text) <= 1:
        return text
    return f'{text[:-1]}<span class="accent">{text[-1]}</span>'


def build_server_html(
    *,
    title: str,
    version: str,
    docs_url: str | None = None,
    admin_url: str | None = None,
    app_name: str | None = None,
    powered_by: str | None = None,
) -> str:
    """Render the operational status page used for the base route.

    This is the server page that was on ``/health`` in the original
    Rivex shell — a big RIVEX wordmark, pulsing green dot, ``curl``
    hint, info drawer with service identity, and a dark/light theme
    toggle.  When an admin URL is configured the page also shows a
    small token-input form that POSTs to ``<admin_url>?token=...``
    so users can sign in from a browser (which can't set custom
    request headers from a URL).
    """
    from html import escape

    t, v = escape(title), escape(version)
    brand = _brand_mark(app_name or "Rivex", accent=False)
    docs_row = (
        f'<div class="info-row"><span class="label">Docs</span>'
        f'<a href="{escape(docs_url)}" class="value link">{escape(docs_url)}</a></div>'
        if docs_url
        else ""
    )
    admin_row = (
        f'<div class="info-row"><span class="label">Admin</span>'
        f'<a href="{escape(admin_url)}" class="value link">{escape(admin_url)}</a></div>'
        if admin_url
        else ""
    )
    signin = (
        f'<div id="signin-wrap">'
        f'<div id="signin-error" class="signin-error" role="alert" aria-live="polite"></div>'
        f'<form class="signin" id="signin-form" method="post" '
        f'action="{escape(admin_url)}/session" '
        f'hx-post="{escape(admin_url)}/session" '
        f'hx-target="#signin-error" hx-swap="innerHTML" '
        f'hx-disabled-elt="find button">'
        f'<input name="token" type="password" placeholder="admin token" required autofocus '
        f'autocomplete="current-password">'
        f'<button type="submit">Sign in</button>'
        f"</form></div>"
        if admin_url
        else ""
    )
    attribution = _powered_by_rivex()
    return f"""<!DOCTYPE html>
<html lang="en"><head><title>{t}</title><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>:root{{--bg:#fff;--fg:#000;--muted:#a1a1aa;--line:#e4e4e7;--soft:#f4f4f5;--accent:#f97316;--green:#22c55e;--mono:"SF Mono","Fira Code",Consolas,monospace;--sans:Inter,system-ui,sans-serif}}.dark{{--bg:#09090b;--fg:#fff;--muted:#52525b;--line:#27272a;--soft:#18181b;--green:#4ade80}}*{{box-sizing:border-box;margin:0}}body{{min-height:100vh;background:var(--bg);color:var(--fg);font-family:var(--sans);-webkit-font-smoothing:antialiased;transition:background .3s,color .3s}}.shell{{min-height:100vh;display:flex;align-items:center;justify-content:center}}.center{{text-align:center;max-width:680px;width:100%;padding:24px}}.logo{{font-family:var(--mono);font-size:clamp(64px,11vw,128px);font-weight:900;letter-spacing:-.05em;line-height:.95;user-select:none}}.accent{{color:var(--accent)}}.status{{display:flex;align-items:center;justify-content:center;gap:10px;margin-top:clamp(20px,3vw,36px)}}.pulse-ring{{position:relative;width:10px;height:10px}}.pulse-dot{{position:absolute;inset:1px;border-radius:50%;background:var(--green)}}.pulse-ring::before{{content:"";position:absolute;inset:0;border-radius:50%;background:var(--green);animation:pulse 2s ease-out infinite;opacity:0}}@keyframes pulse{{0%{{transform:scale(1);opacity:.55}}100%{{transform:scale(2.8);opacity:0}}}}.status-text{{font-family:var(--mono);font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--green)}}.curl{{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:14px;letter-spacing:.02em}}.topbar{{position:fixed;top:0;left:0;right:0;display:flex;justify-content:flex-end;align-items:center;padding:18px 24px;z-index:5}}.theme-toggle{{display:inline-flex;align-items:center;gap:8px;padding:8px 14px;border:1px solid var(--line);border-radius:999px;background:var(--bg);color:var(--muted);font-family:var(--mono);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;cursor:pointer;transition:all .2s;box-shadow:0 1px 2px rgba(0,0,0,.04)}}.theme-toggle:hover{{color:var(--fg);border-color:var(--fg)}}.theme-toggle svg{{width:14px;height:14px}}.theme-toggle .icon-sun{{display:block}}.theme-toggle .icon-moon{{display:none}}.dark .theme-toggle .icon-sun{{display:none}}.dark .theme-toggle .icon-moon{{display:block}}.powered{{position:absolute;top:24px;right:24px;font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}}.powered-inline{{position:static;display:block;margin:14px auto 0;text-align:center;font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}}.powered-rivex{{position:static;display:flex;align-items:baseline;justify-content:flex-end;gap:0;margin:18px 0 0;font-family:var(--mono);font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:12px 18px}}.powered-rivex .label{{color:var(--muted);font-size:10px;letter-spacing:.18em;margin-right:10px;font-weight:600}}.powered-rivex .x{{color:var(--accent);font-weight:700;font-size:14px;letter-spacing:.14em;text-shadow:0 0 14px rgba(249,115,22,.25)}}.signin{{margin:36px auto 0;display:flex;gap:8px;max-width:380px;padding:8px;border:1px solid var(--line);border-radius:12px;background:var(--soft);box-shadow:0 1px 0 var(--line) inset}}.signin input{{flex:1;border:0;background:transparent;color:var(--fg);padding:10px 12px;font-family:var(--mono);font-size:13px;outline:none}}.signin input::placeholder{{color:var(--muted)}}.signin button{{border:0;background:var(--fg);color:var(--bg);font-family:var(--mono);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;padding:0 16px;border-radius:6px;cursor:pointer}}.signin button:hover{{opacity:.85}}.signin button:disabled{{opacity:.6;cursor:progress}}.signin-error:empty{{display:none}}.signin-error{{display:flex;align-items:center;gap:10px;margin:20px auto 0;max-width:380px;padding:12px 16px;border:1px solid var(--red);border-radius:10px;background:rgba(239,68,68,.08);color:var(--red);font-family:var(--mono);font-size:12px;font-weight:600;letter-spacing:.02em;line-height:1.5}}.signin-error svg{{flex-shrink:0;width:16px;height:16px;stroke:var(--red)}}.signin-error code{{color:inherit;background:rgba(239,68,68,.12);padding:1px 5px;border-radius:4px;font-size:11px}}.info-btn{{position:fixed;bottom:24px;left:24px;width:40px;height:40px;border-radius:50%;border:1px solid var(--line);background:var(--bg);color:var(--muted);cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;z-index:10}}.info-btn svg{{width:18px;height:18px}}.info-btn:hover{{color:var(--fg);border-color:var(--fg)}}.theme-btn{{position:fixed;bottom:24px;right:24px;width:40px;height:40px;border-radius:50%;border:1px solid var(--line);background:var(--bg);color:var(--muted);cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;z-index:10}}.theme-btn svg{{width:18px;height:18px;display:none}}.theme-btn:hover{{color:var(--fg);border-color:var(--fg)}}:root .theme-btn .icon-sun{{display:block}}.dark .theme-btn .icon-sun{{display:none}}.dark .theme-btn .icon-moon{{display:block}}.overlay{{position:fixed;inset:0;background:rgba(0,0,0,.4);opacity:0;pointer-events:none;transition:opacity .3s;z-index:20}}.overlay.open{{opacity:1;pointer-events:auto}}.drawer{{position:fixed;bottom:0;left:0;width:min(100%,400px);background:var(--bg);border-top:1px solid var(--line);border-right:1px solid var(--line);border-radius:0 12px 0 0;padding:28px;transform:translateY(100%);transition:transform .3s cubic-bezier(.4,0,.2,1),background .3s;z-index:30}}.drawer.open{{transform:translateY(0)}}.drawer-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}}.drawer-title{{font-family:var(--mono);font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}}.close-btn{{background:none;border:none;color:var(--muted);font-size:22px;cursor:pointer;padding:0 4px;line-height:1;transition:color .2s}}.close-btn:hover{{color:var(--fg)}}.info-grid{{display:grid;gap:1px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--line)}}.info-row{{display:grid;grid-template-columns:80px 1fr;gap:12px;background:var(--bg);padding:12px 16px;transition:background .3s}}.label{{font-family:var(--mono);font-size:11px;font-weight:700;text-transform:uppercase;color:var(--muted)}}.value{{font-family:var(--mono);font-size:13px;overflow-wrap:anywhere}}.link{{color:var(--accent);text-decoration:none}}.link:hover{{text-decoration:underline}}</style>
</head><body x-data="serverPage()" x-init="init()" :class="theme">
<header class="topbar">
  <button class="theme-toggle" @click="toggleTheme()" :title="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'">
    <svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
    <svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
    <span x-text="theme === 'dark' ? 'Light' : 'Dark'"></span>
  </button>
</header>
<main class="shell">
<div class="center">
<div class="logo">{brand}</div>
{attribution}
<div class="status"><div class="pulse-ring"><div class="pulse-dot"></div></div><span class="status-text">Operational</span></div>
<div class="curl">curl <span x-text="origin"></span> — <span x-text="uptimeFmt()"></span></div>
{signin}
</div>
<button class="info-btn" @click="drawer=true" aria-label="Info"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><circle cx="12" cy="8" r=".5" fill="currentColor"/></svg></button>
<div class="drawer" :class="drawer ? 'open' : ''">
<div class="drawer-head"><span class="drawer-title">Service Info</span><button class="close-btn" @click="drawer=false" aria-label="Close">&times;</button></div>
<div class="info-grid">
<div class="info-row"><span class="label">Service</span><span class="value">{t}</span></div>
<div class="info-row"><span class="label">Version</span><span class="value">{v}</span></div>
<div class="info-row"><span class="label">Runtime</span><span class="value">Rust + Python</span></div>
<div class="info-row"><span class="label">Uptime</span><span class="value" x-text="uptimeFmt()"></span></div>
{docs_row}
{admin_row}
</div>
</div>
<div class="overlay" :class="drawer ? 'open' : ''" @click="drawer=false"></div>
</main>
<script src="/admin/static/alpine.min.js" defer></script>
<script src="/admin/static/htmx.min.js" defer></script>
<script>
function serverPage() {{
  return {{
    startedAt: Date.now(),
    seconds: 0,
    timer: null,
    drawer: false,
    theme: 'dark',
    origin: location.origin,
    init() {{
      try {{
        const saved = localStorage.getItem('rivex-theme');
        if (saved === 'dark' || saved === 'light') {{
          this.theme = saved;
        }}
      }} catch (e) {{ /* localStorage may be disabled */ }}
      this.timer = setInterval(() => {{ this.seconds = Math.floor((Date.now() - this.startedAt) / 1000); }}, 1000);
    }},
    uptimeFmt() {{
      const s = this.seconds, m = Math.floor(s/60), h = Math.floor(m/60), d = Math.floor(h/24);
      if (d > 0) return d + 'd ' + (h%24) + 'h ' + (m%60) + 'm';
      if (h > 0) return h + 'h ' + (m%60) + 'm ' + (s%60) + 's';
      if (m > 0) return m + 'm ' + (s%60) + 's';
      return s + 's';
    }},
    toggleTheme() {{
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      try {{ localStorage.setItem('rivex-theme', this.theme); }} catch (e) {{}}
    }},
  }};
}}
// HTMX belt-and-suspenders: when /admin/session returns 4xx, the
// response body is the error banner — swap it into #signin-error
// manually (HTMX skips the swap on non-2xx by default).
document.body.addEventListener('htmx:responseError', function (evt) {{
  var xhr = evt.detail && evt.detail.xhr;
  if (!xhr) return;
  var target = evt.detail.target || evt.target;
  if (target && xhr.responseText) {{
    target.innerHTML = xhr.responseText;
  }}
  // Re-enable the submit button in case the form was disabled
  var form = document.getElementById('signin-form');
  if (form) {{
    var btn = form.querySelector('button[type=submit]');
    if (btn) btn.disabled = false;
  }}
}});
</script>
</body></html>"""


def _powered_by(powered_by: str | None, *, inline: bool = False) -> str:
    """Render a small ``powered by <name>`` line.

    With ``inline=True`` the line renders as a centered subtitle that
    sits directly under the wordmark.  Otherwise it sits in the
    top-right corner.  Empty string hides it.
    """
    if not powered_by:
        return ""
    from html import escape

    cls = "powered powered-inline" if inline else "powered"
    return f'<div class="{cls}">powered by {escape(powered_by)}</div>'


def _powered_by_rivex() -> str:
    """Render the fixed ``powered by RiveX`` line for the server page.

    A small divider sits above and below the line, the brand mark
    uses a 22px accent X with a soft glow so it reads at a glance.
    The whole row is right-aligned, sitting just under the logo.
    """
    return (
        '<div class="powered-rivex">'
        '<span class="label">powered by</span>'
        ' Rive<span class="x">X</span>'
        "</div>"
    )


def _fallback_docs_html(
    title: str,
    openapi_url: str,
    *,
    app_name: str | None = None,
    powered_by: str | None = None,
) -> str:
    from html import escape

    t, u = escape(title), escape(openapi_url)
    app_label = escape(app_name or "Rivex")
    brand = _brand_mark(app_name or "Rivex")
    attribution = _powered_by_rivex()
    return f"""<!DOCTYPE html>
<html lang="en" x-data="docsPage()" x-init="init()" :class="theme">
<head>
<meta charset="utf-8">
<title>{t} — API Docs</title>
<meta name="description" content="Interactive API Documentation">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root {{
  --bg: #fff;
  --fg: #000;
  --muted: #a1a1aa;
  --line: #e4e4e7;
  --soft: #f4f4f5;
  --accent: #f97316;
  --m-get: #d1fae5; --m-get-fg: #047857;
  --m-post: #dbeafe; --m-post-fg: #1d4ed8;
  --m-put: #fef3c7; --m-put-fg: #b45309;
  --m-patch: #f3e8ff; --m-patch-fg: #7e22ce;
  --m-delete: #fee2e2; --m-delete-fg: #b91c1c;
  --p-query: #e0e7ff; --p-query-fg: #3730a3;
  --p-path: #fce7f3; --p-path-fg: #be185d;
  --p-header: #f3f4f6; --p-header-fg: #374151;
  --p-body: #ecfdf5; --p-body-fg: #065f46;
  --s-ok: #d1fae5; --s-ok-fg: #047857;
  --s-err: #fee2e2; --s-err-fg: #b91c1c;
  --mono: "SF Mono", "Fira Code", Consolas, monospace;
  --sans: Inter, system-ui, -apple-system, sans-serif;
  --radius: 8px;
}}
.dark {{
  --bg: #09090b;
  --fg: #fff;
  --muted: #52525b;
  --line: #27272a;
  --soft: #18181b;
  --m-get: #022c22; --m-get-fg: #34d399;
  --m-post: #172554; --m-post-fg: #60a5fa;
  --m-put: #451a03; --m-put-fg: #fbbf24;
  --m-patch: #2e1065; --m-patch-fg: #c084fc;
  --m-delete: #450a0a; --m-delete-fg: #f87171;
  --p-query: #1e1b4b; --p-query-fg: #818cf8;
  --p-path: #500724; --p-path-fg: #f472b6;
  --p-header: #1f2937; --p-header-fg: #9ca3af;
  --p-body: #064e3b; --p-body-fg: #34d399;
  --s-ok: #022c22; --s-ok-fg: #34d399;
  --s-err: #450a0a; --s-err-fg: #f87171;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg); color: var(--fg); font-family: var(--sans);
  -webkit-font-smoothing: antialiased; min-height: 100vh;
  transition: background 0.3s ease, color 0.3s ease;
}}
a {{ color: inherit; text-decoration: none; }}
code, pre {{ font-family: var(--mono); font-size: 0.85em; }}

/* Navigation */
.topbar {{
  position: sticky; top: 0; z-index: 50; display: flex;
  justify-content: space-between; align-items: center; padding: 18px 24px;
  background: var(--bg); border-bottom: 1px solid var(--line);
}}
.topbar .brand {{ font-family: var(--mono); font-weight: 900; font-size: 1.1rem; letter-spacing: -0.04em; display: flex; align-items: center; gap: 8px; }}
.links {{ display: flex; gap: 12px; align-items: center; }}

.btn {{
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 8px 14px; border: 1px solid var(--line); border-radius: 999px;
  background: var(--bg); color: var(--fg); font-family: var(--mono);
  font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em;
  cursor: pointer; transition: all 0.2s ease;
}}
.btn:hover {{ border-color: var(--fg); }}
.btn.primary {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}
.btn.primary:hover {{ opacity: 0.85; }}

.theme-toggle svg {{ width: 14px; height: 14px; }}
.theme-toggle .icon-sun {{ display: block; }} .theme-toggle .icon-moon {{ display: none; }}
.dark .theme-toggle .icon-sun {{ display: none; }} .dark .theme-toggle .icon-moon {{ display: block; }}

/* Layout */
.layout {{
  display: grid; grid-template-columns: 280px 1fr; gap: 48px;
  max-width: 1400px; margin: 0 auto; padding: 40px 24px 80px;
}}
.sidebar {{
  position: sticky; top: 100px; height: fit-content; max-height: calc(100vh - 120px);
  overflow-y: auto; padding-right: 16px;
  scrollbar-width: thin; scrollbar-color: var(--muted) transparent;
}}
.sidebar::-webkit-scrollbar {{ width: 4px; }}
.sidebar::-webkit-scrollbar-thumb {{ background: var(--muted); border-radius: 4px; }}

.search-container {{ position: relative; margin-bottom: 24px; }}
.search-container svg {{ position: absolute; left: 12px; top: 50%; transform: translateY(-50%); width: 14px; height: 14px; color: var(--muted); }}
.search {{
  width: 100%; padding: 10px 12px 10px 34px; border: 1px solid var(--line);
  border-radius: var(--radius); background: var(--bg); color: var(--fg);
  font-family: var(--mono); font-size: 13px; outline: none; transition: border-color 0.2s;
}}
.search:focus {{ border-color: var(--fg); }}

.nav-title {{ margin: 0 0 12px 4px; font-family: var(--mono); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.14em; color: var(--muted); }}
.nav-link {{
  display: grid; grid-template-columns: 60px 1fr; gap: 8px; align-items: center;
  padding: 8px 12px; border-radius: 6px; color: var(--muted);
  font-family: var(--mono); font-size: 13px; transition: all 0.15s ease; border: 1px solid transparent;
}}
.nav-link:hover {{ background: var(--soft); color: var(--fg); }}
.nav-link.active {{ background: var(--soft); color: var(--fg); border-color: var(--line); }}

/* Methods */
.method {{
  display: inline-flex; align-items: center; justify-content: center;
  padding: 4px 6px; border-radius: 4px; font-family: var(--mono);
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; min-width: 50px;
}}
.method-GET {{ background: var(--m-get); color: var(--m-get-fg); }}
.method-POST {{ background: var(--m-post); color: var(--m-post-fg); }}
.method-PUT {{ background: var(--m-put); color: var(--m-put-fg); }}
.method-PATCH {{ background: var(--m-patch); color: var(--m-patch-fg); }}
.method-DELETE {{ background: var(--m-delete); color: var(--m-delete-fg); }}

/* Param Types */
.param-type {{
  display: inline-flex; align-items: center; justify-content: center;
  padding: 2px 6px; border-radius: 4px; font-family: var(--mono);
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
}}
.param-query {{ background: var(--p-query); color: var(--p-query-fg); }}
.param-path {{ background: var(--p-path); color: var(--p-path-fg); }}
.param-header {{ background: var(--p-header); color: var(--p-header-fg); }}
.param-body {{ background: var(--p-body); color: var(--p-body-fg); }}

/* Main Content */
.section-head {{
  display: flex; justify-content: space-between; align-items: flex-end;
  margin-bottom: 32px; padding-bottom: 16px; border-bottom: 1px solid var(--line);
}}
.section-head h2 {{ font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; }}
.count {{ font-family: var(--mono); font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; }}

.endpoint {{
  border: 1px solid var(--line); border-radius: var(--radius); background: var(--bg);
  margin-bottom: 16px; overflow: hidden; transition: border-color 0.2s;
}}
.endpoint:hover {{ border-color: var(--muted); }}
.endpoint[hidden] {{ display: none; }}

.endpoint-header {{
  display: flex; align-items: center; gap: 16px; padding: 16px 20px; cursor: pointer; user-select: none;
}}
.endpoint-header:hover {{ background: var(--soft); }}
.endpoint-header .path {{ font-family: var(--mono); font-size: 13px; font-weight: 600; color: var(--fg); word-break: break-all; }}
.endpoint-header .summary {{ flex: 1; color: var(--muted); font-size: 13px; text-align: right; }}
.endpoint-header .chevron {{ transition: transform 0.2s; width: 16px; height: 16px; color: var(--muted); }}
.endpoint.open .chevron {{ transform: rotate(180deg); }}

.detail-body {{ border-top: 1px solid var(--line); padding: 24px; background: var(--soft); }}

.subhead {{
  font-family: var(--mono); font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.1em; color: var(--muted); margin-bottom: 12px; display: flex; align-items: center; gap: 8px;
}}
.subhead::after {{ content: ""; flex: 1; height: 1px; background: var(--line); }}

/* Forms & Tables */
.table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; margin-bottom: 24px; }}
.table th, .table td {{ padding: 12px; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; }}
.table th {{
  font-family: var(--mono); font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted); background: var(--bg);
}}
.table tr:last-child td {{ border-bottom: none; }}
.table input, .table textarea {{
  width: 100%; padding: 8px 12px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--bg); color: var(--fg); font-family: var(--mono); font-size: 13px; outline: none; transition: border-color 0.2s;
}}
.table input:focus, .table textarea:focus {{ border-color: var(--fg); }}
.table .param-desc {{ display: block; margin-top: 4px; font-size: 12px; color: var(--muted); font-family: var(--sans); }}

.req-body-editor {{ width: 100%; min-height: 150px; padding: 16px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); color: var(--fg); font-family: var(--mono); font-size: 13px; resize: vertical; outline: none; margin-bottom: 24px; }}
.req-body-editor:focus {{ border-color: var(--fg); }}

.execute-bar {{ display: flex; justify-content: flex-end; gap: 12px; margin-top: 12px; padding-top: 24px; border-top: 1px solid var(--line); }}

/* Responses */
.response-block {{ margin-top: 24px; border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; background: var(--bg); }}
.response-header {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: var(--line); font-family: var(--mono); font-size: 13px; font-weight: 600; }}
.status-code {{ padding: 2px 6px; border-radius: 4px; font-size: 11px; }}
.status-code.ok {{ background: var(--s-ok); color: var(--s-ok-fg); }}
.status-code.err {{ background: var(--s-err); color: var(--s-err-fg); }}
.response-body {{ padding: 16px; font-family: var(--mono); font-size: 13px; overflow-x: auto; color: var(--fg); }}
.response-headers {{ padding: 16px; background: var(--soft); border-bottom: 1px solid var(--line); font-family: var(--mono); font-size: 12px; color: var(--muted); }}

.empty {{ padding: 48px 24px; text-align: center; color: var(--muted); border: 1px dashed var(--line); border-radius: var(--radius); font-size: 13px; }}

.doc-footer-wrap {{
  position: sticky; bottom: 0; background: var(--bg); border-top: 1px solid var(--line); z-index: 40; width: 100%;
}}
.doc-footer {{
  display: flex; justify-content: space-between; align-items: center;
  max-width: 1400px; margin: 0 auto; padding: 24px;
  font-family: var(--mono); font-size: 11px; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.12em;
}}
.doc-footer .brand {{ font-weight: 900; font-size: 13px; }}
.doc-footer .powered {{ display: flex; align-items: baseline; gap: 6px; }}

.accent {{ color: var(--accent); }}
.powered-rivex .x {{ color: var(--accent); font-weight: 800; text-shadow: 0 0 12px rgba(249,115,22,0.25); }}

@media(max-width: 900px) {{
  .layout {{ grid-template-columns: 1fr; padding: 24px 16px; }}
  .sidebar {{ position: static; max-height: none; padding: 0 0 32px; border-bottom: 1px solid var(--line); border-right: none; margin-bottom: 32px; }}
}}

[x-cloak] {{ display: none !important; }}
</style>
<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/collapse@3.x.x/dist/cdn.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body>

<header class="topbar">
  <div class="brand" aria-label="{app_label}" title="{app_label}">
    {brand}
  </div>
  <div class="links">
    <a class="btn" href="{u}" target="_blank">OpenAPI JSON</a>
    <button class="btn theme-toggle" @click="toggleTheme()" :title="theme === 'dark' ? 'Light' : 'Dark'">
      <svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
      <svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
      <span x-text="theme === 'dark' ? 'Light Mode' : 'Dark Mode'"></span>
    </button>
  </div>
</header>

<main class="layout">
  <aside class="sidebar">
    <div class="search-container">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
      <input class="search" type="search" placeholder="Filter endpoints…" autocomplete="off" x-model="query">
    </div>
    <div class="nav-title">Routes</div>
    <nav>
      <template x-for="e in filtered" :key="e.id">
        <a class="nav-link" href="#" @click.prevent="activeId = e.id; window.scrollTo(0,0)" :class="activeId === e.id ? 'active' : ''">
          <span :class="'method method-' + e.method" x-text="e.method"></span>
          <span x-text="e.path" style="text-overflow: ellipsis; overflow: hidden; white-space: nowrap;"></span>
        </a>
      </template>
    </nav>
  </aside>

  <div class="content">
    <section id="endpoints">
      <div>
        <template x-for="e in filtered" :key="e.id">
          <article class="endpoint" :id="e.id" :class="e.open ? 'open' : ''" x-show="e.id === activeId">
            <div class="endpoint-header" @click="e.open = !e.open">
              <span :class="'method method-' + e.method" x-text="e.method"></span>
              <span class="path"><span style="opacity: 0.5; font-weight: normal;" x-text="window.location.origin"></span><span x-text="e.path"></span></span>
              <span class="summary" x-text="e.summary"></span>
              <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m6 9 6 6 6-6"/></svg>
            </div>
            
            <div x-show="e.open" x-collapse x-cloak>
              <div class="detail-body">
                
                <div x-show="e.parameters.length > 0">
                  <div class="subhead">Parameters</div>
                  <table class="table">
                    <thead><tr><th>Name</th><th>Value</th><th>Details</th></tr></thead>
                    <tbody>
                      <template x-for="p in e.parameters" :key="p.name">
                        <tr>
                          <td>
                            <strong x-text="p.name"></strong>
                            <span x-show="p.required" style="color:var(--red)">*</span>
                          </td>
                          <td>
                            <input type="text" x-model="e.inputs[p.name]" :placeholder="p.schema && p.schema.default ? String(p.schema.default) : ''">
                          </td>
                          <td>
                            <div><span :class="'param-type param-' + p.in" x-text="p.in"></span> • <code x-text="schemaName(p.schema)"></code></div>
                            <span class="param-desc" x-text="p.description || ''"></span>
                          </td>
                        </tr>
                      </template>
                    </tbody>
                  </table>
                </div>

                <div x-show="e.requestBody">
                  <div class="subhead">Request Body</div>
                  <textarea class="req-body-editor" x-model="e.reqBodyStr" placeholder="{{ ... }}"></textarea>
                </div>
                
                <div class="execute-bar">
                  <button class="btn" @click="e.inputs = {{}}; e.result = null; e.reqBodyStr = e.requestBody ? '{{\\n  \\n}}' : ''">Clear</button>
                  <button class="btn" @click="copyCurl(e)">Copy cURL</button>
                  <button class="btn primary" @click="execute(e)" :disabled="e.running">
                    <span x-show="!e.running">Execute</span>
                    <span x-show="e.running">Running...</span>
                  </button>
                </div>

                <div x-show="e.result" class="response-block" x-cloak>
                  <div class="response-header">
                    <div>Response <span :class="'status-code ' + (e.result && e.result.status < 400 ? 'ok' : 'err')" x-text="e.result && e.result.status + ' ' + (e.result.statusText||'')"></span></div>
                    <div style="display:flex; align-items:center; gap:16px;">
                      <div x-text="e.result && e.result.time + ' ms'"></div>
                      <button class="btn" style="padding: 2px 8px; font-size: 10px;" @click="copyResponse(e)">Copy</button>
                    </div>
                  </div>
                  <div class="response-headers" x-show="e.result && e.result.headers && Object.keys(e.result.headers).length">
                    <template x-for="(val, key) in e.result ? e.result.headers : {{}}">
                      <div><strong x-text="key + ':'"></strong> <span x-text="val"></span></div>
                    </template>
                  </div>
                  <div class="response-body">
                    <pre x-text="e.result && (typeof e.result.body === 'string' ? e.result.body : pretty(e.result.body))"></pre>
                  </div>
                </div>

                <div style="margin-top: 24px;">
                  <div class="subhead">Responses</div>
                  <table class="table">
                    <thead><tr><th>Status</th><th>Description</th><th>Schema</th></tr></thead>
                    <tbody>
                      <template x-for="(re, status) in e.responses" :key="status">
                        <tr>
                          <td><code x-text="status"></code></td>
                          <td x-text="re.description || ''"></td>
                          <td><code x-text="schemaName(re.content && re.content['application/json'] && re.content['application/json'].schema)"></code></td>
                        </tr>
                      </template>
                    </tbody>
                  </table>
                </div>

                <div x-show="e.usedSchemas && e.usedSchemas.length > 0" style="margin-top: 24px;">
                  <div class="subhead">Associated Data Models</div>
                  <template x-for="sname in e.usedSchemas" :key="sname">
                    <div style="margin-bottom: 12px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--bg);">
                      <div class="endpoint-header" style="padding: 12px 16px; border-bottom: 1px solid var(--line); cursor: default;">
                        <span class="method method-MODEL">MODEL</span>
                        <span class="path" x-text="sname"></span>
                      </div>
                      <div class="detail-body" style="padding: 16px; border-top: none;">
                        <pre x-text="pretty(schemas[sname])"></pre>
                      </div>
                    </div>
                  </template>
                </div>

              </div>
            </div>
          </article>
        </template>
        <div class="empty" x-show="!loading && filtered.length === 0">No endpoints match your search.</div>
      </div>
    </section>



  </div>
</main>

<div class="doc-footer-wrap">
  <footer class="doc-footer">
    <span class="brand">{brand}</span>
    <span class="powered">{attribution}</span>
  </footer>
</div>

<script>
function docsPage() {{
  return {{
    specUrl: "{u}",
    theme: "dark",
    query: "",
    loading: true,
    endpoints: [],
    schemas: {{}},
    activeId: "",
    init() {{
      try {{
        var t = localStorage.getItem("rivex-theme");
        if (t === "dark" || t === "light") this.theme = t;
      }} catch (e) {{}}
      this.$watch("theme", function (v) {{
        try {{ localStorage.setItem("rivex-theme", v); }} catch (e) {{}}
      }});
      this.loadSpec();
    }},
    async loadSpec() {{
      try {{
        var r = await fetch(this.specUrl);
        if (!r.ok) throw new Error("HTTP " + r.status);
        var spec = await r.json();
        var mo = ["get","post","put","patch","delete","head","options","trace"];
        var ml = {{get:"GET",post:"POST",put:"PUT",patch:"PATCH",delete:"DELETE",head:"HEAD",options:"OPTIONS",trace:"TRACE"}};
        var eps = [];
        Object.entries(spec.paths || {{}}).forEach(([p, ms]) => {{
          mo.forEach(m => {{
            var op = ms[m];
            if (!op) return;
            var l = ml[m] || m.toUpperCase();
            var used = {{}};
            var extractRef = (s) => {{
              if (!s) return;
              if (s.$ref) used[s.$ref.split('/').pop()] = true;
              if (s.items && s.items.$ref) used[s.items.$ref.split('/').pop()] = true;
            }};
            try {{
              if (op.requestBody && op.requestBody.content) {{
                Object.values(op.requestBody.content).forEach(c => extractRef(c.schema));
              }}
              if (op.responses) {{
                Object.values(op.responses).forEach(r => {{
                  if (r.content) Object.values(r.content).forEach(c => extractRef(c.schema));
                }});
              }}
            }} catch(ex) {{}}

            eps.push({{
              method: l,
              path: p,
              id: (l + "-" + p).replace(/[^a-z0-9]+/gi, "-").toLowerCase(),
              summary: op.summary || "",
              parameters: op.parameters || [],
              requestBody: op.requestBody || null,
              responses: op.responses || {{}},
              search: (l + " " + p + " " + (op.summary || "")).toLowerCase(),
              open: true,
              inputs: {{}},
              reqBodyStr: op.requestBody ? '{{\\n  \\n}}' : '',
              running: false,
              result: null,
              usedSchemas: Object.keys(used)
            }});
          }});
        }});
        this.endpoints = eps;
        if (eps.length > 0) this.activeId = eps[0].id;
        
        var rawSchemas = (spec.components && spec.components.schemas) || {{}};
        var processedSchemas = {{}};
        Object.keys(rawSchemas).forEach(k => {{
          processedSchemas[k] = {{ ...rawSchemas[k], open: true }};
        }});
        this.schemas = processedSchemas;
      }} catch (e) {{
        var el = document.getElementById("endpoints");
        if (el) {{
          var list = el.querySelector("div:nth-child(2)");
          if (list) list.innerHTML = '<div class="error empty" style="border-color:var(--red);color:var(--red)">Failed to load spec: ' + e.message + "</div>";
        }}
      }} finally {{
        this.loading = false;
      }}
    }},
    get filtered() {{
      var q = (this.query || "").trim().toLowerCase();
      var res = !q ? this.endpoints : this.endpoints.filter(e => e.search.indexOf(q) >= 0);
      if (res.length > 0 && !res.find(e => e.id === this.activeId)) {{
        this.activeId = res[0].id;
      }}
      return res;
    }},
    schemaName(s) {{
      if (!s) return "any";
      if (s.$ref) return s.$ref.split("/").pop();
      if (s.type) return s.format ? s.type + ":" + s.format : s.type;
      return "object";
    }},
    pretty(v) {{
      try {{ return JSON.stringify(v, null, 2); }} catch (e) {{ return String(v); }}
    }},
    buildRequest(e) {{
      let urlStr = this.specUrl.replace('/openapi.json', '') + e.path;
      if (!urlStr.startsWith('http')) {{
        urlStr = window.location.origin + urlStr;
      }}
      let headers = {{ "Accept": "application/json" }};
      let bodyData = undefined;
      
      e.parameters.forEach(p => {{
        const val = e.inputs[p.name] || (p.schema && p.schema.default);
        if (p.in === 'path') {{
          urlStr = urlStr.replace('{{' + p.name + '}}', encodeURIComponent(val || ''));
        }} else if (p.in === 'query' && val) {{
          const u = new URL(urlStr);
          u.searchParams.append(p.name, val);
          urlStr = u.toString();
        }} else if (p.in === 'header' && val) {{
          headers[p.name] = val;
        }}
      }});

      if (e.requestBody && e.reqBodyStr) {{
        headers["Content-Type"] = "application/json";
      }}
      if (e.method !== 'GET' && e.method !== 'HEAD' && e.reqBodyStr) {{
        bodyData = e.reqBodyStr;
      }}
      return {{ url: urlStr, headers, body: bodyData }};
    }},
    copyCurl(e) {{
      const req = this.buildRequest(e);
      let cmd = `curl -X ${{e.method}} "${{req.url}}"`;
      Object.entries(req.headers).forEach(([k, v]) => {{
        cmd += ` -H "${{k}}: ${{v}}"`;
      }});
      if (req.body) {{
        cmd += ` -d '${{req.body.replace(/'/g, "'\\''")}}'`;
      }}
      navigator.clipboard.writeText(cmd).then(() => alert("cURL copied!"));
    }},
    copyResponse(e) {{
      if (!e.result || !e.result.body) return;
      const text = typeof e.result.body === 'string' ? e.result.body : JSON.stringify(e.result.body, null, 2);
      navigator.clipboard.writeText(text).then(() => alert("Response copied!"));
    }},
    async execute(e) {{
      e.running = true;
      e.result = null;
      const req = this.buildRequest(e);

      try {{
        const start = performance.now();
        const res = await fetch(req.url, {{
          method: e.method,
          headers: req.headers,
          body: req.body
        }});
        const time = performance.now() - start;
        
        const bodyText = await res.text();
        let bodyJson = null;
        try {{ bodyJson = JSON.parse(bodyText); }} catch(err) {{}}

        e.result = {{
          status: res.status,
          statusText: res.statusText,
          time: Math.round(time),
          headers: Object.fromEntries(res.headers.entries()),
          body: bodyJson || bodyText
        }};
      }} catch(err) {{
        e.result = {{ error: err.message, status: 0, statusText: "Network Error" }};
      }} finally {{
        e.running = false;
      }}
    }},
    toggleTheme() {{
      this.theme = this.theme === "dark" ? "light" : "dark";
    }}
  }};
}}
</script>
</body>
</html>"""


def _fallback_redoc_html(title: str, openapi_url: str) -> str:
    from html import escape

    t, u = escape(title), escape(openapi_url)
    return f"""<!DOCTYPE html>
<html lang="en"><head><title>{t} — ReDoc</title><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{margin:0;padding:0}}</style></head><body>
<redoc spec-url="{u}"></redoc>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
</body></html>"""


def _fallback_health_html(
    title: str,
    version: str,
    docs_url: str | None,
    *,
    app_name: str | None = None,
    powered_by: str | None = None,
) -> str:
    from html import escape

    t, v = escape(title), escape(version)
    brand = _brand_mark(app_name or "Rivex")
    attribution = _powered_by(powered_by if powered_by is not None else "Rivex")
    docs_row = (
        f'<div class="info-row"><span class="label">Docs</span><a href="{escape(docs_url)}" class="value link">{escape(docs_url)}</a></div>'
        if docs_url
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><title>{t}</title><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>:root{{--bg:#fff;--fg:#000;--muted:#a1a1aa;--line:#e4e4e7;--soft:#f4f4f5;--accent:#f97316;--green:#22c55e;--mono:"SF Mono","Fira Code",Consolas,monospace;--sans:Inter,system-ui,sans-serif}}.dark{{--bg:#09090b;--fg:#fff;--muted:#52525b;--line:#27272a;--soft:#18181b;--green:#4ade80}}*{{box-sizing:border-box;margin:0}}body{{min-height:100vh;background:var(--bg);color:var(--fg);font-family:var(--sans);-webkit-font-smoothing:antialiased;transition:background .3s,color .3s}}.shell{{min-height:100vh;display:flex;align-items:center;justify-content:center}}.center{{text-align:center}}.logo{{font-family:var(--mono);font-size:clamp(80px,18vw,180px);font-weight:900;letter-spacing:-.04em;line-height:1;user-select:none}}.accent{{color:var(--accent)}}.status{{display:flex;align-items:center;justify-content:center;gap:10px;margin-top:clamp(18px,3vw,32px)}}.pulse-ring{{position:relative;width:10px;height:10px}}.pulse-dot{{position:absolute;inset:1px;border-radius:50%;background:var(--green)}}.pulse-ring::before{{content:"";position:absolute;inset:0;border-radius:50%;background:var(--green);animation:pulse 2s ease-out infinite;opacity:0}}@keyframes pulse{{0%{{transform:scale(1);opacity:.55}}100%{{transform:scale(2.8);opacity:0}}}}.status-text{{font-family:var(--mono);font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--green)}}.curl{{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:14px;letter-spacing:.02em}}.powered{{position:absolute;top:24px;right:24px;font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}}.info-btn{{position:fixed;bottom:24px;left:24px;width:40px;height:40px;border-radius:50%;border:1px solid var(--line);background:var(--bg);color:var(--muted);cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;z-index:10}}.info-btn svg{{width:18px;height:18px}}.info-btn:hover{{color:var(--fg);border-color:var(--fg)}}.theme-btn{{position:fixed;bottom:24px;right:24px;width:40px;height:40px;border-radius:50%;border:1px solid var(--line);background:var(--bg);color:var(--muted);cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;z-index:10}}.theme-btn svg{{width:18px;height:18px;display:none}}.theme-btn:hover{{color:var(--fg);border-color:var(--fg)}}:root .theme-btn .icon-sun{{display:block}}.dark .theme-btn .icon-sun{{display:none}}.dark .theme-btn .icon-moon{{display:block}}.overlay{{position:fixed;inset:0;background:rgba(0,0,0,.4);opacity:0;pointer-events:none;transition:opacity .3s;z-index:20}}.overlay.open{{opacity:1;pointer-events:auto}}.drawer{{position:fixed;bottom:0;left:0;width:min(100%,400px);background:var(--bg);border-top:1px solid var(--line);border-right:1px solid var(--line);border-radius:0 12px 0 0;padding:28px;transform:translateY(100%);transition:transform .3s cubic-bezier(.4,0,.2,1),background .3s;z-index:30}}.drawer.open{{transform:translateY(0)}}.drawer-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}}.drawer-title{{font-family:var(--mono);font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}}.close-btn{{background:none;border:none;color:var(--muted);font-size:22px;cursor:pointer;padding:0 4px;line-height:1;transition:color .2s}}.close-btn:hover{{color:var(--fg)}}.info-grid{{display:grid;gap:1px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--line)}}.info-row{{display:grid;grid-template-columns:80px 1fr;gap:12px;background:var(--bg);padding:12px 16px;transition:background .3s}}.label{{font-family:var(--mono);font-size:11px;font-weight:700;text-transform:uppercase;color:var(--muted)}}.value{{font-family:var(--mono);font-size:13px;overflow-wrap:anywhere}}.link{{color:var(--accent);text-decoration:none}}.link:hover{{text-decoration:underline}}</style>
</head><body><main class="shell">
{attribution}
<div class="center">
<div class="logo">{brand}</div>
<div class="status"><div class="pulse-ring"><div class="pulse-dot"></div></div><span class="status-text">Operational</span></div>
<div class="curl">curl <span id="curl-url"></span> — <span id="uptime">0s</span></div>
</div>
<button class="info-btn" id="info-btn" aria-label="Info"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><circle cx="12" cy="8" r=".5" fill="currentColor"/></svg></button>
<button class="theme-btn" id="theme-btn" aria-label="Toggle theme"><svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg><svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg></button>
<div class="drawer" id="drawer">
<div class="drawer-head"><span class="drawer-title">Service Info</span><button class="close-btn" id="close-btn" aria-label="Close">&times;</button></div>
<div class="info-grid">
<div class="info-row"><span class="label">Service</span><span class="value">{t}</span></div>
<div class="info-row"><span class="label">Version</span><span class="value">{v}</span></div>
<div class="info-row"><span class="label">Runtime</span><span class="value">Rust + Python</span></div>
<div class="info-row"><span class="label">Uptime</span><span class="value" id="uptime2">0s</span></div>
{docs_row}
</div>
</div>
<div class="overlay" id="overlay"></div>
</main>
<script>
const t0=Date.now();
function fmt(ms){{const s=Math.floor(ms/1000),m=Math.floor(s/60),h=Math.floor(m/60),d=Math.floor(h/24);if(d>0)return d+"d "+h%24+"h "+m%60+"m";if(h>0)return h+"h "+m%60+"m "+s%60+"s";if(m>0)return m+"m "+s%60+"s";return s+"s"}}
document.getElementById("curl-url").textContent=location.origin;
setInterval(()=>{{const t=fmt(Date.now()-t0);document.getElementById("uptime").textContent=t;const u2=document.getElementById("uptime2");if(u2)u2.textContent=t}},1000);
(()=>{{
const dr=document.getElementById("drawer"),ov=document.getElementById("overlay");
document.getElementById("info-btn").onclick=()=>{{dr.classList.add("open");ov.classList.add("open")}};
document.getElementById("close-btn").onclick=()=>{{dr.classList.remove("open");ov.classList.remove("open")}};
ov.onclick=()=>{{dr.classList.remove("open");ov.classList.remove("open")}};
const html=document.documentElement;
const q=window.matchMedia("(prefers-color-scheme:dark)");
if(q.matches)html.classList.add("dark");
document.getElementById("theme-btn").onclick=()=>{{html.classList.toggle("dark")}};
}})();
</script></body></html>"""


def _fallback_admin_html(
    *,
    title: str,
    base_path: str,
    static_url: str,
    app_name: str,
    powered_by: str,
    version: str,
    partials: list[dict[str, str]],
) -> str:
    from html import escape

    brand = _brand_mark(app_name)
    nav_items = "".join(
        f'<a class="nav-link" href="{base_path}/partials/{escape(p["name"])}" '
        f'hx-get="{base_path}/partials/{escape(p["name"])}" '
        f'hx-target="#admin-panel" hx-swap="innerHTML" hx-push-url="true">'
        f'<span class="nav-icon">{escape(p.get("icon", ""))}</span>'
        f"<span>{escape(p['title'])}</span></a>"
        for p in partials
    )

    initial_partial = partials[0]["name"] if partials else "overview"
    initial_title = partials[0]["title"] if partials else "Overview"

    htmx_url = f"{static_url}/htmx.min.js"
    alpine_url = f"{static_url}/alpine.min.js"

    return f"""<!DOCTYPE html>
<html lang="en" x-data="{{
  panel: '{initial_partial}',
  title: '{escape(initial_title)}',
  theme: (function(){{
    try {{
      var t = localStorage.getItem('rivex-theme');
      if (t === 'dark' || t === 'light') return t;
    }} catch(e) {{}}
    return 'dark';
  }})(),
  init() {{
    this.$watch('theme', v => {{
      try {{ localStorage.setItem('rivex-theme', v); }} catch(e) {{}}
    }});
  }},
  toggleTheme() {{ this.theme = this.theme === 'dark' ? 'light' : 'dark'; }}
}}" x-init="init()" :class="theme">
<head>
<meta charset="utf-8">
<title>{escape(title)} — Admin</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="htmx-config" content='{{"includeIndicatorStyles": false}}'>
<script src="{escape(htmx_url)}" defer></script>
<script src="{escape(alpine_url)}" defer></script>
<style>
:root {{
  --bg: #fff; --fg: #000; --muted: #a1a1aa; --line: #e4e4e7; --soft: #f4f4f5;
  --accent: #f97316; --green: #22c55e; --red: #ef4444; --blue: #3b82f6;
  --mono: "SF Mono","Fira Code",Consolas,monospace;
  --sans: Inter, system-ui, -apple-system, sans-serif;
}}
.dark {{ --bg: #09090b; --fg: #fff; --muted: #71717a; --line: #27272a; --soft: #18181b;
  --green: #4ade80; --red: #f87171; }}
* {{ box-sizing: border-box; margin: 0; }}
body {{ background: var(--bg); color: var(--fg); font-family: var(--sans);
  -webkit-font-smoothing: antialiased; min-height: 100vh; transition: background .3s, color .3s; }}
a {{ color: inherit; text-decoration: none; }}
.mono {{ font-family: var(--mono); }}
.muted {{ color: var(--muted); }}

/* ── Top bar (Vexarr family) ────────────────────────────────────── */
.topbar {{ position: sticky; top: 0; z-index: 10; display: flex;
  justify-content: space-between; align-items: center; padding: 14px 24px;
  background: var(--bg); border-bottom: 1px solid var(--line); }}
.topbar-left, .topbar-right {{ display: flex; align-items: center; gap: 10px; }}
.status-pill {{ display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px;
  border: 1px solid var(--line); border-radius: 999px; font-family: var(--mono);
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .12em;
  color: var(--muted); }}
.pulse {{ position: relative; width: 8px; height: 8px; }}
.pulse::after {{ content: ""; position: absolute; inset: 1px; border-radius: 50%;
  background: var(--green); }}
.pulse::before {{ content: ""; position: absolute; inset: 0; border-radius: 50%;
  background: var(--green); animation: pulse-ring 2s ease-out infinite; opacity: 0; }}
@keyframes pulse-ring {{
  0% {{ transform: scale(1); opacity: .55; }}
  100% {{ transform: scale(2.8); opacity: 0; }}
}}
.status-pill.ok {{ color: var(--green); }}
.pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px;
  border: 1px solid var(--line); border-radius: 999px; background: var(--bg);
  color: var(--muted); font-family: var(--mono); font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .1em; cursor: pointer; transition: all .2s; }}
.pill:hover {{ color: var(--fg); border-color: var(--fg); }}
.pill svg {{ width: 13px; height: 13px; }}
.pill .icon-sun {{ display: block; }} .pill .icon-moon {{ display: none; }}
.dark .pill .icon-sun {{ display: none; }} .dark .pill .icon-moon {{ display: block; }}

/* ── Shell layout ───────────────────────────────────────────────── */
.shell {{ display: grid; grid-template-columns: 260px 1fr; min-height: calc(100vh - 56px); }}

/* ── Sidebar (Vexarr family) ───────────────────────────────────── */
.sidebar {{ border-right: 1px solid var(--line); padding: 24px 18px; display: flex;
  flex-direction: column; gap: 22px; background: var(--bg); }}
.brand {{ font-family: var(--mono); font-weight: 900; letter-spacing: -.05em; font-size: 22px; }}
.brand .accent {{ color: var(--accent); }}
.powered {{ display: flex; justify-content: flex-end; align-items: baseline; gap: 6px;
  margin-top: 8px; font-family: var(--mono); font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .14em; color: var(--muted); }}
.powered .x {{ color: var(--accent); font-size: 12px; text-shadow: 0 0 10px rgba(249,115,22,.25); }}
.nav {{ display: flex; flex-direction: column; gap: 2px; flex: 1; }}
.nav-title {{ font-family: var(--mono); font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .14em; color: var(--muted);
  padding: 0 12px; margin-bottom: 6px; }}
.nav-link {{ display: flex; align-items: center; gap: 10px; padding: 9px 12px;
  border-radius: 8px; color: var(--muted); font-size: 12px; font-weight: 600;
  cursor: pointer; transition: background .15s, color .15s; border: 1px solid transparent;
  font-family: var(--mono); text-transform: uppercase; letter-spacing: .08em; }}
.nav-link:hover {{ background: var(--soft); color: var(--fg); }}
.nav-link.htmx-request, .nav-link.active {{ background: var(--soft); color: var(--fg);
  border-color: var(--line); }}
.nav-icon {{ width: 14px; text-align: center; font-size: 12px; opacity: .7; }}
.sidebar .footer {{ font-family: var(--mono); font-size: 10px; color: var(--muted);
  text-transform: uppercase; letter-spacing: .12em; padding: 0 12px; }}

/* ── Main panel ────────────────────────────────────────────────── */
.main {{ padding: 32px 40px 60px; min-width: 0; }}
.page-head {{ display: flex; justify-content: space-between; align-items: end;
  margin-bottom: 28px; padding-bottom: 20px; border-bottom: 1px solid var(--line); }}
.page-head h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -.02em; }}
.head-actions {{ display: flex; align-items: center; gap: 12px; }}
.page-head .meta {{ font-family: var(--mono); font-size: 10px; color: var(--muted);
  text-transform: uppercase; letter-spacing: .14em; margin-top: 6px; }}

/* ── Panels (Vexarr family) ────────────────────────────────────── */
#admin-panel {{ min-height: 200px; }}
.panel {{ background: var(--bg); border: 1px solid var(--line); border-radius: 12px;
  padding: 22px 24px; margin-bottom: 18px; }}
.panel h2 {{ font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .14em; color: var(--muted); margin-bottom: 16px;
  display: flex; align-items: center; gap: 8px; }}
.panel h2::before {{ content: ""; display: inline-block; width: 4px; height: 14px;
  background: var(--accent); border-radius: 1px; }}
table.kv {{ width: 100%; border-collapse: collapse; }}
table.kv th, table.kv td {{ text-align: left; padding: 10px 0;
  border-bottom: 1px solid var(--line); font-size: 13px; vertical-align: top; }}
table.kv tr:last-child th, table.kv tr:last-child td {{ border-bottom: none; }}
table.kv th {{ width: 200px; font-weight: 600; color: var(--muted);
  font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: .1em; }}
code {{ font-family: var(--mono); font-size: 12px; background: var(--soft);
  padding: 2px 6px; border-radius: 4px; }}
pre.logs {{ font-family: var(--mono); font-size: 11px; background: var(--soft);
  padding: 16px; border-radius: 8px; max-height: 420px; overflow: auto;
  white-space: pre-wrap; line-height: 1.5; border: 1px solid var(--line); }}

/* ── Action cards ──────────────────────────────────────────────── */
.action-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px; }}
.action-card {{ border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px;
  background: var(--bg); display: flex; flex-direction: column; gap: 10px; }}
.action-card h3 {{ font-size: 13px; font-weight: 700; font-family: var(--mono);
  text-transform: uppercase; letter-spacing: .1em; }}
.action-card p {{ font-size: 12px; line-height: 1.5; color: var(--muted); }}
.btn {{ display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px;
  background: var(--fg); color: var(--bg); border: 1px solid var(--fg);
  border-radius: 8px; font-family: var(--mono); font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .1em; cursor: pointer;
  transition: opacity .15s; align-self: flex-start; }}
.btn:hover {{ opacity: .85; }}
.btn.danger {{ background: var(--red); border-color: var(--red); color: #fff; }}
#action-status:empty {{ display: none; }}
#action-status {{ margin-top: 16px; }}

/* ── Generate form ─────────────────────────────────────────────── */
.gen-form {{ display: grid; gap: 14px; max-width: 760px; }}
.gen-form label {{ display: flex; flex-direction: column; gap: 4px;
  font-size: 11px; font-weight: 700; color: var(--muted); font-family: var(--mono);
  text-transform: uppercase; letter-spacing: .12em; }}
.gen-form input, .gen-form textarea {{ font-family: var(--mono); font-size: 12px;
  background: var(--soft); color: var(--fg); border: 1px solid var(--line);
  border-radius: 8px; padding: 8px 10px; }}
.gen-form input {{ height: 34px; }}
.gen-form textarea {{ resize: vertical; min-height: 240px; line-height: 1.5; }}
.gen-form code {{ font-family: var(--mono); font-size: 11px; color: var(--muted);
  font-weight: 400; }}
.gen-form-actions {{ display: flex; gap: 8px; }}
.gen-result {{ margin-top: 18px; }}
.gen-summary {{ padding: 12px 14px; background: var(--soft);
  border: 1px solid var(--line); border-radius: 8px; margin-bottom: 12px;
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap; font-size: 13px; }}
.gen-summary form {{ display: inline-flex; }}

/* ── Action results ────────────────────────────────────────────── */
.action-result {{ padding: 12px 16px; border-radius: 8px; font-size: 13px;
  font-family: var(--mono); border: 1px solid var(--line); background: var(--soft); }}
.action-result.ok {{ border-color: var(--green); color: var(--green); }}
.action-result.err {{ border-color: var(--red); color: var(--red); }}
.action-result pre {{ background: transparent; padding: 0; margin-top: 8px;
  font-size: 11px; color: var(--fg); }}

/* ── Misc ──────────────────────────────────────────────────────── */
.htmx-indicator {{ display: none; }}
.htmx-request .htmx-indicator {{ display: inline-flex; align-items: center; }}
.spinner {{ width: 12px; height: 12px; border: 2px solid var(--muted);
  border-top-color: transparent; border-radius: 50%; animation: spin .7s linear infinite; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-left">
    <span class="status-pill ok"><span class="pulse"></span>Operational</span>
  </div>
  <div class="topbar-right">
    <span class="htmx-indicator"><span class="spinner"></span></span>
    <button class="pill" @click="toggleTheme()" :title="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'">
      <svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
      <svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
      <span x-text="theme === 'dark' ? 'Light' : 'Dark'"></span>
    </button>
    <a class="pill" href="{base_path}/logout">Sign out</a>
  </div>
</header>
<div class="shell">
  <aside class="sidebar">
    <div>
      <div class="brand">{brand}</div>
      <div class="powered"><span>powered by</span> <span class="x">RiveX</span></div>
    </div>
    <div class="nav-title">Panels</div>
    <nav class="nav">{nav_items}</nav>
    <div class="footer">v{escape(version)} · {escape(title)}</div>
  </aside>
  <main class="main">
    <header class="page-head">
      <div>
        <h1 x-text="title">{escape(initial_title)}</h1>
        <div class="meta">Panel: <span x-text="panel">{escape(initial_partial)}</span></div>
      </div>
    </header>
    <div id="admin-panel"
         hx-get="{base_path}/partials/{initial_partial}"
         hx-trigger="load"
         hx-swap="innerHTML">
      <p class="muted">Loading…</p>
    </div>
    <div id="action-status"></div>
  </main>
</div>
<script>
document.body.addEventListener('htmx:afterRequest', function (evt) {{
  if (evt.detail.pathInfo && evt.detail.pathInfo.requestPath.includes('/partials/')) {{
    var parts = evt.detail.pathInfo.requestPath.split('/');
    var name = parts[parts.length - 1];
    var titleEl = document.querySelector('.nav-link[href$="/partials/' + name + '"] span:last-child');
    if (titleEl) {{
      document.querySelector('h1').textContent = titleEl.textContent;
      var root = document.querySelector('[x-data]');
      if (root && root._x_dataStack) {{
        root._x_dataStack[0].panel = name;
        root._x_dataStack[0].title = titleEl.textContent;
      }}
    }}
    document.querySelectorAll('.nav-link').forEach(function (a) {{
      a.classList.toggle('active', a.getAttribute('href').endsWith('/' + name));
    }});
  }}
  if (evt.detail.pathInfo && evt.detail.pathInfo.requestPath.includes('/actions/')) {{
    var status = document.getElementById('action-status');
    if (status) status.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
  }}
}});
</script>
</body>
</html>"""
