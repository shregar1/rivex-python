import json

import pytest

from rivex.di._injection import build_handler_wrapper
from rivex.di.dependencies import Dependency, Depends


def _make_request(**overrides):
    base = {
        "method": "GET",
        "path": "/test",
        "path_params": {},
        "query_string": "",
        "headers": [],
        "body": b"",
    }
    base.update(overrides)
    return base


def _json_body(result):
    if "body_json" in result:
        return result["body_json"]
    return json.loads(result["body"])


@pytest.mark.asyncio
async def test_simple_sync_depends():
    def get_value():
        return 42

    async def handler(val: int = Depends(get_value)):
        return {"value": val}

    wrapper = build_handler_wrapper(handler, "/test", 200, False)
    result = await wrapper(_make_request())
    assert result["status"] == 200
    assert _json_body(result)["value"] == 42


@pytest.mark.asyncio
async def test_async_depends():
    async def get_value():
        return "async_result"

    async def handler(val: str = Depends(get_value)):
        return {"value": val}

    wrapper = build_handler_wrapper(handler, "/test", 200, False)
    result = await wrapper(_make_request())
    assert _json_body(result)["value"] == "async_result"


@pytest.mark.asyncio
async def test_depends_with_request():
    from rivex.http.requests import Request

    def get_token(request: Request):
        return request.header("authorization", "none")

    async def handler(token: str = Depends(get_token)):
        return {"token": token}

    wrapper = build_handler_wrapper(handler, "/test", 200, False)
    result = await wrapper(_make_request(headers=[("authorization", "Bearer xyz")]))
    assert _json_body(result)["token"] == "Bearer xyz"


@pytest.mark.asyncio
async def test_class_dependency_type_with_request():
    from rivex.http.requests import Request

    class CurrentUser:
        async def __call__(self, request: Request):
            return {"token": request.header("authorization", "none")}

    async def handler(user: dict = Depends(CurrentUser)):
        return user

    wrapper = build_handler_wrapper(handler, "/test", 200, False)
    result = await wrapper(_make_request(headers=[("authorization", "Bearer class")]))
    assert _json_body(result)["token"] == "Bearer class"


@pytest.mark.asyncio
async def test_dependency_base_resolve_method():
    from rivex.http.requests import Request

    class TenantDependency(Dependency):
        def resolve(self, request: Request):
            return request.header("x-tenant", "public")

    async def handler(tenant: str = Depends(TenantDependency)):
        return {"tenant": tenant}

    wrapper = build_handler_wrapper(handler, "/test", 200, False)
    result = await wrapper(_make_request(headers=[("x-tenant", "acme")]))
    assert _json_body(result)["tenant"] == "acme"


@pytest.mark.asyncio
async def test_class_dependency_instance_with_nested_depends():
    def get_prefix():
        return "tenant"

    class HeaderDependency:
        def __call__(self, prefix: str = Depends(get_prefix)):
            return f"{prefix}-42"

    async def handler(value: str = Depends(HeaderDependency())):
        return {"value": value}

    wrapper = build_handler_wrapper(handler, "/test", 200, False)
    result = await wrapper(_make_request())
    assert _json_body(result)["value"] == "tenant-42"


@pytest.mark.asyncio
async def test_nested_depends():
    def get_config():
        return {"db_url": "postgres://localhost/mydb"}

    def get_db(config: dict = Depends(get_config)):
        return f"connected to {config['db_url']}"

    async def handler(db: str = Depends(get_db)):
        return {"db": db}

    wrapper = build_handler_wrapper(handler, "/test", 200, False)
    result = await wrapper(_make_request())
    body = _json_body(result)
    assert "postgres://localhost/mydb" in body["db"]


@pytest.mark.asyncio
async def test_depends_caching():
    call_count = 0

    def expensive():
        nonlocal call_count
        call_count += 1
        return call_count

    async def handler(a: int = Depends(expensive), b: int = Depends(expensive)):
        return {"a": a, "b": b}

    wrapper = build_handler_wrapper(handler, "/test", 200, False)
    result = await wrapper(_make_request())
    body = _json_body(result)
    assert body["a"] == body["b"]
    assert call_count == 1


@pytest.mark.asyncio
async def test_depends_no_cache():
    call_count = 0

    def counter():
        nonlocal call_count
        call_count += 1
        return call_count

    async def handler(
        a: int = Depends(counter, use_cache=False),
        b: int = Depends(counter, use_cache=False),
    ):
        return {"a": a, "b": b}

    wrapper = build_handler_wrapper(handler, "/test", 200, False)
    result = await wrapper(_make_request())
    body = _json_body(result)
    assert body["a"] != body["b"]
    assert call_count == 2


@pytest.mark.asyncio
async def test_depends_with_path_and_query():
    def get_multiplier():
        return 10

    async def handler(name: str, factor: int = Depends(get_multiplier), repeat: int = 1):
        return {"result": f"{name} x{factor}", "repeat": repeat}

    wrapper = build_handler_wrapper(handler, "/test/{name}", 200, False)
    result = await wrapper(
        _make_request(
            path="/test/hello",
            path_params={"name": "hello"},
            query_string="repeat=3",
        )
    )
    body = _json_body(result)
    assert body["result"] == "hello x10"
    assert body["repeat"] == 3


@pytest.mark.asyncio
async def test_dependency_receives_path_query_and_request_url():
    from rivex.http.requests import Request

    def audit_context(item_id: int, verbose: bool, request: Request):
        return {
            "item_id": item_id,
            "verbose": verbose,
            "url": request.url,
        }

    async def handler(context: dict = Depends(audit_context)):
        return context

    wrapper = build_handler_wrapper(handler, "/items/{item_id}", 200, False)
    result = await wrapper(
        _make_request(
            path="/items/42",
            path_params={"item_id": "42"},
            query_string="verbose=true",
        )
    )

    body = _json_body(result)
    assert body == {
        "item_id": 42,
        "verbose": True,
        "url": "/items/42?verbose=true",
    }


@pytest.mark.asyncio
async def test_class_dependency_receives_request_mapping_params():
    class ItemRepository:
        def resolve(self, item_id: int, include_deleted: bool = False):
            return {"item_id": item_id, "include_deleted": include_deleted}

    async def handler(repo_result: dict = Depends(ItemRepository)):
        return repo_result

    wrapper = build_handler_wrapper(handler, "/items/{item_id}", 200, False)
    result = await wrapper(
        _make_request(
            path="/items/7",
            path_params={"item_id": "7"},
            query_string="include_deleted=true",
        )
    )

    body = _json_body(result)
    assert body["item_id"] == 7
    assert body["include_deleted"] is True


@pytest.mark.asyncio
async def test_dependency_missing_required_parameter_returns_422():
    def needs_query(required: str):
        return required

    async def handler(value: str = Depends(needs_query)):
        return {"value": value}

    wrapper = build_handler_wrapper(handler, "/test", 200, False)
    result = await wrapper(_make_request())
    body = json.loads(result["body"])

    assert result["status"] == 422
    assert body["detail"] == "Missing required dependency parameter: required"


def test_depends_repr():
    def my_func():
        pass

    d = Depends(my_func)
    assert "my_func" in repr(d)
