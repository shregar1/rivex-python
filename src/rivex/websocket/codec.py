from __future__ import annotations

import json
from typing import Any

try:
    import rivex_core as _rc
    HAS_ENCODE = hasattr(_rc, "ws_codec_encode")
except ImportError:
    _rc = None
    HAS_ENCODE = False

_codec_registry: dict[str, type[BinaryCodec]] = {}


def register_codec(name: str, codec_cls: type[BinaryCodec]) -> None:
    """Add a codec class to the global registry so auto-detect can find it.

    Replaces any existing codec registered under the same ``name``. Called
    by users that want to make a custom :class:`BinaryCodec` subclass
    available to :func:`auto_decode` and :func:`auto_encode`.

    Args:
        name: Identifier used to look the codec up in :func:`get_codec`
            and to match against ``preferred`` in :func:`auto_encode`.
        codec_cls: Concrete subclass of :class:`BinaryCodec` to register.
    """
    _codec_registry[name] = codec_cls


def get_codec(name: str) -> type[BinaryCodec] | None:
    """Look up a previously-registered codec by name.

    Args:
        name: Identifier passed to :func:`register_codec`.

    Returns:
        The registered codec class, or ``None`` if no codec has been
        registered under that name.
    """
    return _codec_registry.get(name)


class BinaryCodec:
    name: str = "raw"

    @staticmethod
    def encode(data: Any) -> bytes:
        """Encode ``data`` into raw bytes.

        Subclasses must override this. The base implementation raises
        ``NotImplementedError`` to make accidental use of the abstract
        base class explicit.

        Args:
            data: The value to serialise.

        Returns:
            The encoded byte string.
        """
        ...

    @staticmethod
    def decode(data: bytes) -> Any:
        """Decode ``data`` from raw bytes back into a Python value.

        Subclasses must override this. The base implementation raises
        ``NotImplementedError`` so accidental use of the abstract base
        class surfaces immediately.

        Args:
            data: The byte string to deserialise.

        Returns:
            The decoded Python value.
        """
        ...

    @staticmethod
    def detect(data: bytes) -> bool:
        """Return whether ``data`` looks like an instance of this codec.

        Used by :func:`auto_decode` to pick the right decoder. The base
        implementation returns ``False`` so a bare :class:`BinaryCodec`
        is never chosen.

        Args:
            data: The byte string to inspect.

        Returns:
            ``True`` if this codec should be used to decode ``data``.
        """
        ...


class JSONCodec(BinaryCodec):
    name = "json"

    @staticmethod
    def encode(data: Any) -> bytes:
        """Serialise ``data`` to UTF-8-encoded JSON bytes.

        Args:
            data: Any JSON-serialisable Python value.

        Returns:
            The JSON document encoded as ``utf-8`` bytes.
        """
        return json.dumps(data).encode("utf-8")

    @staticmethod
    def decode(data: bytes) -> Any:
        """Parse UTF-8-encoded JSON bytes back into a Python value.

        Args:
            data: The JSON document encoded as ``utf-8`` bytes.

        Returns:
            The decoded Python value (dict, list, str, int, etc.).
        """
        return json.loads(data.decode("utf-8"))

    @staticmethod
    def detect(data: bytes) -> bool:
        """Return whether ``data`` parses as valid JSON.

        Attempts to decode and parse the bytes; any
        :class:`ValueError` or :class:`UnicodeDecodeError` is treated as
        a non-match so the auto-detector can move on to the next codec.

        Args:
            data: Bytes that may or may not be JSON.

        Returns:
            ``True`` when ``data`` parses as JSON, ``False`` otherwise.
        """
        try:
            json.loads(data.decode("utf-8"))
            return True
        except (ValueError, UnicodeDecodeError):
            return False


class MsgPackCodec(BinaryCodec):
    name = "msgpack"

    @staticmethod
    def encode(data: Any) -> bytes:
        """Serialise ``data`` to MessagePack bytes.

        Imports :mod:`msgpack` lazily so the dependency is only required
        when this codec is actually used.

        Args:
            data: Any MessagePack-serialisable Python value.

        Returns:
            The MessagePack-encoded byte string.
        """
        import msgpack
        return msgpack.packb(data)

    @staticmethod
    def decode(data: bytes) -> Any:
        """Decode MessagePack bytes back into a Python value.

        Imports :mod:`msgpack` lazily so the dependency is only required
        when this codec is actually used.

        Args:
            data: The MessagePack-encoded byte string.

        Returns:
            The decoded Python value.
        """
        import msgpack
        return msgpack.unpackb(data)

    @staticmethod
    def detect(data: bytes) -> bool:
        """Return whether ``data`` starts with a valid MessagePack marker.

        Performs a cheap check on the first byte only — it must fall into
        one of the MessagePack "fixmap", "fixarray", "fixstr", positive
        fixint, negative fixint, or higher-range marker ranges.

        Args:
            data: Bytes that may or may not be a MessagePack document.

        Returns:
            ``True`` when the first byte is a plausible MessagePack
            marker, ``False`` otherwise (including for empty input).
        """
        if not data:
            return False
        b = data[0]
        return (
            (0x80 <= b <= 0x8F)
            or (0x90 <= b <= 0x9F)
            or (0xA0 <= b <= 0xBF)
            or (0xC0 <= b <= 0xDF)
            or (0xE0 <= b <= 0xFF)
        )


register_codec("json", JSONCodec)
register_codec("msgpack", MsgPackCodec)


def auto_decode(data: bytes) -> Any:
    """Decode ``data`` using the first codec whose ``detect`` matches.

    Iterates over every codec registered via :func:`register_codec` in
    insertion order. The first codec whose ``detect`` returns ``True``
    is used to decode ``data``. When no codec claims the bytes, they are
    returned unchanged so the caller can decide what to do with raw
    input.

    Args:
        data: The bytes to inspect and decode.

    Returns:
        The decoded Python value, or ``data`` itself when no codec
        matches.
    """
    for _name, codec_cls in _codec_registry.items():
        if codec_cls.detect(data):
            return codec_cls.decode(data)
    return data


def auto_encode(data: Any, preferred: str = "json") -> bytes:
    """Serialise ``data`` using the preferred codec (or JSON by default).

    Falls back to JSON when the requested codec has not been registered.
    When the native core exposes ``ws_codec_encode``, ``data`` is JSON-
    pre-serialised and the Rust helper is asked to re-encode it according
    to ``preferred`` for a faster path.

    Args:
        data: The value to serialise.
        preferred: Name of the codec to use. Defaults to ``"json"``. If
            the named codec is missing, JSON is used as a fallback.

    Returns:
        The encoded byte string ready to send on the wire.
    """
    if HAS_ENCODE:
        serialized = json.dumps(data)
        return _rc.ws_codec_encode(serialized, preferred)
    codec_cls = _codec_registry.get(preferred) or JSONCodec
    return codec_cls.encode(data)
