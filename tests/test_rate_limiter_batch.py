"""Batch API tests for the Rust-backed TokenBucket / SlidingWindow rate limiters.

Verifies that the new ``check_many`` / ``remaining_many`` (TokenBucket) and
``allow_many`` / ``get_remaining_many`` (SlidingWindow) pyclass methods match
the semantics of their per-key counterparts, including edge cases like empty
input, mixed allowed/denied keys, and ordering preservation.

Also exercises the Python-side ``RateLimitMiddleware.check_batch`` and
``BaseThrottle.check_many`` helpers to make sure the fallback path stays
in sync with the Rust path.
"""
from __future__ import annotations

import time

import pytest

rivex_core = pytest.importorskip("rivex_core")

RC_V2 = getattr(rivex_core, "RC_V2", True) if hasattr(rivex_core, "TokenBucket") else False
pytestmark = pytest.mark.skipif(
    not hasattr(rivex_core, "TokenBucket"),
    reason="Rust TokenBucket not available in installed rivex_core",
)


# ---------------------------------------------------------------------------
# TokenBucket.check_many / remaining_many
# ---------------------------------------------------------------------------


def test_token_bucket_check_many_empty():
    tb = rivex_core.TokenBucket(5, 60.0)
    assert tb.check_many([]) == []


def test_token_bucket_check_many_orders_preserved():
    tb = rivex_core.TokenBucket(3, 60.0)
    keys = ["a", "b", "c"]
    out = tb.check_many(keys)
    assert out == [True, True, True]


def test_token_bucket_check_many_consumes_one_per_key():
    tb = rivex_core.TokenBucket(2, 60.0)
    out1 = tb.check_many(["a", "a", "a"])
    assert out1 == [True, True, False]


def test_token_bucket_check_many_mixed_keys_isolated():
    tb = rivex_core.TokenBucket(2, 60.0)
    assert tb.check_many(["x", "x", "y", "y"]) == [True, True, True, True]
    assert tb.check_many(["x", "x", "y", "y", "z"]) == [False, False, False, False, True]


def test_token_bucket_remaining_many_empty():
    tb = rivex_core.TokenBucket(5, 60.0)
    assert tb.remaining_many([]) == []


def test_token_bucket_remaining_many_after_check_many():
    tb = rivex_core.TokenBucket(3, 60.0)
    tb.check_many(["a", "b", "c"])
    remain = tb.remaining_many(["a", "b", "c", "d"])
    assert remain[3] == pytest.approx(3.0, abs=1e-9)
    for r in remain[:3]:
        assert r == pytest.approx(2.0, abs=1e-3)


def test_token_bucket_remaining_many_does_not_mutate():
    # ``remaining_many`` should never consume a token. If it did, a second
    # ``check`` after ``remaining_many`` would observe fewer tokens than
    # expected. Use a wide window so refill doesn't mask the difference.
    tb = rivex_core.TokenBucket(10, 3600.0)
    tb.check_many(["a"])
    initial = tb.remaining("a")
    tb.remaining_many(["a", "b", "c", "d"])
    tb.remaining_many(["a", "b", "c", "d"])
    assert tb.remaining("a") == pytest.approx(initial, abs=1e-6)
    # And ``len`` should be unchanged across the batch reads.
    assert tb.len() == 1


# ---------------------------------------------------------------------------
# SlidingWindow.allow_many / get_remaining_many
# ---------------------------------------------------------------------------


def test_sliding_window_allow_many_empty():
    sw = rivex_core.SlidingWindow(5, 60.0)
    assert sw.allow_many([]) == []


def test_sliding_window_allow_many_orders_preserved():
    sw = rivex_core.SlidingWindow(10, 60.0)
    out = sw.allow_many(["u1", "u2", "u3"])
    assert out == [True, True, True]


def test_sliding_window_allow_many_per_key_independent():
    sw = rivex_core.SlidingWindow(2, 60.0)
    assert sw.allow_many(["u1", "u2"]) == [True, True]
    assert sw.allow_many(["u1", "u2", "u3"]) == [True, True, True]
    assert sw.allow_many(["u1", "u2", "u3"]) == [False, False, True]


def test_sliding_window_get_remaining_many_empty():
    sw = rivex_core.SlidingWindow(5, 60.0)
    assert sw.get_remaining_many([]) == []


def test_sliding_window_get_remaining_many_full_bucket():
    sw = rivex_core.SlidingWindow(3, 60.0)
    sw.allow_many(["a", "b", "c"])
    assert sw.get_remaining_many(["a", "b", "c", "d"]) == [2, 2, 2, 3]


def test_sliding_window_get_remaining_many_does_not_mutate():
    sw = rivex_core.SlidingWindow(5, 60.0)
    sw.allow_many(["a", "b"])
    before = sw.get_remaining_many(["a", "b"])
    after = sw.get_remaining_many(["a", "b"])
    assert before == after


def test_sliding_window_allow_many_window_expiry():
    sw = rivex_core.SlidingWindow(2, window=0.05)
    assert sw.allow_many(["a", "a", "a"]) == [True, True, False]
    time.sleep(0.07)
    assert sw.allow_many(["a", "a", "a"]) == [True, True, False]


# ---------------------------------------------------------------------------
# Per-call equivalence: batch vs N individual calls
# ---------------------------------------------------------------------------


def test_token_batch_matches_individual_when_spread_over_time():
    tb = rivex_core.TokenBucket(5, 60.0)
    keys = [f"k{i}" for i in range(5)]

    individual = [tb.check(k) for k in keys]
    tb2 = rivex_core.TokenBucket(5, 60.0)
    batched = tb2.check_many(keys)
    assert individual == batched


def test_sliding_window_batch_matches_individual():
    sw = rivex_core.SlidingWindow(3, 60.0)
    keys = ["x", "y", "z"]
    individual = [sw.allow(k) for k in keys]
    sw2 = rivex_core.SlidingWindow(3, 60.0)
    batched = sw2.allow_many(keys)
    assert individual == batched


# ---------------------------------------------------------------------------
# Python-side batch helpers (RateLimitMiddleware / BaseThrottle)
# ---------------------------------------------------------------------------


def test_rate_limit_middleware_check_batch_rust_path():
    from rivex.middleware import RateLimitMiddleware

    m = RateLimitMiddleware(rate=3, per=60.0)
    if not m._is_rust:
        pytest.skip("Rust TokenBucket not available")

    ip = "10.0.0.1"
    reqs = [{"headers": [("x-forwarded-for", ip)]} for _ in range(4)]
    assert m.check_batch(reqs) == [True, True, True, False]


def test_rate_limit_middleware_check_batch_empty():
    from rivex.middleware import RateLimitMiddleware

    m = RateLimitMiddleware(rate=10, per=60.0)
    assert m.check_batch([]) == []


def test_base_throttle_check_many_rust_path():
    from rivex.middleware.throttling import AnonRateThrottle

    t = AnonRateThrottle()
    t.rate = "2/minute"
    if not t._is_rust:
        pytest.skip("Rust SlidingWindow not available")

    reqs = [
        {"headers": [("x-forwarded-for", "10.0.0.1")]},
        {"headers": [("x-forwarded-for", "10.0.0.1")]},
        {"headers": [("x-forwarded-for", "10.0.0.1")]},
        {"headers": [("x-forwarded-for", "10.0.0.2")]},
    ]
    out = t.check_many(reqs)
    assert out == [True, True, False, True]


def test_base_throttle_check_many_no_rate_returns_all_true():
    from rivex.middleware.throttling import BaseThrottle

    t = BaseThrottle()
    t.rate = None
    out = t.check_many([{"headers": []}, {"headers": []}])
    assert out == [True, True]


def test_base_throttle_check_many_matches_individual_calls():
    from rivex.middleware.throttling import AnonRateThrottle

    t = AnonRateThrottle()
    t.rate = "5/minute"

    reqs = [
        {"headers": [("x-forwarded-for", f"10.0.0.{i}")]} for i in range(5)
    ]
    batched = t.check_many(reqs)

    t2 = AnonRateThrottle()
    t2.rate = "5/minute"
    individual = [t2.allow_request(r) for r in reqs]

    assert batched == individual