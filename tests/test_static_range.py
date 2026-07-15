"""Tests for Range request support in StaticFiles."""

from __future__ import annotations

import tempfile
from pathlib import Path

from rivex import Rivex
from rivex.web.staticfiles import StaticFiles, _parse_range
from rivex.testing.testing import TestClient


def test_parse_range_full():
    assert _parse_range("bytes=0-9", 100) == (0, 9)


def test_parse_range_open_end():
    assert _parse_range("bytes=90-", 100) == (90, 99)


def test_parse_range_suffix():
    assert _parse_range("bytes=-10", 100) == (90, 99)


def test_parse_range_invalid():
    assert _parse_range("bytes=abc", 100) is None


def test_parse_range_out_of_bounds():
    assert _parse_range("bytes=0-200", 100) is None


def test_parse_range_reversed():
    assert _parse_range("bytes=50-0", 100) is None


def test_static_file_single_range(tmp_path: Path):
    content = b"hello world this is a test file"
    f = tmp_path / "test.txt"
    f.write_bytes(content)
    file_len = len(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/test.txt", headers={"Range": "bytes=0-4"})
    assert resp.status_code == 206
    assert resp.text == "hello"
    assert resp.headers.get("content-range") == f"bytes 0-4/{file_len}"
    assert resp.headers.get("accept-ranges") == "bytes"


def test_static_file_middle_range(tmp_path: Path):
    content = b"abcdefghijklmnopqrstuvwxyz"
    f = tmp_path / "letters.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/letters.txt", headers={"Range": "bytes=5-10"})
    assert resp.status_code == 206
    assert resp.text == "fghijk"


def test_static_file_open_end_range(tmp_path: Path):
    content = b"0123456789"
    f = tmp_path / "digits.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/digits.txt", headers={"Range": "bytes=5-"})
    assert resp.status_code == 206
    assert resp.text == "56789"


def test_static_file_suffix_range(tmp_path: Path):
    content = b"hello world"
    f = tmp_path / "suffix.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/suffix.txt", headers={"Range": "bytes=-5"})
    assert resp.status_code == 206
    assert resp.text == "world"


def test_static_file_unsatisfiable_range(tmp_path: Path):
    content = b"small"
    f = tmp_path / "small.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/small.txt", headers={"Range": "bytes=100-200"})
    assert resp.status_code == 416


def test_static_file_no_range_returns_full(tmp_path: Path):
    content = b"full content here"
    f = tmp_path / "full.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/full.txt")
    assert resp.status_code == 200
    assert resp.text == "full content here"
    assert resp.headers.get("accept-ranges") == "bytes"


def test_static_file_accept_ranges_header(tmp_path: Path):
    content = b"data"
    f = tmp_path / "accept.txt"
    f.write_bytes(content)

    app = Rivex()
    app.mount("/static", StaticFiles(directory=str(tmp_path)))

    client = TestClient(app)
    resp = client.get("/static/accept.txt")
    assert resp.headers.get("accept-ranges") == "bytes"
