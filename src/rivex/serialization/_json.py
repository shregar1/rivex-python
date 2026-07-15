"""Internal JSON helpers.

Single seam between the SDK and the underlying JSON implementation. The
Rust extension's `json_serialize` walks `PyObject` straight to JSON bytes
without going through a `serde_json::Value` intermediate — measured 2×
faster than Python's stdlib `json.dumps().encode()` on typical API
payloads. Deserialise is roughly par with stdlib but lives here for
symmetry and to keep the swap reversible.

Keeping every per-request call site behind these two functions means we
only need to edit one file if we ever want to compare against / revert
to `json.dumps` / `json.loads`.
"""

from __future__ import annotations

from typing import Any

import rivex_core


def dumps(value: Any) -> bytes:
    """Serialise ``value`` to JSON, returning UTF-8 bytes.

    Raises ``ValueError`` on NaN/Infinity floats and ``TypeError`` on
    non-serialisable types (matches orjson's defaults).
    """
    return rivex_core.json_serialize(value)


def loads(data: bytes | str) -> Any:
    """Parse JSON ``data`` into a Python value.

    Accepts both ``bytes`` and ``str`` for stdlib compatibility; the
    underlying Rust path is bytes-only.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return rivex_core.json_deserialize(data)
