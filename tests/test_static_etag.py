"""Tests for ETag / If-Match / If-None-Match support in StaticFiles."""

from __future__ import annotations

from pathlib import Path

from rivex import Rivex
from rivex.staticfiles import StaticFiles, _file_etag
from rivex.testing import TestClient


def test_etag_included_in_response(tmp_path: Path):
    content = b"hello"
    f = tmp_path / "test.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/test.txt")
    assert resp.status_code == 200
    assert resp.headers.get("etag") is not None
    assert resp.headers["etag"].startswith('W/"')


def test_if_none_match_returns_304(tmp_path: Path):
    content = b"cached content"
    f = tmp_path / "cached.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp1 = client.get("/static/cached.txt")
    etag = resp1.headers["etag"]

    resp2 = client.get("/static/cached.txt", headers={"If-None-Match": etag})
    assert resp2.status_code == 304
    assert resp2.text == ""


def test_if_none_match_wildcard_returns_304(tmp_path: Path):
    content = b"wildcard"
    f = tmp_path / "wild.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/wild.txt", headers={"If-None-Match": "*"})
    assert resp.status_code == 304


def test_if_match_mismatch_returns_412(tmp_path: Path):
    content = b"important"
    f = tmp_path / "important.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/important.txt", headers={"If-Match": '"wrong-etag"'})
    assert resp.status_code == 412


def test_if_match_wildcard_passes(tmp_path: Path):
    content = b"match all"
    f = tmp_path / "matchall.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/matchall.txt", headers={"If-Match": "*"})
    assert resp.status_code == 200


def test_file_etag_generation(tmp_path: Path):
    content = b"etag test"
    f = tmp_path / "etag.txt"
    f.write_bytes(content)

    etag = _file_etag(str(f))
    assert etag.startswith('W/"')
    assert etag.endswith('"')
    # Same call should produce identical ETag
    assert _file_etag(str(f)) == etag
