from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import count
from typing import Any


@dataclass
class RouteRecord:
    method: str
    path: str
    endpoint: Callable
    status_code: int = 200
    request_dto: Any = None
    response_dto: Any = None
    response_model: Any = None  # alias for response_dto (kept for back-compat)
    tags: list[str] = field(default_factory=list)
    summary: str | None = None
    description: str | None = None
    operation_id: str | None = None
    deprecated: bool = False
    include_in_schema: bool = True
    access_key: str | None = None
    openapi_extra: dict[str, Any] | None = None
    responses: dict[int, dict[str, Any]] | None = None
    response_model_include: set[str] | None = None
    response_model_exclude: set[str] | None = None
    response_model_exclude_unset: bool = False
    response_model_exclude_defaults: bool = False
    response_model_exclude_none: bool = False
    name: str | None = None
    middleware: list[tuple[type, dict]] | None = None
    exception_handlers: dict[type, Callable] | None = None
    validate_response: bool = False
    cache_ttl: int | None = None
    host: str | None = None

    def __post_init__(self) -> None:
        # ``response_model`` is the legacy alias for ``response_dto``;
        # keep the two in sync so callers can use either.
        if self.response_dto is None and self.response_model is not None:
            self.response_dto = self.response_model
        elif self.response_model is None and self.response_dto is not None:
            self.response_model = self.response_dto


@dataclass
class RouteHandlerMetadata:
    method: str
    path: str
    status_code: int = 200
    request_dto: Any = None
    response_dto: Any = None
    response_model: Any = None  # alias for response_dto
    tags: list[str] = field(default_factory=list)
    summary: str | None = None
    description: str | None = None
    operation_id: str | None = None
    deprecated: bool = False
    include_in_schema: bool = True
    access_key: str | None = None
    openapi_extra: dict[str, Any] | None = None
    responses: dict[int, dict[str, Any]] | None = None
    response_model_include: set[str] | None = None
    response_model_exclude: set[str] | None = None
    response_model_exclude_unset: bool = False
    response_model_exclude_defaults: bool = False
    response_model_exclude_none: bool = False
    middleware: list[Any] | None = None
    name: str | None = None
    order: int = 0


_route_order = count()


def _join_paths(*parts: str) -> str:
    cleaned = [part.strip("/") for part in parts if part and part.strip("/")]
    if not cleaned:
        return "/"
    return "/" + "/".join(cleaned)


def route(
    method: str,
    path: str,
    *,
    status_code: int = 200,
    request_dto: Any = None,
    response_dto: Any = None,
    response_model: Any = None,
    tags: list[str] | None = None,
    summary: str | None = None,
    description: str | None = None,
    operation_id: str | None = None,
    deprecated: bool = False,
    include_in_schema: bool = True,
    access_key: str | None = None,
    openapi_extra: dict[str, Any] | None = None,
    responses: dict[int, dict[str, Any]] | None = None,
    response_model_include: set[str] | None = None,
    response_model_exclude: set[str] | None = None,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    middleware: list[Any] | None = None,
) -> Callable:
    """Mark a function or controller method as a route handler."""
    if middleware is not None:
        for item in middleware:
            if isinstance(item, str) or not (isinstance(item, (type, tuple)) or callable(item)):
                raise TypeError(f"Invalid middleware entry: {item!r}")

    def decorator(func: Callable) -> Callable:
        metadata = RouteHandlerMetadata(
            method=method,
            path=path,
            status_code=status_code,
            request_dto=request_dto,
            response_dto=response_dto,
            response_model=response_model,
            tags=tags or [],
            summary=summary,
            description=description,
            operation_id=operation_id,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            access_key=access_key,
            openapi_extra=openapi_extra,
            responses=responses,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            middleware=middleware,
            order=next(_route_order),
        )
        records = list(getattr(func, "_rivex_route_handlers", []))
        records.append(metadata)
        func._rivex_route_handlers = records  # type: ignore[attr-defined]
        return func

    return decorator


def get(path: str, **kwargs: Any) -> Callable:
    return route("GET", path, **kwargs)


def post(path: str, **kwargs: Any) -> Callable:
    return route("POST", path, **kwargs)


def put(path: str, **kwargs: Any) -> Callable:
    return route("PUT", path, **kwargs)


def delete(path: str, **kwargs: Any) -> Callable:
    return route("DELETE", path, **kwargs)


def patch(path: str, **kwargs: Any) -> Callable:
    return route("PATCH", path, **kwargs)


def head(path: str, **kwargs: Any) -> Callable:
    return route("HEAD", path, **kwargs)


def options(path: str, **kwargs: Any) -> Callable:
    return route("OPTIONS", path, **kwargs)


# Attribute-style access — ``@route.get("/x")`` etc. Lets a Controller method be
# named after an HTTP verb without shadowing the decorator: a bare ``from rivex
# import get`` is rebound by ``def get(self): ...`` in the class body (Python
# class-scope name binding), but ``route`` isn't. ``route("GET", "/x")`` still works.
for _verb in (get, post, put, delete, patch, head, options):
    setattr(route, _verb.__name__, _verb)
del _verb


class Controller:
    """Base class for grouped route handlers.

    Subclass and either set the class attributes below, OR pass the
    same values to the route decorator (``@post(path=..., tags=...)``).
    Decorator values win when both are provided; class attributes are
    used as defaults.

    Class attributes set the *whole-controller* defaults — every
    method on the controller inherits them unless its decorator
    overrides the specific field. For values that differ per route,
    pass them to the decorator instead of overriding the class.

    Required at registration time:

    * ``path`` — URL prefix for every route on this controller.
      Supply either here on the class (``/api/v1/assessments``) or per
      method on the decorator (``@post(path="/assessments")``), but
      not both as empty.

    Optional (each falls back to a sensible default if neither class
    nor decorator sets it):

    * ``tags`` — OpenAPI tags merged with the per-method tags.
    * ``summary`` / ``description`` / ``operation_id`` — OpenAPI
      metadata.
    * ``deprecated`` — mark every route on this controller as
      OpenAPI-deprecated.
    * ``include_in_schema`` — opt out of schema generation.
    * ``status_code`` — default success status.
    * ``request_dto`` / ``response_dto`` — pydantic / dataclass models
      for body validation + response serialisation. ``response_model``
      is also accepted as an alias for ``response_dto``.
    * ``access_key`` — per-API-user access key required to call the
      route (string). When set, the framework rejects requests whose
      ``X-Access-Key`` header doesn't match.

    Validation runs at ``include_router`` time (when the controller
    is mounted) and raises :class:`ValueError` if a route resolves
    with an empty path. Both the decorator and the class attribute
    can be set independently, but at least one must be non-empty.
    """

    path: str = ""
    tags: list[str] = []
    summary: str | None = None
    description: str | None = None
    operation_id: str | None = None
    deprecated: bool = False
    include_in_schema: bool = True
    status_code: int = 200
    request_dto: Any = None
    response_dto: Any = None
    response_model: Any = None  # alias for response_dto
    access_key: str | None = None


def is_controller(value: Any) -> bool:
    return isinstance(value, Controller) or (
        isinstance(value, type) and issubclass(value, Controller)
    )


def _resolve_str(
    class_value: str | None,
    decorator_value: str | None,
    *,
    field: str,
    controller_name: str,
    method_name: str,
) -> str:
    """Pick the decorator value if non-empty, else the class value, else raise.

    Returns ``""`` for both as a sentinel; callers convert empty-string
    into a :class:`ValueError` for ``path`` (where empty is illegal)
    and into the framework default for everything else.
    """
    deco = (decorator_value or "").strip()
    cls = (class_value or "").strip()
    if deco:
        return deco
    if cls:
        return cls
    return ""


def _resolve_list(
    class_value: list | None,
    decorator_value: list | None,
) -> list:
    """Merge class + decorator lists with decorator appended last."""
    merged: list = []
    if class_value:
        merged.extend(class_value)
    if decorator_value:
        merged.extend(decorator_value)
    return merged


def _resolve_bool(
    class_value: bool,
    decorator_explicit: bool | None,
) -> bool:
    """Decorator only overrides when explicitly set (not ``None``)."""
    return class_value if decorator_explicit is None else decorator_explicit


def _resolve_optional(
    class_value: Any,
    decorator_value: Any,
) -> Any:
    """Pick decorator value if not ``None`` / empty, else class value."""
    if decorator_value is None:
        return class_value
    if isinstance(decorator_value, str) and not decorator_value:
        return class_value
    return decorator_value


def controller_to_router(controller: type[Controller] | Controller) -> Router:
    """Convert a :class:`Controller` (class or instance) into a :class:`Router`.

    Resolution rules (per route):

    1. Decorator value wins if it is non-empty / non-``None``.
    2. Class attribute value is the fallback.
    3. If both are missing:

       * For ``path`` — raise :class:`ValueError` (every route needs
         a path).
       * For everything else — fall through to the framework default
         (``None`` / ``[]`` / ``False``).

    Class-level ``path`` is treated as a *prefix* and concatenated to
    the per-method path; if the class path is ``""`` the method path
    is used as-is.
    """
    cls = controller if isinstance(controller, type) else type(controller)
    instance = controller() if isinstance(controller, type) else controller

    class_prefix: str = getattr(cls, "path", "") or ""
    class_tags: list = list(getattr(cls, "tags", []) or [])
    class_summary: str | None = getattr(cls, "summary", None)
    class_description: str | None = getattr(cls, "description", None)
    class_operation_id: str | None = getattr(cls, "operation_id", None)
    class_deprecated: bool = bool(getattr(cls, "deprecated", False))
    class_include_in_schema: bool = bool(getattr(cls, "include_in_schema", True))
    class_status_code: int = int(getattr(cls, "status_code", 200))
    class_request_dto: Any = getattr(cls, "request_dto", None)
    class_response_dto: Any = (
        getattr(cls, "response_dto", None)
        if getattr(cls, "response_dto", None) is not None
        else getattr(cls, "response_model", None)
    )
    class_access_key: str | None = getattr(cls, "access_key", None)

    router = Router(prefix="", tags=[])

    handlers: list[tuple[int, Callable, str, RouteHandlerMetadata]] = []

    for name in dir(instance):
        if name.startswith("_"):
            continue
        bound = getattr(instance, name)
        if not callable(bound):
            continue
        source = getattr(bound, "__func__", bound)
        for metadata in getattr(source, "_rivex_route_handlers", []):
            handlers.append((metadata.order, bound, name, metadata))

    for _, endpoint, method_name, metadata in sorted(handlers, key=lambda item: item[0]):
        # Decorator wins on every field it touches.
        method_path = _resolve_str(
            None,
            metadata.path,
            field="path",
            controller_name=cls.__name__,
            method_name=method_name,
        )
        if class_prefix:
            final_path = _join_paths(class_prefix, method_path) if method_path else class_prefix
        else:
            final_path = method_path
        if not final_path:
            raise ValueError(
                f"Controller '{cls.__name__}.{method_name}' has no path. "
                f"Set the 'path' class attribute on the controller, "
                f"or pass it to the route decorator "
                f"(@get/@post/@put/@delete/@patch/@head/@options)."
            )

        route_tags = _resolve_list(class_tags, metadata.tags)
        route_summary = _resolve_optional(class_summary, metadata.summary)
        route_description = _resolve_optional(class_description, metadata.description)
        route_operation_id = _resolve_optional(class_operation_id, metadata.operation_id)
        route_deprecated = _resolve_bool(class_deprecated, None if metadata.deprecated is False else metadata.deprecated)
        route_include_in_schema = _resolve_bool(
            class_include_in_schema,
            None if metadata.include_in_schema is True else metadata.include_in_schema,
        )
        route_status_code = (
            metadata.status_code if metadata.status_code != 200 else class_status_code
        )
        route_request_dto = _resolve_optional(class_request_dto, metadata.request_dto)
        route_response_dto = _resolve_optional(class_response_dto, metadata.response_dto) or _resolve_optional(
            class_response_dto, metadata.response_model
        )
        route_access_key = _resolve_optional(class_access_key, metadata.access_key)

        router._routes.append(
            RouteRecord(
                method=metadata.method,
                path=final_path,
                endpoint=endpoint,
                middleware=metadata.middleware,
                status_code=route_status_code,
                request_dto=route_request_dto,
                response_dto=route_response_dto,
                tags=route_tags,
                summary=route_summary,
                description=route_description,
                operation_id=route_operation_id,
                deprecated=route_deprecated,
                include_in_schema=route_include_in_schema,
                access_key=route_access_key,
                openapi_extra=metadata.openapi_extra,
                responses=metadata.responses,
                response_model_include=metadata.response_model_include,
                response_model_exclude=metadata.response_model_exclude,
                response_model_exclude_unset=metadata.response_model_exclude_unset,
                response_model_exclude_defaults=metadata.response_model_exclude_defaults,
                response_model_exclude_none=metadata.response_model_exclude_none,
            )
        )

    return router


class _LifecycleHookMiddleware:
    def __init__(self, before: list[Callable] | None = None, after: list[Callable] | None = None):
        self._before = before or []
        self._after = after or []

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        import asyncio as _aio

        # Match the app-level hook short-circuit semantics: any
        # ``dict`` returned by a ``before_request`` hook short-
        # circuits the request. The previous "must have 'status'"
        # rule meant that app-level and router-level hooks behaved
        # inconsistently for the same return value.
        for hook in self._before:
            result = hook(request_data)
            if _aio.iscoroutine(result):
                result = await result
            if isinstance(result, dict):
                return result
        response: dict = await call_next(request_data)
        for hook in self._after:
            result = hook(request_data, response)
            if _aio.iscoroutine(result):
                result = await result
            if isinstance(result, dict):
                response = result
        return response


class RouteGroup:
    def __init__(
        self,
        parent: Router,
        prefix: str = "",
        tags: list[str] | None = None,
        middleware: list[tuple[type, dict]] | None = None,
    ):
        self._parent = parent
        self._prefix = prefix
        self._tags = tags or []
        self._middleware = middleware or []
        self._routes: list[RouteRecord] = []
        self._flushed = False

    def _route(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Callable:
        def decorator(func: Callable) -> Callable:
            full_path = self._parent.prefix + self._prefix + path
            route_tags = self._parent.tags + self._tags + (kwargs.pop("tags", None) or [])
            route_mw = (
                list(self._parent._middleware)
                + self._middleware
                + (kwargs.pop("middleware", None) or [])
            )
            record = RouteRecord(
                method=method,
                path=full_path,
                endpoint=func,
                tags=route_tags,
                middleware=route_mw if route_mw else None,
                exception_handlers=dict(self._parent._exception_handlers)
                if self._parent._exception_handlers
                else None,
                **kwargs,
            )
            self._routes.append(record)
            return func

        return decorator

    def get(self, path: str, **kwargs: Any) -> Callable:
        return self._route("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable:
        return self._route("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Callable:
        return self._route("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Callable:
        return self._route("DELETE", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Callable:
        return self._route("PATCH", path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> Callable:
        return self._route("HEAD", path, **kwargs)

    def options(self, path: str, **kwargs: Any) -> Callable:
        return self._route("OPTIONS", path, **kwargs)

    def flush(self) -> None:
        if self._flushed:
            return
        self._flushed = True
        self._parent._routes.extend(self._routes)

    def __enter__(self) -> RouteGroup:
        return self

    def __exit__(self, *args: Any) -> None:
        self.flush()


class Router:
    def __init__(self, prefix: str = "", tags: list[str] | None = None):
        self.prefix = prefix
        self.tags = tags or []
        self._routes: list[RouteRecord] = []
        self._middleware: list[tuple[type, dict]] = []
        self._exception_handlers: dict[type, Callable] = {}
        self._before_request_hooks: list[Callable] = []
        self._after_request_hooks: list[Callable] = []
        self._groups: list[RouteGroup] = []

    def add_middleware(self, middleware_cls: type, **kwargs: Any) -> None:
        self._middleware.append((middleware_cls, kwargs))

    def before_request(self, func: Callable) -> Callable:
        self._before_request_hooks.append(func)
        return func

    def after_request(self, func: Callable) -> Callable:
        self._after_request_hooks.append(func)
        return func

    def group(
        self,
        prefix: str = "",
        tags: list[str] | None = None,
        middleware: list[tuple[type, dict]] | None = None,
    ) -> RouteGroup:
        grp = RouteGroup(parent=self, prefix=prefix, tags=tags, middleware=middleware)
        self._groups.append(grp)
        return grp

    def exception_handler(self, exc_class: type) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._exception_handlers[exc_class] = func
            return func

        return decorator

    def get(self, path: str, **kwargs: Any) -> Callable:
        return self._route("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable:
        return self._route("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Callable:
        return self._route("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Callable:
        return self._route("DELETE", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Callable:
        return self._route("PATCH", path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> Callable:
        return self._route("HEAD", path, **kwargs)

    def options(self, path: str, **kwargs: Any) -> Callable:
        return self._route("OPTIONS", path, **kwargs)

    def _route(
        self,
        method: str,
        path: str,
        *,
        status_code: int = 200,
        response_model: Any = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        operation_id: str | None = None,
        deprecated: bool = False,
        include_in_schema: bool = True,
        openapi_extra: dict[str, Any] | None = None,
        responses: dict[int, dict[str, Any]] | None = None,
        response_model_include: set[str] | None = None,
        response_model_exclude: set[str] | None = None,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        name: str | None = None,
        validate_response: bool = False,
        cache_ttl: int | None = None,
        host: str | None = None,
        middleware: list[Any] | None = None,
    ) -> Callable:
        if middleware is not None:
            for item in middleware:
                if isinstance(item, str) or not (isinstance(item, (type, tuple)) or callable(item)):
                    raise TypeError(f"Invalid middleware entry: {item!r}")

        def decorator(func: Callable) -> Callable:
            full_path = self.prefix + path
            route_mw = (list(self._middleware) if self._middleware else []) + (middleware or [])
            record = RouteRecord(
                method=method,
                path=full_path,
                endpoint=func,
                middleware=route_mw,
                status_code=status_code,
                response_model=response_model,
                tags=self.tags + (tags or []),
                summary=summary,
                description=description,
                operation_id=operation_id,
                deprecated=deprecated,
                include_in_schema=include_in_schema,
                openapi_extra=openapi_extra,
                responses=responses,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                name=name,
                exception_handlers=dict(self._exception_handlers)
                if self._exception_handlers
                else None,
                validate_response=validate_response,
                cache_ttl=cache_ttl,
                host=host,
            )
            self._routes.append(record)
            return func

        return decorator

    def include_route(
        self,
        method: str,
        path: str,
        endpoint: Callable,
        *,
        name: str | None = None,
        prefix: str = "",
        status_code: int = 200,
        request_dto: Any = None,
        response_dto: Any = None,
        response_model: Any = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        operation_id: str | None = None,
        deprecated: bool = False,
        include_in_schema: bool = True,
        access_key: str | None = None,
        openapi_extra: dict[str, Any] | None = None,
        responses: dict[int, dict[str, Any]] | None = None,
        response_model_include: set[str] | None = None,
        response_model_exclude: set[str] | None = None,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        middleware: list[tuple[type, dict]] | None = None,
        exception_handlers: dict[type, Callable] | None = None,
        validate_response: bool = False,
        cache_ttl: int | None = None,
        host: str | None = None,
    ) -> RouteRecord:
        """Register a single route on this router without a full Controller.

        Convenience wrapper around :meth:`_route` for one-off routes
        (health checks, webhooks, decorators-injected handlers) that
        don't justify a Controller class. Returns the created
        :class:`RouteRecord` so callers can introspect or later
        override metadata.

        Parameters:
            method: HTTP method (``"GET"``, ``"POST"``, …, case-insensitive).
            path: Route path relative to this router's ``prefix`` and
                the *prefix* override passed here (the override wins).
            endpoint: Callable handling the request.
            name: Stable route name (used by ``url_for(name, **path_params)``
                and OpenAPI ``operationId`` when ``operation_id`` is unset).
            prefix: One-off URL prefix; appended to ``self.prefix``.
            request_dto: pydantic / dataclass used for body validation
                and OpenAPI request schema.
            response_dto: pydantic / dataclass used for response
                serialisation and OpenAPI response schema. ``response_model``
                is accepted as an alias for back-compat.
            status_code / tags / summary / description / operation_id /
            deprecated / include_in_schema / access_key / openapi_extra /
            responses / response_model_include / response_model_exclude /
            response_model_exclude_unset / response_model_exclude_defaults /
            response_model_exclude_none / middleware / exception_handlers /
            validate_response / cache_ttl / host: forwarded straight to
            :class:`RouteRecord` (same semantics as the decorator forms
            on :meth:`get` / :meth:`post` / etc.).

            access_key: When set, the framework rejects requests whose
                ``X-Access-Key`` header doesn't match. Useful for
                per-API-user authorisation on internal endpoints.
        """
        full_path = (self.prefix + prefix) + path
        route_mw: list[tuple[type, dict]] = list(self._middleware)
        if middleware:
            route_mw = route_mw + list(middleware)
        record = RouteRecord(
            method=method.upper(),
            path=full_path,
            endpoint=endpoint,
            name=name,
            status_code=status_code,
            request_dto=request_dto,
            response_dto=response_dto,
            response_model=response_model,
            tags=self.tags + (tags or []),
            summary=summary,
            description=description,
            operation_id=operation_id,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            access_key=access_key,
            openapi_extra=openapi_extra,
            responses=responses,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            middleware=route_mw if route_mw else None,
            exception_handlers=dict(self._exception_handlers) if self._exception_handlers else exception_handlers,
            validate_response=validate_response,
            cache_ttl=cache_ttl,
            host=host,
        )
        self._routes.append(record)
        return record

    def include_router(
        self,
        router: Router | type[Controller] | Controller,
        *,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        if is_controller(router):
            router = controller_to_router(router)  # type: ignore[arg-type]
        if not isinstance(router, Router):
            raise TypeError(
                f"include_router expected a Router (or Controller), "
                f"got {type(router).__name__}: {router!r}"
            )
        # Flush any route groups on the child router
        for grp in getattr(router, "_groups", []):
            grp.flush()
        # Convert child router lifecycle hooks into middleware entries
        hook_mw: list[tuple[type, dict]] = []
        if router._before_request_hooks or router._after_request_hooks:
            hook_mw.append(
                (
                    _LifecycleHookMiddleware,
                    {
                        "before": list(router._before_request_hooks),
                        "after": list(router._after_request_hooks),
                    },
                )
            )
        # Combine parent middleware (runs first/outer) with child middleware
        combined_mw = list(self._middleware) + hook_mw + (router._middleware or [])
        # Combine exception handlers: child overrides parent for same type
        combined_exc: dict[type, Callable] = dict(self._exception_handlers)
        combined_exc.update(router._exception_handlers or {})
        for record in router._routes:
            # Merge parent middleware with route-level middleware
            route_mw = list(combined_mw) + (record.middleware or [])
            # Merge exception handlers: route-level overrides parent+child
            route_exc = dict(combined_exc)
            if record.exception_handlers:
                route_exc.update(record.exception_handlers)
            merged = RouteRecord(
                method=record.method,
                path=self.prefix + prefix + record.path,
                endpoint=record.endpoint,
                status_code=record.status_code,
                response_model=record.response_model,
                tags=self.tags + (tags or []) + record.tags,
                summary=record.summary,
                description=record.description,
                operation_id=record.operation_id,
                deprecated=record.deprecated,
                include_in_schema=record.include_in_schema,
                openapi_extra=record.openapi_extra,
                responses=record.responses,
                response_model_include=record.response_model_include,
                response_model_exclude=record.response_model_exclude,
                response_model_exclude_unset=record.response_model_exclude_unset,
                response_model_exclude_defaults=record.response_model_exclude_defaults,
                response_model_exclude_none=record.response_model_exclude_none,
                name=record.name,
                middleware=route_mw if route_mw else None,
                exception_handlers=route_exc if route_exc else None,
                validate_response=record.validate_response,
                cache_ttl=record.cache_ttl,
                host=record.host,
            )
            self._routes.append(merged)

    def include_controller(
        self,
        controller: type[Controller] | Controller,
        *,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        self.include_router(controller, prefix=prefix, tags=tags)


APIRouter = Router
