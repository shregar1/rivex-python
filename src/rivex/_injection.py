from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
from collections.abc import Callable
from math import isfinite as _math_isfinite
from typing import Any, cast, get_type_hints
from urllib.parse import parse_qs

from rivex import _json

# Cache imports at module level — NOT per-request
from rivex._compat import RC_V2, get_request_header
from rivex._compat import rc as _rc
from rivex.background import BackgroundTasks
from rivex.exceptions import HTTPException, RequestValidationError
from rivex.responses import Response as OxResponse

# Prefer orjson for JSON serialization when available — up to 30x faster
# than walking PyObjects through PyO3 for large payloads.
try:
    import orjson as _orjson

    _fast_json_dumps = _orjson.dumps  # bytes output, no .encode() needed
except ImportError:
    _orjson = None  # type: ignore[assignment]
    _fast_json_dumps = None  # type: ignore[assignment]

# Import JsonBytes marker type for Rust-generated JSON responses.
from rivex.gen import JsonBytes as _JsonBytes

# ── Background task thread pool (reuse threads instead of per-request spawn) ──
_BG_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="rivex-bg")

# ── Dependency signature cache (avoid per-request inspect.signature) ──
_DEP_SIG_CACHE: dict[Callable, tuple[inspect.Signature, dict[str, Any]]] = {}

# ── Singleton-scoped dependency cache (lives for the process lifetime) ──
# Singletons don't follow the per-request ``cache`` dict — they survive
# across requests so providers annotated with ``scope="singleton"`` are
# created exactly once.
_SINGLETON_CACHE: dict[Any, Any] = {}


def _get_cached_signature(func: Callable) -> tuple[inspect.Signature, dict[str, Any]]:
    """Return (signature, type_hints) for *func*, caching the result.

    ``inspect.signature()`` and ``get_type_hints()`` are expensive
    introspection calls. Dependency providers never change at runtime,
    so we cache the result per callable to avoid re-introspecting on
    every request.
    """
    cached = _DEP_SIG_CACHE.get(func)
    if cached is not None:
        return cached
    sig = inspect.signature(func, follow_wrapped=True)
    try:
        hints = get_type_hints(func, include_extras=True)
    except Exception:
        hints = {}
    _DEP_SIG_CACHE[func] = (sig, hints)
    return sig, hints


def _build_codegen_wrapper(
    *,
    func: Callable,
    path: str,
    default_status: int,
    debug: bool,
    exception_handlers: dict[type, Callable] | None,
    response_model: Any,
    params_info: list[tuple[str, str, Any, Any]],
    is_async: bool,
) -> Callable:
    """Compile a wrapper specialised to ``func``'s signature.

    For each parameter in ``params_info`` we emit straight-line extraction
    code into a generated ``async def _wrapper`` source. The compiled
    function captures ``func``, the hint/default tables, and helper
    references in its globals dict — so every reference inside the
    request loop becomes a plain local or global lookup, not a list
    iteration + chained ``isinstance`` check.

    The fallback generic wrapper in ``build_handler_wrapper`` does the
    same work but discovers the shape per request. On a 3-param handler
    that's ~12 dict/condition operations per request before the handler
    body even runs. This codegen cuts that to one direct extraction per
    param.
    """
    from rivex._bodies import coerce_body as _coerce_body
    from rivex.requests import Request

    needs_path = any(s == "path" for s, *_ in params_info)
    needs_query = any(s == "query" for s, *_ in params_info)
    needs_body = any(s in ("body", "body_raw") for s, *_ in params_info)
    has_handlers = bool(exception_handlers)

    lines: list[str] = []
    lines.append("async def _wrapper(request_data):")
    lines.append("    try:")
    if needs_path:
        lines.append("        _path_params = request_data.get('path_params') or {}")
    if needs_body:
        lines.append("        _body = request_data.get('body', b'')")
    if needs_query:
        # Prefer pre-parsed query_params from Rust (avoids Python parse_qs)
        lines.append("        _qp = request_data.get('query_params')")
        lines.append("        if _qp is None:")
        lines.append("            _qs = request_data.get('query_string', '')")
        lines.append("            _qp = _parse_qs(_qs, keep_blank_values=True) if _qs else {}")

    call_parts: list[str] = []
    for i, (source_type, name, _hint, default) in enumerate(params_info):
        var = f"_kw{i}"
        has_default = default is not inspect.Parameter.empty

        if source_type == "request":
            lines.append(f"        {var} = _Request._from_raw(request_data)")
        elif source_type == "path":
            lines.append(f"        _raw = _path_params.get({name!r})")
            lines.append("        if _raw is not None:")
            lines.append(f"            {var} = _coerce(_raw, _hints[{i}])")
            if has_default:
                lines.append("        else:")
                lines.append(f"            {var} = _defaults[{i}]")
            else:
                lines.append("        else:")
                lines.append(
                    f"            raise _HTTPException(422, "
                    f"detail='Missing required path parameter: {name}')"
                )
        elif source_type == "query":
            lines.append(f"        _vals = _qp.get({name!r})")
            lines.append("        if _vals:")
            lines.append(f"            {var} = _coerce(_vals[0], _hints[{i}])")
            if has_default:
                lines.append("        else:")
                lines.append(f"            {var} = _defaults[{i}]")
            else:
                lines.append("        else:")
                lines.append(
                    f"            raise _HTTPException(422, "
                    f"detail='Missing required query parameter: {name}')"
                )
        elif source_type == "body":
            # Dispatch to :func:`rivex._bodies.coerce_body` so every
            # supported backend (Pydantic, Schemax, Marshmallow, plain
            # ``dict``) goes through the same code path.  No Pydantic
            # shortcut here — a Schemax ``Message`` or Marshmallow
            # ``Schema`` is a first-class body type, not a fallback.
            lines.append("        if _body:")
            lines.append(f"            _h = _hints[{i}]")
            lines.append("            try:")
            lines.append(f"                {var} = _coerce_body(_body, _h)")
            lines.append("            except _HTTPException:")
            lines.append("                raise")
            lines.append("            except Exception as _ve:")
            lines.append(
                "                raise _RequestValidationError("
                "[{'loc': ('body',), 'msg': str(_ve), 'type': 'value_error'}])"
            )
            if has_default:
                lines.append("        else:")
                lines.append(f"            {var} = _defaults[{i}]")
            else:
                lines.append("        else:")
                lines.append(
                    "            raise _HTTPException(422, detail='Missing required request body')"
                )
        elif source_type == "body_raw":
            # Body() marker OR a bare ``payload: dict`` annotation. For the
            # former ``_defaults[i]`` is a :class:`Body` instance whose
            # ``.default`` holds the user's fallback for empty bodies; for
            # the latter ``_defaults[i]`` is ``inspect.Parameter.empty`` or
            # the function's own default literal.
            lines.append("        if _body:")
            lines.append(f"            {var} = _json_loads(_body)")
            lines.append("        else:")
            lines.append(f"            _d = _defaults[{i}]")
            lines.append("            _bd = getattr(_d, 'default', _d)")
            lines.append(
                "            if _bd is Ellipsis or _bd is _inspect_empty:"
            )
            lines.append(
                f"                raise _HTTPException(422, "
                f"detail='Missing required body parameter: {name}')"
            )
            lines.append("            else:")
            lines.append(f"                {var} = _bd")
        else:  # pragma: no cover — gated by _CODEGEN_SOURCES check
            raise ValueError(f"codegen does not support source type: {source_type}")
        call_parts.append(f"{name}={var}")

    call_kwargs = ", ".join(call_parts)
    await_kw = "await " if is_async else ""
    lines.append(f"        _result = {await_kw}_func({call_kwargs})")
    if response_model is not None:
        lines.append("        _result = _apply_response_model(_result, _response_model)")
    lines.append(f"        return _normalize_response_fast(_result, {default_status})")

    lines.append("    except _HTTPException as exc:")
    if has_handlers:
        lines.append("        _h = _find_best_handler(_exc_handlers, exc)")
        lines.append("        if _h is not None:")
        lines.append("            _req = _Request._from_raw(request_data)")
        lines.append("            _r = await _call_handler(_h, _req, exc)")
        lines.append("            return _normalize_response_fast(_r, exc.status_code)")
    lines.append("        return _http_exception_response(exc)")

    lines.append("    except Exception as exc:")
    if has_handlers:
        lines.append("        _h = _find_best_handler(_exc_handlers, exc)")
        lines.append("        if _h is not None:")
        lines.append("            _req = _Request._from_raw(request_data)")
        lines.append("            _r = await _call_handler(_h, _req, exc)")
        lines.append("            return _normalize_response_fast(_r, 500)")
    if debug:
        lines.append("        return _error_response(500, str(exc))")
    else:
        lines.append("        return _error_response(500, 'Internal Server Error')")

    source = "\n".join(lines)
    # The filename appears in stack traces so the user knows generated code
    # came from this route, not a typo in their own source.
    fname = f"<rivex generated handler for {path or func.__name__}>"
    namespace: dict[str, Any] = {
        "_func": func,
        "_hints": [info[2] for info in params_info],
        "_defaults": [info[3] for info in params_info],
        "_Request": Request,
        "_HTTPException": HTTPException,
        "_RequestValidationError": RequestValidationError,
        "_coerce": _coerce,
        "_coerce_body": _coerce_body,
        "_json_loads": _json.loads,
        "_parse_qs": parse_qs,
        "_normalize_response_fast": _normalize_response_fast,
        "_http_exception_response": _http_exception_response,
        "_error_response": _error_response,
        "_apply_response_model": _apply_response_model,
        "_response_model": response_model,
        "_exc_handlers": exception_handlers,
        "_find_best_handler": _find_best_handler,
        "_call_handler": _call_handler,
        "_inspect_empty": inspect.Parameter.empty,
    }
    code = compile(source, fname, "exec")
    exec(code, namespace)  # noqa: S102 — intentional codegen, deterministic from sig
    wrapper: Callable[..., Any] = namespace["_wrapper"]
    wrapper._rivex_codegen_source = source  # type: ignore[attr-defined]
    return wrapper


# ---------------------------------------------------------------------------
# Per-source-type extraction strategies
# ---------------------------------------------------------------------------
# Each function below reads a single handler parameter from the
# request envelope.  They share a ``Ctx`` namespace built once per
# request (path_params, query_params, body, etc.) so the dispatch
# table at the bottom of the file is the only place we ever branch on
# the parameter's source kind.  Adding a new source = one function
# + one entry in ``_SOURCE_STRATEGIES``.


async def _extract_depends(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    return await _resolve_depends(
        default,
        ctx.request_data,
        ctx.dep_cache,
        ctx.yield_cleanups,
        ctx.dependency_overrides,
    )


def _extract_path(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex.exceptions import RequestValidationError

    raw = ctx.path_params.get(name)
    if raw is not None:
        return _coerce(raw, hint)
    if default is not inspect.Parameter.empty:
        return default
    raise RequestValidationError(
        [{"loc": ("path", name), "msg": "Field required", "type": "missing"}]
    )


def _extract_path_param(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex.exceptions import RequestValidationError

    raw = ctx.path_params.get(default.alias or name)
    if raw is not None:
        val = _coerce(raw, hint)
        try:
            default.validate(val, name)
        except ValueError as e:
            raise RequestValidationError(
                [{"loc": ("path", name), "msg": str(e), "type": "value_error"}]
            ) from e
        return val
    if not default.required:
        return default.default
    raise RequestValidationError(
        [{"loc": ("path", name), "msg": "Field required", "type": "missing"}]
    )


def _extract_query(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex.exceptions import RequestValidationError

    values = ctx.query_params.get(name) if ctx.query_params else None
    if values:
        return _coerce(values[0], hint)
    if default is not inspect.Parameter.empty:
        return default
    raise RequestValidationError(
        [{"loc": ("query", name), "msg": "Field required", "type": "missing"}]
    )


def _extract_query_param(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex.exceptions import RequestValidationError

    field_name = default.alias or name
    values = ctx.query_params.get(field_name) if ctx.query_params else None
    if values:
        # Coerce *before* running param-level constraints — ``_coerce``
        # peels off ``X | None`` so ``int | None = Query(ge=1)`` hits the
        # numeric branch instead of comparing a raw string to a number.
        try:
            val = _coerce(values[0], hint)
        except (ValueError, TypeError) as e:
            raise RequestValidationError(
                [{"loc": ("query", name), "msg": str(e), "type": "type_error"}]
            ) from e
        try:
            default.validate(val, name)
        except ValueError as e:
            raise RequestValidationError(
                [{"loc": ("query", name), "msg": str(e), "type": "value_error"}]
            ) from e
        return val
    if not default.required:
        return default.default
    raise RequestValidationError(
        [{"loc": ("query", name), "msg": "Field required", "type": "missing"}]
    )


def _extract_header_param(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex.exceptions import RequestValidationError

    header_key = default.header_name(name)
    val = ctx.header_dict.get(header_key) if ctx.header_dict else None
    if val is not None:
        val = _coerce(val, hint)
        try:
            default.validate(val, name)
        except ValueError as e:
            raise RequestValidationError(
                [{"loc": ("header", name), "msg": str(e), "type": "value_error"}]
            ) from e
        return val
    if not default.required:
        return default.default
    raise RequestValidationError(
        [{"loc": ("header", name), "msg": "Field required", "type": "missing"}]
    )


def _extract_cookie_param(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex.exceptions import RequestValidationError

    cookie_name = default.alias or name
    val = ctx.cookie_dict.get(cookie_name) if ctx.cookie_dict else None
    if val is not None:
        val = _coerce(val, hint)
        try:
            default.validate(val, name)
        except ValueError as e:
            raise RequestValidationError(
                [{"loc": ("cookie", name), "msg": str(e), "type": "value_error"}]
            ) from e
        return val
    if not default.required:
        return default.default
    raise RequestValidationError(
        [{"loc": ("cookie", name), "msg": "Field required", "type": "missing"}]
    )


def _extract_body_param(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    import json as _json

    from rivex._bodies import coerce_body, is_body_model
    from rivex.exceptions import RequestValidationError

    if not ctx.body:
        if not default.required:
            return default.default
        return default.default  # not present; the default applies

    # When the hint is a body model (Pydantic, schemax, dataclass, …) and the
    # field is not ``embed``ed, the user wants a validated DTO instance, not
    # the raw dict. The numeric/string param-level constraints on ``Body()``
    # don't apply to a class instance anyway.
    if not default.embed and is_body_model(hint) and hint not in (dict, bytes, str):
        try:
            return coerce_body(ctx.body, hint)
        except RequestValidationError:
            raise
        except Exception as e:
            raise RequestValidationError(
                [{"loc": ("body",), "msg": str(e), "type": "value_error"}]
            ) from e

    parsed = _json.loads(ctx.body)
    val = parsed.get(name) if default.embed else parsed

    # ``embed=True`` with a body-model hint: coerce the sub-payload to the
    # DTO. Otherwise keep the raw value and run primitive constraints.
    if default.embed and val is not None and is_body_model(hint) and hint not in (dict, bytes, str):
        try:
            return coerce_body(val, hint) if isinstance(val, (dict, list)) else val
        except RequestValidationError:
            raise
        except Exception as e:
            raise RequestValidationError(
                [{"loc": ("body", name), "msg": str(e), "type": "value_error"}]
            ) from e

    if val is not None:
        try:
            default.validate(val, name)
        except ValueError as e:
            raise RequestValidationError(
                [{"loc": ("body", name), "msg": str(e), "type": "value_error"}]
            ) from e
        return val
    if not default.required:
        return default.default
    return default.default


def _extract_body_raw(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    import json as _json

    if ctx.body:
        return _json.loads(ctx.body)
    # ``default`` may be a :class:`Body` instance (whose ``.default``
    # holds the empty-body fallback) or — for a bare ``payload: dict``
    # annotation — ``inspect.Parameter.empty`` or a literal Python default.
    fallback = getattr(default, "default", default)
    if fallback is not ... and fallback is not inspect.Parameter.empty:
        return fallback
    raise HTTPException(422, detail=f"Missing required body parameter: {name}")


def _extract_body(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex._bodies import coerce_body
    from rivex.exceptions import RequestValidationError

    if ctx.body:
        try:
            return coerce_body(ctx.body, hint)
        except Exception as e:
            raise RequestValidationError(
                [{"loc": ("body", name), "msg": str(e), "type": "value_error"}]
            ) from e
    if default is not inspect.Parameter.empty:
        return default
    raise RequestValidationError([{"loc": ("body",), "msg": "Field required", "type": "missing"}])


async def _extract_request(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex.requests import Request

    return Request._from_raw(ctx.request_data)


async def _extract_background_tasks(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    return BackgroundTasks()


def _extract_file(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex.exceptions import RequestValidationError
    from rivex.uploads import File

    if ctx.multipart_fields and name in ctx.multipart_fields:
        return ctx.multipart_fields[name][0]
    if isinstance(default, File) and default.default is not ...:
        return default.default
    raise RequestValidationError(
        [{"loc": ("body", name), "msg": "Field required", "type": "missing"}]
    )


def _extract_form(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex.uploads import Form

    if ctx.multipart_fields and name in ctx.multipart_fields:
        val = ctx.multipart_fields[name][0]
        return _coerce(val, hint) if isinstance(val, str) else val
    if ctx.content_type and "application/x-www-form-urlencoded" in ctx.content_type:
        form_params = parse_qs(
            ctx.body.decode("utf-8", errors="replace"),
            keep_blank_values=True,
        )
        if name in form_params:
            return _coerce(form_params[name][0], hint)
        if isinstance(default, Form) and default.default is not ...:
            return default.default
    if isinstance(default, Form) and default.default is not ...:
        return default.default
    return None  # form fields are inherently optional


def _extract_form_model(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    from rivex._bodies import coerce_form_data
    from rivex.exceptions import RequestValidationError

    form_data: dict[str, Any] = {}
    if ctx.multipart_fields:
        for fk, fv in ctx.multipart_fields.items():
            form_data[fk] = fv[0] if len(fv) == 1 else fv
    elif ctx.content_type and "application/x-www-form-urlencoded" in ctx.content_type:
        parsed_form = parse_qs(
            ctx.body.decode("utf-8", errors="replace"),
            keep_blank_values=True,
        )
        for fk, fv in parsed_form.items():
            form_data[fk] = fv[0] if len(fv) == 1 else fv
    elif ctx.body:
        parsed_form = parse_qs(
            ctx.body.decode("utf-8", errors="replace"),
            keep_blank_values=True,
        )
        for fk, fv in parsed_form.items():
            form_data[fk] = fv[0] if len(fv) == 1 else fv
    if form_data:
        try:
            return coerce_form_data(form_data, hint)
        except Exception as e:
            raise RequestValidationError(
                [{"loc": ("body", name), "msg": str(e), "type": "value_error"}]
            ) from e
    if not default.required:
        return default.default
    raise RequestValidationError(
        [{"loc": ("body", name), "msg": "Field required", "type": "missing"}]
    )


# Per-source-type dispatch table — the ONLY place we branch on
# ``source`` for parameter extraction.  Each strategy is an async
# function so the lookup is uniform even when the underlying source
# is sync (we just ``await`` the result, which is a no-op for non-
# coroutine return values when the coroutine has already been awaited).
_SOURCE_STRATEGIES: dict[str, Callable[..., Any]] = {
    "depends": _extract_depends,
    "path": _extract_path,
    "path_param": _extract_path_param,
    "query": _extract_query,
    "query_param": _extract_query_param,
    "header_param": _extract_header_param,
    "cookie_param": _extract_cookie_param,
    "body_param": _extract_body_param,
    "body_raw": _extract_body_raw,
    "body": _extract_body,
    "request": _extract_request,
    "background_tasks": _extract_background_tasks,
    "file": _extract_file,
    "form": _extract_form,
    "form_model": _extract_form_model,
}


def build_handler_wrapper(
    func: Callable,
    path: str,
    default_status: int,
    debug: bool,
    exception_handlers: dict[type, Callable] | None = None,
    response_model: Any = None,
    dependency_overrides: dict[Callable, Callable] | None = None,
    *,
    response_model_include: set[str] | None = None,
    response_model_exclude: set[str] | None = None,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    validate_response: bool = False,
) -> Callable:
    from rivex.caching import _CachedWrapper
    from rivex.dependencies import Depends
    from rivex.params import Body, Cookie, Header, Path, Query
    from rivex.uploads import File, Form, UploadFile

    # ``CompiledGen`` lives in the Rust core (not always present in
    # test envs). Import it lazily at the call site.
    _CompiledGen = None  # type: ignore[assignment]

    if isinstance(func, _CachedWrapper):

        async def cached_wrapper(request_data: dict | None = None) -> dict:
            try:
                return cast(dict, await func())
            except HTTPException as exc:
                return _http_exception_response(exc)
            except Exception as exc:
                detail = str(exc) if debug else "Internal Server Error"
                return _error_response(500, detail)

        cached_wrapper._rivex_skip_request = True  # type: ignore[attr-defined]
        return cached_wrapper

    if _CompiledGen is not None and isinstance(func, _CompiledGen):
        _gen = func

        async def gen_wrapper(request_data: dict | None = None) -> dict:
            return _gen.generate_response()

        gen_wrapper._rivex_skip_request = True  # type: ignore[attr-defined]
        return gen_wrapper

    path_param_names: set[str] = set()
    for segment in path.split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            inner = segment[1:-1]
            # Support {name:type} syntax — extract just the name
            if ":" in inner:
                inner = inner.split(":", 1)[0]
            path_param_names.add(inner)
    sig = inspect.signature(func, follow_wrapped=True)

    try:
        hints = get_type_hints(func, include_extras=True)
    except Exception:
        hints = {}

    is_async = asyncio.iscoroutinefunction(func)

    # Build model_dump kwargs for response model filtering
    _dump_kwargs: dict[str, Any] = {}
    if response_model_include:
        _dump_kwargs["include"] = response_model_include
    if response_model_exclude:
        _dump_kwargs["exclude"] = response_model_exclude
    if response_model_exclude_unset:
        _dump_kwargs["exclude_unset"] = True
    if response_model_exclude_defaults:
        _dump_kwargs["exclude_defaults"] = True
    if response_model_exclude_none:
        _dump_kwargs["exclude_none"] = True

    params_info: list[tuple[str, str, Any, Any]] = []
    for name, param in sig.parameters.items():
        hint = hints.get(name, str)

        if isinstance(param.default, Depends):
            params_info.append(("depends", name, hint, param.default))
        elif isinstance(param.default, File):
            params_info.append(("file", name, hint, param.default))
        elif isinstance(param.default, Form):
            if _is_strict_body_model(hint):
                params_info.append(("form_model", name, hint, param.default))
            else:
                params_info.append(("form", name, hint, param.default))
        elif isinstance(param.default, Path):
            params_info.append(("path_param", name, hint, param.default))
        elif isinstance(param.default, Query):
            params_info.append(("query_param", name, hint, param.default))
        elif isinstance(param.default, Header):
            params_info.append(("header_param", name, hint, param.default))
        elif isinstance(param.default, Cookie):
            params_info.append(("cookie_param", name, hint, param.default))
        elif isinstance(param.default, Body):
            if _is_body_model(hint) or param.default.embed:
                params_info.append(("body_param", name, hint, param.default))
            else:
                params_info.append(("body_raw", name, hint, param.default))
        elif name in path_param_names:
            params_info.append(("path", name, hint, param.default))
        elif _is_request_type(hint):
            params_info.append(("request", name, hint, param.default))
        elif _is_background_tasks_type(hint):
            params_info.append(("background_tasks", name, hint, param.default))
        elif hint is UploadFile or (isinstance(hint, type) and issubclass(hint, UploadFile)):
            params_info.append(("file", name, hint, File()))
        elif _is_body_model(hint):
            params_info.append(("body", name, hint, param.default))
        elif hint is dict or hint is bytes:
            # Untagged ``dict`` / ``bytes`` annotation is almost always
            # a request body (the JSON object as a whole) rather than
            # a query parameter.  Route it through the raw-body path
            # so handlers like ``async def handler(item: dict)`` work.
            params_info.append(("body_raw", name, hint, param.default))
        else:
            # Untagged scalar parameters default to query string lookup.
            params_info.append(("query", name, hint, param.default))

    # ── FAST PATH: no parameters at all → skip request extraction ──
    if not params_info and not exception_handlers:

        async def direct_wrapper(request_data: dict | None = None) -> dict:
            try:
                if is_async:
                    result = await func()
                else:
                    result = func()
                result = _apply_response_model(
                    result, response_model, _dump_kwargs, validate_response
                )
                return _normalize_response_fast(result, default_status)
            except HTTPException as exc:
                return _http_exception_response(exc)
            except Exception as exc:
                detail = str(exc) if debug else "Internal Server Error"
                return _error_response(500, detail)

        direct_wrapper._rivex_skip_request = True  # type: ignore[attr-defined]
        return direct_wrapper

    _CODEGEN_SOURCES = ("request", "path", "query", "body", "body_raw")
    if all(s in _CODEGEN_SOURCES for s, *_ in params_info):
        return _build_codegen_wrapper(
            func=func,
            path=path,
            default_status=default_status,
            debug=debug,
            exception_handlers=exception_handlers,
            response_model=response_model,
            params_info=params_info,
            is_async=is_async,
        )

    # ── STANDARD PATH: full parameter extraction ──
    has_multipart = any(s in ("file", "form", "form_model") for s, *_ in params_info)
    has_query = any(s in ("query", "query_param") for s, *_ in params_info)
    has_header = any(s == "header_param" for s, *_ in params_info)
    has_cookie = any(s == "cookie_param" for s, *_ in params_info)

    async def wrapper(request_data: dict) -> dict:
        bg_tasks = None
        yield_cleanups: list[Any] = []

        try:
            kwargs: dict[str, Any] = {}
            path_params = request_data.get("path_params", {})
            body = request_data.get("body", b"")

            query_params = None
            if has_query:
                query_string = request_data.get("query_string", "")
                if query_string:
                    query_params = parse_qs(query_string, keep_blank_values=True)
                else:
                    query_params = {}

            header_dict = None
            if has_header:
                header_dict = {}
                for k, v in request_data.get("headers", []):
                    header_dict[k.lower()] = v

            cookie_dict = None
            if has_cookie:
                cookie_dict = _parse_cookies(request_data)

            dep_cache: dict[Any, Any] = {}
            multipart_fields: dict[str, list[Any]] | None = None

            if has_multipart:
                content_type = _get_content_type(request_data)
                if content_type and "multipart/form-data" in content_type:
                    from rivex.uploads import parse_multipart

                    multipart_fields = parse_multipart(body, content_type)
            else:
                content_type = None

            # Build the per-request extraction context once and let
            # each source-type strategy consume only the slice of the
            # request it needs.  ``Ctx`` is a tiny namespace — the
            # dispatch table maps ``source`` name → strategy function.
            from types import SimpleNamespace

            Ctx = SimpleNamespace
            ctx = Ctx(
                path_params=path_params,
                query_params=query_params,
                header_dict=header_dict,
                cookie_dict=cookie_dict,
                body=body,
                content_type=content_type,
                multipart_fields=multipart_fields,
                request_data=request_data,
                dep_cache=dep_cache,
                yield_cleanups=yield_cleanups,
                dependency_overrides=dependency_overrides,
            )

            for source, name, hint, default in params_info:
                strategy = _SOURCE_STRATEGIES.get(source)
                if strategy is None:
                    raise RuntimeError(f"no source strategy for {source!r}")
                value = strategy(ctx, name, hint, default)
                if inspect.isawaitable(value):
                    value = await value
                kwargs[name] = value

            # The dispatch-table strategy for ``background_tasks``
            # returns a fresh :class:`BackgroundTasks` instance into
            # ``kwargs``; mirror it on the local ``bg_tasks`` so the
            # post-response runner can fire its tasks in a daemon
            # thread.  Without this, the strategy is purely a
            # per-request scratch object and ``bg_tasks._run_all``
            # is never invoked.
            if bg_tasks is None:
                for source, name, _hint, _default in params_info:
                    if source == "background_tasks":
                        bg_tasks = kwargs.get(name)
                        break

            if is_async:
                result = await func(**kwargs)
            else:
                result = func(**kwargs)

            result = _apply_response_model(result, response_model, _dump_kwargs, validate_response)
            response = _normalize_response_fast(result, default_status)

            if bg_tasks and bg_tasks._tasks:
                import threading

                threading.Thread(target=bg_tasks._run_all, daemon=True).start()

            return response

        except HTTPException as exc:
            if exception_handlers:
                handler_func = _find_best_handler(exception_handlers, exc)
                if handler_func:
                    from rivex.requests import Request

                    request = Request._from_raw(request_data)
                    result = await _call_handler(handler_func, request, exc)
                    if (
                        isinstance(result, dict)
                        and "status" in result
                        and ("body" in result or "headers" in result)
                    ):
                        return result
                    return _normalize_response_fast(result, exc.status_code)
            return _http_exception_response(exc)
        except Exception as exc:
            if exception_handlers:
                handler_func = _find_best_handler(exception_handlers, exc)
                if handler_func:
                    from rivex.requests import Request

                    request = Request._from_raw(request_data)
                    result = await _call_handler(handler_func, request, exc)
                    if (
                        isinstance(result, dict)
                        and "status" in result
                        and ("body" in result or "headers" in result)
                    ):
                        return result
                    return _normalize_response_fast(result, 500)
            detail = str(exc) if debug else "Internal Server Error"
            return _error_response(500, detail)
        finally:
            for cleanup in reversed(yield_cleanups):
                try:
                    if inspect.isasyncgen(cleanup):
                        await cleanup.__anext__()
                    elif inspect.isgenerator(cleanup):
                        next(cleanup, None)
                except StopIteration:
                    pass
                except StopAsyncIteration:
                    pass
                except Exception:
                    pass

    return wrapper


# ── Pre-built response helpers (avoid per-request dict/list creation) ──

_JSON_CT = ("content-type", "application/json")
_TEXT_CT = ("content-type", "text/plain; charset=utf-8")
_OCTET_CT = ("content-type", "application/octet-stream")


def _http_exception_response(exc: HTTPException) -> dict:
    from rivex._compat import json_error_response

    resp = json_error_response(exc.status_code, exc.detail)
    if exc.headers:
        resp["headers"].extend(exc.headers.items())
    return resp


def _error_response(status: int, detail: str) -> dict:
    from rivex._compat import json_error_response

    return json_error_response(status, detail)


def _normalize_response_fast(result: Any, status_code: int) -> dict:
    """Optimized response normalization.

    For dict/list results: passes the raw object as body_json so the Rust
    side can serialize with serde_json (faster than Python json.dumps).
    Falls back to Python serialization when serde can't handle the type.
    """
    if isinstance(result, OxResponse):
        return result._to_raw()

    if isinstance(result, tuple):
        if len(result) == 2:
            sc, body = result
            return _normalize_response_fast(body, sc)
        if len(result) == 3:
            sc, body, extra = result
            resp = _normalize_response_fast(body, sc)
            if isinstance(extra, dict):
                resp["headers"] = resp.get("headers", []) + list(extra.items())
            return resp

    if result is None:
        return {"status": 204, "headers": [], "body": b""}

    if isinstance(result, str):
        return {
            "status": status_code,
            "headers": [_TEXT_CT],
            "body": result.encode("utf-8"),
        }

    if isinstance(result, _JsonBytes):
        return {
            "status": status_code,
            "headers": [_JSON_CT],
            "body": result,
        }

    if isinstance(result, bytes):
        return {
            "status": status_code,
            "headers": [_OCTET_CT],
            "body": result,
        }

    try:
        from pydantic import BaseModel

        if isinstance(result, BaseModel):
            return {
                "status": status_code,
                "headers": [_JSON_CT],
                "body": result.model_dump_json().encode("utf-8"),
            }
    except ImportError:
        pass

    if hasattr(result, "model_dump_json"):
        return {
            "status": status_code,
            "headers": [_JSON_CT],
            "body": result.model_dump_json().encode("utf-8"),
        }

    # A raw low-level response dict (e.g. returned by a custom exception handler
    # or middleware) carries an explicit body/headers envelope — pass it through
    # unchanged instead of serializing the whole envelope as a JSON body.
    if isinstance(result, dict) and ("body" in result or "body_json" in result):
        result.setdefault("status", status_code)
        result.setdefault("headers", [])
        return result

    # For dict/list: pass raw object to Rust for serde_json serialization
    if isinstance(result, (dict, list)):
        return {
            "status": status_code,
            "headers": [_JSON_CT],
            "body_json": result,  # Rust will serialize this with serde_json
        }

    # Fallback: Python serialization
    try:
        import json

        body = json.dumps(result).encode("utf-8")
        return {
            "status": status_code,
            "headers": [_JSON_CT],
            "body": body,
        }
    except (TypeError, ValueError):
        return _error_response(500, "Could not serialize response")


def _normalize_response(result: Any, status_code: int) -> dict:
    response = _normalize_response_fast(result, status_code)
    if "body_json" in response and "body" not in response:
        import json

        response = dict(response)
        response["body"] = json.dumps(response.pop("body_json")).encode("utf-8")
    return response


def _apply_response_model(
    result: Any,
    response_model: Any,
    dump_kwargs: dict[str, Any] | None = None,
    validate_response: bool = False,
) -> Any:
    if response_model is None or isinstance(result, OxResponse):
        return result

    status_code = None
    headers = None
    if isinstance(result, tuple):
        if len(result) == 2:
            status_code, result = result
        elif len(result) == 3:
            status_code, result, headers = result

    try:
        from pydantic import BaseModel

        if isinstance(response_model, type) and issubclass(response_model, BaseModel):
            if validate_response and isinstance(result, dict):
                model_fields = set(response_model.model_fields.keys())
                result_fields = set(result.keys())
                extra = result_fields - model_fields
                if extra:
                    import logging

                    logging.getLogger("rivex.validation").warning(
                        f"Response contains fields not in model {response_model.__name__}: {extra}"
                    )
            if isinstance(result, response_model):
                modeled = result
            else:
                modeled = response_model.model_validate(result)
            if dump_kwargs:
                result = modeled.model_dump(**dump_kwargs)
            else:
                result = modeled
    except (ImportError, TypeError):
        pass

    if status_code is not None and headers is not None:
        return status_code, result, headers
    if status_code is not None:
        return status_code, result
    return result


async def _resolve_depends(
    dep: Any,
    request_data: dict,
    cache: dict[Any, Any],
    yield_cleanups: list[Any] | None = None,
    dependency_overrides: dict[Callable, Callable] | None = None,
) -> Any:
    from rivex.dependencies import Depends

    provider = dep.dependency
    if dependency_overrides and provider in dependency_overrides:
        provider = dependency_overrides[provider]

    scope = getattr(dep, "scope", "request")

    if scope == "singleton" and provider in _SINGLETON_CACHE:
        return _SINGLETON_CACHE[provider]
    if scope == "request" and dep.use_cache and provider in cache:
        return cache[provider]

    func = _dependency_callable(provider)

    sig = inspect.signature(func, follow_wrapped=True)
    try:
        hints = get_type_hints(func, include_extras=True)
    except Exception:
        hints = {}

    dep_kwargs: dict[str, Any] = {}
    path_params = request_data.get("path_params", {})
    query_params: dict[str, list[str]] | None = None

    for pname, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        phint = hints.get(pname, str)
        if isinstance(param.default, Depends):
            dep_kwargs[pname] = await _resolve_depends(
                param.default,
                request_data,
                cache,
                yield_cleanups,
                dependency_overrides,
            )
        elif _is_request_type(phint):
            from rivex.requests import Request

            dep_kwargs[pname] = Request._from_raw(request_data)
        elif pname in path_params:
            dep_kwargs[pname] = _coerce(path_params[pname], phint)
        elif _is_body_model(phint):
            body = request_data.get("body", b"")
            if body:
                if hasattr(phint, "model_validate_json"):
                    dep_kwargs[pname] = phint.model_validate_json(body)
                else:
                    import json

                    dep_kwargs[pname] = json.loads(body)
            elif param.default is not inspect.Parameter.empty:
                dep_kwargs[pname] = param.default
        else:
            if query_params is None:
                query_string = request_data.get("query_string", "")
                query_params = parse_qs(query_string, keep_blank_values=True)

            values = query_params.get(pname)
            if values:
                dep_kwargs[pname] = _coerce(values[0], phint)
            elif param.default is not inspect.Parameter.empty:
                dep_kwargs[pname] = param.default
            else:
                raise HTTPException(422, detail=f"Missing required dependency parameter: {pname}")

    result = func(**dep_kwargs)

    if inspect.isasyncgen(result):
        value = await result.__anext__()
        if yield_cleanups is not None:
            yield_cleanups.append(result)
        result = value
    elif inspect.isgenerator(result):
        value = next(result)
        if yield_cleanups is not None:
            yield_cleanups.append(result)
        result = value
    elif inspect.isawaitable(result):
        result = await result

    if scope == "singleton":
        _SINGLETON_CACHE[provider] = result
    elif scope == "request" and dep.use_cache:
        cache[provider] = result

    return result


def _dependency_callable(provider: Any) -> Callable:
    if inspect.isclass(provider):
        provider = provider()

    resolver: Callable[..., Any] | None = getattr(provider, "resolve", None)
    if callable(resolver):
        return resolver

    if not inspect.isfunction(provider) and not inspect.ismethod(provider):
        if callable(provider):
            call: Callable[..., Any] = provider.__call__
            return call

    if callable(provider):
        func: Callable[..., Any] = provider
        return func

    raise TypeError("Depends() dependency must be callable or define resolve()")


def _find_best_handler(handlers: dict[type, Callable], exc: Exception) -> Callable | None:
    """Find the most specific (most derived) exception handler for ``exc``."""
    best_cls: type | None = None
    best_func: Callable | None = None
    for exc_class, handler_func in handlers.items():
        if isinstance(exc, exc_class):
            if best_cls is None or issubclass(exc_class, best_cls):
                best_cls = exc_class
                best_func = handler_func
    return best_func


async def _call_handler(handler_func: Callable, request: Any, exc: Exception) -> Any:
    if asyncio.iscoroutinefunction(handler_func):
        return await handler_func(request, exc)
    return handler_func(request, exc)


def _is_request_type(hint: Any) -> bool:
    try:
        from rivex.requests import Request

        return hint is Request or (isinstance(hint, type) and issubclass(hint, Request))
    except (TypeError, ImportError):
        return False


def _is_background_tasks_type(hint: Any) -> bool:
    try:
        from rivex.background import BackgroundTasks

        return hint is BackgroundTasks or (
            isinstance(hint, type) and issubclass(hint, BackgroundTasks)
        )
    except (TypeError, ImportError):
        return False


def _is_strict_body_model(hint: Any) -> bool:
    """Return ``True`` only for *class* types that the body-coercion
    layer validates (Pydantic ``BaseModel``, Schemax ``Message``,
    Marshmallow ``Schema``, Rivex ``Schema``).

    Unlike :func:`_is_body_model`, this never returns ``True`` for
    the primitive types ``dict``/``bytes``/``str`` — those have their
    own dedicated branches in the parameter classifier (form fields,
    raw body, query strings).  The "strict" variant is what we use to
    distinguish a form *field* (a single value) from a form *model*
    (the entire form bound to a Pydantic class).
    """
    if hint is dict or hint is bytes or hint is str:
        return False
    return _is_body_model(hint)


def _is_body_model(hint: Any) -> bool:
    """Return ``True`` iff *hint* is a *class* that the body-coercion
    layer can validate (Pydantic ``BaseModel``, Schemax ``Message``,
    Marshmallow ``Schema``, Rivex ``Schema``).

    Used by the parameter-classification path: a handler whose
    annotation is ``name: str = Form()`` must *not* be classified as
    a body-model slot just because ``str`` happens to be JSON-decodable
    end-to-end.  Plain ``str``/``dict``/``bytes`` body values are
    handled by the ``body_raw`` branch instead — see
    :func:`coerce_body` for that fast path.
    """
    if hint is dict or hint is bytes or hint is str:
        return False
    # Defer to the centralised classifier in :mod:`rivex._bodies` so
    # the list of recognised backends (Pydantic, Schemax, Marshmallow,
    # Rivex ``Schema``) lives in one place.
    _is_bm: Callable[[Any], bool] | None
    try:
        from rivex._bodies import is_body_model as _is_bm
    except ImportError:  # pragma: no cover - module is in the same package
        _is_bm = None
    if _is_bm is not None:
        return _is_bm(hint)
    # Fallback for the absolute path the original code took.
    if hasattr(hint, "model_validate_json"):
        return True
    try:
        from pydantic import BaseModel

        return isinstance(hint, type) and issubclass(hint, BaseModel)
    except (TypeError, ImportError):
        return False


def _get_content_type(request_data: dict) -> str | None:
    return get_request_header(request_data, "content-type")


def _coerce_optional_hint(hint: Any) -> Any:
    """Peel ``X | None`` / ``Optional[X]`` down to ``X`` so primitive
    coercion can target the underlying type.

    Returns *hint* unchanged when it isn't an Optional/Union, or when the
    Union has more than one non-``None`` member (in which case we can't
    pick a single target — fall back to ``str``).
    """
    import typing
    from types import UnionType

    origin = typing.get_origin(hint)
    if origin is typing.Union or origin is UnionType:
        non_none = [a for a in typing.get_args(hint) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return hint


def _coerce(value: str, hint: Any) -> Any:
    # Peel ``X | None`` so query/header/path params declared as
    # ``int | None = Query(...)`` still hit the numeric branch.
    hint = _coerce_optional_hint(hint)
    if RC_V2:
        target = {int: "int", float: "float", bool: "bool"}.get(hint)
        if target:
            result = _rc.coerce_value(value, target)
            if target == "float" and not _math_isfinite(result):
                raise HTTPException(422, detail=f"Value '{value}' is not a finite number")
            return result
        return value
    if hint is int:
        return int(value)
    if hint is float:
        f = float(value)
        if not _math_isfinite(f):
            raise HTTPException(422, detail=f"Value '{value}' is not a finite number")
        return f
    if hint is bool:
        return value.lower() in ("true", "1", "yes")
    return value


def _parse_cookies(request_data: dict) -> dict[str, str]:
    from rivex._compat import parse_request_cookies

    return parse_request_cookies(request_data)
