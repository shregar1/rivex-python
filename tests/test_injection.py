import json

import pytest

from rivex import HTTPException
from rivex._injection import _coerce, _normalize_response, build_handler_wrapper


def _json_body(result):
    if "body_json" in result:
        return result["body_json"]
    return json.loads(result["body"])


def test_coerce_int():
    assert _coerce("42", int) == 42


def test_coerce_float():
    assert _coerce("3.14", float) == 3.14


def test_coerce_bool_true():
    assert _coerce("true", bool) is True


def test_coerce_bool_false():
    assert _coerce("false", bool) is False


def test_coerce_str():
    assert _coerce("hello", str) == "hello"


def test_coerce_bad_int_raises_422_not_valueerror():
    # A non-numeric or out-of-range int param must be a 422, not a bare
    # ValueError that surfaces as a 500 (regression: this used to leak from the
    # unguarded _extract_path / _extract_query call sites).
    for bad in ("abc", "1.5", "99999999999999999999999999", ""):
        with pytest.raises(HTTPException) as exc:
            _coerce(bad, int)
        assert exc.value.status_code == 422


def test_coerce_bad_float_raises_422():
    for bad in ("abc", "", "inf", "nan"):
        with pytest.raises(HTTPException) as exc:
            _coerce(bad, float)
        assert exc.value.status_code == 422


def test_normalize_dict():
    result = _normalize_response({"key": "value"}, 200)
    assert result["status"] == 200
    body = json.loads(result["body"])
    assert body == {"key": "value"}


def test_normalize_string():
    result = _normalize_response("hello", 200)
    assert result["status"] == 200
    assert result["body"] == b"hello"
    assert ("content-type", "text/plain; charset=utf-8") in result["headers"]


def test_normalize_none():
    result = _normalize_response(None, 200)
    assert result["status"] == 204
    assert result["body"] == b""


def test_normalize_list():
    result = _normalize_response([1, 2, 3], 200)
    assert result["status"] == 200
    assert json.loads(result["body"]) == [1, 2, 3]


def test_normalize_tuple_status():
    result = _normalize_response((201, {"created": True}), 200)
    assert result["status"] == 201


def test_normalize_pydantic():
    from pydantic import BaseModel

    class Item(BaseModel):
        name: str
        price: float

    item = Item(name="Widget", price=9.99)
    result = _normalize_response(item, 200)
    assert result["status"] == 200
    body = json.loads(result["body"])
    assert body["name"] == "Widget"
    assert body["price"] == 9.99


@pytest.mark.asyncio
async def test_handler_wrapper_path_and_query():
    async def handler(name: str, age: int = 25):
        return {"name": name, "age": age}

    wrapper = build_handler_wrapper(handler, "/users/{name}", 200, False)
    result = await wrapper(
        {
            "method": "GET",
            "path": "/users/alice",
            "path_params": {"name": "alice"},
            "query_string": "age=30",
            "headers": [],
            "body": b"",
        }
    )
    assert result["status"] == 200
    body = _json_body(result)
    assert body["name"] == "alice"
    assert body["age"] == 30


@pytest.mark.asyncio
async def test_handler_wrapper_body_model():
    from pydantic import BaseModel

    class UserCreate(BaseModel):
        name: str
        email: str

    async def handler(user: UserCreate):
        return {"name": user.name, "email": user.email}

    wrapper = build_handler_wrapper(handler, "/users", 201, False)
    result = await wrapper(
        {
            "method": "POST",
            "path": "/users",
            "path_params": {},
            "query_string": "",
            "headers": [("content-type", "application/json")],
            "body": b'{"name": "Bob", "email": "bob@example.com"}',
        }
    )
    assert result["status"] == 201
    body = _json_body(result)
    assert body["name"] == "Bob"
    assert body["email"] == "bob@example.com"


@pytest.mark.asyncio
async def test_post_handler_with_no_body_param_accepts_empty_body():
    """Handlers with no body parameter (e.g. ``POST /things/{id}/restore``)
    must accept an empty request body cleanly."""
    from rivex.params import Path
    from rivex.requests import Request

    async def handler(request: Request, version_id: int = Path(ge=1)):
        return {"version_id": version_id, "method": request.method}

    wrapper = build_handler_wrapper(handler, "/items/{version_id}/restore", 200, False)
    result = await wrapper(
        {
            "method": "POST",
            "path": "/items/42/restore",
            "path_params": {"version_id": "42"},
            "query_string": "",
            "headers": [],
            "body": b"",
        }
    )
    assert result["status"] == 200
    assert _json_body(result) == {"version_id": 42, "method": "POST"}


@pytest.mark.asyncio
async def test_required_dict_body_with_empty_body_returns_422_not_500():
    """``payload: dict`` (no default) with empty body should surface a
    clean 422, not crash the codegen wrapper with a 500."""

    async def handler(payload: dict):
        return {"got": payload}

    wrapper = build_handler_wrapper(handler, "/x", 200, False)
    result = await wrapper(
        {
            "method": "POST",
            "path": "/x",
            "path_params": {},
            "query_string": "",
            "headers": [],
            "body": b"",
        }
    )
    assert result["status"] == 422


@pytest.mark.asyncio
async def test_optional_int_query_with_ge_constraint():
    """``int | None = Query(ge=1)`` must coerce *before* validating the
    ``ge`` bound, otherwise the raw query-string ``"42"`` is compared
    against ``1`` and raises ``TypeError`` from the str/int comparison.
    """
    from rivex.params import Query

    async def handler(design_id: int | None = Query(default=None, ge=1)):
        return {"design_id": design_id, "is_int": isinstance(design_id, int)}

    wrapper = build_handler_wrapper(handler, "/items", 200, False)
    result = await wrapper(
        {
            "method": "GET",
            "path": "/items",
            "path_params": {},
            "query_string": "design_id=42",
            "headers": [],
            "body": b"",
        }
    )
    assert result["status"] == 200
    body = _json_body(result)
    assert body == {"design_id": 42, "is_int": True}


@pytest.mark.asyncio
async def test_optional_int_query_absent_uses_default():
    from rivex.params import Query

    async def handler(design_id: int | None = Query(default=None, ge=1)):
        return {"design_id": design_id}

    wrapper = build_handler_wrapper(handler, "/items", 200, False)
    result = await wrapper(
        {
            "method": "GET",
            "path": "/items",
            "path_params": {},
            "query_string": "",
            "headers": [],
            "body": b"",
        }
    )
    assert result["status"] == 200
    assert _json_body(result) == {"design_id": None}


@pytest.mark.asyncio
async def test_optional_int_query_violates_ge_bound():
    from rivex.params import Query

    async def handler(design_id: int | None = Query(default=None, ge=10)):
        return {"design_id": design_id}

    wrapper = build_handler_wrapper(handler, "/items", 200, False)
    result = await wrapper(
        {
            "method": "GET",
            "path": "/items",
            "path_params": {},
            "query_string": "design_id=3",
            "headers": [],
            "body": b"",
        }
    )
    assert result["status"] == 422


@pytest.mark.asyncio
async def test_handler_wrapper_sync_function():
    def handler(x: int = 1):
        return {"value": x * 2}

    wrapper = build_handler_wrapper(handler, "/double", 200, False)
    result = await wrapper(
        {
            "method": "GET",
            "path": "/double",
            "path_params": {},
            "query_string": "x=5",
            "headers": [],
            "body": b"",
        }
    )
    assert result["status"] == 200
    body = _json_body(result)
    assert body["value"] == 10


@pytest.mark.asyncio
async def test_handler_wrapper_http_exception():
    from rivex.exceptions import HTTPException

    async def handler():
        raise HTTPException(404, detail="not found")

    wrapper = build_handler_wrapper(handler, "/fail", 200, False)
    result = await wrapper(
        {
            "method": "GET",
            "path": "/fail",
            "path_params": {},
            "query_string": "",
            "headers": [],
            "body": b"",
        }
    )
    assert result["status"] == 404
    body = json.loads(result["body"])
    assert body["detail"] == "not found"


def test_coerce_float_rejects_inf():
    with pytest.raises(HTTPException):
        _coerce("inf", float)


def test_coerce_float_rejects_nan():
    with pytest.raises(HTTPException):
        _coerce("nan", float)


def test_coerce_float_rejects_negative_inf():
    with pytest.raises(HTTPException):
        _coerce("-inf", float)


@pytest.mark.asyncio
async def test_missing_required_body_returns_422():
    from pydantic import BaseModel

    class Item(BaseModel):
        name: str

    async def handler(item: Item):
        return {"name": item.name}

    wrapper = build_handler_wrapper(handler, "/items", 200, False)
    result = await wrapper(
        {
            "method": "POST",
            "path": "/items",
            "path_params": {},
            "query_string": "",
            "headers": [("content-type", "application/json")],
            "body": b"",
        }
    )
    assert result["status"] == 422
    body = json.loads(result["body"])
    assert "required" in body["detail"].lower() or "missing" in body["detail"].lower()
