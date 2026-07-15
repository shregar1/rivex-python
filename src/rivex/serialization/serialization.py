from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def _default_serializer(v: Any) -> bytes:
    return json.dumps(v).encode("utf-8")


_serializer: Callable[[Any], bytes] = _default_serializer
_deserializer: Callable[[bytes | str], Any] = json.loads


def set_serializer(
    serializer: Callable[[Any], bytes],
    deserializer: Callable[[bytes | str], Any] | None = None,
) -> None:
    """Override the global JSON serializer/deserializer.

    Usage:
        import orjson
        set_serializer(orjson.dumps, orjson.loads)

    Or:
        import msgspec
        encoder = msgspec.json.Encoder()
        decoder = msgspec.json.Decoder()
        set_serializer(encoder.encode, decoder.decode)
    """
    global _serializer, _deserializer
    _serializer = serializer
    if deserializer is not None:
        _deserializer = deserializer


def serialize(value: Any) -> bytes:
    result = _serializer(value)
    if isinstance(result, str):
        return result.encode("utf-8")
    return result


def deserialize(data: bytes | str) -> Any:
    return _deserializer(data)
