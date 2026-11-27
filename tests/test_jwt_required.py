"""Tests for the ``@jwt_required`` decorator's verification path.

Two layers:

1. **Direct unit tests** of the decorator's ``_verify`` callable (extracted
   via ``func._rivex_jwt_config["verify"]``). These pin the verification
   semantics in isolation — good token / wrong secret / expired / within
   the Rust 60s leeway / missing-``exp`` / HS384 / HS512 / extra claims.

2. **End-to-end subprocess test** that boots ``rivex run`` against a real
   JWT-protected app and curls it. ``TestClient`` cannot exercise this
   path because the in-process ``RivexSyncApp`` does not honour
   ``_rivex_jwt_config`` (only the async Rust server and the ASGI
   adapter do), so we drive the real server with httpx. This catches
   the wiring from decorator → ``_build_jwt_wrapper`` → ``RivexServer``
   → 200/401 response.

The "no-leeway parity" guarantee — that ``@jwt_required`` rejects
expired tokens even when they fall inside the Rust core's 60-second
``jsonwebtoken`` clock-skew leeway — was introduced to match the
original pure-Python fallback's strict behaviour. The dedicated
``test_verify_within_rust_leeway_rejected`` test pins that contract.
"""

from __future__ import annotations

import sys
import time

import pytest

from rivex import Rivex
from rivex.auth import jwt as J
from rivex.auth.auth import jwt_required

# ---------------------------------------------------------------------------
# 1. Direct unit tests of _verify (the function the decorator exposes via
#    func._rivex_jwt_config["verify"]). Avoids the TestClient limitation
#    that sync_server has no JWT awareness.
# ---------------------------------------------------------------------------


def _make_verify(*, secret="s3cret", algorithm="HS256"):
    """Build a route carrying ``@jwt_required`` and hand back its ``_verify``."""

    app = Rivex(title="jwt")

    @app.get("/_dummy")  # pragma: no cover - never invoked
    @jwt_required(secret=secret, algorithm=algorithm)
    async def dummy():
        pass

    return dummy._rivex_jwt_config["verify"]


def test_verify_accepts_good_hs256_token():
    verify = _make_verify(secret="s3cret")
    token = J.encode({"sub": "alice", "role": "user"}, "s3cret", expires_in=60)
    claims = verify(token)
    assert claims is not None
    assert claims["sub"] == "alice"
    assert claims["role"] == "user"


def test_verify_rejects_wrong_secret():
    verify = _make_verify(secret="s3cret")
    token = J.encode({"sub": "a"}, "WRONG", expires_in=60)
    assert verify(token) is None


def test_verify_rejects_expired_token():
    verify = _make_verify()
    token = J.encode({"sub": "a"}, "s3cret", expires_in=-3600)
    assert verify(token) is None


def test_verify_rejects_within_rust_leeway():
    """Strict no-leeway parity: the in-Python check rejects tokens that
    the Rust core's 60s leeway would otherwise let through. This was the
    point of the parity addition — both verify paths must reach the
    same answer regardless of whether ``rivex_core`` is loaded.
    """
    verify = _make_verify()
    token = J.encode({"sub": "a"}, "s3cret", expires_in=-5)  # 5s past
    assert verify(token) is None


def test_verify_accepts_token_without_exp_claim():
    verify = _make_verify()
    token = J.encode({"sub": "no-exp"}, "s3cret")
    claims = verify(token)
    assert claims is not None and claims["sub"] == "no-exp"


def test_verify_handles_malformed_token():
    verify = _make_verify()
    assert verify("not.a.real.jwt") is None
    assert verify("garbage") is None
    assert verify("a.b") is None


def test_verify_accepts_hs384():
    """HS384 / HS512 tokens are minted by hand (J.encode is HS256-only
    upstream), but the verify side is supposed to support all three.
    """
    verify = _make_verify(secret="s3cret", algorithm="HS384")

    import base64
    import hashlib
    import hmac
    import json

    def mint_384(payload):
        def b(d):
            return base64.urlsafe_b64encode(d).rstrip(b"=").decode()
        h = b(json.dumps({"alg": "HS384", "typ": "JWT"}, separators=(",", ":")).encode())
        p = b(json.dumps(payload, separators=(",", ":")).encode())
        sig = hmac.new(b"s3cret", f"{h}.{p}".encode(), hashlib.sha384).digest()
        return f"{h}.{p}.{b(sig)}"

    claims = verify(mint_384({"sub": "u384", "exp": int(time.time()) + 60}))
    assert claims is not None and claims["sub"] == "u384"


def test_verify_accepts_hs512():
    verify = _make_verify(secret="s3cret", algorithm="HS512")

    import base64
    import hashlib
    import hmac
    import json

    def mint_512(payload):
        def b(d):
            return base64.urlsafe_b64encode(d).rstrip(b"=").decode()
        h = b(json.dumps({"alg": "HS512", "typ": "JWT"}, separators=(",", ":")).encode())
        p = b(json.dumps(payload, separators=(",", ":")).encode())
        sig = hmac.new(b"s3cret", f"{h}.{p}".encode(), hashlib.sha512).digest()
        return f"{h}.{p}.{b(sig)}"

    claims = verify(mint_512({"sub": "u512", "exp": int(time.time()) + 60}))
    assert claims is not None and claims["sub"] == "u512"


def test_verify_preserves_extra_claims():
    verify = _make_verify()
    token = J.encode(
        {"sub": "u1", "role": "admin", "tenant": "acme", "exp": int(time.time()) + 60},
        "s3cret",
    )
    claims = verify(token)
    assert claims["role"] == "admin"
    assert claims["tenant"] == "acme"


# ---------------------------------------------------------------------------
# 2. End-to-end: drive the real Rust server through `rivex run` and
#    observe the 200/401 contract on a JWT-protected route. We bypass
#    TestClient (which goes through RivexSyncApp, a path that does not
#    honour _rivex_jwt_config) and drive the async Rust engine instead.
# ---------------------------------------------------------------------------


def _free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def jwt_app(tmp_path):
    """Write an app with a JWT-protected route into tmp_path."""
    (tmp_path / "jwtapp.py").write_text(
        "from rivex import Rivex\n"
        "from rivex.auth.auth import jwt_required, get_jwt_claims\n"
        "\n"
        "app = Rivex(title='jwt-e2e')\n"
        "\n"
        "@app.get('/me')\n"
        "@jwt_required(secret='s3cret')\n"
        "async def me():\n"
        "    claims = get_jwt_claims()\n"
        "    return {'sub': claims.get('sub')}\n"
    )
    return tmp_path


def test_jwt_required_e2e_run(jwt_app, tmp_path):
    """`rivex run jwtapp:app` enforces JWT via the Rust path."""
    import socket
    import subprocess
    import time

    import httpx

    import os
    from pathlib import Path
    env = dict(os.environ)
    src_dir = str(Path(__file__).parent.parent / "src")
    env["PYTHONPATH"] = f"{src_dir}:{env.get('PYTHONPATH', '')}" if "PYTHONPATH" in env else src_dir

    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "rivex.cli.cli", "run", "jwtapp:app",
            "--host", "127.0.0.1", "--port", str(port),
        ],
        cwd=jwt_app,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Wait for the server to bind.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5) as _:
                    break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail(f"server on {port} did not bind")

        with httpx.Client(timeout=2.0) as client:
            token = J.encode({"sub": "e2e-user"}, "s3cret", expires_in=60)
            good = client.get(
                f"http://127.0.0.1:{port}/me",
                headers={"authorization": f"Bearer {token}"},
            )
            bad = client.get(f"http://127.0.0.1:{port}/me")
            wrong = client.get(
                f"http://127.0.0.1:{port}/me",
                headers={"authorization": "Bearer not.a.real.jwt"},
            )

        assert good.status_code == 200
        assert good.json() == {"sub": "e2e-user"}
        assert bad.status_code == 401
        assert wrong.status_code == 401
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
