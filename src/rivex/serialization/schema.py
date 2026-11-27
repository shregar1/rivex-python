"""``rivex.schema`` — thin validator built directly on ``pydantic_core``.

Pydantic v2 is split into two halves: ``pydantic_core`` (a Rust extension
that does the actual validation + serialisation) and ``pydantic`` itself
(the Python BaseModel layer with all the ergonomics — validators,
JSON-Schema generation, model_dump, deep config, etc.).

``rivex.schema.Schema`` is the bottom half only. It uses ``pydantic_core``'s
``SchemaValidator`` and ``SchemaSerializer`` directly, skipping the
Python-level BaseModel machinery and the per-instance metadata that
BaseModel carries around.

Supported types
---------------
* primitives — ``int``, ``float``, ``str``, ``bool``, ``bytes``, ``None``
* date/time — ``datetime``, ``date``, ``time``, ``timedelta``
* identity / numeric — ``uuid.UUID``, ``decimal.Decimal``
* ``enum.Enum`` subclasses (including ``str``/``int``-mixed enums)
* ``Literal[…]``
* containers — ``list[T]``, ``dict[K, V]``, ``tuple[X, Y, Z]`` (fixed-arity)
  and ``tuple[X, ...]`` (variadic), ``set[T]``, ``frozenset[T]``
* file / network — ``pathlib.Path``, ``ipaddress.IPv4Address`` /
  ``IPv6Address`` / network / interface variants
* regex / callable — ``re.Pattern``, ``Callable``
* ``Optional[T]`` / ``X | None`` / ``Union[…]``
* tagged unions — ``Annotated[A | B, Discriminator("kind")]``
* nested ``Schema`` subclasses
* pydantic specials — ``pydantic.HTTPUrl``, ``EmailStr``,
  ``IPvAnyAddress``, ``SecretStr``, ``SecretBytes``, ``Json[T]``,
  ``AwareDatetime``, ``NaiveDatetime``, ``PastDate``, ``FutureDate``
  (delegated to pydantic's ``TypeAdapter`` so they "just work")

Field constraints (``Field(...)``)
----------------------------------
* numeric — ``ge``, ``le``, ``gt``, ``lt``, ``multiple_of``,
  ``allow_inf_nan``
* decimal — ``decimal_places``, ``max_digits``
* string / collection length — ``min_length``, ``max_length``,
  ``pattern``
* aliases — ``alias``, ``validation_alias``, ``serialization_alias``
* defaults — ``default`` value or ``default_factory`` callable
* flags — ``frozen``, ``repr``, ``exclude``
* OpenAPI / JSON-Schema metadata — ``title``, ``description``,
  ``examples``, ``deprecated``, ``json_schema_extra``

Pydantic decorators recognised
------------------------------
* ``@field_validator(*names, mode="before"|"after"|"plain")``
* ``@model_validator(mode="before"|"after")``
* ``@computed_field`` (on top of ``@property``)
* ``@field_serializer(*names, mode="plain"|"wrap")``
* ``@model_serializer(mode="plain"|"wrap")``

Detection is structural (we read ``decorator_info`` and ``wrapped`` off
the ``PydanticDescriptorProxy``) so we don't pin to pydantic's internal
module layout.

Class-level ``model_config``
----------------------------
* ``extra`` — ``"allow"`` / ``"ignore"`` / ``"forbid"``
* ``populate_by_name`` — accept either the alias or the field name
* ``alias_generator`` — callable applied to every field name
* ``frozen`` — make all fields immutable

Other API surface
-----------------
* ``model_validate`` / ``model_validate_json``
* ``model_dump`` / ``model_dump_json`` — full pydantic kwargs:
  ``include``, ``exclude``, ``by_alias``, ``exclude_unset``,
  ``exclude_defaults``, ``exclude_none``, ``round_trip``, ``warnings``,
  ``indent``, ``mode``.
* ``model_copy(update=..., deep=False)``
* ``model_construct(_fields_set=None, **values)`` — bypass validation
* ``model_post_init(self, __context)`` — post-construction hook
* ``model_json_schema()`` — JSON Schema for OpenAPI integration
* ``model_fields`` / ``model_computed_fields`` / ``model_fields_set``
  / ``model_extra`` — introspection

What we deliberately don't carry
--------------------------------
* Pydantic v1 legacy decorators (``@validator``, ``@root_validator``)
* The full ``ConfigDict`` surface — only the four config keys above are
  honoured. Edge-case toggles (``str_strip_whitespace``,
  ``revalidate_instances``, ``defer_build``, …) are not.
* ``TypeAdapter[T]`` for non-model types, and the
  ``@pydantic.dataclasses.dataclass`` decorator
* Forward references / ``model_rebuild()`` / generic parametrised
  models

For routes that need anything outside that surface, mix and match —
``BaseModel`` and ``Schema`` are interchangeable at the SDK boundary
(both detected by duck-typing on ``model_validate_json`` /
``model_json_schema``).
"""

from __future__ import annotations

import datetime as _dt
import decimal
import enum
import inspect
import ipaddress
import pathlib
import re as _re
import types
import typing
import uuid
from collections.abc import Callable as _Callable
from typing import (
    Annotated,
    Any,
    ClassVar,
    Literal,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

import pydantic_core
from pydantic_core import core_schema

# PEP 604 ``X | Y`` syntax produces ``types.UnionType`` at runtime instead
# of ``typing.Union`` — both need to be treated the same way.
_UNION_ORIGINS = {Union, types.UnionType}


def _is_classvar(hint: Any) -> bool:
    """``True`` if ``hint`` is ``typing.ClassVar[...]`` (in any form)."""
    if hint is ClassVar:
        return True
    return get_origin(hint) is ClassVar


_REQUIRED = object()


class Field:
    """Per-field constraints, metadata, and default value.

    Mirrors ``pydantic.Field`` for the subset that feeds into
    ``pydantic_core``'s schema or pydantic's JSON-Schema generator.
    """

    __slots__ = (
        # Default + aliases.
        "default",
        "default_factory",
        "alias",
        "validation_alias",
        "serialization_alias",
        # Numeric constraints.
        "ge",
        "le",
        "gt",
        "lt",
        "multiple_of",
        "decimal_places",
        "max_digits",
        "allow_inf_nan",
        # String constraints.
        "min_length",
        "max_length",
        "pattern",
        # Behaviour flags.
        "frozen",
        "repr",
        "exclude",
        # JSON-Schema / OpenAPI metadata.
        "title",
        "description",
        "examples",
        "deprecated",
        "json_schema_extra",
    )

    def __init__(
        self,
        default: Any = _REQUIRED,
        *,
        default_factory: Any = None,
        alias: str | None = None,
        validation_alias: str | None = None,
        serialization_alias: str | None = None,
        ge: int | float | None = None,
        le: int | float | None = None,
        gt: int | float | None = None,
        lt: int | float | None = None,
        multiple_of: int | float | None = None,
        decimal_places: int | None = None,
        max_digits: int | None = None,
        allow_inf_nan: bool | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        pattern: str | None = None,
        frozen: bool | None = None,
        repr: bool = True,  # noqa: A002 — match pydantic's parameter name
        exclude: bool | None = None,
        title: str | None = None,
        description: str | None = None,
        examples: list[Any] | None = None,
        deprecated: bool | None = None,
        json_schema_extra: dict[str, Any] | None = None,
    ) -> None:
        self.default = default
        self.default_factory = default_factory
        self.alias = alias
        self.validation_alias = validation_alias
        self.serialization_alias = serialization_alias
        self.ge = ge
        self.le = le
        self.gt = gt
        self.lt = lt
        self.multiple_of = multiple_of
        self.decimal_places = decimal_places
        self.max_digits = max_digits
        self.allow_inf_nan = allow_inf_nan
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern
        self.frozen = frozen
        self.repr = repr
        self.exclude = exclude
        self.title = title
        self.description = description
        self.examples = examples
        self.deprecated = deprecated
        self.json_schema_extra = json_schema_extra

    def _apply_numeric(self, schema: Any) -> Any:
        """Copy numeric constraint attributes onto *schema* in place.

        Iterates the supported JSON-Schema numeric keys (``ge``,
        ``le``, ``gt``, ``lt``, ``multiple_of``) and writes the
        non-``None`` ones onto the supplied schema dict. The
        ``allow_inf_nan`` flag is added when explicitly set, since
        it is opt-in. The schema is mutated and returned for
        fluent chaining.

        Args:
            schema: The mutable schema dict to update.

        Returns:
            The same ``schema`` instance, with numeric constraints
            added.
        """
        for k in ("ge", "le", "gt", "lt", "multiple_of"):
            v = getattr(self, k)
            if v is not None:
                schema[k] = v
        if self.allow_inf_nan is not None:
            schema["allow_inf_nan"] = self.allow_inf_nan
        return schema

    def _apply_decimal(self, schema: Any) -> Any:
        """Copy numeric and decimal-specific constraints onto *schema*.

        Calls :meth:`_apply_numeric` first to share the common
        range constraints, then layers the decimal-specific
        ``decimal_places`` and ``max_digits`` keys on top when set.
        The schema is mutated in place and returned for chaining.

        Args:
            schema: The mutable schema dict to update.

        Returns:
            The same ``schema`` instance with decimal constraints
            merged in.
        """
        schema = self._apply_numeric(schema)
        if self.decimal_places is not None:
            schema["decimal_places"] = self.decimal_places
        if self.max_digits is not None:
            schema["max_digits"] = self.max_digits
        return schema

    def _apply_string(self, schema: Any) -> Any:
        """Copy string constraint attributes onto *schema* in place.

        Writes ``min_length``, ``max_length``, and ``pattern`` when
        set. Used for the ``str`` / ``SecretStr`` / ``EmailStr`` /
        URL-style field types in the schema builder.

        Args:
            schema: The mutable schema dict to update.

        Returns:
            The same ``schema`` instance with string constraints
            added.
        """
        if self.min_length is not None:
            schema["min_length"] = self.min_length
        if self.max_length is not None:
            schema["max_length"] = self.max_length
        if self.pattern is not None:
            schema["pattern"] = self.pattern
        return schema

    def _apply_collection(self, schema: Any) -> Any:
        """Copy collection length constraints onto *schema* in place.

        Writes the ``min_length`` / ``max_length`` keys (which
        pydantic_core interprets as element-count bounds for
        ``list`` / ``set`` / ``frozenset`` schemas) when set.
        Element-type constraints are not handled here — they live
        on the per-element schema in the caller.

        Args:
            schema: The mutable schema dict to update.

        Returns:
            The same ``schema`` instance with collection length
            bounds added.
        """
        if self.min_length is not None:
            schema["min_length"] = self.min_length
        if self.max_length is not None:
            schema["max_length"] = self.max_length
        return schema

    def _json_schema_meta(self) -> dict[str, Any]:
        """Return a dict of OpenAPI/JSON-Schema metadata to merge in."""
        meta: dict[str, Any] = {}
        if self.title is not None:
            meta["title"] = self.title
        if self.description is not None:
            meta["description"] = self.description
        if self.examples is not None:
            meta["examples"] = self.examples
        if self.deprecated is not None:
            meta["deprecated"] = self.deprecated
        if self.json_schema_extra:
            meta.update(self.json_schema_extra)
        return meta


def _is_pydantic_json(hint: Any) -> bool:
    """Detect ``pydantic.Json`` / ``pydantic.Json[T]`` without importing it."""
    obj = get_origin(hint) or hint
    return type(obj).__name__ == "_GenericAlias" and getattr(obj, "__name__", "") == "Json"


def _try_pydantic_native_schema(hint: Any) -> Any:
    """Ask pydantic itself for the core schema of a pydantic special type.

    Used as a fallback for types like ``EmailStr`` / ``HTTPUrl`` /
    ``SecretStr`` / ``AwareDatetime`` where pydantic ships first-class
    handling that's tedious to reimplement here.
    """
    try:
        from pydantic import TypeAdapter

        return TypeAdapter(hint).core_schema
    except Exception:
        # No pydantic support found — fall back to ``Any``.
        return core_schema.any_schema()


def _takes_info(func: Any) -> bool:
    """Check if a validator function expects a second ``info`` argument."""
    try:
        sig = inspect.signature(func)
        return len(sig.parameters) >= 2
    except (ValueError, TypeError):
        return False


def _apply_constraints(schema: dict[str, Any], constraints: dict[str, Any]) -> None:
    """Mutate a core schema dict to include numeric/string constraints."""
    for key in (
        "gt",
        "ge",
        "lt",
        "le",
        "multiple_of",
        "min_length",
        "max_length",
        "pattern",
        "strict",
    ):
        if key in constraints:
            schema[key] = constraints[key]


def _literal_value(node: Any) -> Any | None:
    """Pull the literal value out of a ``Literal[X]`` annotation.

    Returns the singleton value when the annotation is a single-arg
    Literal (the discriminator-tag pattern), else ``None``. Multi-value
    literals fall through.
    """
    if get_origin(node) is Literal:
        args = get_args(node)
        if len(args) == 1:
            return args[0]
    return None


def _extract_discriminator_tag(member: Any, discriminator: str) -> Any | None:
    """Return the literal-tag value a Schema subclass uses for ``discriminator``.

    For ``class Cat(Schema): kind: Literal["cat"]``, looking up the
    ``kind`` field annotation returns the string ``"cat"``. The tag is
    what ``tagged_union_schema`` keys the choice on.
    """
    if not (isinstance(member, type) and issubclass(member, Schema)):
        return None
    try:
        hints = get_type_hints(member, include_extras=True)
    except Exception:
        return None
    tag_hint = hints.get(discriminator)
    if tag_hint is None:
        return None
    return _literal_value(tag_hint)


def _annotation_to_core_schema(hint: Any) -> Any:
    """Map a Python type annotation to a ``pydantic_core`` schema dict.

    Return type is intentionally ``Any`` — ``pydantic_core`` ships fine-
    grained ``TypedDict``s for each schema variety (``IntSchema``,
    ``ListSchema``, ``ModelSchema``, etc.) that vary by branch; threading
    a precise union through every helper is more noise than signal.
    """
    # ``Annotated[T, meta1, meta2, ...]`` — strip annotations down to the
    # underlying type, but pick off ``Discriminator`` to switch a Union
    # into a tagged union.
    if get_origin(hint) is Annotated:
        args = get_args(hint)
        underlying, *metas = args

        discriminator_meta = None
        validators: list[Any] = []
        constraints: dict[str, Any] = {}

        for meta in metas:
            meta_type_name = type(meta).__name__
            if meta_type_name == "Discriminator":
                discriminator_meta = meta
            elif meta_type_name == "AfterValidator":
                validators.append(("after", getattr(meta, "func", None)))
            elif meta_type_name == "BeforeValidator":
                validators.append(("before", getattr(meta, "func", None)))
            elif meta_type_name == "PlainValidator":
                validators.append(("plain", getattr(meta, "func", None)))
            elif meta_type_name == "WrapValidator":
                validators.append(("wrap", getattr(meta, "func", None)))
            elif hasattr(meta, "__dict__"):
                for attr in (
                    "gt",
                    "ge",
                    "lt",
                    "le",
                    "multiple_of",
                    "min_length",
                    "max_length",
                    "pattern",
                    "strict",
                ):
                    val = getattr(meta, attr, None)
                    if val is not None:
                        constraints[attr] = val

        if discriminator_meta is not None:
            discriminator = getattr(discriminator_meta, "discriminator", None)
            if isinstance(discriminator, str):
                inner_origin = get_origin(underlying)
                if inner_origin in _UNION_ORIGINS:
                    choices: dict[Any, Any] = {}
                    for choice in get_args(underlying):
                        tag = _extract_discriminator_tag(choice, discriminator)
                        if tag is None:
                            choices = {}
                            break
                        choices[tag] = _annotation_to_core_schema(choice)
                    if choices:
                        return core_schema.tagged_union_schema(
                            choices=choices,
                            discriminator=discriminator,
                        )

        inner_schema = _annotation_to_core_schema(underlying)

        for kind, func in validators:
            if func is None:
                continue
            if kind == "after":
                inner_schema = (
                    core_schema.with_info_plain_validator_function(func)
                    if _takes_info(func)
                    else core_schema.no_info_plain_validator_function(func)
                )
                inner_schema = core_schema.chain_schema(
                    [_annotation_to_core_schema(underlying), inner_schema]
                )
            elif kind == "before":
                pre = (
                    core_schema.with_info_plain_validator_function(func)
                    if _takes_info(func)
                    else core_schema.no_info_plain_validator_function(func)
                )
                inner_schema = core_schema.chain_schema(
                    [pre, _annotation_to_core_schema(underlying)]
                )
            elif kind == "plain":
                inner_schema = (
                    core_schema.with_info_plain_validator_function(func)
                    if _takes_info(func)
                    else core_schema.no_info_plain_validator_function(func)
                )

        if constraints:
            _apply_constraints(inner_schema, constraints)

        return inner_schema

    # ``Literal["a", "b", 1]`` — emit a literal_schema with the values.
    if get_origin(hint) is Literal:
        return core_schema.literal_schema(list(get_args(hint)))

    if hint is int:
        return core_schema.int_schema()
    if hint is float:
        return core_schema.float_schema()
    if hint is str:
        return core_schema.str_schema()
    if hint is bool:
        return core_schema.bool_schema()
    if hint is bytes:
        return core_schema.bytes_schema()
    if hint is Any:
        return core_schema.any_schema()
    if hint is type(None):
        return core_schema.none_schema()

    # Common API value types — datetime, date, time, timedelta, UUID, Decimal.
    if hint is _dt.datetime:
        return core_schema.datetime_schema()
    if hint is _dt.date:
        return core_schema.date_schema()
    if hint is _dt.time:
        return core_schema.time_schema()
    if hint is _dt.timedelta:
        return core_schema.timedelta_schema()
    if hint is uuid.UUID:
        return core_schema.uuid_schema()
    if hint is decimal.Decimal:
        return core_schema.decimal_schema()

    # ``pathlib.Path`` and concrete subclasses — pydantic_core has no
    # dedicated path schema, so we validate as a str and convert.
    if isinstance(hint, type) and issubclass(hint, pathlib.PurePath):
        target: Any = hint

        def _to_path(v: Any, _t: Any = target) -> Any:
            """Convert a validated string into a ``pathlib`` path of the target subclass.

            Wrapped in a default-argument trick so the ``_t``
            closure captures the concrete ``pathlib`` subclass
            (e.g. ``Path``, ``PurePosixPath``) rather than the
            loop variable.
            """
            return _t(v)

        return core_schema.no_info_after_validator_function(_to_path, core_schema.str_schema())

    # IP address types.
    if hint in (
        ipaddress.IPv4Address,
        ipaddress.IPv6Address,
        ipaddress.IPv4Network,
        ipaddress.IPv6Network,
        ipaddress.IPv4Interface,
        ipaddress.IPv6Interface,
    ):
        ip_target: Any = hint

        def _to_ip(v: Any, _t: Any = ip_target) -> Any:
            """Convert a validated IP-address string into the target IP type.

            ``_t`` is bound through a default argument so the
            closure captures the concrete IP class (``IPv4Address``,
            ``IPv6Network``, etc.) rather than the surrounding
            loop variable.
            """
            return _t(v)

        return core_schema.no_info_after_validator_function(_to_ip, core_schema.str_schema())

    # ``re.Pattern`` — validate as str, compile to a Pattern.
    if hint is _re.Pattern or get_origin(hint) is _re.Pattern:
        return core_schema.no_info_after_validator_function(_re.compile, core_schema.str_schema())

    # ``Callable`` — accept any callable. Pass through, no validation.
    if hint is _Callable or get_origin(hint) is _Callable:
        return core_schema.is_instance_schema(_Callable)

    # Pydantic special string types — detected by class name so we don't
    # pin to a specific pydantic submodule layout.
    pydantic_type_name = getattr(hint, "__name__", "")
    if pydantic_type_name == "Json" or _is_pydantic_json(hint):
        # ``pydantic.Json[T]`` means "the JSON-string form of T". Parse it
        # and then validate against T's schema.
        inner_args = get_args(hint)
        inner = (
            _annotation_to_core_schema(inner_args[0]) if inner_args else core_schema.any_schema()
        )
        return core_schema.json_schema(inner)
    if pydantic_type_name in ("SecretStr", "SecretBytes"):
        # Pydantic's SecretStr/SecretBytes have first-class schemas in
        # pydantic_core but they're not exposed cleanly — fall back to
        # the Python-side type which knows how to build its own schema.
        return _try_pydantic_native_schema(hint)
    if pydantic_type_name in ("EmailStr", "HTTPUrl", "AnyUrl", "AnyHTTPUrl"):
        return _try_pydantic_native_schema(hint)
    if pydantic_type_name in (
        "PastDate",
        "FutureDate",
        "PastDatetime",
        "FutureDatetime",
        "AwareDatetime",
        "NaiveDatetime",
    ):
        return _try_pydantic_native_schema(hint)

    # Enums — pydantic_core's enum_schema reads members off the class.
    if isinstance(hint, type) and issubclass(hint, enum.Enum):
        return core_schema.enum_schema(hint, list(hint))

    origin = get_origin(hint)
    args = get_args(hint)

    if origin is list:
        item_schema = _annotation_to_core_schema(args[0]) if args else core_schema.any_schema()
        return core_schema.list_schema(items_schema=item_schema)
    if origin is set:
        item_schema = _annotation_to_core_schema(args[0]) if args else core_schema.any_schema()
        return core_schema.set_schema(items_schema=item_schema)
    if origin is frozenset:
        item_schema = _annotation_to_core_schema(args[0]) if args else core_schema.any_schema()
        return core_schema.frozenset_schema(items_schema=item_schema)
    if origin is tuple:
        if not args:
            return core_schema.tuple_schema([])
        # ``tuple[X, ...]`` is variadic (homogeneous), ``tuple[X, Y, Z]`` is
        # a fixed-arity heterogeneous tuple.
        if len(args) == 2 and args[1] is Ellipsis:
            return core_schema.tuple_schema(
                [_annotation_to_core_schema(args[0])],
                variadic_item_index=0,
            )
        return core_schema.tuple_schema([_annotation_to_core_schema(a) for a in args])
    if origin is dict:
        if args:
            return core_schema.dict_schema(
                keys_schema=_annotation_to_core_schema(args[0]),
                values_schema=_annotation_to_core_schema(args[1]),
            )
        return core_schema.dict_schema()
    if origin in _UNION_ORIGINS:
        # ``Optional[X]`` and ``X | None`` both land here.
        non_none = [a for a in args if a is not type(None)]
        has_none = len(non_none) != len(args)
        if len(non_none) == 1:
            inner = _annotation_to_core_schema(non_none[0])
            return core_schema.nullable_schema(inner) if has_none else inner
        union = core_schema.union_schema([_annotation_to_core_schema(a) for a in non_none])
        return core_schema.nullable_schema(union) if has_none else union

    if isinstance(hint, type) and issubclass(hint, Schema):
        return hint.__rivex_core_schema__

    raise TypeError(
        f"rivex.Schema does not support annotation {hint!r}. "
        "Supported: int, float, str, bool, bytes, list[T], dict[K, V], "
        "Optional[T], Union[…], nested Schema."
    )


def _apply_field_constraints(schema: Any, field: Field) -> Any:
    """Fold ``Field`` constraints into a ``pydantic_core`` schema."""
    schema_type = schema.get("type")
    if schema_type in ("int", "float"):
        return field._apply_numeric(schema)
    if schema_type == "decimal":
        return field._apply_decimal(schema)
    if schema_type == "str":
        return field._apply_string(schema)
    if schema_type in ("list", "set", "frozenset", "dict", "tuple"):
        return field._apply_collection(schema)
    return schema


def _model_field_kwargs(
    field: Field,
    *,
    populate_by_name: bool,
    alias_generator: Any | None,
    field_name: str,
) -> dict[str, Any]:
    """Build the keyword args we pass to ``core_schema.model_field`` for a field."""
    kwargs: dict[str, Any] = {}

    # Validation alias: pydantic's resolution order is validation_alias →
    # alias → alias_generator(name) → field name. We pass an explicit
    # validation_alias to pydantic_core; with ``populate_by_name`` set,
    # both the alias and the field name are accepted on input.
    validation_alias = field.validation_alias or field.alias
    if not validation_alias and alias_generator is not None:
        validation_alias = alias_generator(field_name)
    if validation_alias:
        if populate_by_name:
            kwargs["validation_alias"] = [
                [validation_alias],
                [field_name],
            ]
        else:
            kwargs["validation_alias"] = validation_alias

    serialization_alias = field.serialization_alias or field.alias
    if not serialization_alias and alias_generator is not None:
        serialization_alias = alias_generator(field_name)
    if serialization_alias:
        kwargs["serialization_alias"] = serialization_alias

    if field.frozen is not None:
        kwargs["frozen"] = field.frozen
    if field.exclude:
        kwargs["serialization_exclude"] = True

    meta = field._json_schema_meta()
    if meta:
        kwargs["metadata"] = {"pydantic_js_updates": meta}

    return kwargs


# ---------------------------------------------------------------------------
# Pydantic ``@field_validator`` / ``@model_validator`` integration
#
# Pydantic v2 wraps decorated methods in a ``PydanticDescriptorProxy`` that
# exposes three attributes — ``wrapped`` (the function or classmethod),
# ``decorator_info`` (a dataclass describing the decoration), and ``shim``.
# We don't import the pydantic-internal classes; we identify them
# structurally by attribute presence. That keeps us decoupled from
# pydantic's internal module layout (which has shifted between minor
# versions).
# ---------------------------------------------------------------------------


def _unwrap_callable(wrapped: Any) -> Any:
    """Return the plain function out of a (potentially) ``classmethod``."""
    return wrapped.__func__ if hasattr(wrapped, "__func__") else wrapped


def _collect_decorations(
    cls: type,
) -> tuple[
    dict[str, list[tuple[str, Any]]],
    list[tuple[str, Any]],
    list[tuple[str, Any, Any]],
    dict[str, list[tuple[Any, str | None, str]]],
    list[tuple[Any, str]],
]:
    """Walk ``cls`` and group pydantic-style decorations on its members.

    Returns ``(field_validators, model_validators, computed_fields,
    field_serializers, model_serializers)``:

    * ``field_validators[field_name]`` → list of ``(mode, func)``.
    * ``model_validators`` → list of ``(mode, func)``.
    * ``computed_fields`` → list of ``(name, getter, return_type)``.
    * ``field_serializers[field_name]`` → list of
      ``(func, return_type_str_or_None, mode)`` where ``mode`` is one of
      ``"plain"`` / ``"wrap"``.
    * ``model_serializers`` → list of ``(func, mode)`` (same modes).
    """
    field_validators: dict[str, list[tuple[str, Any]]] = {}
    model_validators: list[tuple[str, Any]] = []
    computed_fields: list[tuple[str, Any, Any]] = []
    field_serializers: dict[str, list[tuple[Any, str | None, str]]] = {}
    model_serializers: list[tuple[Any, str]] = []

    for name, member in cls.__dict__.items():
        info = getattr(member, "decorator_info", None)
        wrapped = getattr(member, "wrapped", None)
        if info is None or wrapped is None:
            continue

        kind = type(info).__name__

        if kind == "FieldValidatorDecoratorInfo":
            func = _unwrap_callable(wrapped)
            mode = getattr(info, "mode", "after")
            for field_name in getattr(info, "fields", ()):
                field_validators.setdefault(field_name, []).append((mode, func))
        elif kind == "ModelValidatorDecoratorInfo":
            func = _unwrap_callable(wrapped)
            mode = getattr(info, "mode", "after")
            model_validators.append((mode, func))
        elif kind == "ComputedFieldInfo":
            getter = wrapped.fget if isinstance(wrapped, property) else wrapped
            return_type: Any = getattr(info, "return_type", None)
            if return_type is None or repr(return_type) == "PydanticUndefined":
                return_type = typing.get_type_hints(getter).get("return", Any)
            computed_fields.append((name, getter, return_type))
        elif kind == "FieldSerializerDecoratorInfo":
            func = _unwrap_callable(wrapped)
            mode = getattr(info, "mode", "plain")
            return_type_str: str | None = getattr(info, "return_type", None)
            for field_name in getattr(info, "fields", ()):
                field_serializers.setdefault(field_name, []).append((func, return_type_str, mode))
        elif kind == "ModelSerializerDecoratorInfo":
            func = _unwrap_callable(wrapped)
            mode = getattr(info, "mode", "plain")
            model_serializers.append((func, mode))
        # Other pydantic decorators (legacy @validator, @serializer, …)
        # are intentionally ignored — they need wider machinery than we
        # expose, and most users reach for them rarely.

    return (
        field_validators,
        model_validators,
        computed_fields,
        field_serializers,
        model_serializers,
    )


def _wrap_with_field_serializer(
    schema: Any,
    func: Any,
    mode: str,
    return_type: Any,
) -> Any:
    """Wrap a field schema with a ``@field_serializer`` callback.

    ``is_field_serializer=True`` tells pydantic_core to invoke the
    function as a bound method on the model instance — matching the
    ``def fmt(self, v)`` signature that pydantic.field_serializer
    accepts. The ``return_type`` (if set on the decorator) is currently
    ignored; pydantic_core infers ``Any`` which is fine for the common
    "format a value as a string" cases.
    """
    sersch: Any
    if mode == "plain":
        sersch = core_schema.plain_serializer_function_ser_schema(
            func, is_field_serializer=True, info_arg=False
        )
    else:  # mode == "wrap"
        sersch = core_schema.wrap_serializer_function_ser_schema(
            func, is_field_serializer=True, info_arg=False
        )
    out: dict[str, Any] = dict(schema)
    out["serialization"] = sersch
    return out


def _wrap_with_field_validator(schema: Any, mode: str, func: Any, cls: type) -> Any:
    """Compose ``func(cls, v) -> v`` around an existing field schema."""
    bound = lambda v: func(cls, v)  # noqa: E731 — small inline closure
    if mode == "before":
        return core_schema.no_info_before_validator_function(bound, schema)
    if mode == "after":
        return core_schema.no_info_after_validator_function(bound, schema)
    if mode == "plain":
        return core_schema.no_info_plain_validator_function(bound)
    raise ValueError(f"unsupported field_validator mode: {mode!r}")


def _wrap_with_model_validator(schema: Any, mode: str, func: Any, cls: type) -> Any:
    """Compose ``@model_validator`` around the whole model schema.

    Pydantic's convention is asymmetric:
      * ``mode="before"`` expects ``func(cls, data) -> data`` (raw input
        ``dict`` in, possibly massaged ``dict`` out).
      * ``mode="after"`` expects ``func(self) -> self`` (model instance
        in, validated instance out — typically used for cross-field
        invariants).
    """
    if mode == "before":
        bound = lambda data: func(cls, data)  # noqa: E731
        return core_schema.no_info_before_validator_function(bound, schema)
    if mode == "after":
        # ``after`` runs post-construction so ``func`` already takes ``self``.
        return core_schema.no_info_after_validator_function(func, schema)
    raise ValueError(f"unsupported model_validator mode: {mode!r}")


class Schema:
    """Minimal validated model on top of ``pydantic_core``.

    Define a subclass with annotated attributes (and optional ``Field``
    defaults for constraints); the validator + serializer are built once at
    class-definition time and reused on every request.
    """

    __rivex_core_schema__: ClassVar[Any] = None
    __rivex_validator__: ClassVar[pydantic_core.SchemaValidator | None] = None
    __rivex_serializer__: ClassVar[pydantic_core.SchemaSerializer | None] = None
    # Per-class metadata for the introspection surface. ``__rivex_fields__``
    # maps field name -> the ``Field`` instance describing it; the order
    # tuple preserves declaration order; ``__rivex_computed_fields__`` is
    # the tuple of computed-field names so they're easy to filter in dump.
    __rivex_fields__: ClassVar[dict[str, Field]] = {}
    __rivex_field_order__: ClassVar[tuple[str, ...]] = ()
    __rivex_computed_fields__: ClassVar[tuple[str, ...]] = ()
    # Pydantic's `GenerateJsonSchema` reads ``cls.model_config`` for things
    # like title customisation. Stub an empty ConfigDict so we can reuse
    # pydantic's JSON-Schema converter on ``__rivex_core_schema__``.
    model_config: ClassVar[dict[str, Any]] = {}
    # Cached JSON Schema — generated lazily on first ``model_json_schema``
    # call. The schema itself is immutable for the lifetime of the class.
    __rivex_json_schema__: ClassVar[dict[str, Any] | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        try:
            hints = get_type_hints(cls, include_extras=True)
        except Exception:
            hints = {}

        # Class-level ``model_config`` dict, e.g.:
        #   class User(Schema):
        #       model_config = {"extra": "forbid", "populate_by_name": True}
        cfg: dict[str, Any] = dict(getattr(cls, "model_config", {}) or {})
        extra_behaviour: str | None = cfg.get("extra")
        populate_by_name: bool = bool(cfg.get("populate_by_name", False))
        alias_generator: Any | None = cfg.get("alias_generator")
        frozen_default: bool = bool(cfg.get("frozen", False))

        # Pydantic-style decorations on methods.
        (
            field_validators,
            model_validators,
            computed_fields,
            field_serializers,
            model_serializers,
        ) = _collect_decorations(cls)

        # Track field metadata for the introspection surface
        # (``cls.model_fields``, ``inst.model_fields_set``, ``inst.model_extra``).
        field_info_map: dict[str, Field] = {}
        ordered_field_names: list[str] = []

        fields: dict[str, Any] = {}
        for name, hint in hints.items():
            if name.startswith("__rivex"):
                continue
            if _is_classvar(hint):
                continue
            raw = _annotation_to_core_schema(hint)
            default = getattr(cls, name, _REQUIRED)

            field_info: Field
            if isinstance(default, Field):
                field_info = default
                raw = _apply_field_constraints(raw, field_info)
                if field_info.default is not _REQUIRED:
                    raw = core_schema.with_default_schema(raw, default=field_info.default)
                elif field_info.default_factory is not None:
                    raw = core_schema.with_default_schema(
                        raw, default_factory=field_info.default_factory
                    )
            else:
                field_info = Field()
                if default is not _REQUIRED:
                    raw = core_schema.with_default_schema(raw, default=default)
                    field_info.default = default

            for mode, func in field_validators.get(name, ()):
                raw = _wrap_with_field_validator(raw, mode, func, cls)

            for sfunc, _ret_type, smode in field_serializers.get(name, ()):
                raw = _wrap_with_field_serializer(raw, sfunc, smode, _ret_type)

            field_kwargs = _model_field_kwargs(
                field_info,
                populate_by_name=populate_by_name,
                alias_generator=alias_generator,
                field_name=name,
            )
            fields[name] = core_schema.model_field(raw, **field_kwargs)
            field_info_map[name] = field_info
            ordered_field_names.append(name)

        # ``computed_fields`` from @computed_field.
        computed_field_schemas = [
            core_schema.computed_field(cname, _annotation_to_core_schema(rt))
            for cname, _getter, rt in computed_fields
        ]
        model_fields_kwargs: dict[str, Any] = {
            "fields": fields,
            "model_name": cls.__name__,
        }
        if computed_field_schemas:
            model_fields_kwargs["computed_fields"] = computed_field_schemas
        if extra_behaviour in ("allow", "ignore", "forbid"):
            model_fields_kwargs["extras_schema"] = (
                core_schema.any_schema() if extra_behaviour == "allow" else None
            )
            model_fields_kwargs["extra_behavior"] = extra_behaviour
        fields_schema = core_schema.model_fields_schema(**model_fields_kwargs)

        model_schema_kwargs: dict[str, Any] = {
            "cls": cls,
            "schema": fields_schema,
            "ref": cls.__name__,
        }
        if frozen_default:
            model_schema_kwargs["frozen"] = True
        if extra_behaviour == "forbid":
            model_schema_kwargs["extra_behavior"] = "forbid"
        schema: Any = core_schema.model_schema(**model_schema_kwargs)

        # ``@model_validator`` wraps the entire model schema.
        for mode, func in model_validators:
            schema = _wrap_with_model_validator(schema, mode, func, cls)

        # ``model_post_init(self, __context=None)`` — if the user defined
        # this method, run it after the model is fully constructed.
        if "model_post_init" in cls.__dict__:
            post = cls.__dict__["model_post_init"]

            def _run_post_init(inst: Any, _p: Any = post) -> Any:
                """Invoke the user-defined ``model_post_init`` hook on *inst*.

                The ``_p`` default-argument binding ensures the
                closure captures the bound ``model_post_init``
                callable from the enclosing class, not the loop
                variable. ``None`` is passed as the context
                argument because the core schema wrapper only
                supplies one positional value.
                """
                _p(inst, None)
                return inst

            schema = core_schema.no_info_after_validator_function(_run_post_init, schema)

        # ``@model_serializer`` attaches to the model schema's serialization.
        if model_serializers:
            sfunc, smode = model_serializers[0]
            schema = dict(schema)
            if smode == "plain":
                schema["serialization"] = core_schema.plain_serializer_function_ser_schema(sfunc)
            else:  # wrap
                schema["serialization"] = core_schema.wrap_serializer_function_ser_schema(sfunc)

        cls.__rivex_core_schema__ = schema
        cls.__rivex_validator__ = pydantic_core.SchemaValidator(schema)
        cls.__rivex_serializer__ = pydantic_core.SchemaSerializer(schema)
        cls.__rivex_fields__ = field_info_map
        cls.__rivex_field_order__ = tuple(ordered_field_names)
        cls.__rivex_computed_fields__ = tuple(name for name, _, _ in computed_fields)
        # Expose pydantic-style introspection on the class. We set these
        # as plain class attributes (not classmethod-property pairs since
        # those were removed in Python 3.13).
        cls.model_fields = field_info_map  # type: ignore[attr-defined]
        cls.model_computed_fields = tuple(name for name, _, _ in computed_fields)  # type: ignore[attr-defined]

    def __init__(self, **data: Any) -> None:
        """Validate keyword arguments and populate the instance."""
        if not data:
            return
        cls = type(self)
        if cls.__rivex_validator__ is None:
            raise TypeError(f"{cls.__name__} has no compiled schema")
        validated = cls.__rivex_validator__.validate_python(data)
        if not isinstance(validated, cls):
            raise TypeError(f"expected {cls.__name__} from validator, got {type(validated)!r}")
        self.__dict__.update(validated.__dict__)

    # ── Pydantic-compatible API surface (so the SDK auto-detects either) ──

    @classmethod
    def model_validate_json(cls, data: bytes | str) -> Schema:
        """Parse and validate a JSON document into a model instance.

        Mirrors pydantic's ``model_validate_json`` so callers that
        detect either framework get a working entry point. The
        underlying validator must already be compiled; otherwise
        a :class:`TypeError` is raised.

        Args:
            data: The JSON payload, as ``bytes`` or ``str``.

        Returns:
            A new :class:`Schema` instance populated from the
            parsed JSON.
        """
        if cls.__rivex_validator__ is None:
            raise TypeError(f"{cls.__name__} has no compiled schema")
        return cls.__rivex_validator__.validate_json(data)  # type: ignore[no-any-return]

    @classmethod
    def model_validate(cls, data: Any) -> Schema:
        """Validate a Python ``data`` mapping into a model instance.

        Mirrors pydantic's ``model_validate`` so callers that
        detect either framework get a working entry point. The
        input is forwarded to the compiled core-schema validator
        which applies field-level coercion and constraint checks
        before constructing the instance.

        Args:
            data: A Python ``dict`` (or compatible mapping) of
                field values to validate.

        Returns:
            A new :class:`Schema` instance populated from
            *data*.
        """
        if cls.__rivex_validator__ is None:
            raise TypeError(f"{cls.__name__} has no compiled schema")
        return cls.__rivex_validator__.validate_python(data)  # type: ignore[no-any-return]

    def model_dump(
        self,
        *,
        mode: str = "python",
        include: Any = None,
        exclude: Any = None,
        by_alias: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        round_trip: bool = False,
        warnings: Any = True,
    ) -> dict[str, Any]:
        """Serialise to a Python dict. Keyword args mirror ``BaseModel.model_dump``."""
        return self.__rivex_serializer__.to_python(  # type: ignore[union-attr,no-any-return]
            self,
            mode=mode,
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            round_trip=round_trip,
            warnings=warnings,
        )

    def model_dump_json(
        self,
        *,
        indent: int | None = None,
        include: Any = None,
        exclude: Any = None,
        by_alias: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        round_trip: bool = False,
        warnings: Any = True,
    ) -> str:
        """Serialise to a JSON string. Keyword args mirror ``BaseModel.model_dump_json``."""
        return self.__rivex_serializer__.to_json(  # type: ignore[union-attr]
            self,
            indent=indent,
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            round_trip=round_trip,
            warnings=warnings,
        ).decode("utf-8")

    def model_copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> Schema:
        """Return a copy of this model, optionally with field updates applied."""
        if deep:
            import copy as _copy

            data = _copy.deepcopy(self.model_dump())
        else:
            data = self.model_dump()
        if update:
            data.update(update)
        return type(self).model_validate(data)

    @classmethod
    def model_construct(cls, _fields_set: set[str] | None = None, **values: Any) -> Schema:
        """Create an instance **without** validation.

        Use for trusted data only (caches, internal builders, fixtures).
        Mirrors ``pydantic.BaseModel.model_construct`` — fields not in
        ``values`` get their declared defaults, ``_fields_set`` controls
        ``model_fields_set``.
        """
        instance = cls.__new__(cls)
        # Apply declared defaults first so dump-shape is consistent.
        for name, field_info in cls.__rivex_fields__.items():
            if name in values:
                continue
            if field_info.default is not _REQUIRED:
                values[name] = field_info.default
            elif field_info.default_factory is not None:
                values[name] = field_info.default_factory()
        instance.__dict__.update(values)
        # pydantic_core's model schema expects these private attrs to exist
        # on the instance — without them the serializer crashes.
        instance.__dict__.setdefault("__pydantic_extra__", None)
        instance.__dict__.setdefault("__pydantic_private__", None)
        instance.__dict__["__pydantic_fields_set__"] = (
            _fields_set if _fields_set is not None else set(values)
        )
        return instance

    @property
    def model_fields_set(self) -> set[str]:
        """Names of fields that were explicitly set on this instance."""
        return set(self.__dict__.get("__pydantic_fields_set__") or ())

    @property
    def model_extra(self) -> dict[str, Any] | None:
        """Captured extra kwargs when ``model_config["extra"] == "allow"``."""
        return self.__dict__.get("__pydantic_extra__")

    @classmethod
    def model_json_schema(cls) -> dict[str, Any]:
        """Emit a JSON Schema for this model.

        Delegates to pydantic's ``GenerateJsonSchema`` over our own
        ``__rivex_core_schema__`` — pydantic_core's schema format is the
        common currency, so the JSON-Schema converter works on either.
        Cached on the class after the first call.

        Used by ``rivex.openapi`` to emit our Schema types into the
        generated OpenAPI 3.1 document, so they show up in ``/docs``
        alongside Pydantic models.
        """
        if cls.__rivex_json_schema__ is None:
            from pydantic.json_schema import GenerateJsonSchema

            cls.__rivex_json_schema__ = GenerateJsonSchema().generate(cls.__rivex_core_schema__)
        return cls.__rivex_json_schema__

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        fields = ", ".join(
            f"{k}={v!r}" for k, v in self.__dict__.items() if not k.startswith("__pydantic")
        )
        return f"{type(self).__name__}({fields})"
