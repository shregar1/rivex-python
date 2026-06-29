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
    _codec_registry[name] = codec_cls


def get_codec(name: str) -> type[BinaryCodec] | None:
    return _codec_registry.get(name)


class BinaryCodec:
    name: str = "raw"

    @staticmethod
    def encode(data: Any) -> bytes: ...

    @staticmethod
    def decode(data: bytes) -> Any: ...

    @staticmethod
    def detect(data: bytes) -> bool: ...


class JSONCodec(BinaryCodec):
    name = "json"

    @staticmethod
    def encode(data: Any) -> bytes:
        return json.dumps(data).encode("utf-8")

    @staticmethod
    def decode(data: bytes) -> Any:
        return json.loads(data.decode("utf-8"))

    @staticmethod
    def detect(data: bytes) -> bool:
        try:
            json.loads(data.decode("utf-8"))
            return True
        except (ValueError, UnicodeDecodeError):
            return False


class MsgPackCodec(BinaryCodec):
    name = "msgpack"

    @staticmethod
    def encode(data: Any) -> bytes:
        import msgpack
        return msgpack.packb(data)

    @staticmethod
    def decode(data: bytes) -> Any:
        import msgpack
        return msgpack.unpackb(data)

    @staticmethod
    def detect(data: bytes) -> bool:
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
    for _name, codec_cls in _codec_registry.items():
        if codec_cls.detect(data):
            return codec_cls.decode(data)
    return data


def auto_encode(data: Any, preferred: str = "json") -> bytes:
    if HAS_ENCODE:
        serialized = json.dumps(data)
        return _rc.ws_codec_encode(serialized, preferred)
    codec_cls = _codec_registry.get(preferred) or JSONCodec
    return codec_cls.encode(data)
