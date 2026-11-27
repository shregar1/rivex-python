"""``rivex.cli.dev_repl`` — interactive developer REPL."""

from __future__ import annotations

import code
from typing import Any

__all__ = ["start_repl"]


def start_repl(app: Any, banner: str = "Rivex Interactive REPL") -> None:
    """Start an interactive Python REPL with *app* in scope."""
    local_ns = {"app": app, "rivex": app}
    code.interact(banner=banner, local=local_ns)
