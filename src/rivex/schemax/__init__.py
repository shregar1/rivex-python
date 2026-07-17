"""``rivex.schemax`` — back-compat shim. The canonical home is ``schemax.idl``.

The IDL/RPC toolchain that used to live here has moved to the standalone
``schemax`` package, where it sits alongside the Schemax validation library
(``schemax.Schema``, ``schemax.Field``, …) as ``schemax.idl.*``.

This module re-exports the new location so existing imports
(``from rivex.schemax import parse, Message, RpcClient, …``) keep working.
A DeprecationWarning fires on first import.

Migration:

* ``from rivex.schemax import …`` → ``from schemax.idl import …``
* ``from rivex.schemax.fastapi_plugin import …``
  → ``from schemax.idl.adapters.fastapi import …``
* ``rivex schemax compile foo.schemax`` → ``schemax idl compile foo.schemax``
"""

from __future__ import annotations

import warnings

try:
    from schemax.idl import *  # noqa: F401,F403
    from schemax.idl import __all__ as __all__
    from schemax.idl.adapters import fastapi as fastapi_plugin  # noqa: F401

    _AVAILABLE = True
except ImportError as e:  # pragma: no cover
    _AVAILABLE = False
    _ERR = e
    __all__ = []

if _AVAILABLE:
    warnings.warn(
        "rivex.schemax has moved to schemax.idl. "
        "Please update your imports: `from schemax.idl import ...`. "
        "This shim will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
else:

    def __getattr__(name):  # pragma: no cover
        raise AttributeError(
            f"module 'rivex.schemax' has no attribute {name!r}; "
            f"the upstream schemax.idl package is no longer shipped. "
            f"Install it with `pip install schemax` "
            f"(original error: {_ERR})"
        )
