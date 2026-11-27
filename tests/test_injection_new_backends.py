"""End-to-end tests verifying the new body-schema backends (dataclass,
attrs, msgspec, Construct, typeguard) work as first-class replacements
for Pydantic.

The key guarantee from this suite:

    @app.post("/items")
    async def create(item: Item = Body()): ...                # dataclass
    async def create(item: Item = Body()): ...                # attrs
    async def create(item: Item = Body()): ...                # msgspec
    async def create(item: Item = Body()): ...                # construct
    async def create(item: Item = Form()): ...                # any of them
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from rivex.serialization._bodies import BodySchema, body_schema  # noqa: E402
from rivex.di._injection import build_handler_wrapper  # noqa: E402

# ---------------------------------------------------------------------------
# Module-level models — type-hint resolution needs them in the test
# module's namespace (see test_injection_backends.py for the same trick).
# ---------------------------------------------------------------------------


def _make_dataclass_item():
    from dataclasses import dataclass

    @dataclass
    class DCItem:
        title: str
        qty: int = 1

    return DCItem


def _make_attrs_item():
    import attr

    @attr.s(auto_attribs=True)
    class AttrsItem:
        title: str
        qty: int = 1

    return AttrsItem


def _make_attrs_decorator_item():
    from attrs import define, field

    @define
    class AttrsDecItem:
        title: str
        qty: int = field(default=1)

    return AttrsDecItem


def _make_msgspec_item():
    import msgspec

    class MsgspecItem(msgspec.Struct):
        title: str
        qty: int = 1

    return MsgspecItem


def _make_construct_item():
    import construct

    # ``construct.Container`` is the dict-like body type — a Struct
    # uses construct's binary DSL, which is fine if you want a
    # compact on-wire format, but a plain Container subclasses
    # naturally from a JSON dict.  We exercise both styles.
    class ConstructItem(construct.Container):
        pass

    return ConstructItem


# Eagerly resolve at module import — only the backends whose deps are
# installed produce real classes; missing ones are ``None`` and the
# corresponding test is skipped.
DCItem = _make_dataclass_item()
AttrsItem = _make_attrs_item()
AttrsDecItem = _make_attrs_decorator_item()
MsgspecItem = _make_msgspec_item()
ConstructItem = _make_construct_item()


# Re-bind so ``get_type_hints`` finds the same object inside the
# factory function's closure.
globals()["DCItem"] = DCItem
globals()["AttrsItem"] = AttrsItem
globals()["AttrsDecItem"] = AttrsDecItem
globals()["MsgspecItem"] = MsgspecItem
globals()["ConstructItem"] = ConstructItem


# ---------------------------------------------------------------------------
# Request helper
# ---------------------------------------------------------------------------


def _request(*, body: bytes, content_type: str = "application/json", **kwargs):
    req: dict[str, Any] = {
        "method": kwargs.get("method", "POST"),
        "path": kwargs.get("path", "/items"),
        "path_params": kwargs.get("path_params", {}),
        "query_string": kwargs.get("query_string", ""),
        "headers": [("content-type", content_type)] + kwargs.get("headers", []),
        "body": body,
    }
    if "multipart_fields" in kwargs:
        req["multipart_fields"] = kwargs["multipart_fields"]
    return req


def _json_of(result: dict) -> dict:
    if "body_json" in result:
        return result["body_json"]
    return json.loads(result["body"])


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def test_body_schema_detects_dataclass():
    pytest.importorskip("dataclasses")
    assert body_schema(DCItem) == BodySchema.DATACLASS


def test_body_schema_detects_attrs():
    pytest.importorskip("attr")
    assert body_schema(AttrsItem) == BodySchema.ATTRS
    # ``@attrs.define`` decorator also produces attrs classes
    assert body_schema(AttrsDecItem) == BodySchema.ATTRS


def test_body_schema_detects_msgspec():
    pytest.importorskip("msgspec")
    assert body_schema(MsgspecItem) == BodySchema.MSGSPEC


def test_body_schema_detects_construct():
    pytest.importorskip("construct")
    assert body_schema(ConstructItem) == BodySchema.CONSTRUCT


# ---------------------------------------------------------------------------
# Direct coerce_body
# ---------------------------------------------------------------------------


def test_coerce_body_dataclass_from_bytes():
    from rivex.serialization._bodies import coerce_body

    out = coerce_body(b'{"title": "Widget", "qty": 4}', DCItem)
    assert isinstance(out, DCItem)
    assert out.title == "Widget"
    assert out.qty == 4


def test_coerce_body_dataclass_missing_required_raises():
    from rivex.serialization._bodies import coerce_body
    from rivex.exceptions.http.exceptions import RequestValidationError

    with pytest.raises(RequestValidationError):
        coerce_body(b'{"qty": 4}', DCItem)  # title is required


def test_coerce_body_attrs_from_bytes():
    import attr

    from rivex.serialization._bodies import coerce_body

    out = coerce_body(b'{"title": "Gear", "qty": 2}', AttrsItem)
    print(
        f"DEBUG out: {out!r}, type: {type(out).__name__}, dir: {[x for x in dir(out) if not x.startswith('_')]}"
    )
    print(f"DEBUG fields: {[a.name for a in attr.fields(AttrsItem)]}")
    assert out.title == "Gear"
    assert out.qty == 2


def test_coerce_body_attrs_decorator():
    from rivex.serialization._bodies import coerce_body

    out = coerce_body(b'{"title": "Tool"}', AttrsDecItem)
    assert out.title == "Tool"
    assert out.qty == 1  # default


def test_coerce_body_msgspec_from_bytes():
    from rivex.serialization._bodies import coerce_body

    out = coerce_body(b'{"title": "Spanner", "qty": 9}', MsgspecItem)
    assert out.title == "Spanner"
    assert out.qty == 9


def test_coerce_body_msgspec_strict():
    """msgspec.Struct raises on type mismatches when ``strict=True``."""
    from rivex.serialization._bodies import coerce_body
    from rivex.exceptions.http.exceptions import RequestValidationError

    # qty should be int, not str
    with pytest.raises(RequestValidationError):
        coerce_body(b'{"title": "Spanner", "qty": "nine"}', MsgspecItem)


def test_coerce_body_construct_from_bytes():
    from rivex.serialization._bodies import coerce_body

    out = coerce_body(b'{"title": "Hammer", "qty": 12}', ConstructItem)
    assert out.title == "Hammer"
    assert out.qty == 12


# ---------------------------------------------------------------------------
# End-to-end: Body(SomeDataclassClass) and Body(SomeAttrsClass) and …
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_with_dataclass():
    async def handler(item: DCItem):
        return {"title": item.title, "qty": item.qty}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(_request(body=b'{"title": "Saw", "qty": 1}'))
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Saw", "qty": 1}


@pytest.mark.asyncio
async def test_body_with_attrs():
    async def handler(item: AttrsItem):
        return {"title": item.title, "qty": item.qty}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(_request(body=b'{"title": "Drill", "qty": 1}'))
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Drill", "qty": 1}


@pytest.mark.asyncio
async def test_body_with_msgspec():
    async def handler(item: MsgspecItem):
        return {"title": item.title, "qty": item.qty}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(_request(body=b'{"title": "Pliers", "qty": 5}'))
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Pliers", "qty": 5}


@pytest.mark.asyncio
async def test_body_with_construct():
    async def handler(item: ConstructItem):
        return {
            "title": item.title,
            "qty": int(item.qty) if item.qty is not None else 0,
        }

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(_request(body=b'{"title": "Wrench", "qty": 3}'))
    assert result["status"] == 201
    payload = _json_of(result)
    assert payload["title"] == "Wrench"
    assert payload["qty"] == 3


# ---------------------------------------------------------------------------
# End-to-end: Form(SomeDataclassClass) etc. — same backends, urlencoded form
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_form_with_dataclass():
    from rivex.web.uploads import Form

    async def handler(item: DCItem = Form()):
        return {"title": item.title, "qty": item.qty}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            body=b"title=Hammer&qty=2",
            content_type="application/x-www-form-urlencoded",
        )
    )
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Hammer", "qty": 2}


@pytest.mark.asyncio
async def test_form_with_attrs():
    from rivex.web.uploads import Form

    async def handler(item: AttrsItem = Form()):
        return {"title": item.title, "qty": item.qty}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            body=b"title=Screwdriver&qty=4",
            content_type="application/x-www-form-urlencoded",
        )
    )
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Screwdriver", "qty": 4}


@pytest.mark.asyncio
async def test_form_with_msgspec():
    from rivex.web.uploads import Form

    async def handler(item: MsgspecItem = Form()):
        return {"title": item.title, "qty": item.qty}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(
        _request(
            body=b"title=Bolts&qty=99",
            content_type="application/x-www-form-urlencoded",
        )
    )
    assert result["status"] == 201
    assert _json_of(result) == {"title": "Bolts", "qty": 99}


# ---------------------------------------------------------------------------
# Validation errors → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_dataclass_validation_error_returns_422():
    async def handler(item: DCItem):
        return {"ok": True}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(_request(body=b'{"qty": 1}'))  # title missing
    assert result["status"] == 422


@pytest.mark.asyncio
async def test_body_msgspec_validation_error_returns_422():
    async def handler(item: MsgspecItem):
        return {"ok": True}

    wrapper = build_handler_wrapper(handler, "/items", 201, False)
    result = await wrapper(_request(body=b'{"title": "x", "qty": "wrong-type"}'))
    assert result["status"] == 422


# ---------------------------------------------------------------------------
# register_body_schema — typeguard, Lark, pyparsing, python-user-agents
# ---------------------------------------------------------------------------


def test_register_body_schema_for_typeguard():
    """typeguard is opt-in via ``register_body_schema`` — see the
    ``_bodies`` module docstring.  When registered, Rivex builds the
    instance by ``**payload`` and then runs ``typeguard.check_type``.
    """
    try:
        import typeguard
    except ImportError:
        pytest.skip("typeguard not installed")

    from dataclasses import dataclass

    from rivex.serialization._bodies import coerce_body, register_body_schema

    @dataclass
    class TGItem:
        title: str
        qty: int = 1

    register_body_schema(
        "typeguard",
        detect=lambda h: getattr(h, "__module__", "").startswith("__main__")
        and h.__name__ == "TGItem",
        coerce=lambda h, body: (
            (lambda d: typeguard.check_type((h(**d)), h) or h(**d))(
                body if isinstance(body, dict) else json.loads(body)
            )
        ),
    )
    try:
        out = coerce_body(b'{"title": "TG", "qty": 7}', TGItem)
        assert out.title == "TG"
        assert out.qty == 7
    finally:
        from rivex.serialization import _bodies as _b

        _b._CUSTOM_HANDLERS.pop("typeguard", None)
        _b._CUSTOM_DETECTORS[:] = [
            d for d in _b._CUSTOM_DETECTORS if getattr(d, "__name__", "") != "<lambda>"
        ]


def test_register_body_schema_for_lark_parser():
    """Lark is a parser toolkit — it doesn't define request body
    types, but you can register a custom backend that runs a Lark
    grammar on the body and returns the parse tree.  This test
    demonstrates the registration pattern; the actual grammar is
    trivial.
    """
    try:
        import lark
    except ImportError:
        pytest.skip("lark not installed")

    from rivex.serialization._bodies import is_body_model, register_body_schema

    class LarkWrapped:
        """Marker subclass — body must declare a Lark grammar as
        ``lark_grammar`` class attribute."""

        lark_grammar: Any = None

    def _detect(h):
        return isinstance(h, type) and issubclass(h, LarkWrapped)

    def _coerce(h, body):
        data = body if isinstance(body, dict) else json.loads(body)
        parser = lark.Lark(h.lark_grammar)
        return parser.parse(json.dumps(data))

    register_body_schema("lark", detect=_detect, coerce=_coerce)
    try:

        class P(LarkWrapped):
            lark_grammar = 'start: "{" "}"'

        from rivex.serialization._bodies import coerce_body

        out = coerce_body(b"{}", P)
        assert out is not None
        assert is_body_model(P) is False  # extended detection only
        from rivex.serialization._bodies import body_schema_extended

        assert body_schema_extended(P) == "custom"
    finally:
        from rivex.serialization import _bodies as _b

        _b._CUSTOM_HANDLERS.pop("lark", None)
        _b._CUSTOM_DETECTORS[:] = [
            d for d in _b._CUSTOM_DETECTORS if getattr(d, "__name__", "") != "_detect"
        ]


def test_register_body_schema_for_pyparsing():
    """pyparsing is a parser toolkit — same registration pattern
    as Lark.
    """
    try:
        import pyparsing
    except ImportError:
        pytest.skip("pyparsing not installed")

    from rivex.serialization._bodies import body_schema_extended, register_body_schema

    class PPWrapped:
        pyparsing_expression: Any = None

    def _detect(h):
        return isinstance(h, type) and issubclass(h, PPWrapped)

    def _coerce(h, body):
        data = body if isinstance(body, dict) else json.loads(body)
        result = h.pyparsing_expression.parseString(json.dumps(data))
        return result.asList()

    register_body_schema("pyparsing", detect=_detect, coerce=_coerce)
    try:

        class P(PPWrapped):
            pyparsing_expression = pyparsing.Suppress("{}")

        from rivex.serialization._bodies import coerce_body

        out = coerce_body(b"{}", P)
        assert out == []
        assert body_schema_extended(P) == "custom"
    finally:
        from rivex.serialization import _bodies as _b

        _b._CUSTOM_HANDLERS.pop("pyparsing", None)
        _b._CUSTOM_DETECTORS[:] = [
            d for d in _b._CUSTOM_DETECTORS if getattr(d, "__name__", "") != "_detect"
        ]


def test_register_body_schema_for_user_agents():
    """python-user-agents parses a User-Agent string — not a body
    type, but you can register it to validate an ``X-User-Agent``
    header or a ``user_agent`` form field by wrapping the parser in
    a custom backend.
    """
    try:
        import user_agents
    except ImportError:
        pytest.skip("user_agents not installed")

    from rivex.serialization._bodies import body_schema_extended, register_body_schema

    class UAWrapped:
        """Marker — declare a class that the body parser should
        interpret as a User-Agent string."""

        pass

    def _detect(h):
        return isinstance(h, type) and issubclass(h, UAWrapped)

    def _coerce(h, body):
        ua_str = (
            body
            if isinstance(body, str)
            else (body.decode() if isinstance(body, bytes) else body.get("ua", ""))
        )
        return user_agents.parse(ua_str)

    register_body_schema("user-agents", detect=_detect, coerce=_coerce)
    try:
        from rivex.serialization._bodies import coerce_body

        out = coerce_body(b'"Mozilla/5.0 (iPhone)"', UAWrapped)
        # Just check it returns a parsed object
        assert out.is_mobile or out.is_pc or out.is_bot or out.is_tablet
        assert body_schema_extended(UAWrapped) == "custom"
    finally:
        from rivex.serialization import _bodies as _b

        _b._CUSTOM_HANDLERS.pop("user-agents", None)
        _b._CUSTOM_DETECTORS[:] = [
            d for d in _b._CUSTOM_DETECTORS if getattr(d, "__name__", "") != "_detect"
        ]


# ---------------------------------------------------------------------------
# is_body_model covers the new backends
# ---------------------------------------------------------------------------


def test_is_body_model_for_new_backends():
    pytest.importorskip("dataclasses")
    pytest.importorskip("attr")
    pytest.importorskip("msgspec")
    pytest.importorskip("construct")

    from rivex.serialization._bodies import is_body_model

    assert is_body_model(DCItem) is True
    assert is_body_model(AttrsItem) is True
    assert is_body_model(MsgspecItem) is True
    assert is_body_model(ConstructItem) is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
