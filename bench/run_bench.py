"""Minimal benchmark for Rivex's three engine modes.

Measures request/response throughput for a few representative
workloads, on each of the three engines:

* **async**  — the bundled hyper+Tokio engine.
* **sync**   — the bundled std::thread + httparse engine.
* **asgi**   — uvicorn driving the Rivex ASGI adapter.

Workloads:

* ``hello``   — small JSON response.
* ``json``    — slightly larger JSON response.
* ``param``   — path parameter + JSON body.
* ``const``   — registered via ``app.add_const_route`` (exercises
               the pre-baked response cache).

Run with::

    python bench/run_bench.py

Override the engine list with ``RIVEX_BENCH_ENGINES="async,sync"``.
Override the request count with ``RIVEX_BENCH_REQUESTS=20000``.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# The Rivex app can't be pickled (it holds a Rust object), so we
# rebuild it inside the engine subprocess via the helper module.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import the workload definitions from the sibling factory module.
sys.path.insert(0, str(Path(__file__).parent))
from _app_factory import ENGINE_RUNNERS  # noqa: E402

WORKLOADS = ("hello", "json", "param", "const")
ENGINES = tuple(
    e.strip()
    for e in os.environ.get("RIVEX_BENCH_ENGINES", "async,sync,asgi").split(",")
    if e.strip()
)
REQUESTS = int(os.environ.get("RIVEX_BENCH_REQUESTS", "20000"))
WARMUP = max(500, REQUESTS // 50)


# ─── Workload driver ──────────────────────────────────────────────────


def fetch(url: str, timeout: float = 5.0) -> bytes:
    """Single ``urllib`` fetch. Errors are returned as empty bytes
    so the workload doesn't crash on a transient hiccup."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return b""


def drive_workload(base: str, workload: str, n: int) -> list[float]:
    """Send ``n`` sequential requests; return per-request latency in
    milliseconds. Sequential is more honest about the per-request
    cost the user can see and feel under load; concurrent would
    conflate many latencies into a single throughput number."""
    times: list[float] = []
    if workload == "hello":
        url = f"{base}/hello"
    elif workload == "json":
        url = f"{base}/json"
    elif workload == "param":
        url = f"{base}/users/42"
    elif workload == "const":
        url = f"{base}/health"
    else:
        raise ValueError(f"unknown workload: {workload}")
    for _ in range(n):
        t0 = time.perf_counter()
        fetch(url)
        times.append((time.perf_counter() - t0) * 1000)
    return times


def summarise(latencies: list[float]) -> dict[str, float]:
    if not latencies:
        return {"avg_ms": 0.0, "p50_ms": 0.0, "p99_ms": 0.0, "rps": 0.0}
    sorted_lat = sorted(latencies)
    n = len(sorted_lat)
    p50 = sorted_lat[n // 2]
    p99 = sorted_lat[min(n - 1, int(n * 0.99))]
    avg = sum(sorted_lat) / n
    rps = n / (sum(sorted_lat) / 1000)
    return {
        "avg_ms": avg,
        "p50_ms": p50,
        "p99_ms": p99,
        "rps": rps,
    }


# ─── Driver ───────────────────────────────────────────────────────────


def main() -> int:
    print(f"Engines: {', '.join(ENGINES)}")
    print(f"Requests per workload: {REQUESTS} (warmup: {WARMUP})")
    print()

    # Find a free port.
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    results: dict[str, dict[str, dict[str, float]]] = {}
    for engine in ENGINES:
        if engine not in ENGINE_RUNNERS:
            print(f"  skipping unknown engine {engine!r}")
            continue
        print(f"== engine: {engine} ==")
        # Spawn a fresh interpreter per engine. The Rivex app
        # holds a Rust object that can't be pickled, but we can
        # rebuild it in the child via the helper.
        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(
            target=_engine_main,
            args=(engine, port),
            daemon=True,
        )
        proc.start()
        try:
            # Wait for the server to come up.
            base = f"http://127.0.0.1:{port}"
            started = False
            for _ in range(60):
                try:
                    urllib.request.urlopen(base + "/health", timeout=1).read()
                    started = True
                    break
                except Exception:
                    time.sleep(0.25)
            if not started:
                print(f"  {engine}: server didn't start in 15s")
                continue

            results[engine] = {}
            for w in WORKLOADS:
                # Warmup (don't count).
                drive_workload(base, w, WARMUP)
                # Real run.
                latencies = drive_workload(base, w, REQUESTS)
                results[engine][w] = summarise(latencies)
                s = results[engine][w]
                print(
                    f"  {w:5s}: avg={s['avg_ms']:.3f}ms "
                    f"p50={s['p50_ms']:.3f}ms "
                    f"p99={s['p99_ms']:.3f}ms "
                    f"rps={s['rps']:.0f}"
                )
            print()
        finally:
            proc.terminate()
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=2)

    if not results:
        print("No engines produced results — bailing out.")
        return 1

    # Print a compact comparison table.
    print("=== summary (rps / p99 ms) ===")
    header = f"{'workload':<10}" + "".join(f"{e:>16}" for e in results)
    print(header)
    for w in WORKLOADS:
        row = f"{w:<10}"
        for engine in results:
            s = results[engine].get(w, {})
            row += f" {s.get('rps', 0):>6.0f}/{s.get('p99_ms', 0):>5.2f}".rjust(16)
        print(row)
    return 0


def _engine_main(engine: str, port: int) -> None:
    """Subprocess entry point: build the app and run a single engine."""
    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from _app_factory import ENGINE_RUNNERS, make_app

    app = make_app()
    ENGINE_RUNNERS[engine](app, port)


if __name__ == "__main__":
    sys.exit(main())
