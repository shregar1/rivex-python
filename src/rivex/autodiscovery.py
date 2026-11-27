"""``rivex.autodiscovery`` — automatic route discovery."""

from __future__ import annotations

import fnmatch
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from rivex.web.routing import Router

__all__ = ["autodiscover"]


def autodiscover(
    app: Any,
    directory: str | Path,
    *,
    prefix: str = "",
    pattern: str = "*.py",
    exclude: list[str] | None = None,
) -> int:
    """Scan *directory* for Python files exposing a ``Router`` or ``router`` and mount them onto *app*.

    Returns the number of routers auto-discovered and mounted.
    """
    dir_path = Path(directory)
    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    exclude_patterns = exclude or []
    count = 0

    for root, _, files in os.walk(dir_path):
        for fname in files:
            if not fnmatch.fnmatch(fname, pattern):
                continue

            if any(fnmatch.fnmatch(fname, pat) for pat in exclude_patterns):
                continue

            file_path = Path(root) / fname
            mod_name = f"_autodiscover_{file_path.stem}_{hash(str(file_path)) & 0xFFFFFFFF}"

            spec = importlib.util.spec_from_file_location(mod_name, file_path)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(mod_name, None)
                continue

            # Look for any Router instance in the imported module
            found_router = False
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, Router):
                    if prefix:
                        app.include_router(attr, prefix=prefix)
                    else:
                        app.include_router(attr)
                    found_router = True

            if found_router:
                count += 1

    return count
