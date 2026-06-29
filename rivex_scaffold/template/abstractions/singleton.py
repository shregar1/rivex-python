"""Thread-safe singleton metaclass for configuration objects."""

from __future__ import annotations

import threading
from typing import Any, ClassVar


class SingletonMeta(type):
    """Ensures at most one instance per concrete class."""

    _instances: ClassVar[dict[type, Any]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)
            return cls._instances[cls]

    @classmethod
    def reset(mcls, target: type | None = None) -> None:
        """Clear cached instance(s). Intended for tests only."""
        with mcls._lock:
            if target is None:
                mcls._instances.clear()
            else:
                mcls._instances.pop(target, None)
