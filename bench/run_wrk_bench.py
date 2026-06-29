"""Robust wrk benchmark — wraps each engine in a subprocess.

Each engine subprocess builds its own Rivex app and runs it.
The parent process runs wrk against the bound port with a strict
timeout and a kill-on-failure path so a hung subprocess can't
stall the whole harness.

Usage::

    python bench/run_wrk_bench.py
    BENCH_DURATION=20s BENCH_CONNECTIONS=256 python bench/run_wrk_bench.py
"""

from __future__ import annotations

import multiprocessing
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

DURATION = os.environ.get("BENCH_DURATION", "10s")
WRK_THREADS = os.environ.get("BENCH_THREADS", "4")
WRK_CONNECTIONS = os.environ.get("BENCH_CONNECTIONS", "128")
WARMUP = os.environ.get("BENCH_WARMUP", "3s")


def _server_main(engine: str, port: int) -> None:
    """Subprocess entry: build the app and run a single engine."""
    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from _app_factory import ENGINE_RUNNERS, make_app

    app = make_app()
    ENGINE_RUNNERS[engine](app, port)


def _find_free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_for_server(port: int, timeout: float = 10.0) -> bool:
    """Poll ``/health`` until the server is up, with a hard timeout."""
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            time.sleep(0.1)
    return False


def run_wrk(port: int, duration: str = DURATION) -> tuple[float, float]:
    """Run ``wrk`` and parse the RPS / p99 from its output."""
    cmd = [
        "wrk",
        f"-t{WRK_THREADS}",
        f"-c{WRK_CONNECTIONS}",
        "-d",
        duration,
        "--latency",
        f"http://127.0.0.1:{port}/hello",
    ]
    print(f"  $ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print("  wrk timed out after 120s")
        return (0.0, 0.0)
    if result.returncode != 0:
        print(f"  wrk failed (rc={result.returncode}):\n{result.stderr}")
        return (0.0, 0.0)
    rps = 0.0
    p99 = 0.0
    for line in result.stdout.splitlines():
        if "Requests/sec:" in line:
            try:
                rps = float(line.split()[-1])
            except (ValueError, IndexError):
                pass
        if "99%" in line:
            try:
                # wrk's latency table looks like:
                # "   99%      1.23ms"
                last = line.strip().split()[-1]
                for suffix in ("ms", "µs", "us", "s"):
                    if last.endswith(suffix):
                        last = last[: -len(suffix)]
                        break
                p99 = float(last)
            except (ValueError, IndexError):
                pass
    return (rps, p99)


def bench_one(engine: str) -> tuple[float, float] | None:
    """Run wrk against a fresh engine subprocess, return (rps, p99)."""
    port = _find_free_port()
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(
        target=_server_main, args=(engine, port), daemon=True
    )
    proc.start()
    try:
        if not _wait_for_server(port, timeout=10):
            print("  server didn't come up")
            return None
        # Warmup
        subprocess.run(
            [
                "wrk",
                f"-t{WRK_THREADS}",
                f"-c{WRK_CONNECTIONS}",
                "-d",
                WARMUP,
                f"http://127.0.0.1:{port}/hello",
            ],
            capture_output=True, text=True, timeout=30,
        )
        return run_wrk(port)
    finally:
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2)


def main() -> int:
    print("Engines: async, sync, asgi")
    print(f"Duration: {DURATION}, threads: {WRK_THREADS}, conns: {WRK_CONNECTIONS}")
    print()

    results: dict[str, tuple[float, float]] = {}
    for engine in ("async", "sync", "asgi"):
        print(f"== engine: {engine} ==")
        r = bench_one(engine)
        if r is None:
            continue
        rps, p99 = r
        results[engine] = (rps, p99)
        print(f"  → {rps:.0f} rps, p99 {p99:.2f}ms")
        print()

    if not results:
        print("No engines produced results — bailing out.")
        return 1

    print("=== summary (rps / p99 ms) ===")
    print(f"{'engine':<10} {'rps':>12} {'p99_ms':>10}")
    for engine, (rps, p99) in results.items():
        print(f"{engine:<10} {rps:>12.0f} {p99:>10.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())