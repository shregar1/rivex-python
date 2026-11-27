"""Rivex parameter markers — ``Query``, ``Path``, ``Body``, ``Header``, ``Cookie``.

These classes are used as default values in handler signatures to declare where
each parameter comes from. They are recognised by the framework's wrapper
builder (see :func:`rivex.di._injection.build_handler_wrapper`) and never
reach the handler body — only the extracted value does.

Example::

    from rivex import Body, Cookie, Header, Path, Query, Rivex

    app = Rivex()

    @app.get("/items/{item_id}")
    async def get_item(
        item_id: int = Path(ge=1),
        expand: bool = Query(default=False),
        trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
        session: str | None = Cookie(default=None),
        body: dict = Body(),
    ):
        ...
"""
from __future__ import annotations

from typing import Any

from rivex.native._compat import HAS_CORE
from rivex.native._compat import rc as _rc


class _ParamBase:
    """Shared field validation + OpenAPI metadata for all parameter markers.

    Holds the constraints (``gt``, ``ge``, ``lt``, ``le``, ``min_length``,
    ``max_length``, ``pattern``), the documentation fields (``title``,
    ``description``, ``examples``) and the alias / deprecation flags used by
    the OpenAPI generator. Subclasses set ``_in`` to declare where the value
    is sourced from (``"query"``, ``"path"``, ``"body"``, ``"header"``,
    ``"cookie"``).
    """

    __slots__ = (
        "default",
        "alias",
        "title",
        "description",
        "gt",
        "ge",
        "lt",
        "le",
        "min_length",
        "max_length",
        "pattern",
        "examples",
        "deprecated",
        "include_in_schema",
    )

    _in: str = ""

    def __init__(
        self,
        default: Any = ...,
        *,
        alias: str | None = None,
        title: str | None = None,
        description: str | None = None,
        gt: float | None = None,
        ge: float | None = None,
        lt: float | None = None,
        le: float | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        pattern: str | None = None,
        examples: list[Any] | None = None,
        deprecated: bool = False,
        include_in_schema: bool = True,
    ):
        """Declare a parameter's default, validation, and OpenAPI metadata.

        Args:
            default: Default value. Use ``...`` (Ellipsis) for required params.
            alias: Alternative name used by the framework to look up the
                value (for ``Header`` aliases the HTTP header name, etc.).
            title: Short human-readable title for the OpenAPI schema.
            description: Long-form description for the OpenAPI schema.
            gt: Value must be strictly greater than this.
            ge: Value must be greater than or equal to this.
            lt: Value must be strictly less than this.
            le: Value must be less than or equal to this.
            min_length: Strings must be at least this long.
            max_length: Strings must be at most this long.
            pattern: Strings must fully match this regular expression.
            examples: List of example values for the OpenAPI schema.
            deprecated: Marks the parameter as deprecated in the schema.
            include_in_schema: When ``False``, omit the parameter from the
                generated OpenAPI document.
        """
        self.default = default
        self.alias = alias
        self.title = title
        self.description = description
        self.gt = gt
        self.ge = ge
        self.lt = lt
        self.le = le
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern
        self.examples = examples
        self.deprecated = deprecated
        self.include_in_schema = include_in_schema

    @property
    def required(self) -> bool:
        """``True`` when no default value was supplied."""
        return self.default is ...

    def validate(self, value: Any, name: str) -> Any:
        """Apply numeric / string constraints to *value* and raise ``ValueError`` on violation.

        Args:
            value: The candidate value extracted from the request.
            name: Parameter name, used for error messages.
        Returns:
            The value unchanged on success.
        Raises:
            ValueError: If a constraint is violated.
        """
        if value is None or value is ...:
            return value
        if HAS_CORE and isinstance(value, (int, float)):
            err = _rc.validate_number(
                float(value),
                name,
                gt=self.gt,
                ge=self.ge,
                lt=self.lt,
                le=self.le,
            )
            if err:
                raise ValueError(err)
        else:
            if self.gt is not None and value <= self.gt:
                raise ValueError(f"{name}: must be > {self.gt}")
            if self.ge is not None and value < self.ge:
                raise ValueError(f"{name}: must be >= {self.ge}")
            if self.lt is not None and value >= self.lt:
                raise ValueError(f"{name}: must be < {self.lt}")
            if self.le is not None and value > self.le:
                raise ValueError(f"{name}: must be <= {self.le}")
        if isinstance(value, str):
            if HAS_CORE:
                err = _rc.validate_string(
                    value,
                    name,
                    min_length=self.min_length,
                    max_length=self.max_length,
                )
                if err:
                    raise ValueError(err)
            else:
                if self.min_length is not None and len(value) < self.min_length:
                    raise ValueError(f"{name}: min length is {self.min_length}")
                if self.max_length is not None and len(value) > self.max_length:
                    raise ValueError(f"{name}: max length is {self.max_length}")
            if self.pattern is not None:
                import re

                if not re.fullmatch(self.pattern, value):
                    raise ValueError(f"{name}: does not match pattern {self.pattern}")
        return value

    def openapi_schema_extra(self) -> dict[str, Any]:
        """Return the JSON Schema fragment for the parameter's constraints."""
        extra: dict[str, Any] = {}
        if self.gt is not None:
            extra["exclusiveMinimum"] = self.gt
        if self.ge is not None:
            extra["minimum"] = self.ge
        if self.lt is not None:
            extra["exclusiveMaximum"] = self.lt
        if self.le is not None:
            extra["maximum"] = self.le
        if self.min_length is not None:
            extra["minLength"] = self.min_length
        if self.max_length is not None:
            extra["maxLength"] = self.max_length
        if self.pattern is not None:
            extra["pattern"] = self.pattern
        return extra


class Query(_ParamBase):
    """Marker for a value extracted from the URL query string.

    Example::

        @app.get("/search")
        async def search(q: str = Query(min_length=1, max_length=100),
                         page: int = Query(default=1, ge=1)):
            ...
    """

    _in = "query"


class Path(_ParamBase):
    """Marker for a value extracted from a URL path parameter.

    Path parameters are always required (no default) and validated against
    the path template declared in the route.

    Example::

        @app.get("/users/{user_id}")
        async def get_user(user_id: int = Path(ge=1)):
            ...
    """

    _in = "path"

    def __init__(self, default: Any = ..., **kwargs: Any):
        """Forward to :meth:`_ParamBase.__init__` — path params have no extra options."""
        super().__init__(default, **kwargs)


class Body(_ParamBase):
    """Marker for a value extracted from the request body.

    The framework will coerce the raw bytes / JSON string into the annotation
    type using :mod:`rivex.serialization._bodies`. ``Body()`` with no default
    makes the parameter required.

    Example::

        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            qty: int

        @app.post("/items")
        async def create(item: Item = Body()):
            ...
    """

    _in = "body"

    __slots__ = (*_ParamBase.__slots__, "embed")

    def __init__(self, default: Any = ..., *, embed: bool = False, **kwargs: Any):
        """Declare a body parameter.

        Args:
            default: Default value, or ``...`` for required.
            embed: When ``True``, embed the schema in the OpenAPI operation
                rather than referencing it by name.
            **kwargs: Forwarded to :class:`_ParamBase`.
        """
        super().__init__(default, **kwargs)
        self.embed = embed


class Header(_ParamBase):
    """Marker for a value extracted from an HTTP request header.

    Underscores in the parameter name are converted to dashes by default
    (``trace_id`` → ``trace-id`` header). Use ``alias`` to override.

    Example::

        @app.get("/items")
        async def list_items(trace_id: str | None = Header(default=None)):
            ...
    """

    _in = "header"

    def __init__(self, default: Any = ..., *, convert_underscores: bool = True, **kwargs: Any):
        """Declare a header parameter.

        Args:
            default: Default value, or ``...`` for required.
            convert_underscores: When ``True`` (default), underscores in the
                parameter name are converted to dashes for header lookup.
            **kwargs: Forwarded to :class:`_ParamBase`.
        """
        super().__init__(default, **kwargs)
        self._convert_underscores = convert_underscores

    def header_name(self, param_name: str) -> str:
        """Return the actual HTTP header name used to look up the value."""
        name = self.alias or param_name
        if self._convert_underscores:
            name = name.replace("_", "-")
        return name.lower()


class Cookie(_ParamBase):
    """Marker for a value extracted from a request cookie.

    Example::

        @app.get("/me")
        async def me(session: str = Cookie()):
            ...
    """

    _in = "cookie"