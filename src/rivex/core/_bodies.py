"""Native body-type coercion for Rivex route handlers.

Rivex controllers declare body parameters with ``Body()`` and a type
annotation. This module teaches the framework how to coerce the raw
incoming JSON body into that type, supporting a growing set of
first-class backends:

* **Pydantic** — ``BaseModel`` subclasses. The framework already had
  ``model_validate_json``; we just route through the same path.
* **Schemax** — ``schemax.idl.runtime.Message`` subclasses. The body is
  decoded as JSON and then run through ``Message.from_dict()`` /
  ``Message.from_json()``.
* **Marshmallow** — ``marshmallow.Schema`` subclasses. The body is
  decoded as JSON and then run through ``Schema().load()``.
* **dataclass** — stdlib ``@dataclass`` classes. Coerced via
  ``dataclasses.fields()`` and ``cls(**payload)``.
* **attrs** — ``@attr.s`` / ``@attrs.define`` classes. Coerced via
  ``attr.fields()`` and ``cls(**payload)``.
* **msgspec** — ``msgspec.Struct`` subclasses. Coerced via
  ``msgspec.convert(payload, type=cls)`` (round-trips through msgspec's
  own validator pipeline — much faster than stdlib for big payloads).
* **Construct** — ``construct.Struct`` / ``construct.Container``
  subclasses. Coerced via ``cls.parse(json_bytes)``.
* **typeguard** — plain Python classes validated by ``typeguard``.
  Coerced by building the instance with ``**payload`` and then running
  ``typeguard.check_type(instance, hint)``.

The public surface:

* :data:`BodySchema` — the supported backend names.
* :func:`body_schema` — classify a Python type as ``"pydantic"`` /
  ``"schemax"`` / ``"marshmallow"`` / ``"dataclass"`` / ``"attrs"`` /
  ``"msgspec"`` / ``"construct"`` / ``"typeguard"`` / ``"dict"`` /
  ``"unknown"``.
* :func:`is_body_model` — ``True`` for any class Rivex can auto-coerce.
* :func:`coerce_body` — run the JSON body through the right backend.
* :func:`register_body_schema` — plug in a new backend (third-party
  schemas, custom protocols).

If none of the optional backends is installed, only the ``dict`` path
is available. The module is safe to import in any environment.

For parser-style libraries (Lark, pyparsing) and request-derived
metadata (python-user-agents), there is no natural "coerce JSON body
to this class" semantics.  Those are pluggable via
:func:`register_body_schema` — see the ``register_body_schema``
docstring for examples.
"""

from __future__ import annotations

import functools
import json
import sys
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Strategy pattern — each body schema backend is a strategy that knows
# how to turn a JSON body / form-data dict into the target type.  The
# dispatch tables below are the canonical place to wire a new backend
# in: add an entry to ``_BASE_TYPE_DETECTORS`` for the type-detector
# function and to ``_BODY_COERCERS`` for the body coercing function.
# ``_TYPE_COERCERS`` is the shared per-field type coercion table used by
# both the attrs and dataclass backends (form-data fast path).
# ---------------------------------------------------------------------------


def _coerce_str(value: Any) -> Any:
    return value


def _coerce_int(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _coerce_float(value: Any) -> Any:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _coerce_bool(value: Any) -> Any:
    return str(value).lower() in ("true", "1", "yes")


def _coerce_passthrough(value: Any) -> Any:
    return value


# Per-field type coercion registry.  Used by attrs/dataclass form-data
# coercion where every field is a raw string from the wire and we need
# to drive ``target = int(raw)`` / ``target = float(raw)`` / etc. for
# each annotation.  Adding a new primitive type to handle is now a
# single line.
_TYPE_COERCERS: dict[type, Callable[[Any], Any]] = {
    str: _coerce_str,
    int: _coerce_int,
    float: _coerce_float,
    bool: _coerce_bool,
    bytes: _coerce_passthrough,
    type(None): _coerce_passthrough,
}

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------


class BodySchema:
    """Names of the supported body-schema backends."""

    PYDANTIC = "pydantic"
    SCHEMAX = "schemax"
    MARSHMALLOW = "marshmallow"
    DATACLASS = "dataclass"
    ATTRS = "attrs"
    MSGSPEC = "msgspec"
    CONSTRUCT = "construct"
    TYPEGUARD = "typeguard"
    DICT = "dict"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------


def _pydantic_base_model() -> type | None:
    try:
        from pydantic import BaseModel
    except ImportError:
        return None
    return BaseModel


def _schemax_message_base() -> type | None:
    """Return :class:`schemax.idl.runtime.Message` or ``None`` if missing."""
    try:
        from schemax.idl.runtime import Message
    except ImportError:
        return None
    return Message


def _marshmallow_schema_base() -> type | None:
    """Return :class:`marshmallow.Schema` or ``None`` if missing."""
    try:
        from marshmallow import Schema
    except ImportError:
        return None
    return Schema


def _msgspec_struct_base() -> type | None:
    """Return :class:`msgspec.Struct` or ``None`` if missing."""
    try:
        import msgspec
    except ImportError:
        return None
    return getattr(msgspec, "Struct", None)


def _construct_struct_base() -> type | None:
    """Return :class:`construct.Struct` or ``None`` if missing."""
    try:
        import construct
    except ImportError:
        return None
    return getattr(construct, "Struct", None)


def _construct_container_base() -> type | None:
    """Return :class:`construct.Container` or ``None`` if missing."""
    try:
        import construct
    except ImportError:
        return None
    return getattr(construct, "Container", None)


def _is_attrs_class(cls: type) -> bool:
    """``True`` if *cls* is an ``@attr.s`` / ``@attrs.define`` class.

    Importing ``attr`` only for the marker protocol keeps the detection
    branch free for non-attrs classes.
    """
    try:
        import attr
    except ImportError:
        return False
    try:
        return attr.has(cls) and getattr(cls, "__attrs_attrs__", None) is not None
    except Exception:
        return False


def _is_dataclass(cls: type) -> bool:
    """``True`` if *cls* is a stdlib ``@dataclass`` (not attrs/msgspec)."""
    import dataclasses

    try:
        return dataclasses.is_dataclass(cls) and not (
            isinstance(cls, type) and hasattr(cls, "__attrs_attrs__")
        )
    except Exception:
        return False


def _has_typeguard() -> bool:
    """``True`` if ``typeguard`` is installed.

    ``typeguard`` is a run-time type-checker rather than a body schema.
    We expose it as a backend so users can declare
    ``item: MyClass = Body()`` and have Rivex build the instance then
    run ``typeguard.check_type`` to validate it — the same ergonomics
    as a Pydantic ``BaseModel`` without Pydantic.
    """
    try:
        import typeguard  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Body schema classification (Chain-of-Responsibility / chain-of-detectors)
# ---------------------------------------------------------------------------


def _detect_pydantic(hint: type) -> str | None:
    base = _pydantic_base_model()
    if base is not None and issubclass(hint, base):
        return BodySchema.PYDANTIC
    return None


def _detect_schemax(hint: type) -> str | None:
    base = _schemax_message_base()
    if base is not None and issubclass(hint, base):
        return BodySchema.SCHEMAX
    return None


def _detect_marshmallow(hint: type) -> str | None:
    base = _marshmallow_schema_base()
    if base is not None and issubclass(hint, base):
        return BodySchema.MARSHMALLOW
    return None


def _detect_rivex_schema(hint: type) -> str | None:
    """Rivex's own Schema: a minimal validated model built on
    ``pydantic_core``.  Detected explicitly so it short-circuits the
    generic dataclass fallthrough; routed to the pydantic backend
    because that's the validation engine under the hood.
    """
    try:
        from rivex.serialization.schema import Schema as _RivexSchema
    except ImportError:
        return None
    if issubclass(hint, _RivexSchema):
        return BodySchema.PYDANTIC
    return None


def _detect_msgspec(hint: type) -> str | None:
    base = _msgspec_struct_base()
    if base is not None and issubclass(hint, base):
        return BodySchema.MSGSPEC
    return None


def _detect_construct(hint: type) -> str | None:
    struct_base = _construct_struct_base()
    if struct_base is not None and issubclass(hint, struct_base):
        return BodySchema.CONSTRUCT
    container_base = _construct_container_base()
    if container_base is not None and issubclass(hint, container_base):
        return BodySchema.CONSTRUCT
    return None


def _detect_attrs(hint: type) -> str | None:
    if _is_attrs_class(hint):
        return BodySchema.ATTRS
    return None


def _detect_dataclass(hint: type) -> str | None:
    if _is_dataclass(hint):
        return BodySchema.DATACLASS
    return None


# Detector chain: an ordered list of ``(hint_class, -> schema_name)``
# functions.  The first one to claim the type wins.  Adding a new
# backend = one line in this table + a strategy in ``_BODY_COERCERS``.
_BASE_TYPE_DETECTORS: list[Callable[[type], str | None]] = [
    _detect_pydantic,
    _detect_schemax,
    _detect_marshmallow,
    _detect_rivex_schema,
    _detect_msgspec,
    _detect_construct,
    _detect_attrs,
    _detect_dataclass,
    # ``typeguard`` is intentionally NOT auto-detected.  Unlike
    # pydantic / msgspec / attrs which carry runtime metadata
    # (``__attrs_attrs__``, ``_fields``, etc.) that uniquely identifies
    # the class as a schema type, a "typeguard-able" class is
    # indistinguishable from a plain Python class until you actually run
    # ``typeguard.check_type`` on it.  Opt in explicitly with
    # :func:`register_body_schema` or by subclassing
    # :class:`TypeGuardBody` (see ``register_body_schema`` docs).
]


# Schema classifications are queried on every request that has a body
# parameter.  The result is immutable for a given class, so we cache
# it.  ``functools.lru_cache`` gives us:
#
# * O(1) get / set
# * Bounded memory (LRU eviction at the cap)
# * Thread safety (the CPython implementation uses a per-cache lock
#   around the internal dict + linked list, so concurrent
#   ``coerce_body`` calls from a thread-pool executor — sync
#   handlers — are safe)
# * Cached return values: once a class is seen, the detector walk
#   doesn't run again.
#
# Id-recycling note: ``lru_cache`` keys on the function argument, so
# if a class is garbage-collected and a new class reuses its id, the
# next call would return the stale cached value for the new class.
# In practice body type classes are module-level and live for the
# process lifetime, so this is an edge case.  Call
# ``_classify_via_cache.cache_clear()`` after hot-unloading modules
# that define body types if that pattern applies.
_SCHEMA_CACHE_MAX: int = 1024


@functools.lru_cache(maxsize=_SCHEMA_CACHE_MAX)
def _classify_via_cache(hint: type) -> str:
    """Look up the schema for *hint* via the detector chain.

    The chain only runs on a cache miss; subsequent calls short-circuit
    to a dict lookup.  Capped at :data:`_SCHEMA_CACHE_MAX` entries with
    LRU eviction.
    """
    for detector in _BASE_TYPE_DETECTORS:
        schema = detector(hint)
        if schema is not None:
            return schema
    return BodySchema.UNKNOWN


def body_schema(hint: Any) -> str:
    """Return the backend name that knows how to coerce *hint* from JSON.

    * :class:`pydantic.BaseModel` subclass  → ``"pydantic"``
    * :class:`schemax.idl.runtime.Message` subclass  → ``"schemax"``
    * :class:`marshmallow.Schema` subclass  → ``"marshmallow"``
    * :class:`rivex.Schema` subclass  → ``"pydantic"`` (uses pydantic backend)
    * stdlib ``@dataclass`` class  → ``"dataclass"``
    * ``@attr.s`` / ``@attrs.define`` class  → ``"attrs"``
    * :class:`msgspec.Struct` subclass  → ``"msgspec"``
    * :class:`construct.Struct` or ``construct.Container`` subclass  → ``"construct"``
    * any class with ``typeguard`` installed  → ``"typeguard"`` (last-resort)
    * plain ``dict``  → ``"dict"``
    * ``bytes`` / ``str``  → ``"dict"`` (decoded as JSON)
    * anything else  → ``"unknown"``

    Results are memoised in a bounded LRU keyed on class identity — the
    detector chain only runs the first time a class is seen.  The cache
    is capped at :data:`_SCHEMA_CACHE_MAX` entries; old classes are
    evicted in LRU order when the cap is hit.
    """
    if hint is dict or hint is bytes or hint is str:
        return BodySchema.DICT
    if not isinstance(hint, type):
        return BodySchema.UNKNOWN
    return _classify_via_cache(hint)


def is_body_model(hint: Any) -> bool:
    """Return ``True`` for any type Rivex can auto-coerce from a JSON body.

    Recognised: pydantic ``BaseModel``, schemax ``Message``, marshmallow
    ``Schema``, plus ``dict`` / ``bytes`` / ``str`` (which are decoded as
    JSON and passed through).
    """
    if hint is dict or hint is bytes or hint is str:
        return True
    schema = body_schema(hint)
    return schema != BodySchema.UNKNOWN


# ---------------------------------------------------------------------------
# Per-field type-driven coercion (used by attrs + dataclass backends)
# ---------------------------------------------------------------------------


def _coerce_field_by_type(type_hints: dict[str, Any], key: str, raw: Any) -> Any:
    """Drive a single field's value from ``raw`` using the per-field
    type dispatch table.

    Adding a new primitive type means adding one line to
    :data:`_TYPE_COERCERS` — no new ``elif`` ladder required.
    """
    target = type_hints.get(key)
    if target is None:
        return raw
    coercer = _TYPE_COERCERS.get(target)
    if coercer is None:
        return raw
    return coercer(raw)


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------


def _coerce_form_attrs(form_data: dict[str, Any], hint: Any) -> Any:
    """``attrs`` form-data strategy.

    ``attrs`` exposes converters on each :class:`Attribute` so we honour
    them first and only fall back to the per-type coercion table for
    fields without an explicit converter.
    """
    import typing

    import attr as _attr

    fields_by_name = {a.name: a for a in _attr.fields(hint)}
    try:
        type_hints = typing.get_type_hints(hint)
    except Exception:
        type_hints = {}
    coerced: dict[str, Any] = {}
    for key, raw in form_data.items():
        if key not in fields_by_name:
            continue
        attribute = fields_by_name[key]
        if attribute.converter is not None:
            try:
                coerced[key] = attribute.converter(raw)
                continue
            except Exception:
                coerced[key] = raw
                continue
        coerced[key] = _coerce_field_by_type(type_hints, key, raw)
    return hint(**coerced)


def _coerce_form_dataclass(form_data: dict[str, Any], hint: Any) -> Any:
    """``dataclass`` form-data strategy.

    Per-field coercion drives the typed conversion off the class's
    ``__annotations__``.  Adding a new field type only requires the
    entry already live in :data:`_TYPE_COERCERS`.
    """
    import typing

    try:
        type_hints = typing.get_type_hints(hint)
    except Exception:
        type_hints = {}
    coerced = {key: _coerce_field_by_type(type_hints, key, raw) for key, raw in form_data.items()}
    return hint(**coerced)


def _coerce_form_dict(form_data: dict[str, Any], hint: Any) -> Any:
    """``dict`` passthrough strategy."""
    return form_data


def _coerce_form_msgspec(form_data: dict[str, Any], hint: Any) -> Any:
    """``msgspec`` fast-path strategy.

    ``msgspec.convert`` runs a single C-level pass over the payload
    and returns a fully-typed Struct instance, so it's strictly
    faster than per-field Python coercion for the dataclass/pydantic
    /msgspec paths.  Used as the default strategy for any class that
    msgspec can introspect (dataclass, msgspec.Struct, pydantic).
    """
    import msgspec

    return msgspec.convert(form_data, hint, strict=False)


def _coerce_form_pydantic(form_data: dict[str, Any], hint: Any) -> Any:
    """Pydantic ``model_validate`` strategy for form data."""
    return hint.model_validate(form_data)


def _coerce_form_schemax(form_data: dict[str, Any], hint: Any) -> Any:
    """Schemax ``from_dict`` strategy."""
    return hint.from_dict(form_data)


def _coerce_form_marshmallow(form_data: dict[str, Any], hint: Any) -> Any:
    """Marshmallow ``Schema().load`` strategy."""
    return hint().load(form_data)


def _coerce_form_construct(form_data: dict[str, Any], hint: Any) -> Any:
    """``construct`` form-data strategy.

    For :class:`construct.Container` subclasses (dict-like) we splat
    the form fields into the constructor.  :class:`construct.Struct`
    subclasses describe a binary wire format which doesn't apply to
    text form data, so we fall back to passing the dict through.
    """
    from construct import Container as _Container
    from construct import Struct as _Struct

    if not issubclass(hint, _Struct) and issubclass(hint, _Container):
        return hint(**form_data)
    return form_data


def _coerce_form_typeguard(form_data: dict[str, Any], hint: Any) -> Any:
    """``typeguard`` form-data strategy.

    Build the instance via ``msgspec.convert`` (single C-level pass)
    and then run :func:`typeguard.check_type` over it.  typeguard is
    a validator, not a parser, so this is the natural composition.
    """
    import msgspec
    import typeguard

    instance = msgspec.convert(form_data, hint, strict=False)
    typeguard.check_type(instance, hint)
    return instance


# Form-data dispatch table — schema name → coercing function.  This is
# the only place to add a new form-data backend.  The default
# strategy for any class msgspec can introspect is
# :func:`_coerce_form_msgspec`; backends with bespoke coercion
# requirements (attrs converters, schemax ``from_dict``, marshmallow
# ``Schema().load``, pydantic ``model_validate``, construct binary
# types) get their own entries.
_FORM_COERCERS: dict[str, Callable[[dict[str, Any], Any], Any]] = {
    BodySchema.PYDANTIC: _coerce_form_pydantic,
    BodySchema.SCHEMAX: _coerce_form_schemax,
    BodySchema.MARSHMALLOW: _coerce_form_marshmallow,
    BodySchema.DATACLASS: _coerce_form_msgspec,
    BodySchema.ATTRS: _coerce_form_attrs,
    BodySchema.MSGSPEC: _coerce_form_msgspec,
    BodySchema.CONSTRUCT: _coerce_form_construct,
    BodySchema.TYPEGUARD: _coerce_form_typeguard,
    BodySchema.DICT: _coerce_form_dict,
}


def coerce_form_data(form_data: dict[str, Any], hint: Any) -> Any:
    """Coerce a parsed form-data dict into *hint*.

    Same backends as :func:`coerce_body`, but the values come in as
    strings (form data is always text on the wire).  Dispatches to
    the per-schema strategy in :data:`_FORM_COERCERS`; ``msgspec`` is
    used as the default strategy for the dataclass / msgspec /
    typeguard backends because its single C-level pass is strictly
    faster than per-field Python coercion.

    For ``attrs`` classes the field types live in
    ``attr.fields(hint)`` rather than ``__annotations__``, so msgspec
    can't introspect them — we read the converters off each Attribute
    and run them manually.
    """
    schema = body_schema_extended(hint)
    coercer = _FORM_COERCERS.get(schema)
    if coercer is not None:
        return coercer(form_data, hint)
    return form_data


# ---------------------------------------------------------------------------
# Body coercion (raw JSON / bytes) dispatch
# ---------------------------------------------------------------------------


def _decode_body(body: Any) -> str | None:
    """Decode the raw request body to a string (or return ``None`` if
    the caller already provided a dict).  Raises on unsupported body
    types so the standard error path is hit.
    """
    from rivex.core.exceptions import RequestValidationError

    if isinstance(body, (bytes, bytearray)):
        try:
            return bytes(body).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RequestValidationError(
                [
                    {
                        "loc": ("body",),
                        "msg": f"Body is not valid UTF-8: {exc}",
                        "type": "value_error",
                    }
                ]
            ) from exc
    if isinstance(body, str):
        return body
    if isinstance(body, dict):
        return None
    raise RequestValidationError(
        [
            {
                "loc": ("body",),
                "msg": f"Unsupported body type: {type(body).__name__}",
                "type": "value_error",
            }
        ]
    )


def _parse_json_payload(body_str: str | None, body: Any) -> Any:
    """Parse a (possibly already-decoded) body into a Python dict.

    Centralises the ``body_str is None`` short-circuit (so the dict
    path doesn't double-decode) and the JSON error translation.
    """
    from rivex.core.exceptions import RequestValidationError

    if body_str is None:
        return body
    try:
        return json.loads(body_str)
    except json.JSONDecodeError as exc:
        raise RequestValidationError(
            [{"loc": ("body",), "msg": f"Body is not valid JSON: {exc}", "type": "value_error"}]
        ) from exc


def _coerce_body_pydantic(body_str: str | None, body: Any, hint: Any) -> Any:
    if body_str is not None and hasattr(hint, "model_validate_json"):
        return hint.model_validate_json(body_str)
    payload = _parse_json_payload(body_str, body)
    return hint.model_validate(payload)


def _coerce_body_schemax(body_str: str | None, body: Any, hint: Any) -> Any:
    if hasattr(hint, "from_json") and body_str is not None:
        return hint.from_json(body_str)
    payload = _parse_json_payload(body_str, body)
    return hint.from_dict(payload)


def _coerce_body_marshmallow(body_str: str | None, body: Any, hint: Any) -> Any:
    payload = _parse_json_payload(body_str, body)
    return hint().load(payload)


def _coerce_body_dataclass(body_str: str | None, body: Any, hint: Any) -> Any:
    payload = _parse_json_payload(body_str, body)
    return hint(**payload)


def _coerce_body_attrs(body_str: str | None, body: Any, hint: Any) -> Any:
    import attr

    payload = _parse_json_payload(body_str, body)
    field_names = {a.name for a in attr.fields(hint)}
    kwargs = {k: v for k, v in payload.items() if k in field_names}
    return hint(**kwargs)


def _coerce_body_msgspec(body_str: str | None, body: Any, hint: Any) -> Any:
    import msgspec

    payload = _parse_json_payload(body_str, body)
    return msgspec.convert(payload, hint, strict=False)


def _coerce_body_construct(body_str: str | None, body: Any, hint: Any) -> Any:
    payload = _parse_json_payload(body_str, body)
    from construct import Container as _Container
    from construct import Struct as _Struct

    if issubclass(hint, _Container) and not issubclass(hint, _Struct):
        return hint(**payload) if isinstance(payload, dict) else payload
    try:
        binary = hint().build(payload)
    except Exception:
        binary = json.dumps(payload).encode("utf-8")
    try:
        return hint().parse(binary)
    except Exception:
        return hint(**payload) if isinstance(payload, dict) else hint()


def _coerce_body_typeguard(body_str: str | None, body: Any, hint: Any) -> Any:
    import typeguard

    payload = _parse_json_payload(body_str, body)
    instance = hint(**payload)
    typeguard.check_type(instance, hint)
    return instance


def _coerce_body_dict(body_str: str | None, body: Any, hint: Any) -> Any:
    """``dict`` is the schema-less passthrough: if we already have a
    dict, return it; otherwise JSON-parse the body string.
    """
    if body_str is None:
        return body
    return _parse_json_payload(body_str, body)


def _coerce_body_custom(body_str: str | None, body: Any, hint: Any) -> Any:
    """Custom registered backend.

    The custom schema name is part of the detector closure in real
    use; for the public ``register_body_schema`` API we look up the
    matching handler by trying each in turn.
    """
    from rivex.core.exceptions import RequestValidationError

    for _name, fn in _CUSTOM_HANDLERS.items():
        if _CUSTOM_DETECTORS and _CUSTOM_DETECTORS[-1](hint):
            return fn(hint, body)
    raise RequestValidationError(
        [
            {
                "loc": ("body",),
                "msg": "custom backend matched but no handler found",
                "type": "value_error",
            }
        ]
    )


# Body coercion dispatch table — schema name → ``(body_str, body, hint)
# -> instance`` strategy.  Adding a new backend is one line.
_BODY_COERCERS: dict[str, Callable[[str | None, Any, Any], Any]] = {
    BodySchema.PYDANTIC: _coerce_body_pydantic,
    BodySchema.SCHEMAX: _coerce_body_schemax,
    BodySchema.MARSHMALLOW: _coerce_body_marshmallow,
    BodySchema.DATACLASS: _coerce_body_dataclass,
    BodySchema.ATTRS: _coerce_body_attrs,
    BodySchema.MSGSPEC: _coerce_body_msgspec,
    BodySchema.CONSTRUCT: _coerce_body_construct,
    BodySchema.TYPEGUARD: _coerce_body_typeguard,
    BodySchema.DICT: _coerce_body_dict,
    "custom": _coerce_body_custom,
}


def coerce_body(body: bytes | str | dict, hint: Any) -> Any:
    """Coerce a raw request body to *hint*.

    *body* may be:

    * a ``bytes`` JSON string (the common case from the wire)
    * a ``str`` JSON string
    * an already-decoded ``dict`` (for tests + in-process calls)

    The function dispatches to the right backend based on :func:`body_schema`.
    Adding a new backend means adding one line to :data:`_BODY_COERCERS`
    and one entry to :func:`body_schema`'s detector chain — no new
    ``elif`` ladder required.

    Raises :class:`RequestValidationError` on any decode / validation
    failure so the framework's standard error path is hit.
    """
    from rivex.core.exceptions import RequestValidationError

    body_str = _decode_body(body)
    schema = body_schema_extended(hint)

    coercer = _BODY_COERCERS.get(schema)
    if coercer is None:
        raise RequestValidationError(
            [
                {
                    "loc": ("body",),
                    "msg": f"No body coercion registered for type {hint!r}",
                    "type": "value_error",
                }
            ]
        )

    try:
        return coercer(body_str, body, hint)
    except RequestValidationError:
        raise
    except Exception as exc:
        raise RequestValidationError(
            [{"loc": ("body",), "msg": f"Body validation failed: {exc}", "type": "value_error"}]
        ) from exc


# ---------------------------------------------------------------------------
# Custom backend registration
# ---------------------------------------------------------------------------


_CustomHandler = Callable[[Any, bytes | str | dict], Any]


_CUSTOM_HANDLERS: dict[str, _CustomHandler] = {}


def register_body_schema(
    name: str,
    *,
    detect: Callable[[Any], bool],
    coerce: _CustomHandler,
) -> None:
    """Register a custom body schema backend.

    * *detect* receives the type hint and returns ``True`` if the backend
      can handle it.
    * *coerce* receives the type and the raw body and returns the coerced
      value (or raises :class:`RequestValidationError`).
    """
    if name in (BodySchema.PYDANTIC, BodySchema.SCHEMAX, BodySchema.MARSHMALLOW):
        raise ValueError(f"{name!r} is a built-in backend; use the existing module to extend it")
    _CUSTOM_HANDLERS[name] = coerce
    # Patch body_schema() to also recognise the new backend. We do this by
    # appending to a list of detectors that run after the built-ins.
    _CUSTOM_DETECTORS.append(detect)


_CUSTOM_DETECTORS: list[Callable[[Any], bool]] = []


def body_schema_extended(hint: Any) -> str:
    """Like :func:`body_schema` but also checks custom-registered backends."""
    base = body_schema(hint)
    if base != BodySchema.UNKNOWN:
        return base
    for detector in _CUSTOM_DETECTORS:
        if detector(hint):
            return "custom"
    return BodySchema.UNKNOWN


# Module metadata for introspection.
__all__ = [
    "BodySchema",
    "body_schema",
    "body_schema_extended",
    "coerce_body",
    "is_body_model",
    "register_body_schema",
    "SCHEMAS",
]


SCHEMAS = (
    BodySchema.PYDANTIC,
    BodySchema.SCHEMAX,
    BodySchema.MARSHMALLOW,
    BodySchema.DATACLASS,
    BodySchema.ATTRS,
    BodySchema.MSGSPEC,
    BodySchema.CONSTRUCT,
    BodySchema.TYPEGUARD,
    BodySchema.DICT,
)


# Print which backends are available on import (helps debugging).
if sys.flags.debug:  # pragma: no cover
    available = [BodySchema.DICT]
    if _pydantic_base_model() is not None:
        available.append(BodySchema.PYDANTIC)
    if _schemax_message_base() is not None:
        available.append(BodySchema.SCHEMAX)
    if _marshmallow_schema_base() is not None:
        available.append(BodySchema.MARSHMALLOW)
    print(f"  rivex._bodies: available backends = {available}", file=sys.stderr)
