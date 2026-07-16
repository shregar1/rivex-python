"""HTTP benchmarking for ``rivex bench``.

Stdlib-only (``urllib`` + ``ThreadPoolExecutor``) so the command has no
extra dependencies. Ported from the standalone ``rivex-cli`` package so the
framework ships its own bench tool natively.
"""

from __future__ import annotations

import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import IO
from urllib.error import URLError
from urllib.request import Request, urlopen


def run_bench(
    url: str,
    num_requests: int,
    concurrency: int,
    method: str,
    *,
    out: IO[str] | None = None,
) -> None:
    """Run *num_requests* requests against *url* and print a summary.

    *out* defaults to :data:`sys.stdout`; tests pass a buffer to capture
    output without touching the real stream.
    """
    import sys

    out = out or sys.stdout

    print(f"\n  Benchmarking {url}", file=out)
    print(f"  {num_requests} requests, {concurrency} concurrent\n", file=out)

    latencies: list[float] = []
    status_counts: dict[int, int] = {}
    errors = 0

    def make_request() -> tuple[float, int]:
        start = time.perf_counter()
        try:
            req = Request(url, method=method)
            with urlopen(req, timeout=30) as resp:
                resp.read()
                elapsed = time.perf_counter() - start
                return elapsed, resp.status
        except URLError:
            return time.perf_counter() - start, 0
        except Exception:
            return time.perf_counter() - start, 0

    total_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(make_request) for _ in range(num_requests)]
        for future in as_completed(futures):
            elapsed, status = future.result()
            if 200 <= status < 400:
                latencies.append(elapsed)
            else:
                errors += 1
            status_counts[status] = status_counts.get(status, 0) + 1

    total_elapsed = time.perf_counter() - total_start

    print("  Results", file=out)
    print(f"  {'─' * 40}", file=out)
    print(f"  Total time:     {total_elapsed:.2f}s", file=out)

    if latencies:
        rps = len(latencies) / total_elapsed
        print(f"  Requests/sec:   {rps:.1f}", file=out)
    print(f"  Successful:     {len(latencies)}", file=out)
    print(f"  Failed:         {errors}", file=out)

    if status_counts:
        parts = [f"{s}={c}" for s, c in sorted(status_counts.items())]
        print(f"  Status codes:   {', '.join(parts)}", file=out)

    if latencies:
        latencies.sort()
        print("\n  Latency", file=out)
        print(f"  {'─' * 40}", file=out)
        print(f"  Min:            {_ms(min(latencies))}", file=out)
        print(f"  Mean:           {_ms(statistics.mean(latencies))}", file=out)
        print(f"  Max:            {_ms(max(latencies))}", file=out)
        print(f"  p50:            {_ms(_percentile(latencies, 50))}", file=out)
        print(f"  p90:            {_ms(_percentile(latencies, 90))}", file=out)
        print(f"  p99:            {_ms(_percentile(latencies, 99))}", file=out)
    print(file=out)


def _percentile(data: list[float], p: int) -> float:
    idx = int(len(data) * p / 100)
    return data[min(idx, len(data) - 1)]


def _ms(seconds: float) -> str:
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f}µs"
    if seconds < 1.0:
        return f"{seconds * 1000:.1f}ms"
    return f"{seconds:.2f}s"
