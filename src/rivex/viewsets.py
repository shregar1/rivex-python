from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ViewSet:
    """Base ViewSet providing CRUD actions mapped to HTTP methods.

    Subclasses define ``list``, ``create``, ``retrieve``, ``update``,
    ``partial_update``, and ``destroy`` methods.

    Usage::

        class UserViewSet(ViewSet):
            async def list(self, request):
                return {"users": []}

        router = Router()
        router.register("users", UserViewSet)
    """

    lookup_field = "id"
    permission_classes: list[type] | None = None

    async def list(self, request: Any) -> Any:
        raise NotImplementedError

    async def create(self, request: Any) -> Any:
        raise NotImplementedError

    async def retrieve(self, request: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def update(self, request: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def partial_update(self, request: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def destroy(self, request: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def as_view(self, actions: dict[str, str]) -> Callable:
        async def view(request: Any, **kwargs: Any) -> Any:
            method = request.method.lower() if hasattr(request, "method") else "get"
            action = actions.get(method)
            if action is None:
                return {"error": "Method not allowed"}, 405
            handler = getattr(self, action, None)
            if handler is None:
                return {"error": "Not implemented"}, 501
            return await handler(request, **kwargs)
        return view


class ModelViewSet(ViewSet):
    """ViewSet that auto-generates CRUD from a model and serializer."""

    model_cls: type | None = None
    serializer_cls: type | None = None

    async def get_queryset(self) -> list:
        raise NotImplementedError

    async def get_object(self, **kwargs: Any) -> Any:
        raise NotImplementedError


class ListModelMixin:
    """Adds paginated list support to a ViewSet."""

    paginate_by: int = 20

    async def list(self, request: Any) -> dict:
        queryset = await self.get_queryset() if hasattr(self, "get_queryset") else []
        page = int(request.query_params.get("page", 1)) if hasattr(request, "query_params") else 1
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        page_items = queryset[start:end]
        if hasattr(self, "serializer_cls") and self.serializer_cls:
            serializer = self.serializer_cls(data=page_items)
            results = serializer.to_representation(page_items) if hasattr(serializer, "to_representation") else page_items
        else:
            results = page_items
        return {
            "count": len(queryset),
            "page": page,
            "results": results,
        }


class Router:
    """Auto-registers routes from ViewSets.

    Generates:
    - GET  /{prefix}/        -> viewset.list
    - POST /{prefix}/        -> viewset.create
    - GET  /{prefix}/{id}/   -> viewset.retrieve
    - PUT  /{prefix}/{id}/   -> viewset.update
    - PATCH /{prefix}/{id}/  -> viewset.partial_update
    - DELETE /{prefix}/{id}/ -> viewset.destroy
    """

    def __init__(self):
        self._routes: list[dict] = []

    def register(self, prefix: str, viewset_cls: type, **kwargs: Any) -> None:
        basename = kwargs.get("basename", prefix.rstrip("/"))
        actions = {
            "get": "list",
            "post": "create",
        }
        detail_actions = {
            "get": "retrieve",
            "put": "update",
            "patch": "partial_update",
            "delete": "destroy",
        }

        list_view = viewset_cls().as_view(actions)
        detail_view = viewset_cls().as_view(detail_actions)

        self._routes.append({
            "method": "GET",
            "path": f"/{prefix}/" if not prefix.endswith("/") else prefix,
            "handler": list_view,
            "name": f"{basename}-list",
        })
        self._routes.append({
            "method": "POST",
            "path": f"/{prefix}/" if not prefix.endswith("/") else prefix,
            "handler": list_view,
            "name": f"{basename}-create",
        })
        self._routes.append({
            "method": "GET",
            "path": f"/{prefix}/{{{viewset_cls.lookup_field}}}/",
            "handler": detail_view,
            "name": f"{basename}-detail",
        })
        self._routes.append({
            "method": "PUT",
            "path": f"/{prefix}/{{{viewset_cls.lookup_field}}}/",
            "handler": detail_view,
            "name": f"{basename}-update",
        })
        self._routes.append({
            "method": "PATCH",
            "path": f"/{prefix}/{{{viewset_cls.lookup_field}}}/",
            "handler": detail_view,
            "name": f"{basename}-partial-update",
        })
        self._routes.append({
            "method": "DELETE",
            "path": f"/{prefix}/{{{viewset_cls.lookup_field}}}/",
            "handler": detail_view,
            "name": f"{basename}-destroy",
        })

    @property
    def routes(self) -> list[dict]:
        return list(self._routes)

    def install(self, app: Any) -> None:
        for route in self._routes:
            app.add_route(
                route["method"],
                route["path"],
                route["handler"],
                name=route["name"],
            )


class BrowsableApiMiddleware:
    """Renders HTML browsable API for GET requests when ``Accept: text/html``.

    Usage::

        app.add_middleware(BrowsableApiMiddleware)
    """

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        result: dict = await call_next(request_data)

        headers = request_data.get("headers", {})
        accept = ""
        if isinstance(headers, dict):
            accept = headers.get("accept", headers.get("Accept", ""))

        if "text/html" not in accept:
            return result

        method = request_data.get("method", "GET")
        if method.upper() != "GET":
            return result

        body = result.get("body", "")
        if not isinstance(body, str):
            try:
                body = body.decode() if isinstance(body, bytes) else str(body)
            except Exception:
                return result

        content_type = ""
        resp_headers = result.get("headers", {})
        if isinstance(resp_headers, dict):
            content_type = resp_headers.get("content-type", "")

        if "application/json" in content_type:
            import json as _json
            try:
                data = _json.loads(body) if isinstance(body, str) else body
                formatted = _json.dumps(data, indent=2)
            except Exception:
                formatted = body
            path = request_data.get("path", "/")
            html = f"""<!DOCTYPE html>
<html>
<head><title>Rivex Browsable API - {path}</title>
<style>
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0;padding:20px;background:#f5f5f5; }}
h1 {{ color:#333;font-size:24px; }}
pre {{ background:#fff;border:1px solid #ddd;padding:16px;border-radius:4px;overflow-x:auto; }}
</style>
</head>
<body>
<h1>Browsable API: {path}</h1>
<pre>{formatted}</pre>
</body>
</html>"""
            result["body"] = html
            if isinstance(resp_headers, dict):
                resp_headers["content-type"] = "text/html; charset=utf-8"
                resp_headers["Content-Type"] = "text/html; charset=utf-8"

        return result
