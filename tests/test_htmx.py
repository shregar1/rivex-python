from __future__ import annotations

from rivex import Rivex
from rivex.web.htmx import (
    HtmxDetails,
    HtmxResponse,
    HXLocation,
    HXPushUrl,
    HXRedirect,
    HXRefresh,
    HXReselect,
    HXRetarget,
    HXSwap,
)
from rivex.http.requests import Request


def test_htmx_details_detects_htmx_request():
    req = Request("GET", "/", [("hx-request", "true")], b"")
    assert req.htmx is not None
    assert req.htmx.request is True


def test_htmx_details_returns_none_for_normal_request():
    req = Request("GET", "/", [], b"")
    assert req.htmx is None


def test_htmx_details_all_headers():
    req = Request(
        "GET",
        "/",
        [
            ("hx-request", "true"),
            ("hx-boosted", "true"),
            ("hx-current-url", "https://example.com/page"),
            ("hx-history-restore-request", "true"),
            ("hx-prompt", "Are you sure?"),
            ("hx-target", "#content"),
            ("hx-trigger", "btn1"),
            ("hx-trigger-name", "submit-btn"),
        ],
        b"",
    )
    assert req.htmx.boosted is True
    assert req.htmx.current_url == "https://example.com/page"
    assert req.htmx.history_restore_request is True
    assert req.htmx.prompt == "Are you sure?"
    assert req.htmx.target == "#content"
    assert req.htmx.trigger == "btn1"
    assert req.htmx.trigger_name == "submit-btn"


def test_htmx_details_missing_headers():
    req = Request("GET", "/", [("hx-request", "true")], b"")
    assert req.htmx.boosted is None
    assert req.htmx.current_url is None
    assert req.htmx.target is None


def test_htmx_details_cached():
    req = Request("GET", "/", [("hx-request", "true")], b"")
    h1 = req.htmx
    h2 = req.htmx
    assert h1 is h2


def test_htmx_response_basic():
    resp = HtmxResponse("<div>Hello</div>")
    assert resp.status_code == 200
    assert resp.media_type == "text/html; charset=utf-8"


def test_htmx_response_trigger_header():
    resp = HtmxResponse("<div>Hello</div>", trigger="itemUpdated")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-trigger") == "itemUpdated"


def test_htmx_response_redirect():
    resp = HtmxResponse("<div>Hello</div>", redirect="/thanks")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-redirect") == "/thanks"


def test_htmx_response_push_url():
    resp = HtmxResponse("<div>Hello</div>", push_url="/new-url")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-push-url") == "/new-url"


def test_htmx_response_refresh():
    resp = HtmxResponse("", refresh=True)
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-refresh") == "true"


def test_htmx_response_reswap():
    resp = HtmxResponse("", reswap="outerHTML")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-reswap") == "outerHTML"


def test_htmx_response_retarget():
    resp = HtmxResponse("", retarget="#new-target")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-retarget") == "#new-target"


def test_htmx_response_reselect():
    resp = HtmxResponse("", reselect="#partial")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-reselect") == "#partial"


def test_htmx_response_after_settle():
    resp = HtmxResponse("", after_settle="itemSettled")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-trigger-after-settle") == "itemSettled"


def test_htmx_response_after_swap():
    resp = HtmxResponse("", after_swap="itemSwapped")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-trigger-after-swap") == "itemSwapped"


def test_htmx_response_multiple_headers():
    resp = HtmxResponse(
        "<div>Hello</div>",
        trigger="itemUpdated",
        push_url="/new",
        retarget="#content",
        reswap="innerHTML",
    )
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-trigger") == "itemUpdated"
    assert headers.get("hx-push-url") == "/new"
    assert headers.get("hx-retarget") == "#content"
    assert headers.get("hx-reswap") == "innerHTML"


def test_hx_redirect():
    resp = HXRedirect("/login", content="<div>Redirecting</div>")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-redirect") == "/login"
    assert resp.media_type == "text/html; charset=utf-8"


def test_hx_refresh():
    resp = HXRefresh()
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-refresh") == "true"


def test_hx_location():
    resp = HXLocation("/new-page")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-redirect") == "/new-page"


def test_hx_swap():
    resp = HXSwap("outerHTML settle:2s")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-reswap") == "outerHTML settle:2s"


def test_hx_retarget():
    resp = HXRetarget("#main")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-retarget") == "#main"


def test_hx_reselect():
    resp = HXReselect("#partial")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-reselect") == "#partial"


def test_hx_push_url():
    resp = HXPushUrl("/history-url")
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-push-url") == "/history-url"


def test_htmx_response_push_url_true():
    resp = HtmxResponse("", push_url=True)
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-push-url") == "true"


def test_htmx_response_push_url_false():
    resp = HtmxResponse("", push_url=False)
    raw = resp._to_raw()
    headers = dict(raw["headers"])
    assert headers.get("hx-push-url") == "false"


def test_htmx_details_on_route():
    app = Rivex()

    @app.get("/htmx-test")
    async def hx_handler(request: Request):
        if request.htmx and request.htmx.target == "#content":
            return {"status": 200, "headers": [("content-type", "text/plain")], "body": b"partial"}
        return {"status": 200, "headers": [("content-type", "text/plain")], "body": b"full"}

    from rivex.testing.testing import TestClient
    client = TestClient(app)

    resp = client.get("/htmx-test")
    assert resp.text == "full"

    resp = client.get("/htmx-test", headers={"HX-Request": "true", "HX-Target": "#content"})
    assert resp.text == "partial"
