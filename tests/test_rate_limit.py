from __future__ import annotations

from rivex import Rivex
from rivex.middleware.middleware import RateLimitMiddleware


def test_rate_limit_ip_default_strategy():
    m = RateLimitMiddleware(rate=10, per=1.0)
    assert m.rate == 10
    assert m.per == 1.0
    assert m.strategy == "ip"


def test_rate_limit_user_strategy():
    m = RateLimitMiddleware(rate=100, per=60, strategy="user")
    key = m._key({"headers": [("authorization", "Bearer tok123")]})
    assert key == "Bearer tok123"


def test_rate_limit_user_anonymous():
    m = RateLimitMiddleware(rate=100, per=60, strategy="user")
    key = m._key({"headers": []})
    assert key == "anonymous"


def test_rate_limit_global_strategy():
    m = RateLimitMiddleware(rate=1000, per=60, strategy="global")
    key = m._key({"headers": []})
    assert key == "_global"


def test_rate_limit_custom_key_header():
    m = RateLimitMiddleware(rate=50, per=10, key_header="x-api-key")
    key = m._key({"headers": [("x-api-key", "mykey123")]})
    assert key == "mykey123"


def test_rate_limit_key_header_fallback_to_ip():
    m = RateLimitMiddleware(rate=50, per=10, key_header="x-api-key")
    key = m._key({"headers": []})
    assert key is not None  # falls back to client_ip which returns something


def test_rate_limit_ip_key():
    m = RateLimitMiddleware(rate=10, per=1.0)
    from rivex.core._compat import client_ip
    key = m._key({"headers": [("x-forwarded-for", "1.2.3.4")]})
    assert key == "1.2.3.4"


def test_rate_limit_token_bucket_allows_up_to_rate(tmp_path):
    import json
    app = Rivex()
    app.add_middleware(RateLimitMiddleware, rate=5, per=10.0)

    @app.get("/test")
    async def handler():
        return {"status": 200, "headers": [], "body": b"ok"}

    from rivex.testing.testing import TestClient
    client = TestClient(app)

    for i in range(5):
        resp = client.get("/test", headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp.status_code == 200, f"request {i} should be allowed"

    # 6th request within bucket should be rate limited
    resp = client.get("/test", headers={"X-Forwarded-For": "10.0.0.1"})
    assert resp.status_code == 429


def test_rate_limit_different_ips_independent():
    app = Rivex()
    app.add_middleware(RateLimitMiddleware, rate=2, per=60.0)

    @app.get("/test")
    async def handler():
        return {"status": 200, "headers": [], "body": b"ok"}

    from rivex.testing.testing import TestClient
    client = TestClient(app)

    resp1 = client.get("/test", headers={"X-Forwarded-For": "10.0.0.1"})
    assert resp1.status_code == 200
    resp1 = client.get("/test", headers={"X-Forwarded-For": "10.0.0.1"})
    assert resp1.status_code == 200
    resp1 = client.get("/test", headers={"X-Forwarded-For": "10.0.0.1"})
    assert resp1.status_code == 429

    resp2 = client.get("/test", headers={"X-Forwarded-For": "10.0.0.2"})
    assert resp2.status_code == 200
