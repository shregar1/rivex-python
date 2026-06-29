"""End-to-end tests verifying that all three body-schema backends
(Pydantic, Schemax, Marshmallow) work uniformly as type annotations in
Rivex controller definitions — for ``Body()``, ``Form()``, ``Query()``,
``Path()``, ``Header()``, and ``Cookie()`` parameters.

The key guarantee from this suite:

    @app.post("/items")
    async def create(item: Body(SomePydanticModel)): ...         # works
    async def create(item: Body(SomeSchemaxMessage)): ...        # works
    async def create(item: Body(SomeMarshmallowSchema)): ...     # works
    async def create(item: Form(SomePydanticModel)): ...         # works
    async def create(item: Form(SomeSchemaxMessage)): ...        # works
    async def create(item: Form(SomeMarshmallowSchema)): ...     # works

The ``Body()`` and ``Form()`` paths dispatch through
:func:`rivex._bodies.coerce_body`, which knows about every backend.
The scalar sources (``Query``, ``Path``, ``Header``, ``Cookie``) only
take string-coerced values and so are backend-agnostic — but we still
exercise them to make sure the plumbing stays consistent.

NOTE: the test classes are defined at *module* level, not inside test
functions.  Python's :func:`typing.get_type_hints` resolves annotations
against the enclosing module's globals; a class defined inside a test
function is invisible to that lookup, which causes the framework to
fall back to ``str`` and skip body coercion entirely.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# conftest.py stubs ``rivex_core`` so the package imports cleanly even
# without the compiled Rust extension.
from rivex._injection import build_handler_wrapper  # noqa: E402
from rivex.params import Body, Cookie, Header, Path, Query  # noqa: E402
from rivex.uploads import File, Form, MultipartBody, UploadFile  # noqa: E402

# ---------------------------------------------------------------------------
# Per-backend test models (module-level so type-hint resolution finds them)
# ---------------------------------------------------------------------------


def _make_pyd_item_class():
    from pydantic import BaseModel

    class PydItem(BaseModel):
        title: str
        qty: int = 1

    return PydItem


def _make_schemax_item_class():
    from schemax.idl.codegen import render
    from schemax.idl.parser import parse
    from schemax.idl.runtime import Message

    src = """
package test.v1;

message SchemaxItem {
    string title = 1;
    int64 qty = 2;
}
"""
    file = parse(src)
    code = render(file)
    namespace: dict[str, Any] = {"Message": Message}
    exec(code, namespace)
    return namespace["SchemaxItem"]


def _make_marshmallow_item_class():
    from marshmallow import Schema, fields

    class MarshmallowItemSchema(Schema):
        title = fields.String(required=True)
        qty = fields.Integer(load_default=1)

    return MarshmallowItemSchema


# Cache so we don't rebuild the same class on every test (and so type-hint
# resolution finds the same object each time).  We also bind the classes
# at module level so ``get_type_hints(handler)`` can find them — Python
# resolves annotations against the *enclosing module's* globals, so a
# class hidden inside a factory function is invisible to the lookup.
# Use ``exec`` to put each class into the module namespace under its
# real name, so type-hint resolution finds it by name.
PydItem = _make_pyd_item_class()
SchemaxItem = _make_schemax_item_class()
MarshSchema = _make_marshmallow_item_class()

# Re-bind under the original class names so handler annotations like
# ``item: PydItem`` resolve to the same object that lives in the
# factory function's closure.
globals()["PydItem"] = PydItem
globals()["SchemaxItem"] = SchemaxItem
globals()["MarshSchema"] = MarshSchema


# ---------------------------------------------------------------------------
# Tiny request helper
# ---------------------------------------------------------------------------


def _request(
    *,
    method: str,
    path: str,
    body: bytes = b"",
    content_type: str = "application/json",
    query: str = "",
    path_params: dict[str, str] | None = None,
    headers: list[tuple[str, str]] | None = None,
    multipart_fields: dict[str, list[bytes]] | None = None,
):
    req: dict[str, Any] = {
        "method": method,
        "path": path,
        "path_params": path_params or {},
        "query_string": query,
        "headers": [("content-type", content_type)] + (headers or []),
        "body": body,
    }
    if multipart_fields is not None:
        req["multipart_fields"] = multipart_fields
    return req


def _json_of(result: dict) -> dict:
    if "body_json" in result:
        return result["body_json"]
    return json.loads(result["body"])


# ---------------------------------------------------------------------------
# Body() — Pydantic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_with_pydantic_model():
    pytest.importorskip("pydantic", reason="pydantic not installed")

    async def handler(item: PydItem):
        return {"title": item.title, "qty": item.qty}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b'{"title": "Widget", "qty": 3}',
        )
    )
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Widget", "qty": 3}


@pytest.mark.asyncio
async def test_body_pydantic_validation_error_returns_422():
    pytest.importorskip("pydantic", reason="pydantic not installed")

    async def handler(item: PydItem):
        return {"ok": True}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b'{"qty": 3}',  # missing required `title`
        )
    )
    assert result["status"] == 422


# ---------------------------------------------------------------------------
# Body() — Schemax
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_with_schemax_message():
    pytest.importorskip("schemax", reason="schemax not installed")

    async def handler(item: SchemaxItem):
        d = item.to_dict() if hasattr(item, "to_dict") else {}
        # Schemax stores field values keyed by tag number — extract title.
        return {"raw": json.dumps(d, default=str), "title": d.get("1") or d.get("title")}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b'{"title": "Gadget", "qty": 7}',
        )
    )
    assert result["status"] == 201


# ---------------------------------------------------------------------------
# Body() — Marshmallow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_with_marshmallow_schema():
    pytest.importorskip("marshmallow", reason="marshmallow not installed")

    async def handler(item: MarshSchema):
        return {"title": item["title"], "qty": item["qty"]}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b'{"title": "Gizmo", "qty": 2}',
        )
    )
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Gizmo", "qty": 2}


@pytest.mark.asyncio
async def test_body_marshmallow_validation_error_returns_422():
    pytest.importorskip("marshmallow", reason="marshmallow not installed")

    async def handler(item: MarshSchema):
        return {"ok": True}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    # Missing required `title` field.
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b'{"qty": 3}',
        )
    )
    assert result["status"] == 422


# ---------------------------------------------------------------------------
# Body() marker WITH a DTO type hint — must coerce to the DTO, not pass
# the raw dict through.  Regression test for the bug where
# ``payload: MyDto = Body()`` returned the JSON ``dict`` (so the handler
# saw ``payload['field']`` work but ``payload.field`` blow up).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_marker_with_pydantic_dto_returns_instance():
    pytest.importorskip("pydantic", reason="pydantic not installed")

    captured: dict[str, Any] = {}

    async def handler(payload: PydItem = Body()):
        captured["type"] = type(payload).__name__
        captured["title"] = payload.title  # attribute access — would fail on a dict
        captured["qty"] = payload.qty
        return {"ok": True}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b'{"title": "Widget", "qty": 3}',
        )
    )
    assert result["status"] == 201
    assert captured == {"type": "PydItem", "title": "Widget", "qty": 3}


@pytest.mark.asyncio
async def test_body_marker_with_dto_validates_payload():
    """Body() + DTO must still surface validation errors as 422."""
    pytest.importorskip("pydantic", reason="pydantic not installed")

    async def handler(payload: PydItem = Body()):
        return {"ok": True}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(method="POST", path="/items", body=b'{"qty": 3}'),
    )
    assert result["status"] == 422


@pytest.mark.asyncio
async def test_body_marker_embed_with_dto_coerces_sub_payload():
    """``Body(embed=True)`` with a DTO hint pulls the named field out of
    the JSON envelope and coerces it to the DTO."""
    pytest.importorskip("pydantic", reason="pydantic not installed")

    async def handler(payload: PydItem = Body(embed=True)):
        return {"title": payload.title, "qty": payload.qty}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b'{"payload": {"title": "Gizmo", "qty": 4}}',
        )
    )
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Gizmo", "qty": 4}


# ---------------------------------------------------------------------------
# Body() — plain dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_with_plain_dict():
    async def handler(item: dict):
        return {"echo": item}

    wrapper = build_handler_wrapper(handler, "/items", 200, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b'{"any": "thing", "n": 1}',
        )
    )
    assert result["status"] == 200
    assert _json_of(result) == {"echo": {"any": "thing", "n": 1}}


# ---------------------------------------------------------------------------
# Form() — Pydantic / Schemax / Marshmallow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_form_with_pydantic_model():
    pytest.importorskip("pydantic", reason="pydantic not installed")

    async def handler(item: PydItem = Form()):
        return {"title": item.title, "qty": item.qty}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b"title=Widget&qty=3",
            content_type="application/x-www-form-urlencoded",
        )
    )
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Widget", "qty": 3}


@pytest.mark.asyncio
async def test_form_with_marshmallow_schema():
    pytest.importorskip("marshmallow", reason="marshmallow not installed")

    async def handler(item: MarshSchema = Form()):
        return {"title": item["title"], "qty": item["qty"]}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b"title=Doorbell&qty=4",
            content_type="application/x-www-form-urlencoded",
        )
    )
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Doorbell", "qty": 4}


@pytest.mark.asyncio
async def test_form_with_schemax_message():
    pytest.importorskip("schemax", reason="schemax not installed")

    async def handler(item: SchemaxItem = Form()):
        d = item.to_dict() if hasattr(item, "to_dict") else {}
        return {"raw": json.dumps(d, default=str)}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=b"title=Lamp&qty=5",
            content_type="application/x-www-form-urlencoded",
        )
    )
    assert result["status"] == 201


@pytest.mark.asyncio
async def test_form_with_multipart_pydantic_model():
    pytest.importorskip("pydantic", reason="pydantic not installed")

    async def handler(item: PydItem = Form()):
        return {"title": item.title, "qty": item.qty}

    # Build a real multipart body so the framework's ``parse_multipart``
    # can decode it on the way through the wrapper.
    boundary = "----X"
    body = (
        b"------X\r\n"
        b'Content-Disposition: form-data; name="title"\r\n\r\n'
        b"Lamp\r\n"
        b"------X\r\n"
        b'Content-Disposition: form-data; name="qty"\r\n\r\n'
        b"5\r\n"
        b"------X--\r\n"
    )

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/items",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
    )
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Lamp", "qty": 5}


# ---------------------------------------------------------------------------
# Form() — scalar coercion (backend-agnostic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_form_scalar_int():
    from rivex.uploads import Form

    async def handler(qty: int = Form()):
        return {"qty": qty * 2}

    wrapper = build_handler_wrapper(handler, "/x", 200, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/x",
            body=b"qty=21",
            content_type="application/x-www-form-urlencoded",
        )
    )
    assert result["status"] == 200
    assert _json_of(result) == {"qty": 42}


@pytest.mark.asyncio
async def test_form_scalar_bool():
    from rivex.uploads import Form

    async def handler(flag: bool = Form()):
        return {"flag": flag}

    wrapper = build_handler_wrapper(handler, "/x", 200, False)
    result = await wrapper(
        _request(
            method="POST",
            path="/x",
            body=b"flag=true",
            content_type="application/x-www-form-urlencoded",
        )
    )
    assert result["status"] == 200
    assert _json_of(result) == {"flag": True}


# ---------------------------------------------------------------------------
# Query() / Path() / Header() / Cookie() — scalar coercion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_scalar_int():
    async def handler(limit: int = Query()):
        return {"limit": limit}

    wrapper = build_handler_wrapper(handler, "/list", 200, False)
    result = await wrapper(_request(method="GET", path="/list", query="limit=25"))
    assert result["status"] == 200
    assert _json_of(result) == {"limit": 25}


@pytest.mark.asyncio
async def test_path_scalar_int():
    async def handler(item_id: int = Path()):
        return {"id": item_id}

    wrapper = build_handler_wrapper(handler, "/items/{item_id}", 200, False)
    result = await wrapper(
        _request(
            method="GET",
            path="/items/42",
            path_params={"item_id": "42"},
        )
    )
    assert result["status"] == 200
    assert _json_of(result) == {"id": 42}


@pytest.mark.asyncio
async def test_header_scalar_str():
    async def handler(trace: str = Header()):
        return {"trace": trace}

    wrapper = build_handler_wrapper(handler, "/x", 200, False)
    result = await wrapper(
        _request(
            method="GET",
            path="/x",
            headers=[("trace", "abc-123")],
        )
    )
    assert result["status"] == 200
    assert _json_of(result) == {"trace": "abc-123"}


@pytest.mark.asyncio
async def test_cookie_scalar_str():
    async def handler(session: str = Cookie()):
        return {"session": session}

    wrapper = build_handler_wrapper(handler, "/x", 200, False)
    result = await wrapper(
        _request(
            method="GET",
            path="/x",
            headers=[("cookie", "session=xyz")],
        )
    )
    assert result["status"] == 200
    assert _json_of(result) == {"session": "xyz"}


# ---------------------------------------------------------------------------
# Sanity: detect each backend via body_schema()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Multipart + DTO + File — canonical "metadata + binary file" recipe
# ---------------------------------------------------------------------------


def _build_multipart(
    fields: list[tuple[str, str, bytes, str | None]],
    boundary: str = "----WebKitFormBoundary7MA4YWxkTrZu0gW",
) -> tuple[bytes, str]:
    """Build a minimal multipart/form-data body from ``fields``.

    Each ``fields`` entry is ``(field_name, content_type, data, filename)``.
    A ``filename`` of ``None`` marks a regular text field.
    """
    parts: list[bytes] = []
    for name, ct, data, filename in fields:
        cd = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            cd += f'; filename="{filename}"'
        head = f"--{boundary}\r\n{cd}\r\nContent-Type: {ct}\r\n\r\n".encode()
        parts.append(head + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


@pytest.mark.asyncio
async def test_multipart_dto_plus_file_handler():
    """Canonical multipart recipe: DTO from string fields + UploadFile
    from the binary part — no base64, no JSON-in-multipart, just one
    well-formed POST."""
    pytest.importorskip("pydantic", reason="pydantic not installed")

    async def handler(
        payload: PydItem = Form(),
        file: UploadFile = File(),
    ):
        return {
            "title": payload.title,
            "qty": payload.qty,
            "filename": file.filename,
            "file_size": file.size,
            "file_ct": file.content_type,
        }

    body, ct = _build_multipart(
        [
            ("title", "text/plain", b"Widget", None),
            ("qty", "text/plain", b"3", None),
            ("file", "application/octet-stream", b"BINARY-PAYLOAD-BYTES", "model.stl"),
        ]
    )
    wrapper = build_handler_wrapper(handler, "/library/models", 201, False)
    result = await wrapper(_request(method="POST", path="/library/models", body=body, content_type=ct))
    assert result["status"] == 201
    assert _json_of(result) == {
        "title": "Widget",
        "qty": 3,
        "filename": "model.stl",
        "file_size": len(b"BINARY-PAYLOAD-BYTES"),
        "file_ct": "application/octet-stream",
    }


@pytest.mark.asyncio
async def test_multipart_body_alias_is_form():
    """``MultipartBody`` is an alias for ``Form`` — same dispatch path,
    nicer name when reading code that mixes a DTO with binary files."""
    pytest.importorskip("pydantic", reason="pydantic not installed")

    assert MultipartBody is Form

    async def handler(payload: PydItem = MultipartBody(), file: UploadFile = File()):
        return {"title": payload.title, "filename": file.filename}

    body, ct = _build_multipart(
        [
            ("title", "text/plain", b"Gadget", None),
            ("qty", "text/plain", b"1", None),
            ("file", "application/octet-stream", b"x", "a.bin"),
        ]
    )
    wrapper = build_handler_wrapper(handler, "/things", 201, False)
    result = await wrapper(_request(method="POST", path="/things", body=body, content_type=ct))
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Gadget", "filename": "a.bin"}


def test_bodies_classify_all_three_backends():
    pytest.importorskip("pydantic", reason="pydantic not installed")
    pytest.importorskip("schemax", reason="schemax not installed")
    pytest.importorskip("marshmallow", reason="marshmallow not installed")

    from rivex._bodies import body_schema

    assert body_schema(PydItem) == "pydantic"
    assert body_schema(SchemaxItem) == "schemax"
    assert body_schema(MarshSchema) == "marshmallow"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
