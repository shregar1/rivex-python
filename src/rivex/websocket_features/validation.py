from __future__ import annotations

from typing import Any

from rivex.exceptions import WebSocketDisconnect

try:
    import rivex_core as _rc
    HAS_SIZE = hasattr(_rc, "PyMessageSizeValidator")
    HAS_SCHEMA = hasattr(_rc, "PySchemaValidator")
except ImportError:
    _rc = None
    HAS_SIZE = False
    HAS_SCHEMA = False


class MessageSizeValidator:
    def __init__(self, max_text_bytes: int = 65536, max_binary_bytes: int = 262144):
        self._max_text = max_text_bytes
        self._max_binary = max_binary_bytes
        if HAS_SIZE:
            self._core = _rc.PyMessageSizeValidator(max_text_bytes, max_binary_bytes)
        else:
            self._core = None

    def validate_text(self, data: str) -> None:
        if self._core:
            self._core.validate_text(data)
            return
        if len(data.encode("utf-8")) > self._max_text:
            raise WebSocketDisconnect(code=1009, reason=f"text message exceeds {self._max_text} byte limit")

    def validate_bytes(self, data: bytes) -> None:
        if self._core:
            self._core.validate_bytes(data)
            return
        if len(data) > self._max_binary:
            raise WebSocketDisconnect(code=1009, reason=f"binary message exceeds {self._max_binary} byte limit")


class SchemaValidator:
    def __init__(self, schemas: dict[str, Any] | None = None, default_schema: Any = None):
        self._schemas: dict[str, Any] = schemas or {}
        self._default = default_schema
        if HAS_SCHEMA:
            self._core = _rc.PySchemaValidator()
            for msg_type, schema in self._schemas.items():
                import json
                self._core.register_schema(msg_type, json.dumps(schema))
        else:
            self._core = None

    def register_schema(self, msg_type: str, schema: Any) -> None:
        self._schemas[msg_type] = schema
        if self._core:
            import json
            self._core.register_schema(msg_type, json.dumps(schema))

    def validate(self, message: dict[str, Any]) -> dict[str, Any]:
        if self._core:
            import json
            self._core.validate(json.dumps(message))
            return message
        msg_type = message.get("type", "")
        schema = self._schemas.get(msg_type, self._default)
        if schema is None:
            return message
        try:
            import jsonschema
            jsonschema.validate(instance=message, schema=schema)
        except ImportError:
            pass
        except Exception as e:
            raise WebSocketDisconnect(code=1008, reason=f"schema validation failed: {e}")
        return message
