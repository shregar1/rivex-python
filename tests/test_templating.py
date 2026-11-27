from __future__ import annotations

from rivex import Rivex
from rivex.http.requests import Request
from rivex.http.responses import HTMLResponse


def test_jinja2_templates_render():
    from rivex.web.templating import Jinja2Templates

    templates = Jinja2Templates("tests/templates")
    resp = templates.render("page.html", title="Hello World")
    assert isinstance(resp, HTMLResponse)
    assert resp.status_code == 200
    assert "Hello World" in resp._render_body().decode()


def test_app_template_method():
    app = Rivex(template_dir="tests/templates")

    @app.get("/page")
    async def handler():
        return app.template("page.html", {"title": "From App"})

    from rivex.testing.testing import TestClient

    client = TestClient(app)
    resp = client.get("/page")
    assert resp.status_code == 200
    assert "From App" in resp.text
    assert "text/html" in resp.headers.get("content-type", "")


def test_app_template_custom_status():
    app = Rivex(template_dir="tests/templates")
    result = app.template("page.html", {"title": "Test"}, status_code=201)
    assert result["status"] == 201
    body = result["body"]
    if isinstance(body, bytes):
        body = body.decode()
    assert "Test" in body


def test_app_template_custom_headers():
    app = Rivex(template_dir="tests/templates")
    result = app.template("page.html", {"title": "Test"}, headers={"x-custom": "val"})
    headers = dict(result["headers"])
    assert headers.get("x-custom") == "val"


def test_app_template_default_template_dir(tmp_path):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "hello.html").write_text("<p>{{ msg }}</p>")
    import os
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        app = Rivex()
        result = app.template("hello.html", {"msg": "Hi"})
        body = result["body"]
        if isinstance(body, bytes):
            body = body.decode()
        assert "Hi" in body
    finally:
        os.chdir(old)


def test_app_template_on_route_with_htmx():
    app = Rivex(template_dir="tests/templates")

    @app.get("/mixed")
    async def mixed_handler(request: Request):
        if request.htmx:
            return app.template("page.html", {"title": "Partial"})
        return app.template("page.html", {"title": "Full"})

    from rivex.testing.testing import TestClient

    client = TestClient(app)
    resp = client.get("/mixed")
    assert "Full" in resp.text

    resp = client.get("/mixed", headers={"HX-Request": "true"})
    assert "Partial" in resp.text
