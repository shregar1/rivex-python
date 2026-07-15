from __future__ import annotations

import dataclasses
import datetime
import enum
from decimal import Decimal
from pathlib import Path, PurePath
from typing import Any
from uuid import UUID


def jsonable_encoder(
    obj: Any,
    *,
    include: set[str] | None = None,
    exclude: set[str] | None = None,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    exclude_none: bool = False,
) -> Any:
    """Convert arbitrary objects into JSON-serializable form."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj

    if isinstance(obj, dict):
        return {
            k: jsonable_encoder(v)
            for k, v in obj.items()
            if (include is None or k in include)
            and (exclude is None or k not in exclude)
            and (not exclude_none or v is not None)
        }

    if isinstance(obj, (list, tuple, set, frozenset)):
        return [jsonable_encoder(item) for item in obj]

    if isinstance(obj, Decimal):
        return float(obj)

    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()

    if isinstance(obj, datetime.timedelta):
        return obj.total_seconds()

    if isinstance(obj, UUID):
        return str(obj)

    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")

    if isinstance(obj, (Path, PurePath)):
        return str(obj)

    if isinstance(obj, enum.Enum):
        return obj.value

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        fields = dataclasses.fields(obj)
        return {
            f.name: jsonable_encoder(getattr(obj, f.name))
            for f in fields
            if (include is None or f.name in include) and (exclude is None or f.name not in exclude)
        }

    # Pydantic model
    if hasattr(obj, "model_dump"):
        kwargs: dict[str, Any] = {}
        if include is not None:
            kwargs["include"] = include
        if exclude is not None:
            kwargs["exclude"] = exclude
        if exclude_unset:
            kwargs["exclude_unset"] = True
        if exclude_defaults:
            kwargs["exclude_defaults"] = True
        if exclude_none:
            kwargs["exclude_none"] = True
        return jsonable_encoder(obj.model_dump(**kwargs))

    # Fallback: try __dict__
    if hasattr(obj, "__dict__"):
        return jsonable_encoder(
            obj.__dict__, include=include, exclude=exclude, exclude_none=exclude_none
        )

    return str(obj)
