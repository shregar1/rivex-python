from __future__ import annotations

from typing import Any

from rivex.core._compat import HAS_CORE
from rivex.core._compat import rc as _rc


class _ParamBase:
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
        return self.default is ...

    def validate(self, value: Any, name: str) -> Any:
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
    _in = "query"


class Path(_ParamBase):
    _in = "path"

    def __init__(self, default: Any = ..., **kwargs: Any):
        super().__init__(default, **kwargs)


class Body(_ParamBase):
    _in = "body"

    __slots__ = (*_ParamBase.__slots__, "embed")

    def __init__(self, default: Any = ..., *, embed: bool = False, **kwargs: Any):
        super().__init__(default, **kwargs)
        self.embed = embed


class Header(_ParamBase):
    _in = "header"

    def __init__(self, default: Any = ..., *, convert_underscores: bool = True, **kwargs: Any):
        super().__init__(default, **kwargs)
        self._convert_underscores = convert_underscores

    def header_name(self, param_name: str) -> str:
        name = self.alias or param_name
        if self._convert_underscores:
            name = name.replace("_", "-")
        return name.lower()


class Cookie(_ParamBase):
    _in = "cookie"
