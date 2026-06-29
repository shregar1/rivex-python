"""Shared DTO primitives."""

from __future__ import annotations

import dataclasses
import json
from abc import ABC
from typing import Any, Self

from rivex import Field, Schema

__all__ = ["IDto", "ApplicationBaseModel", "Field", "Schema"]


class IDto(ABC):
    """Root marker for all DTOs in ``dtos/``."""

    @classmethod
    def validate_payload(cls, data: dict[str, Any]) -> Self:
        """Parse and validate inbound data.

        Default implementation routes through ``cls.model_validate``, which
        every concrete DTO inherits from ``ApplicationBaseModel``.
        """
        validator = getattr(cls, "model_validate", None)
        if validator is None:
            raise NotImplementedError(
                f"{cls.__name__} must override validate_payload or inherit ApplicationBaseModel"
            )
        return validator(data)


class ApplicationBaseModel(Schema):
    """Shared Rivex ``Schema`` base for DTOs (pydantic-core, no full ``BaseModel``)."""

    model_config = {
        "extra": "forbid",
        "populate_by_name": True,
    }

    @staticmethod
    def _strip_string_fields(data: Any) -> Any:
        """Replaces Pydantic ``str_strip_whitespace`` (not on ``rivex.Schema``)."""
        if isinstance(data, dict):
            return {
                key: ApplicationBaseModel._strip_string_fields(value)
                if isinstance(value, (dict, list))
                else value.strip()
                if isinstance(value, str)
                else value
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [
                item.strip() if isinstance(item, str) else ApplicationBaseModel._strip_string_fields(item)
                for item in data
            ]
        return data

    @classmethod
    def model_validate(cls, data: Any, **kwargs: Any) -> Self:
        if isinstance(data, dict):
            data = cls._strip_string_fields(data)
        return super().model_validate(data, **kwargs)

    @classmethod
    def model_validate_json(cls, data: bytes | str, **kwargs: Any) -> Self:
        raw = data.decode() if isinstance(data, bytes) else data
        return cls.model_validate(json.loads(raw), **kwargs)

    @classmethod
    def validate_payload(cls, data: dict[str, Any]) -> Self:
        """Concrete default for the ``IDto`` contract."""
        return cls.model_validate(data)

    @classmethod
    def model_validate_from_object(cls, obj: Any) -> Self:
        """Validate from a dataclass or plain object (replaces ``from_attributes``)."""
        if isinstance(obj, dict):
            return cls.model_validate(obj)
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return cls.model_validate(dataclasses.asdict(obj))
        attrs = {name: getattr(obj, name) for name in cls.model_fields if hasattr(obj, name)}
        if attrs:
            return cls.model_validate(attrs)
        raise TypeError(f"Cannot validate {cls.__name__} from {type(obj)!r}")
