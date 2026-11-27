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
        """Convert a raw input value into the field's Python type.

        Honours ``allow_null`` (returns ``None`` unchanged), then
        dispatches on ``field_type`` to coerce the common primitive
        types (``int``, ``float``, ``bool``). Any other type falls
        through to ``str(data)`` so the validator pipeline still
        sees a string-shaped value.

        Args:
            data: The raw value as received from the request or
                the upstream serializer.

        Returns:
            The coerced value suitable for further validation
            and storage.
        """
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
        """Return the value to expose when serializing this field.

        The default implementation is a pass-through so subclass
        fields can override it for any custom rendering
        (formatted datetimes, masked strings, etc.) without
        needing to special-case the rest of the field.

        Args:
            value: The Python value held on the model instance.

        Returns:
            The value to put into the serialized output.
        """
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
        """Populate ``self._fields`` from class-level ``Field`` declarations.

        Walks the class via :func:`dir` and stores any
        :class:`Field` instance found on the class under its
        attribute name. Called from ``__init__`` so the field
        map is available before any other serializer method
        runs.
        """
        for attr_name in dir(self.__class__):
            val = getattr(self.__class__, attr_name)
            if isinstance(val, Field):
                self._fields[attr_name] = val

    @property
    def fields(self) -> dict[str, Field]:
        """Return a copy of the field map for introspection."""
        return dict(self._fields)

    @property
    def errors(self) -> dict[str, list[str]]:
        """Return a copy of the per-field validation errors from the last :meth:`is_valid` call."""
        return dict(self._errors)

    @property
    def validated_data(self) -> dict[str, Any]:
        """Return a copy of the cleaned values produced by the last successful :meth:`is_valid` call."""
        return dict(self._validated_data)

    def is_valid(self, raise_exception: bool = False) -> bool:
        """Validate the bound data and populate :attr:`errors` and :attr:`validated_data`.

        Iterates every non-read-only field, applies the
        ``default``/``required``/``allow_null`` rules, coerces
        via :meth:`Field.to_internal_value`, and runs each
        field's ``validators`` chain. Errors accumulate per
        field rather than aborting so callers see every
        problem in one pass.

        Args:
            raise_exception: When ``True``, raise
                :class:`ValueError` with the collected errors
                if any field failed. Default ``False``.

        Returns:
            ``True`` when no field produced an error, otherwise
            ``False``.
        """
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
        """Build a JSON-serialisable dict from *instance* using the declared fields.

        Skips write-only fields and reads the value through
        ``field.source or name`` so callers can remap a
        serializer key onto a differently-named attribute on
        the model.

        Args:
            instance: A model instance or ``dict`` whose
                attributes back the serialized output.

        Returns:
            A ``dict`` keyed by serializer field name with
            each value passed through
            :meth:`Field.to_representation`.
        """
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
        """Inherit parent fields and add fields derived from ``_model_cls`` annotations.

        After running the base :meth:`Serializer._build_fields`
        the method also inspects the type hints on
        ``_model_cls`` and adds a default :class:`Field` for any
        attribute the serializer has not already declared
        explicitly — this is what makes a ``ModelSerializer``
        "just work" against a pydantic/dataclass model.
        """
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
        """Validate each list element through the configured ``child`` serializer.

        When ``child`` is ``None`` the data is accepted as long
        as it is a list — no per-element validation runs. With a
        child, each item is wrapped in a fresh child instance,
        validated, and any errors are merged back with the
        index prefix so the caller can tell which element
        failed.

        Args:
            raise_exception: Forwarded for API parity with
                :meth:`Serializer.is_valid`; this implementation
                never raises.

        Returns:
            ``True`` when the data is a list (and every child
            validated, if a child is configured); ``False``
            otherwise.
        """
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
        """Serialize each item of *instances* through ``self.child``.

        When ``child`` is ``None`` the input list is returned
        unchanged — the list serializer cannot synthesize a
        representation without a template.

        Args:
            instances: The list of model instances (or dicts)
                to serialize.

        Returns:
            A list with each item passed through
            ``self.child.to_representation`` when a child is
            configured; the input list otherwise.
        """
        if self.child is None:
            return list(instances)
        return [self.child.to_representation(inst) for inst in instances]
