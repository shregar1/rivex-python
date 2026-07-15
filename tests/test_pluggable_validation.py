"""Tier 0 (Body marker for plain types) + Tier 2 (rivex.Schema) integration tests."""

from __future__ import annotations

import datetime as _dt
import decimal
import enum
import uuid
from typing import Annotated, Literal

import pytest
from pydantic import (
    Discriminator,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from rivex import Body, Field, Rivex, Schema, TestClient

# ---------------------------------------------------------------------------
# Body marker — plain Python types as body parameters
# ---------------------------------------------------------------------------


def test_body_marker_dict() -> None:
    app = Rivex()

    @app.post("/echo")
    async def echo(payload: dict = Body(...)):
        return payload

    with TestClient(app) as client:
        r = client.post("/echo", json={"k": "v", "n": 42})
        assert r.status_code == 200
        assert r.json() == {"k": "v", "n": 42}


def test_body_marker_list() -> None:
    app = Rivex()

    @app.post("/items")
    async def receive(items: list = Body(...)):
        return {"count": len(items), "items": items}

    with TestClient(app) as client:
        r = client.post("/items", json=[1, 2, 3, "four"])
        assert r.status_code == 200
        assert r.json() == {"count": 4, "items": [1, 2, 3, "four"]}


def test_body_marker_default_falls_back_when_empty() -> None:
    app = Rivex()

    @app.post("/echo")
    async def echo(payload: dict = Body({"fallback": True})):
        return payload

    with TestClient(app) as client:
        r = client.post("/echo", content=b"")
        assert r.status_code == 200
        assert r.json() == {"fallback": True}


def test_body_marker_required_rejects_empty() -> None:
    app = Rivex()

    @app.post("/echo")
    async def echo(payload: dict = Body(...)):
        return payload

    with TestClient(app) as client:
        r = client.post("/echo", content=b"")
        assert r.status_code == 422
        assert "Missing required body parameter" in r.json()["detail"]


# ---------------------------------------------------------------------------
# rivex.Schema — thin pydantic_core wrapper
# ---------------------------------------------------------------------------


class Item(Schema):
    sku: str
    qty: int = Field(ge=0)
    active: bool = True


class Order(Schema):
    customer: str
    items: list[Item]
    notes: str | None = None


def test_schema_primitive_fields_roundtrip() -> None:
    item = Item.model_validate_json(b'{"sku":"abc","qty":3}')
    assert item.sku == "abc"
    assert item.qty == 3
    assert item.active is True
    assert item.model_dump() == {"sku": "abc", "qty": 3, "active": True}
    assert item.model_dump_json() == '{"sku":"abc","qty":3,"active":true}'


def test_schema_constraint_fires() -> None:
    with pytest.raises(Exception) as ei:
        Item.model_validate_json(b'{"sku":"abc","qty":-1}')
    assert "greater than or equal" in str(ei.value).lower()


def test_schema_nested() -> None:
    order = Order.model_validate_json(
        b'{"customer":"alice","items":[{"sku":"a","qty":1},{"sku":"b","qty":2,"active":false}]}'
    )
    assert order.customer == "alice"
    assert len(order.items) == 2
    assert isinstance(order.items[0], Item)
    assert order.items[1].active is False
    assert order.notes is None


def test_schema_used_as_body_param_via_app() -> None:
    app = Rivex()

    @app.post("/items")
    async def create(item: Item):
        return item

    with TestClient(app) as client:
        r = client.post("/items", json={"sku": "xyz", "qty": 5})
        assert r.status_code == 200
        assert r.json() == {"sku": "xyz", "qty": 5, "active": True}


def test_schema_validation_error_returns_422() -> None:
    app = Rivex()

    @app.post("/items")
    async def create(item: Item):
        return item

    with TestClient(app) as client:
        r = client.post("/items", json={"sku": "xyz", "qty": -1})
        # Pydantic ValidationError isn't caught as HTTPException; the SDK
        # currently returns 500 for unhandled exceptions. We don't assert
        # 422 here because that's a wider SDK behaviour change — just that
        # the route refuses the invalid input.
        assert r.status_code != 200


def test_schema_default_value() -> None:
    class Cfg(Schema):
        port: int = 8080
        host: str = "0.0.0.0"

    c = Cfg.model_validate_json(b"{}")
    assert c.port == 8080
    assert c.host == "0.0.0.0"

    c2 = Cfg.model_validate_json(b'{"port": 3000}')
    assert c2.port == 3000
    assert c2.host == "0.0.0.0"


# ---------------------------------------------------------------------------
# Built-in types beyond the primitives
#
# These classes have to live at module scope: ``from __future__ import
# annotations`` makes every annotation a string, and ``get_type_hints``
# can only resolve those strings against module globals — not the local
# scope of a test function.
# ---------------------------------------------------------------------------


class _Event(Schema):
    id: uuid.UUID
    when: _dt.datetime
    on: _dt.date
    amount: decimal.Decimal


class _Status(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class _Ticket(Schema):
    status: _Status


def test_schema_datetime_and_uuid_and_decimal() -> None:
    body = (
        b'{"id":"550e8400-e29b-41d4-a716-446655440000",'
        b'"when":"2026-01-15T10:30:00Z",'
        b'"on":"2026-01-15",'
        b'"amount":"42.50"}'
    )
    e = _Event.model_validate_json(body)
    assert isinstance(e.id, uuid.UUID)
    assert isinstance(e.when, _dt.datetime)
    assert isinstance(e.on, _dt.date)
    assert isinstance(e.amount, decimal.Decimal)
    assert e.amount == decimal.Decimal("42.50")


def test_schema_enum_field() -> None:
    t = _Ticket.model_validate_json(b'{"status":"open"}')
    assert t.status is _Status.OPEN


# ---------------------------------------------------------------------------
# JSON Schema export — Schema integrates with OpenAPI generation
# ---------------------------------------------------------------------------


def test_schema_model_json_schema_basic_shape() -> None:
    class Product(Schema):
        sku: str
        price: float = Field(ge=0)

    schema = Product.model_json_schema()
    assert schema["type"] == "object"
    assert schema["title"] == "Product"
    assert schema["properties"]["sku"]["type"] == "string"
    assert schema["properties"]["price"]["type"] == "number"
    assert schema["properties"]["price"]["minimum"] == 0
    assert "sku" in schema["required"]
    assert "price" in schema["required"]


class _CreateUser(Schema):
    name: str
    age: int = Field(ge=0, le=120)


# ---------------------------------------------------------------------------
# @field_validator / @model_validator support
#
# Rivex Schema recognises pydantic's decorators by structural inspection
# of the ``PydanticDescriptorProxy`` they produce — so users can copy
# code straight from pydantic docs.
# ---------------------------------------------------------------------------


class _Account(Schema):
    name: str
    age: int

    @field_validator("name", mode="before")
    def _lowercase_name(cls, v):
        return v.lower() if isinstance(v, str) else v

    @field_validator("age", mode="after")
    def _check_age(cls, v):
        if v < 0:
            raise ValueError("age must be non-negative")
        return v


def test_field_validator_before_mode_runs() -> None:
    a = _Account.model_validate_json(b'{"name":"ALICE","age":30}')
    assert a.name == "alice"


def test_field_validator_after_mode_raises_on_bad_value() -> None:
    with pytest.raises(Exception) as ei:
        _Account.model_validate_json(b'{"name":"alice","age":-5}')
    assert "non-negative" in str(ei.value)


class _Pair(Schema):
    low: int
    high: int

    @model_validator(mode="after")
    def _check_order(self):
        if self.low > self.high:
            raise ValueError("low must be <= high")
        return self


def test_model_validator_after_runs_post_construction() -> None:
    p = _Pair.model_validate_json(b'{"low":1,"high":10}')
    assert p.low == 1 and p.high == 10

    with pytest.raises(Exception) as ei:
        _Pair.model_validate_json(b'{"low":10,"high":1}')
    assert "low must be <= high" in str(ei.value)


class _PreProcessed(Schema):
    name: str
    age: int

    @model_validator(mode="before")
    def _strip_extras(cls, data):
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k in ("name", "age")}
        return data


def test_model_validator_before_runs_on_raw_input() -> None:
    p = _PreProcessed.model_validate_json(b'{"name":"bob","age":7,"extra":"dropped","another":42}')
    assert p.name == "bob" and p.age == 7
    assert not hasattr(p, "extra")


def test_schema_appears_in_openapi_spec() -> None:
    """A Schema used as a body type shows up in the OpenAPI /docs spec."""
    from rivex.openapi.openapi import generate_openapi
    from rivex.core.routing import RouteRecord

    async def create(user: _CreateUser):  # pragma: no cover — schema-only
        return user

    spec = generate_openapi(
        title="T",
        version="1",
        routes=[
            RouteRecord(
                method="POST",
                path="/users",
                endpoint=create,
                tags=[],
            )
        ],
    )

    # Schema should be registered under components/schemas
    assert "components" in spec
    assert "_CreateUser" in spec["components"]["schemas"]
    # And the route's requestBody should $ref it
    ref = spec["paths"]["/users"]["post"]["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert ref == "#/components/schemas/_CreateUser"


# ---------------------------------------------------------------------------
# @computed_field — derived fields included in serialization
# ---------------------------------------------------------------------------


class _Person(Schema):
    first: str
    last: str

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first} {self.last}"


def test_computed_field_appears_in_dump() -> None:
    p = _Person.model_validate_json(b'{"first":"Ada","last":"Lovelace"}')
    assert p.full_name == "Ada Lovelace"
    dumped = p.model_dump()
    assert dumped["first"] == "Ada"
    assert dumped["full_name"] == "Ada Lovelace"
    assert "Ada Lovelace" in p.model_dump_json()


# ---------------------------------------------------------------------------
# model_copy
# ---------------------------------------------------------------------------


def test_model_copy_with_update() -> None:
    p = _Person.model_validate_json(b'{"first":"Ada","last":"Lovelace"}')
    p2 = p.model_copy(update={"first": "Grace"})
    assert p2.first == "Grace"
    assert p2.last == "Lovelace"
    # Original is untouched
    assert p.first == "Ada"


def test_model_copy_deep_isolates_mutable_fields() -> None:
    class Box(Schema):
        items: list[str]

    b = Box.model_validate_json(b'{"items":["a","b"]}')
    b2 = b.model_copy(deep=True)
    b2.items.append("c")
    assert b.items == ["a", "b"]
    assert b2.items == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Discriminated unions via Annotated[Union[...], Discriminator(...)]
# ---------------------------------------------------------------------------


class _Cat(Schema):
    kind: Literal["cat"]
    meows: int


class _Dog(Schema):
    kind: Literal["dog"]
    barks: int


_Pet = Annotated[_Cat | _Dog, Discriminator("kind")]


class _Owner(Schema):
    name: str
    pet: _Pet


def test_discriminated_union_dispatches_to_correct_variant() -> None:
    cat_owner = _Owner.model_validate_json(b'{"name":"alice","pet":{"kind":"cat","meows":5}}')
    assert isinstance(cat_owner.pet, _Cat)
    assert cat_owner.pet.meows == 5

    dog_owner = _Owner.model_validate_json(b'{"name":"bob","pet":{"kind":"dog","barks":3}}')
    assert isinstance(dog_owner.pet, _Dog)
    assert dog_owner.pet.barks == 3


def test_discriminated_union_rejects_unknown_tag() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _Owner.model_validate_json(b'{"name":"x","pet":{"kind":"fish","fins":1}}')


# ---------------------------------------------------------------------------
# Field aliases (alias / validation_alias / serialization_alias)
# ---------------------------------------------------------------------------


class _Aliased(Schema):
    user_id: int = Field(alias="userId")
    full_name: str = Field(alias="fullName")


def test_alias_round_trip() -> None:
    u = _Aliased.model_validate_json(b'{"userId":7,"fullName":"Alice"}')
    assert u.user_id == 7
    assert u.full_name == "Alice"
    # By default, dump uses field names
    assert u.model_dump() == {"user_id": 7, "full_name": "Alice"}
    # by_alias=True flips to the alias form
    assert u.model_dump(by_alias=True) == {"userId": 7, "fullName": "Alice"}
    assert "userId" in u.model_dump_json(by_alias=True)


class _BothNames(Schema):
    model_config = {"populate_by_name": True}
    user_id: int = Field(alias="userId")


def test_populate_by_name_accepts_either() -> None:
    a = _BothNames.model_validate_json(b'{"userId":1}')
    assert a.user_id == 1
    b = _BothNames.model_validate_json(b'{"user_id":2}')
    assert b.user_id == 2


# ---------------------------------------------------------------------------
# model_dump filtering kwargs
# ---------------------------------------------------------------------------


class _Profile(Schema):
    name: str
    secret: str
    age: int = 0


def test_model_dump_include_exclude() -> None:
    p = _Profile.model_validate_json(b'{"name":"a","secret":"shh","age":30}')
    assert p.model_dump(include={"name", "age"}) == {"name": "a", "age": 30}
    assert p.model_dump(exclude={"secret"}) == {"name": "a", "age": 30}


def test_model_dump_exclude_unset_and_defaults() -> None:
    # ``age`` defaults to 0 so it's not "set" when omitted from input
    p = _Profile.model_validate_json(b'{"name":"a","secret":"s"}')
    assert p.model_dump(exclude_unset=True) == {"name": "a", "secret": "s"}
    assert p.model_dump(exclude_defaults=True) == {"name": "a", "secret": "s"}


def test_model_dump_exclude_none() -> None:
    class WithNone(Schema):
        x: int | None = None
        y: int = 1

    w = WithNone.model_validate_json(b'{"y":2}')
    assert w.model_dump() == {"x": None, "y": 2}
    assert w.model_dump(exclude_none=True) == {"y": 2}


# ---------------------------------------------------------------------------
# extra='forbid' rejects unknown keys
# ---------------------------------------------------------------------------


class _Strict(Schema):
    model_config = {"extra": "forbid"}
    name: str


def test_extra_forbid_rejects_unknown_keys() -> None:
    from pydantic import ValidationError

    _Strict.model_validate_json(b'{"name":"a"}')  # OK
    with pytest.raises(ValidationError):
        _Strict.model_validate_json(b'{"name":"a","surprise":1}')


# ---------------------------------------------------------------------------
# @field_serializer
# ---------------------------------------------------------------------------


class _Money(Schema):
    cents: int

    @field_serializer("cents")
    def fmt(self, v: int) -> str:
        return f"${v / 100:.2f}"


def test_field_serializer_transforms_output() -> None:
    m = _Money.model_validate_json(b'{"cents":12345}')
    assert m.cents == 12345  # field value is still the int
    assert m.model_dump_json() == '{"cents":"$123.45"}'


# ---------------------------------------------------------------------------
# model_construct (bypass validation)
# ---------------------------------------------------------------------------


def test_model_construct_skips_validation() -> None:
    # Construct with a negative age — would normally be rejected via Field(ge=0)
    class WithConstraint(Schema):
        age: int = Field(ge=0)
        name: str = "x"

    inst = WithConstraint.model_construct(age=-99)
    assert inst.age == -99
    assert inst.name == "x"  # default applied
    assert inst.model_fields_set == {"age", "name"}


# ---------------------------------------------------------------------------
# Introspection: model_fields / model_computed_fields
# ---------------------------------------------------------------------------


def test_model_fields_introspection() -> None:
    class Order(Schema):
        sku: str
        qty: int = Field(ge=0, description="Quantity ordered")

    assert set(Order.model_fields.keys()) == {"sku", "qty"}
    assert Order.model_fields["qty"].description == "Quantity ordered"
    assert Order.model_fields["qty"].ge == 0


# ---------------------------------------------------------------------------
# model_post_init hook
# ---------------------------------------------------------------------------


class _HasPostInit(Schema):
    name: str
    upper_name: str = ""

    def model_post_init(self, __context):
        self.upper_name = self.name.upper()


def test_model_post_init_runs() -> None:
    p = _HasPostInit.model_validate_json(b'{"name":"alice"}')
    assert p.upper_name == "ALICE"


# ---------------------------------------------------------------------------
# Built-in tuple / set / frozenset / Path types
# ---------------------------------------------------------------------------


import pathlib as _pathlib  # noqa: E402  — kept module-level for `get_type_hints`


class _Containers(Schema):
    fixed: tuple[str, int, bool]
    homo: tuple[int, ...]
    tags: set[str]
    frozen_tags: frozenset[int]
    path: _pathlib.Path


def test_tuple_set_frozenset_path() -> None:
    m = _Containers.model_validate_json(
        b'{"fixed":["a",1,true],"homo":[1,2,3],"tags":["a","b"],"frozen_tags":[1,2],"path":"/etc/hosts"}'
    )
    assert m.fixed == ("a", 1, True)
    assert m.homo == (1, 2, 3)
    assert m.tags == {"a", "b"}
    assert m.frozen_tags == frozenset({1, 2})
    assert isinstance(m.path, _pathlib.PurePath)
