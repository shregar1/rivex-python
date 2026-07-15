from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit

import rivex_core
from rivex.core._injection import build_handler_wrapper
from rivex.core.applications import _run_coroutine_sync


@dataclass
class TestResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.content)


class TestClient:
    __test__ = False

    def __init__(self, app: Any):
        self.app = app
        self._lifespan_state = None
        self._sync_app: rivex_core.RivexSyncApp | None = None
        self._mw_instances: list | None = None
        self._route_mw_cache: dict[int, list] = {}

    def __enter__(self) -> TestClient:
        self._lifespan_state = self.app._enter_lifespan()
        self.app._run_hooks(self.app._startup_hooks)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.app._run_hooks(self.app._shutdown_hooks)
        self.app._exit_lifespan(self._lifespan_state)
        self._lifespan_state = None

    def get(self, url: str, **kwargs: Any) -> TestResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> TestResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> TestResponse:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> TestResponse:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> TestResponse:
        return self.request("DELETE", url, **kwargs)

    def websocket_connect(self, url: str, headers: dict | None = None):
        return _TestWebSocket(self.app, url, headers or {})

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        content: bytes | str | None = None,
        follow_redirects: bool = False,
        max_redirects: int = 20,
    ) -> TestResponse:
        request_data = self._build_request(
            method.upper(), url, headers, params, json, data, content
        )
        sync_app = self._get_sync_app()
        fallback = self.app._fallback_handler

        async def _dispatch(req_data: dict) -> dict:
            result = sync_app.dispatch(req_data)
            if asyncio.iscoroutine(result):
                result = await result

            if isinstance(result, dict):
                status = result.get("status", 0)
                if status == 404 and fallback is not None:
                    from rivex.core.requests import Request

                    request = Request._from_raw(req_data)
                    fb_result = fallback(request)
                    if asyncio.iscoroutine(fb_result):
                        fb_result = await fb_result
                    if isinstance(fb_result, dict):
                        return fb_result
                    from rivex.core.responses import Response

                    if isinstance(fb_result, Response):
                        return fb_result._to_raw()
                    resp: dict = fb_result
                    return resp

            if isinstance(result, dict) and "body_json" in result:
                result = dict(result)
                result["body"] = json_module_dumps(result.pop("body_json"))
            resp_out: dict = result
            return resp_out

        outer_chain = _dispatch
        for mw in reversed(self._get_mw_instances()):
            inner = outer_chain

            async def _wrap(req_data: dict, *, _mw: Any = mw, _next: Any = inner) -> dict:
                result = _mw.process(req_data, _next)
                if asyncio.iscoroutine(result):
                    result = await result
                resp: dict = result
                return resp

            outer_chain = _wrap

        raw = _run_coroutine_sync(outer_chain(request_data))

        # Optionally follow 3xx redirects (off by default, matching the prior
        # behaviour of returning the redirect response as-is). 303 — and 301/302
        # from a non-GET/HEAD — degrade to GET without a body, per the usual
        # browser/httpx semantics; 307/308 replay the method and body.
        if follow_redirects:
            redirects = 0
            cur_method = method.upper()
            while raw.get("status") in (301, 302, 303, 307, 308) and redirects < max_redirects:
                location = next(
                    (v for k, v in raw.get("headers", []) if k.lower() == "location"), None
                )
                if not location:
                    break
                redirects += 1
                if raw["status"] in (301, 302, 303) and cur_method not in ("GET", "HEAD"):
                    cur_method, nxt_json, nxt_data, nxt_content = "GET", None, None, None
                else:
                    nxt_json, nxt_data, nxt_content = json, data, content
                next_data = self._build_request(
                    cur_method, location, headers, None, nxt_json, nxt_data, nxt_content
                )
                raw = asyncio.run(outer_chain(next_data))

        return self._to_response(raw)

    def _get_sync_app(self) -> rivex_core.RivexSyncApp:
        if self._sync_app is not None:
            return self._sync_app

        sync_app = rivex_core.RivexSyncApp()
        dep_overrides = self.app.dependency_overrides if self.app.dependency_overrides else None

        for record in self.app._routes:
            merged_exc_handlers = None
            app_exc = self.app._exception_handlers or {}
            route_exc = record.exception_handlers or {}
            if app_exc or route_exc:
                merged_exc_handlers = dict(app_exc)
                merged_exc_handlers.update(route_exc)

            wrapper = build_handler_wrapper(
                record.endpoint,
                record.path,
                record.status_code,
                self.app.debug,
                merged_exc_handlers,
                record.response_model,
                dep_overrides,
                validate_response=record.validate_response,
            )

            route_mw_instances = None
            if record.middleware:
                route_mw_instances = self._get_route_mw_instances(record.middleware)

            if route_mw_instances:
                chain = wrapper
                for mw in reversed(route_mw_instances):
                    inner = chain

                    async def _wrap(rd: dict, *, _mw: Any = mw, _next: Any = inner) -> dict:
                        result = _mw.process(rd, _next)
                        if asyncio.iscoroutine(result):
                            result = await result
                        resp: dict = result
                        return resp

                    chain = _wrap
                handler = chain
            else:
                handler = wrapper

            host = getattr(record, "host", None)
            sync_app.add_route(record.method, record.path, handler, host=host)

        _mount_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
        for mount_path, mount_app in self.app._mounts:
            if hasattr(mount_app, "_routes"):
                continue
            prefix = mount_path.rstrip("/")
            catch_all = prefix + "/{path:path}"

            async def _mount_handler(
                request_data: dict,
                *,
                _app: Any = mount_app,
                _prefix: str = prefix,
            ) -> dict:
                original = request_data.get("path", "/")
                request_data = dict(request_data)
                request_data["path"] = original[len(_prefix):] or "/"
                result: dict = await _app(request_data)
                return result

            for method in _mount_methods:
                try:
                    sync_app.add_route(method, catch_all, _mount_handler)
                except Exception:
                    pass

            try:
                sync_app.add_route("GET", mount_path, _mount_handler)
            except Exception:
                pass

        if self.app.asyncapi_url and self.app._ws_routes:
            self._register_test_asyncapi(sync_app)

        liveness_bytes = b'{"status":"healthy"}'
        async def _k8s_handler(request_data: dict) -> dict:
            return {
                "status": 200,
                "headers": [("content-type", "application/json")],
                "body": liveness_bytes,
            }
        if self.app.liveness_url:
            sync_app.add_route("GET", self.app.liveness_url, _k8s_handler)
        if self.app.readiness_url:
            sync_app.add_route("GET", self.app.readiness_url, _k8s_handler)

        self._sync_app = sync_app
        return sync_app

    def _register_test_asyncapi(self, sync_app: Any) -> None:
        from rivex.openapi.asyncapi import build_asyncapi_html, generate_asyncapi

        spec = generate_asyncapi(
            title=self.app.title,
            version=self.app.version,
            description=self.app.description,
            ws_routes=self.app._ws_routes,
            servers=self.app.servers,
        )
        spec_bytes = json.dumps(spec, indent=2).encode("utf-8")

        async def handler(request_data: dict) -> dict:
            return {
                "status": 200,
                "headers": [("content-type", "application/json")],
                "body": spec_bytes,
            }

        sync_app.add_route("GET", self.app.asyncapi_url, handler)

        if self.app.asyncapi_docs_url:
            html = build_asyncapi_html(
                self.app.asyncapi_url,
                title=f"{self.app.title} — AsyncAPI",
            )

            async def docs_handler(request_data: dict) -> dict:
                return {
                    "status": 200,
                    "headers": [("content-type", "text/html; charset=utf-8")],
                    "body": html.encode("utf-8"),
                }

            sync_app.add_route("GET", self.app.asyncapi_docs_url, docs_handler)

    def _get_mw_instances(self) -> list:
        if self._mw_instances is None:
            instances = [cls(**kwargs) for cls, kwargs in self.app._middleware]
            hook_cls = self.app._build_hook_middleware()
            if hook_cls is not None:
                instances.insert(0, hook_cls()())
            self._mw_instances = instances
        return self._mw_instances

    def _get_route_mw_instances(self, mw_list: list[tuple[type, dict]]) -> list:
        key = id(tuple(mw_list))
        if key not in self._route_mw_cache:
            self._route_mw_cache[key] = [cls(**kwargs) for cls, kwargs in mw_list]
        return self._route_mw_cache[key]

    def _build_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        params: dict[str, Any] | None,
        body_json: Any,
        data: Any,
        content: bytes | str | None,
    ) -> dict:
        split = urlsplit(url)
        path = split.path or "/"
        query = split.query
        if params:
            extra = urlencode(params, doseq=True)
            query = f"{query}&{extra}" if query else extra

        header_items = [(k.lower(), v) for k, v in (headers or {}).items()]
        body = b""
        if body_json is not None:
            body = json_module_dumps(body_json)
            header_items.append(("content-type", "application/json"))
        elif data is not None:
            body = (
                urlencode(data, doseq=True).encode("utf-8")
                if isinstance(data, dict)
                else str(data).encode("utf-8")
            )
            header_items.append(("content-type", "application/x-www-form-urlencoded"))
        elif content is not None:
            body = content.encode("utf-8") if isinstance(content, str) else content

        return {
            "method": method,
            "path": path,
            "path_params": {},
            "query_string": query,
            "headers": header_items,
            "body": body,
        }

    def _to_response(self, raw: dict) -> TestResponse:
        stream_iter = raw.get("_stream_iter")
        if stream_iter is not None:
            body = self._collect_stream(stream_iter, raw.get("_stream_async", True))
        elif "body_json" in raw:
            body = json_module_dumps(raw["body_json"])
        else:
            body = raw.get("body", b"")
        if isinstance(body, str):
            body = body.encode("utf-8")
        return TestResponse(
            status_code=raw.get("status", 200),
            headers={k.lower(): v for k, v in raw.get("headers", [])},
            content=body,
        )

    @staticmethod
    def _collect_stream(stream_iter: Any, is_async: bool) -> bytes:
        chunks: list[bytes] = []
        if is_async:

            async def _collect() -> list[bytes]:
                result: list[bytes] = []
                async for chunk in stream_iter:
                    if isinstance(chunk, str):
                        result.append(chunk.encode("utf-8"))
                    elif isinstance(chunk, bytes):
                        result.append(chunk)
                    else:
                        result.append(str(chunk).encode("utf-8"))
                return result

            chunks = asyncio.run(_collect())
        else:
            for chunk in stream_iter:
                if isinstance(chunk, str):
                    chunks.append(chunk.encode("utf-8"))
                elif isinstance(chunk, bytes):
                    chunks.append(chunk)
                else:
                    chunks.append(str(chunk).encode("utf-8"))
        return b"".join(chunks)


class _TestWebSocket:
    def __init__(self, app: Any, url: str, headers: dict):
        self.app = app
        self.url = url
        self.headers = headers
        self._sent: list = []
        self._received: list = []
        self._handler = None
        self._ws_func = None

    def __enter__(self):
        for path, handler in getattr(self.app, "_ws_routes", []):
            if rivex_core.match_path(path, self.url) is not None:
                self._ws_func = handler
                break
        return self

    def __exit__(self, *args):
        pass

    def send_text(self, data: str):
        self._sent.append(("text", data))

    def send_json(self, data: Any):
        self._sent.append(("json", data))

    def receive_text(self) -> str:
        if self._received:
            text: str = self._received.pop(0)
            return text
        return ""

    def receive_json(self) -> Any:
        text = self.receive_text()
        return json.loads(text) if text else None


def json_module_dumps(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8")
