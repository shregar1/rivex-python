from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def _default_serializer(v: Any) -> bytes:
    """Serialize a Python value as UTF-8 encoded JSON bytes.

    Used as the fallback serializer when no faster backend is installed
    via ``set_serializer``. Falls back to the standard-library
    ``json`` module which supports the common subset of JSON types.

    Args:
        v: Any JSON-serializable value.

    Returns:
        The value encoded as UTF-8 bytes.
    """
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
    """Encode a Python value to bytes using the active serializer.

    Delegates to the serializer registered through ``set_serializer``
    (which defaults to ``_default_serializer``). When the registered
    serializer returns ``str`` instead of ``bytes`` it is re-encoded
    as UTF-8 so the public return type stays consistent.

    Args:
        value: Any value supported by the active serializer.

    Returns:
        The encoded representation as ``bytes``.
    """
    result = _serializer(value)
    if isinstance(result, str):
        return result.encode("utf-8")
    return result


def deserialize(data: bytes | str) -> Any:
    """Decode bytes or text into a Python value using the active deserializer.

    Delegates to the deserializer registered through ``set_serializer``
    (which defaults to ``json.loads``). The input is forwarded as-is,
    so byte inputs are accepted by backends that know how to handle
    them (e.g. ``orjson``, ``msgspec``) and string inputs by backends
    that expect text.

    Args:
        data: The encoded payload to decode, as ``bytes`` or ``str``.

    Returns:
        The decoded Python value (typically a ``dict`` or ``list`` for
        JSON-shaped payloads).
    """
    return _deserializer(data)
