"""``rivex.reload`` — dev-time hot-reload helper.

Usage:

.. code-block:: python

    if __name__ == "__main__":
        app.run(reload=True)  # picks up the helpers below

When ``reload=True``, the parent process launches the original script in
a subprocess, watches the working directory for ``*.py`` changes, and
restarts the subprocess on modification.

Intentional simplicity: this is a 100-line stdlib-only file watcher, not
``watchfiles`` / ``watchdog``. It polls ``os.stat`` mtimes every
~0.3 s — fine for the small project trees you typically run in dev.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# ``mtime`` is good to whole seconds on every platform; some filesystems
# go finer. ``stat_result.st_mtime_ns`` is the precise integer.

DEFAULT_INTERVAL_S = 0.3


def _snapshot(roots: list[Path], extensions: tuple[str, ...]) -> dict[str, int]:
    """Walk ``roots`` and return ``{path: mtime_ns}`` for every matching file."""
    seen: dict[str, int] = {}
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            if root.suffix in extensions:
                try:
                    seen[str(root)] = root.stat().st_mtime_ns
                except OSError:
                    pass
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # Don't descend into common noise — ``__pycache__``, hidden
            # dirs (``.git``, ``.venv``, ``.pytest_cache``, …), build
            # output.
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith(".")
                and d not in ("__pycache__", "node_modules", "build", "dist")
            ]
            for name in filenames:
                if not name.endswith(extensions):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    seen[full] = os.stat(full).st_mtime_ns
                except OSError:
                    continue
    return seen


def _spawn_child() -> subprocess.Popen[bytes]:
    """Launch a fresh subprocess running the original command-line."""
    return subprocess.Popen(
        [sys.executable, *sys.argv],
        env={**os.environ, "RIVEX_RELOAD_CHILD": "1"},
    )


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    """Send SIGTERM and wait briefly, escalate to SIGKILL if it ignores us."""
    if proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=3.0)
    except (subprocess.TimeoutExpired, ProcessLookupError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def run_with_reload(
    *,
    watch_paths: list[Path] | None = None,
    extensions: tuple[str, ...] = (".py",),
    interval: float = DEFAULT_INTERVAL_S,
) -> None:
    """Block, run the server in a child, restart on source change.

    Called by :meth:`rivex.Rivex.run` when ``reload=True``. Not intended
    to be called directly from user code.
    """
    roots = watch_paths or [Path.cwd()]
    print(f"  rivex: watching {[str(r) for r in roots]} for changes (reload mode)")

    snapshot = _snapshot(roots, extensions)
    child = _spawn_child()

    try:
        while True:
            time.sleep(interval)

            if child.poll() is not None:
                # Child crashed — wait for the next file change before
                # respawning so we don't tight-loop on a syntax error.
                while True:
                    time.sleep(interval)
                    new = _snapshot(roots, extensions)
                    if new != snapshot:
                        snapshot = new
                        break
                child = _spawn_child()
                continue

            new = _snapshot(roots, extensions)
            if new == snapshot:
                continue

            # Print what changed — helpful when watching a big tree.
            changed = sorted(
                set(new) ^ set(snapshot)
                | {k for k in set(new) & set(snapshot) if new[k] != snapshot[k]}
            )
            for path in changed[:5]:
                print(f"  rivex: reload triggered by {path}")
            if len(changed) > 5:
                print(f"  rivex: …and {len(changed) - 5} more")

            snapshot = new
            _terminate(child)
            child = _spawn_child()
    except KeyboardInterrupt:
        print("  rivex: stopping reload watcher")
        _terminate(child)
