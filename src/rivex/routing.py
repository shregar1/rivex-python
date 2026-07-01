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
    response_model: Any = None
    tags: list[str] = field(default_factory=list)
    summary: str | None = None
    description: str | None = None
    operation_id: str | None = None
    deprecated: bool = False
    include_in_schema: bool = True
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


@dataclass
class RouteHandlerMetadata:
    method: str
    path: str
    status_code: int = 200
    response_model: Any = None
    tags: list[str] = field(default_factory=list)
    summary: str | None = None
    description: str | None = None
    operation_id: str | None = None
    deprecated: bool = False
    include_in_schema: bool = True
    openapi_extra: dict[str, Any] | None = None
    responses: dict[int, dict[str, Any]] | None = None
    response_model_include: set[str] | None = None
    response_model_exclude: set[str] | None = None
    response_model_exclude_unset: bool = False
    response_model_exclude_defaults: bool = False
    response_model_exclude_none: bool = False
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
) -> Callable:
    """Mark a function or controller method as a route handler."""

    def decorator(func: Callable) -> Callable:
        metadata = RouteHandlerMetadata(
            method=method,
            path=path,
            status_code=status_code,
            response_model=response_model,
            tags=tags or [],
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
    path: str = ""
    tags: list[str] = []


def is_controller(value: Any) -> bool:
    return isinstance(value, Controller) or (
        isinstance(value, type) and issubclass(value, Controller)
    )


def controller_to_router(controller: type[Controller] | Controller) -> Router:
    instance = controller() if isinstance(controller, type) else controller
    router = Router(
        prefix=getattr(instance, "path", ""),
        tags=list(getattr(instance, "tags", [])),
    )
    handlers: list[tuple[int, Callable, RouteHandlerMetadata]] = []

    for name in dir(instance):
        if name.startswith("_"):
            continue
        bound = getattr(instance, name)
        if not callable(bound):
            continue
        source = getattr(bound, "__func__", bound)
        for metadata in getattr(source, "_rivex_route_handlers", []):
            handlers.append((metadata.order, bound, metadata))

    for _, endpoint, metadata in sorted(handlers, key=lambda item: item[0]):
        router._routes.append(
            RouteRecord(
                method=metadata.method,
                path=_join_paths(router.prefix, metadata.path),
                endpoint=endpoint,
                status_code=metadata.status_code,
                response_model=metadata.response_model,
                tags=router.tags + metadata.tags,
                summary=metadata.summary,
                description=metadata.description,
                operation_id=metadata.operation_id,
                deprecated=metadata.deprecated,
                include_in_schema=metadata.include_in_schema,
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

        for hook in self._before:
            result = hook(request_data)
            if _aio.iscoroutine(result):
                result = await result
            if isinstance(result, dict) and "status" in result:
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
    ) -> Callable:
        def decorator(func: Callable) -> Callable:
            full_path = self.prefix + path
            record = RouteRecord(
                method=method,
                path=full_path,
                endpoint=func,
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
                middleware=list(self._middleware) if self._middleware else None,
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

    def include_router(
        self,
        router: Router | type[Controller] | Controller,
        *,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        if is_controller(router):
            router = controller_to_router(router)  # type: ignore[arg-type]
        assert isinstance(router, Router)
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
