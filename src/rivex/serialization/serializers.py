from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, get_type_hints


class Field:
    """Serializer field definition."""

    def __init__(
        self,
        field_type: type = str,
        required: bool = True,
        default: Any = None,
        label: str = "",
        validators: list[Callable] | None = None,
        source: str | None = None,
        read_only: bool = False,
        write_only: bool = False,
        allow_null: bool = False,
    ):
        self.field_type = field_type
        self.required = required
        self.default = default
        self.label = label
        self.validators = validators or []
        self.source = source
        self.read_only = read_only
        self.write_only = write_only
        self.allow_null = allow_null

    def to_internal_value(self, data: Any) -> Any:
        if data is None and self.allow_null:
            return None
        if self.field_type is int:
            return int(data)
        elif self.field_type is float:
            return float(data)
        elif self.field_type is bool:
            if isinstance(data, str):
                return data.lower() in ("true", "1", "yes")
            return bool(data)
        return str(data)

    def to_representation(self, value: Any) -> Any:
        return value


class Serializer(ABC):
    """Base serializer class for data validation and deserialization.

    Usage::

        class UserSerializer(Serializer):
            id = Field(field_type=int, read_only=True)
            name = Field(field_type=str)
            email = Field(field_type=str)
    """

    def __init__(self, data: dict | None = None, instance: Any = None):
        self._data = data or {}
        self._instance = instance
        self._errors: dict[str, list[str]] = {}
        self._validated_data: dict[str, Any] = {}
        self._fields: dict[str, Field] = {}
        self._build_fields()

    def _build_fields(self) -> None:
        for attr_name in dir(self.__class__):
            val = getattr(self.__class__, attr_name)
            if isinstance(val, Field):
                self._fields[attr_name] = val

    @property
    def fields(self) -> dict[str, Field]:
        return dict(self._fields)

    @property
    def errors(self) -> dict[str, list[str]]:
        return dict(self._errors)

    @property
    def validated_data(self) -> dict[str, Any]:
        return dict(self._validated_data)

    def is_valid(self, raise_exception: bool = False) -> bool:
        self._errors = {}
        self._validated_data = {}
        for name, field in self._fields.items():
            if field.read_only:
                continue
            raw = self._data.get(name, field.default)
            if raw is None and not field.allow_null and field.required:
                self._errors.setdefault(name, []).append("This field is required.")
                continue
            if raw is not None:
                try:
                    cleaned = field.to_internal_value(raw)
                    for validator in field.validators:
                        cleaned = validator(cleaned)
                    self._validated_data[name] = cleaned
                except (ValueError, TypeError) as e:
                    self._errors.setdefault(name, []).append(str(e))
        if raise_exception and self._errors:
            raise ValueError(f"Validation error: {self._errors}")
        return len(self._errors) == 0

    def to_representation(self, instance: Any) -> dict:
        result: dict[str, Any] = {}
        for name, field in self._fields.items():
            if field.write_only:
                continue
            if isinstance(instance, dict):
                value = instance.get(field.source or name)
            else:
                value = getattr(instance, field.source or name, None)
            result[name] = field.to_representation(value)
        return result

    @property
    def data(self) -> dict:
        return self.to_representation(self._instance)


class ModelSerializer(Serializer):
    """Automatically generates fields from model declarations."""

    _model_cls: type | None = None

    def _build_fields(self) -> None:
        super()._build_fields()
        model_cls = getattr(self.__class__, "_model_cls", None) or getattr(self, "_model_cls", None)
        if model_cls:
            declared = set(self._fields.keys())
            hints = get_type_hints(model_cls) if hasattr(model_cls, "__annotations__") else {}
            for attr_name, attr_type in hints.items():
                if attr_name not in declared:
                    self._fields[attr_name] = Field(field_type=attr_type)


class ListSerializer(Serializer):
    """Serializer for lists of items."""

    child: Serializer | None = None

    def is_valid(self, raise_exception: bool = False) -> bool:
        if not isinstance(self._data, list):
            self._errors = {"_non_field": ["Expected a list of items."]}
            return False
        if self.child is None:
            return True
        for i, item in enumerate(self._data):
            child = self.child.__class__(data=item)
            if not child.is_valid():
                for field, errs in child.errors.items():
                    self._errors[f"[{i}].{field}"] = errs
        return len(self._errors) == 0

    def to_representation(self, instances: list) -> list[dict]:
        if self.child is None:
            return list(instances)
        return [self.child.to_representation(inst) for inst in instances]
