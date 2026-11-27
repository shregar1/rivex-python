from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import threading
from collections.abc import Callable
from math import isfinite as _math_isfinite
from typing import Any, cast, get_type_hints
from urllib.parse import parse_qs

from rivex.serialization import _json

# Cache imports at module level — NOT per-request
from rivex.native._compat import RC_V2, get_request_header
from rivex.native._compat import rc as _rc
from rivex.lifecycle.background import BackgroundTasks
from rivex.exceptions.http.exceptions import HTTPException, RequestValidationError
from rivex.http.responses import Response as OxResponse

# Prefer orjson for JSON serialization when available — up to 30x faster
# than walking PyObjects through PyO3 for large payloads.
try:
    import orjson as _orjson

    _fast_json_dumps = _orjson.dumps  # bytes output, no .encode() needed
except ImportError:
    _orjson = None  # type: ignore[assignment]
    _fast_json_dumps = None  # type: ignore[assignment]

# Import JsonBytes marker type for Rust-generated JSON responses.
from rivex.serialization.gen import JsonBytes as _JsonBytes

# ── Background task thread pool (reuse threads instead of per-request spawn) ──
_BG_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="rivex-bg")

# ── Dependency signature cache (avoid per-request inspect.signature) ──
_DEP_SIG_CACHE: dict[Callable, tuple[inspect.Signature, dict[str, Any]]] = {}

# ── Singleton-scoped dependency cache (lives for the process lifetime) ──
# Singletons don't follow the per-request ``cache`` dict — they survive
# across requests so providers annotated with ``scope="singleton"`` are
# created exactly once.
_SINGLETON_CACHE: dict[Any, Any] = {}
# A module-level lock that serialises read-modify-write of
# ``_SINGLETON_CACHE``. Without it, two threads racing to construct
# a singleton for the first time can both miss the cache, both
# build the value, and one will overwrite the other — breaking
# the singleton guarantee. We use a regular ``threading.Lock``
# (not an ``RLock``) because the critical sections are short and
# non-reentrant.
_SINGLETON_CACHE_LOCK = threading.Lock()


# Valid ``source`` values accepted by the codegen wrapper. Hoisted
# to module level (was rebuilt on every ``build_handler_wrapper``
# call before the refactor).
_CODEGEN_SOURCES = ("request", "path", "query", "body", "body_raw")


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
    from rivex.serialization._bodies import coerce_body as _coerce_body
    from rivex.http.requests import Request

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
            # supported backend (Pydantic, Marshmallow, plain
            # ``dict``) goes through the same code path.  No Pydantic
            # shortcut here — a Marshmallow
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
    # RivexException subclasses carry their own status_code; honour it.
    lines.append("        _sc = getattr(exc, 'status_code', None)")
    lines.append("        if isinstance(_sc, int) and _sc != 500 and hasattr(exc, 'to_response'):")
    lines.append("            try:")
    lines.append("                _env = exc.to_response()")
    lines.append("                return {")
    lines.append("                    'status': _sc,")
    lines.append("                    'headers': [('content-type', 'application/json')],")
    lines.append("                    'body': _json.dumps(_env),")
    lines.append("                }")
    lines.append("            except Exception:")
    lines.append("                pass")
    lines.append("        if isinstance(_sc, int) and _sc != 500:")
    lines.append("            return _error_response(_sc, str(exc) if debug else exc.__class__.__name__)")
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
        "_json": _json,
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
    """Resolve a ``Depends``-annotated handler parameter from the request context.

    Thin adapter between the per-source-type dispatch table and
    :func:`_resolve_depends`. The shared ``Ctx`` namespace built once per
    request already carries the dependency cache, request data, yield
    cleanups, and any test-time overrides, so this strategy just forwards
    them.

    Args:
        ctx: Per-request extraction context.
        name: Name of the handler parameter being extracted.
        hint: Resolved type hint for the parameter (unused here).
        default: The :class:`Depends` marker instance from the handler
            signature; the actual dependency to resolve is read from
            ``default.dependency``.

    Returns:
        The resolved dependency value.
    """
    return await _resolve_depends(
        default,
        ctx.request_data,
        ctx.dep_cache,
        ctx.yield_cleanups,
        ctx.dependency_overrides,
    )


def _extract_path(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    """Extract an untagged path parameter from ``ctx.path_params``.

    Used for handler parameters whose name matches a path placeholder
    (e.g. ``user_id`` for the path ``/users/{user_id}``) without an
    explicit ``Path(...)`` marker. The raw string is coerced to the
    parameter's type hint; missing required parameters raise
    :class:`RequestValidationError`.

    Args:
        ctx: Per-request extraction context.
        name: Path-parameter name (and handler parameter name).
        hint: Type hint used to coerce the raw string value.
        default: Either ``inspect.Parameter.empty`` (required) or a
            Python default value to use when the path parameter is
            absent.

    Returns:
        The coerced path parameter value, or ``default`` when the
        path parameter is missing and a default is available.

    Raises:
        RequestValidationError: When the path parameter is missing
            and the handler did not supply a default.
    """
    from rivex.exceptions.http.exceptions import RequestValidationError

    raw = ctx.path_params.get(name)
    if raw is not None:
        return _coerce(raw, hint)
    if default is not inspect.Parameter.empty:
        return default
    raise RequestValidationError(
        [{"loc": ("path", name), "msg": "Field required", "type": "missing"}]
    )


def _extract_path_param(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    """Extract a ``Path(...)``-annotated path parameter and validate it.

    Resolves the path-parameter key through the ``Path`` marker's
    ``alias`` (if any), coerces the raw string to the parameter's
    type hint, then runs the marker's ``validate`` method to enforce
    any extra constraints (regex, ge/le, etc.).

    Args:
        ctx: Per-request extraction context.
        name: Handler parameter name (used for error messages).
        hint: Type hint used to coerce the raw string value.
        default: The :class:`Path` marker instance describing the
            path parameter — supplies ``alias``, ``required``, and
            ``default``.

    Returns:
        The coerced and validated path parameter value, or the
        marker's ``default`` value when the parameter is absent and
        ``required=False``.

    Raises:
        RequestValidationError: When the parameter is missing and
            required, or when validation against the marker fails.
    """
    from rivex.exceptions.http.exceptions import RequestValidationError

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
    """Extract an untagged scalar parameter from the query string.

    Used for handler parameters without an explicit ``Query(...)`` marker
    that are not path parameters, body models, or request types. The
    first value of the query parameter is coerced to the parameter's
    type hint; missing required parameters raise
    :class:`RequestValidationError`.

    Args:
        ctx: Per-request extraction context.
        name: Query-string key (and handler parameter name).
        hint: Type hint used to coerce the raw string value.
        default: Either ``inspect.Parameter.empty`` (required) or a
            Python default value to use when the query parameter is
            absent.

    Returns:
        The coerced query value, or ``default`` when the parameter is
        missing and a default is available.

    Raises:
        RequestValidationError: When the parameter is missing and
            the handler did not supply a default.
    """
    from rivex.exceptions.http.exceptions import RequestValidationError

    values = ctx.query_params.get(name) if ctx.query_params else None
    if values:
        return _coerce(values[0], hint)
    if default is not inspect.Parameter.empty:
        return default
    raise RequestValidationError(
        [{"loc": ("query", name), "msg": "Field required", "type": "missing"}]
    )


def _extract_query_param(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    """Extract a ``Query(...)``-annotated parameter and validate it.

    Coerces the first value of the query parameter to the parameter's
    type hint (peeling off ``X | None`` so ``int | None = Query(ge=1)``
    hits the numeric branch), then runs the marker's ``validate`` method
    to enforce any extra constraints (ge/le, regex, etc.).

    Args:
        ctx: Per-request extraction context.
        name: Handler parameter name (used for error messages).
        hint: Type hint used to coerce the raw string value.
        default: The :class:`Query` marker instance describing the
            query parameter — supplies ``alias``, ``required``, and
            ``default``.

    Returns:
        The coerced and validated query value, or the marker's
        ``default`` value when the parameter is absent and
        ``required=False``.

    Raises:
        RequestValidationError: When the parameter is missing and
            required, when coercion fails, or when the marker's
            ``validate`` method rejects the value.
    """
    from rivex.exceptions.http.exceptions import RequestValidationError

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
    """Extract a ``Header(...)``-annotated parameter from request headers.

    Resolves the header key through the ``Header`` marker's
    ``header_name`` (which handles ``snake_case`` ↔ ``Snake-Case``
    conversion), coerces the raw string to the parameter's type hint,
    then runs the marker's ``validate`` method.

    Args:
        ctx: Per-request extraction context.
        name: Handler parameter name (used for error messages).
        hint: Type hint used to coerce the raw string value.
        default: The :class:`Header` marker instance describing the
            header — supplies ``header_name``, ``required``, and
            ``default``.

    Returns:
        The coerced and validated header value, or the marker's
        ``default`` value when the header is absent and
        ``required=False``.

    Raises:
        RequestValidationError: When the header is missing and
            required, or when the marker's ``validate`` method
            rejects the value.
    """
    from rivex.exceptions.http.exceptions import RequestValidationError

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
    """Extract a ``Cookie(...)``-annotated parameter from the parsed cookies.

    Resolves the cookie key through the ``Cookie`` marker's ``alias``
    (if any), coerces the raw string to the parameter's type hint,
    then runs the marker's ``validate`` method.

    Args:
        ctx: Per-request extraction context.
        name: Handler parameter name (used for error messages).
        hint: Type hint used to coerce the raw string value.
        default: The :class:`Cookie` marker instance describing the
            cookie — supplies ``alias``, ``required``, and ``default``.

    Returns:
        The coerced and validated cookie value, or the marker's
        ``default`` value when the cookie is absent and
        ``required=False``.

    Raises:
        RequestValidationError: When the cookie is missing and
            required, or when the marker's ``validate`` method
            rejects the value.
    """
    from rivex.exceptions.http.exceptions import RequestValidationError

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
    """Extract a single field or sub-model from the JSON request body.

    The body is parsed as JSON once. When ``Body(embed=True)`` is used
    the value is looked up under ``name``; otherwise the whole parsed
    object is returned (or coerced to the body-model class). The
    marker's ``validate`` method is run on the raw value to enforce
    param-level constraints.

    Args:
        ctx: Per-request extraction context; ``ctx.body`` is the raw
            request body bytes.
        name: Handler parameter name (used for error messages and as
            the JSON key when ``embed=True``).
        hint: Type hint used to coerce the value. When the hint is a
            Pydantic/dataclass body model, the field value is coerced
            into an instance of that class.
        default: The :class:`Body` marker instance — supplies
            ``embed``, ``required``, and ``default``.

    Returns:
        The extracted body field, the validated body model instance,
        or the marker's ``default`` value when the body is empty
        and the parameter is optional.

    Raises:
        RequestValidationError: When the body is empty and the
            parameter is required, when JSON parsing fails, when
            body-model coercion fails, or when the marker's
            ``validate`` method rejects the value.
    """
    import json as _json

    from rivex.serialization._bodies import coerce_body, is_body_model
    from rivex.exceptions.http.exceptions import RequestValidationError

    if not ctx.body:
        if default.required:
            raise RequestValidationError(
                [
                    {
                        "loc": ("body",),
                        "msg": "Field required: request body is empty",
                        "type": "missing",
                    }
                ]
            )
        return default.default

    # When the hint is a body model (Pydantic, dataclass, …) and the
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
    """Return the JSON-parsed request body, falling back to ``default``.

    Used for untagged ``payload: dict`` / ``payload: bytes`` parameters
    where the user wants the raw request body as a whole instead of a
    single field. When the body is present it is parsed as JSON; when
    it is empty the caller's default (either a :class:`Body` instance's
    ``.default`` or a literal Python default) is returned.

    Args:
        ctx: Per-request extraction context; ``ctx.body`` is the raw
            request body bytes.
        name: Handler parameter name (used for the 422 error message).
        hint: Type hint (unused — the body is always returned as a
            JSON-decoded object).
        default: Either a :class:`Body` marker whose ``.default``
            holds the fallback, or a literal Python default.

    Returns:
        The JSON-decoded request body, or the supplied default.

    Raises:
        HTTPException: 422 when the body is empty and no default is
            available.
    """
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
    """Coerce the whole JSON body into a body-model instance.

    Used when the parameter type hint is a body model (Pydantic,
    dataclass, etc.) without a ``Body(...)`` marker. The body bytes
    are fed to :func:`coerce_body`; failures are translated into
    ``RequestValidationError`` with the field's location.

    Args:
        ctx: Per-request extraction context; ``ctx.body`` is the raw
            request body bytes.
        name: Handler parameter name (used for error messages).
        hint: The body-model class to coerce the body into.
        default: Either ``inspect.Parameter.empty`` (required) or a
            Python default value to use when the body is empty.

    Returns:
        An instance of the body model populated from the request body,
        or ``default`` when the body is empty and a default is
        available.

    Raises:
        RequestValidationError: When the body is empty and the
            parameter is required, or when body-model coercion fails.
    """
    from rivex.serialization._bodies import coerce_body
    from rivex.exceptions.http.exceptions import RequestValidationError

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
    """Materialise a Rivex :class:`Request` object from the in-flight envelope.

    Args:
        ctx: Per-request extraction context; ``ctx.request_data`` is
            the in-flight request envelope.
        name: Handler parameter name (unused — included for the
            strategy-table signature).
        hint: Type hint (unused).
        default: Default value (unused).

    Returns:
        A :class:`rivex.http.requests.Request` built from the request
        envelope.
    """
    from rivex.http.requests import Request

    return Request._from_raw(ctx.request_data)


async def _extract_background_tasks(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    """Return a fresh :class:`BackgroundTasks` collector for the request.

    The returned instance is captured both as a handler argument and
    on the wrapper's local ``bg_tasks`` slot so tasks can be executed
    after the response has been serialised.

    Args:
        ctx: Per-request extraction context (unused).
        name: Handler parameter name (unused).
        hint: Type hint (unused).
        default: Default value (unused).

    Returns:
        A new, empty :class:`BackgroundTasks` instance.
    """
    return BackgroundTasks()


def _extract_file(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    """Return the uploaded file (or its default) for a ``File()`` parameter.

    Looks up the parsed multipart fields for ``name``; falls back to
    the ``File`` marker's ``default`` when present; otherwise raises
    :class:`RequestValidationError` for a missing required file.

    Args:
        ctx: Per-request extraction context; ``ctx.multipart_fields``
            carries the parsed multipart payload.
        name: Field name in the multipart form (and handler parameter
            name).
        hint: Type hint (unused — the value is returned as parsed by
            the multipart parser).
        default: The :class:`File` marker instance describing the
            upload field — supplies ``default``.

    Returns:
        The parsed upload value (``UploadFile`` or scalar), or
        ``default.default`` when the field is absent and a default
        was supplied.

    Raises:
        RequestValidationError: When the field is missing and no
            default is configured.
    """
    from rivex.exceptions.http.exceptions import RequestValidationError
    from rivex.web.uploads import File

    if ctx.multipart_fields and name in ctx.multipart_fields:
        return ctx.multipart_fields[name][0]
    if isinstance(default, File) and default.default is not ...:
        return default.default
    raise RequestValidationError(
        [{"loc": ("body", name), "msg": "Field required", "type": "missing"}]
    )


def _extract_form(ctx: Any, name: str, hint: Any, default: Any) -> Any:
    """Return the form-field value for a single ``Form()`` parameter.

    Looks the field up first in the parsed multipart payload, then in
    the URL-encoded form body (if the content type is
    ``application/x-www-form-urlencoded``). String values are coerced
    to the parameter's type hint; form fields are inherently optional
    and return ``None`` when no value is found.

    Args:
        ctx: Per-request extraction context.
        name: Field name in the form (and handler parameter name).
        hint: Type hint used to coerce the raw string value.
        default: The :class:`Form` marker instance describing the
            field — supplies ``default``.

    Returns:
        The coerced form value, the marker's ``default`` if absent,
        or ``None`` when no value and no default are present.
    """
    from rivex.web.uploads import Form

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
    """Bind an entire form body to a Pydantic/dataclass body model.

    Aggregates the parsed multipart fields (or URL-encoded form body
    when the request lacks a multipart content type) into a single
    dict, then coerces it into the body-model class via
    :func:`coerce_form_data`. The marker's ``required`` flag decides
    whether a missing form is an error.

    Args:
        ctx: Per-request extraction context.
        name: Handler parameter name (used for error messages).
        hint: The body-model class to bind the form to.
        default: The :class:`Form` marker instance — supplies
            ``required`` and ``default``.

    Returns:
        An instance of the body model populated from the form data,
        or ``default.default`` when the form is empty and the
        parameter is optional.

    Raises:
        RequestValidationError: When the form is empty and the
            parameter is required, or when form-model coercion fails.
    """
    from rivex.serialization._bodies import coerce_form_data
    from rivex.exceptions.http.exceptions import RequestValidationError

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
    """Wrap a user handler with Rivex's parameter-extraction and response pipeline.

    Inspects ``func``'s signature, classifies each parameter into one
    of the source strategies in ``_SOURCE_STRATEGIES`` (path, query,
    header, cookie, body, body field, body model, request,
    background tasks, file, form, form model, depends), and returns a
    new async callable that accepts a request envelope, performs the
    extraction, invokes the handler, and normalises the response.

    A few shortcuts are taken when the wrapper can be simplified:

    * Cached handlers (``_CachedWrapper``) and pre-generated handlers
      (``CompiledGen``) get a minimal pass-through that skips request
      extraction entirely.
    * Handlers with no parameters and no exception handlers get a
      "direct" wrapper that also skips request extraction.
    * Handlers whose parameters are all in the codegen-friendly
      subset are routed through :func:`_build_codegen_wrapper` for
      a generated, faster wrapper.

    Args:
        func: The user handler to wrap.
        path: The route's URL path template (used to identify
            untagged path parameters).
        default_status: Status code to use when the handler returns
            a value with no explicit status.
        debug: When ``True``, error responses include the original
            exception message; otherwise they are scrubbed.
        exception_handlers: Optional mapping of exception type to
            handler, used by the wrapper to translate raised
            exceptions into responses.
        response_model: Optional body-model class used to validate
            and filter the handler's return value.
        dependency_overrides: Optional test-time override map for
            dependency providers.
        response_model_include: Optional set of field names to keep
            when dumping the response model.
        response_model_exclude: Optional set of field names to drop
            when dumping the response model.
        response_model_exclude_unset: When ``True``, drop unset fields.
        response_model_exclude_defaults: When ``True``, drop fields at
            their default value.
        response_model_exclude_none: When ``True``, drop fields whose
            value is ``None``.
        validate_response: When ``True``, log a warning if the
            response contains fields not present in the model.

    Returns:
        An async wrapper compatible with the Rivex dispatch chain.
    """
    from rivex.data.caching import _CachedWrapper
    from rivex.di.dependencies import Depends
    from rivex.di.params import Body, Cookie, Header, Path, Query
    from rivex.web.uploads import File, Form, UploadFile

    # ``CompiledGen`` lives in the Rust core (not always present in
    # test envs). Try to import it; fall back to ``None`` if the
    # native extension isn't available so the rest of the wrapper
    # builder still works in pure-Python environments.
    _CompiledGen: type | None = None
    try:
        import rivex_core as _rc_for_gen  # noqa: F401

        _CompiledGen = getattr(_rc_for_gen, "CompiledGen", None)
    except Exception:
        _CompiledGen = None

    if isinstance(func, _CachedWrapper):

        async def cached_wrapper(request_data: dict | None = None) -> dict:
            """Pass-through wrapper for cached handlers that take no request input.

            The wrapped callable ignores the incoming request envelope
            entirely (``request_data`` is unused); it just awaits the
            underlying handler and converts any raised
            :class:`HTTPException` or unexpected exception into a
            standard error response.
            """
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
            """Pass-through wrapper for Rust-compiled response generators.

            Delegates the entire request to ``_gen.generate_response()``,
            which already returns a fully-formed response envelope.
            """
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
            """Minimal wrapper for handlers that take no request input.

            Skips request-extraction entirely, invokes the user handler
            synchronously or asynchronously depending on its kind,
            applies the response model, and normalises the result.
            Honours :class:`HTTPException` and any custom exception
            carrying a ``status_code`` and ``to_response`` envelope.
            """
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
                _sc = getattr(exc, "status_code", None)
                if isinstance(_sc, int) and _sc != 500 and hasattr(exc, "to_response"):
                    try:
                        _env = exc.to_response()
                        return {
                            "status": _sc,
                            "headers": [("content-type", "application/json")],
                            "body": _json.dumps(_env),
                        }
                    except Exception:
                        pass
                if isinstance(_sc, int) and _sc != 500:
                    return _error_response(_sc, str(exc) if debug else exc.__class__.__name__)
                detail = str(exc) if debug else "Internal Server Error"
                return _error_response(500, detail)

        direct_wrapper._rivex_skip_request = True  # type: ignore[attr-defined]
        return direct_wrapper

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
        """Standard-path handler wrapper with full per-parameter extraction.

        Parses the request envelope (path parameters, query string,
        headers, cookies, body, multipart fields) once into a shared
        ``Ctx`` namespace, dispatches each parameter to its
        source-specific extraction strategy, invokes the user handler
        with the assembled ``kwargs``, applies the response model, and
        normalises the result. Background tasks are captured before
        the response is returned so they can run on a daemon thread
        after the response is serialised. User exception handlers
        (when provided) translate raised exceptions into responses;
        otherwise :class:`HTTPException` and exceptions carrying
        ``status_code`` are formatted directly.

        Args:
            request_data: The in-flight request envelope produced by
                the dispatcher.

        Returns:
            A ``{status, headers, body}`` response dict ready to be
            serialised back to the wire.
        """
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
                    from rivex.web.uploads import parse_multipart

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
                    from rivex.http.requests import Request

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
                    from rivex.http.requests import Request

                    request = Request._from_raw(request_data)
                    result = await _call_handler(handler_func, request, exc)
                    if (
                        isinstance(result, dict)
                        and "status" in result
                        and ("body" in result or "headers" in result)
                    ):
                        return result
                    return _normalize_response_fast(result, 500)
            # RivexException subclasses carry their own status_code; honour it.
            status_code = getattr(exc, "status_code", None)
            if isinstance(status_code, int):
                detail = str(exc) if debug else exc.__class__.__name__
                if "ExceptionUtils" in type(exc).__mro__[0].__module__ or hasattr(
                    exc, "to_response"
                ):
                    try:
                        envelope = exc.to_response()
                        return {
                            "status": status_code,
                            "headers": [("content-type", "application/json")],
                            "body": _json.dumps(envelope),
                        }
                    except Exception:
                        pass
                return _error_response(status_code, detail)
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
    """Build a response dict from a raised :class:`HTTPException`.

    Args:
        exc: The exception instance. ``status_code`` and ``detail``
            become the response status and body; ``headers`` are
            merged into the response headers (after the default
            ``Content-Type``).

    Returns:
        A ``{status, headers, body}`` response dict.
    """
    from rivex.native._compat import json_error_response

    resp = json_error_response(exc.status_code, exc.detail)
    if exc.headers:
        resp["headers"].extend(exc.headers.items())
    return resp


def _error_response(status: int, detail: str) -> dict:
    """Build a JSON error response envelope.

    Args:
        status: HTTP status code.
        detail: Human-readable error detail (placed in the
            ``detail`` field of the JSON body).

    Returns:
        A ``{status, headers, body}`` response dict with a JSON body.
    """
    from rivex.native._compat import json_error_response

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
    """Normalise a handler return value to a wire-ready response dict.

    Same as :func:`_normalize_response_fast` but materialises any
    ``body_json`` shortcut into encoded bytes so the result is ready
    to be sent without further Rust-side serialisation.

    Args:
        result: The handler's return value.
        status_code: Fallback status when the return value does not
            carry its own.

    Returns:
        A ``{status, headers, body}`` response dict with a fully
        encoded body.
    """
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
    """Validate and filter ``result`` through ``response_model`` if provided.

    When ``response_model`` is a Pydantic ``BaseModel`` subclass and
    ``result`` is not already an instance of it, ``model_validate`` is
    used. ``dump_kwargs`` is forwarded to ``model_dump`` so the caller
    can request ``include``/``exclude`` sets or the
    ``exclude_*`` filtering flags. When ``validate_response`` is
    ``True``, fields present in ``result`` but not in the model are
    logged as warnings. Tuple status/header overrides on the result
    are preserved on the way out.

    Args:
        result: The handler's return value, possibly a
            ``(status, body)`` or ``(status, body, headers)`` tuple.
        response_model: Pydantic model class, or ``None`` to skip
            validation/filtering.
        dump_kwargs: Optional ``model_dump`` keyword arguments.
        validate_response: When ``True``, log a warning if the
            response carries fields not present in the model.

    Returns:
        The validated/filtered result. The shape mirrors the input:
        a plain value when ``result`` is a plain value, a
        ``(status, body)`` tuple when ``result`` is a
        ``(status, body)`` tuple, and a ``(status, body, headers)``
        tuple when ``result`` is a ``(status, body, headers)`` tuple.
    """
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
    """Resolve a single :class:`Depends` provider to a concrete value.

    Honours ``dependency_overrides`` (test-time swaps), the
    ``scope`` of the dependency (``"singleton"`` is cached in the
    module-level ``_SINGLETON_CACHE``, ``"request"`` is cached in the
    per-request ``cache``), and ``use_cache`` (request-scoped
    dependencies can opt out of caching). Recursively resolves nested
    ``Depends`` parameters, plain path parameters, body models, and
    query strings. Yield-based generators (sync and async) are advanced
    by one step; the generator object is appended to
    ``yield_cleanups`` so the wrapper can shut it down after the
    response is sent.

    Args:
        dep: The :class:`Depends` marker instance whose ``.dependency``
            attribute names the provider to call.
        request_data: The in-flight request envelope.
        cache: Per-request cache used to memoize request-scoped
            dependencies within one request.
        yield_cleanups: Optional list that collects generator
            providers so they can be advanced on the way out.
        dependency_overrides: Optional map used to substitute the
            provider for tests.

    Returns:
        The resolved dependency value (the result of calling the
        provider with its own extracted ``kwargs``).

    Raises:
        HTTPException: 422 when a non-``Depends`` parameter of the
            provider has no default and no value in the request.
    """
    from rivex.di.dependencies import Depends

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
            from rivex.http.requests import Request

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
        # First-writer wins: take the lock, re-check, and only
        # store the value if no other thread got there first.
        # The losing thread's ``result`` is discarded — that is
        # wasteful but the singleton guarantee is preserved.
        with _SINGLETON_CACHE_LOCK:
            existing = _SINGLETON_CACHE.get(provider)
            if existing is None:
                _SINGLETON_CACHE[provider] = result
            else:
                result = existing
    elif scope == "request" and dep.use_cache:
        cache[provider] = result

    return result


def _dependency_callable(provider: Any) -> Callable:
    """Return the underlying callable to invoke for a ``Depends`` provider.

    Unwraps classes (instantiating them with no arguments), prefers a
    user-defined ``resolve`` method when present, falls back to
    ``__call__`` for callable instances, and otherwise returns the
    provider itself.

    Args:
        provider: The raw value supplied to ``Depends(...)`` — may be
            a class, an instance with a ``resolve`` method, an
            instance with ``__call__``, or a plain function.

    Returns:
        A callable ready to be invoked with extracted ``kwargs``.

    Raises:
        TypeError: When ``provider`` is none of the above.
    """
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
    """Invoke a user exception handler, awaiting it when it is a coroutine.

    Args:
        handler_func: The user-supplied exception handler. May be a
            coroutine function or a plain callable.
        request: The :class:`Request` instance to pass to the handler.
        exc: The exception instance to pass to the handler.

    Returns:
        Whatever the handler returns (typically a response value or
        a ``{status, headers, body}`` dict).
    """
    if asyncio.iscoroutinefunction(handler_func):
        return await handler_func(request, exc)
    return handler_func(request, exc)


def _is_request_type(hint: Any) -> bool:
    """Return ``True`` when ``hint`` is the Rivex :class:`Request` class.

    Args:
        hint: The candidate type hint, typically extracted from a
            handler signature.

    Returns:
        ``True`` if ``hint`` is exactly :class:`Request` or a
        subclass of it; ``False`` otherwise (including when the
        ``rivex.http.requests`` module cannot be imported).
    """
    try:
        from rivex.http.requests import Request

        return hint is Request or (isinstance(hint, type) and issubclass(hint, Request))
    except (TypeError, ImportError):
        return False


def _is_background_tasks_type(hint: Any) -> bool:
    """Return ``True`` when ``hint`` is the Rivex :class:`BackgroundTasks` class.

    Args:
        hint: The candidate type hint, typically extracted from a
            handler signature.

    Returns:
        ``True`` if ``hint`` is exactly :class:`BackgroundTasks` or a
        subclass of it; ``False`` otherwise (including when the
        ``rivex.lifecycle.background`` module cannot be imported).
    """
    try:
        from rivex.lifecycle.background import BackgroundTasks

        return hint is BackgroundTasks or (
            isinstance(hint, type) and issubclass(hint, BackgroundTasks)
        )
    except (TypeError, ImportError):
        return False


def _is_strict_body_model(hint: Any) -> bool:
    """Return ``True`` only for *class* types that the body-coercion
    layer validates (Pydantic ``BaseModel``, Marshmallow ``Schema``,
    Rivex ``Schema``).

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
    layer can validate (Pydantic ``BaseModel``, Marshmallow ``Schema``,
    Rivex ``Schema``).

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
    # the list of recognised backends (Pydantic, Marshmallow,
    # Rivex ``Schema``) lives in one place.
    _is_bm: Callable[[Any], bool] | None
    try:
        from rivex.serialization._bodies import is_body_model as _is_bm
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
    """Return the ``Content-Type`` header value from a request envelope.

    Args:
        request_data: The in-flight request envelope. Only its
            ``headers`` entry is consulted.

    Returns:
        The raw ``Content-Type`` value, or ``None`` when the header
        is missing.
    """
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
    """Coerce a raw query/path/header/cookie string to a Python value.

    Peeks through ``X | None`` and ``Optional[X]`` so primitive
    coercion always targets the underlying type. Recursively unwraps
    generic containers (``list``/``tuple``/``set``/``frozenset``/
    ``dict``), supporting the de-facto ``?ids=1,2,3`` comma-separated
    convention and the ``?k1=v1,k2=v2`` dict form.

    When the Rust core is available, int / float / bool coercions go
    through ``_rc.coerce_value`` so they are uniform with the rest
    of the runtime. A non-numeric value raises :class:`HTTPException`
    422 instead of a bare :class:`ValueError` (which would otherwise
    surface as a 500).

    Args:
        value: The raw string value from the request.
        hint: Target type hint, possibly a union, optional, or generic
            container.

    Returns:
        The coerced value (or the original ``value`` for ``str``
        targets and unsupported hint types).

    Raises:
        HTTPException: 422 when the value cannot be parsed as the
            requested numeric/bool type or when the parsed float is
            non-finite.
    """
    # Peel ``X | None`` so query/header/path params declared as
    # ``int | None = Query(...)`` still hit the numeric branch.
    hint = _coerce_optional_hint(hint)

    # Recursively unwrap generic containers like ``list[str]`` /
    # ``Optional[list[int]]`` / ``dict[str, int]`` so primitive
    # coercion can target the element type. Empty ``value`` is
    # returned as-is (the caller is responsible for the empty-list
    # vs missing-list distinction).
    import typing

    origin = typing.get_origin(hint)
    if origin in (list, tuple, set, frozenset):
        if not value:
            return value
        elem_hint = typing.get_args(hint)[0] if typing.get_args(hint) else str
        # Comma-separated values are the de-facto convention for
        # query strings (``?ids=1,2,3``).
        parts = [p.strip() for p in value.split(",") if p.strip()]
        coerced = [_coerce(p, elem_hint) for p in parts]
        if origin is list:
            return coerced
        if origin is tuple:
            return tuple(coerced)
        if origin is set:
            return set(coerced)
        return frozenset(coerced)
    if origin is dict:
        # ``?k1=v1&k2=v2`` style — split on commas for pairs and
        # ampersands for entries.
        if not value:
            return value
        key_hint, val_hint = typing.get_args(hint) if typing.get_args(hint) else (str, str)
        out: dict = {}
        for entry in value.split(","):
            if "=" not in entry:
                continue
            k, v = entry.split("=", 1)
            out[_coerce(k.strip(), key_hint)] = _coerce(v.strip(), val_hint)
        return out

    if RC_V2:
        target = {int: "int", float: "float", bool: "bool"}.get(hint)
        if target:
            # A non-numeric / out-of-range value must be a 422, not an unhandled
            # ValueError from the core (which otherwise surfaces as a 500 for
            # plain typed path/query params — see _extract_path/_extract_query).
            try:
                result = _rc.coerce_value(value, target)
            except (ValueError, TypeError, OverflowError) as exc:
                raise HTTPException(422, detail=f"Value '{value}' is not a valid {target}") from exc
            if target == "float" and not _math_isfinite(result):
                raise HTTPException(422, detail=f"Value '{value}' is not a finite number")
            return result
        return value
    if hint is int:
        try:
            return int(value)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, detail=f"Value '{value}' is not a valid int") from exc
    if hint is float:
        try:
            f = float(value)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, detail=f"Value '{value}' is not a valid float") from exc
        if not _math_isfinite(f):
            raise HTTPException(422, detail=f"Value '{value}' is not a finite number")
        return f
    if hint is bool:
        return value.lower() in ("true", "1", "yes")
    return value


def _parse_cookies(request_data: dict) -> dict[str, str]:
    """Extract and parse the ``Cookie`` header from a request envelope.

    Thin wrapper over :func:`rivex.native._compat.parse_request_cookies`
    so the per-request extraction code can keep a single import surface.

    Args:
        request_data: The in-flight request envelope.

    Returns:
        Parsed cookies as a ``{name: value}`` dict, or ``{}`` when
        the request has no ``Cookie`` header.
    """
    from rivex.native._compat import parse_request_cookies

    return parse_request_cookies(request_data)
