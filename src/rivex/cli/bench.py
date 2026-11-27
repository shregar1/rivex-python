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
        """Issue a single HTTP request and return ``(elapsed_seconds, status)``.

        A ``URLError`` (network/connection failure) or any unexpected
        exception is reported as status ``0`` so the caller can bucket
        the result alongside genuine HTTP errors. Only successful
        2xx/3xx responses contribute to the latency distribution.

        Returns:
            A ``(elapsed_seconds, status_code)`` tuple. ``status_code``
            is the HTTP status on success, or ``0`` when the call
            failed before a response was received.
        """
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
    """Return the ``p``-th percentile of a sorted latency sample.

    Uses a nearest-rank estimator: ``data`` must be sorted in
    ascending order (the bench loop sorts before calling this).
    Out-of-range percentiles are clamped to the largest index so
    ``p99`` against a 50-sample list still returns a valid value.

    Args:
        data: Latency samples in seconds, sorted ascending.
        p: Percentile to extract, in the closed range ``[0, 100]``.

    Returns:
        The chosen latency value in seconds.
    """
    idx = int(len(data) * p / 100)
    return data[min(idx, len(data) - 1)]


def _ms(seconds: float) -> str:
    """Format a latency in seconds as a human-friendly short string.

    Microseconds (``µs``) are used below 1 ms, milliseconds
    (``ms``) below one second, and seconds otherwise. The unit is
    chosen automatically based on magnitude rather than caller
    configuration.

    Args:
        seconds: Latency in seconds.

    Returns:
        The latency plus an appropriate unit suffix, e.g. ``"1.2ms"``
        or ``"0.42s"``.
    """
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f}µs"
    if seconds < 1.0:
        return f"{seconds * 1000:.1f}ms"
    return f"{seconds:.2f}s"
