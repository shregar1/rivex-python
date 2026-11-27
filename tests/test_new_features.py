"""Tests for all newly added features: params, FileResponse, cookies, dependency
overrides, yield deps, security schemes, middleware, validation errors, etc."""

import os
import tempfile

from rivex import (
    Body,
    Cookie,
    Depends,
    FileResponse,
    Header,
    HTTPSRedirectMiddleware,
    Path,
    Query,
    Request,
    Response,
    Rivex,
    TestClient,
)
from rivex.exceptions.http.exceptions import RequestValidationError, WebSocketDisconnect
from rivex.auth.security import (
    APIKeyCookie,
    APIKeyQuery,
    HTTPBasic,
    HTTPBasicCredentials,
    OAuth2AuthorizationCodeBearer,
    OAuth2PasswordRequestForm,
    SecurityScopes,
)

# ── Query() with validation ──


class TestQueryParam:
    def test_query_basic(self):
        app = Rivex()

        @app.get("/items")
        async def list_items(skip: int = Query(0), limit: int = Query(10, le=100)):
            return {"skip": skip, "limit": limit}

        client = TestClient(app)
        resp = client.get("/items", params={"skip": "5", "limit": "20"})
        assert resp.status_code == 200
        assert resp.json() == {"skip": 5, "limit": 20}

    def test_query_default(self):
        app = Rivex()

        @app.get("/items")
        async def list_items(skip: int = Query(0)):
            return {"skip": skip}

        resp = TestClient(app).get("/items")
        assert resp.status_code == 200
        assert resp.json() == {"skip": 0}

    def test_query_required_missing(self):
        app = Rivex()

        @app.get("/search")
        async def search(q: str = Query(...)):
            return {"q": q}

        resp = TestClient(app).get("/search")
        assert resp.status_code == 422

    def test_query_validation_le(self):
        app = Rivex()

        @app.get("/items")
        async def list_items(limit: int = Query(10, le=100)):
            return {"limit": limit}

        resp = TestClient(app).get("/items", params={"limit": "200"})
        assert resp.status_code == 422

    def test_query_alias(self):
        app = Rivex()

        @app.get("/items")
        async def list_items(item_query: str = Query("default", alias="q")):
            return {"q": item_query}

        resp = TestClient(app).get("/items", params={"q": "test"})
        assert resp.status_code == 200
        assert resp.json() == {"q": "test"}


# ── Path() with validation ──


class TestPathParam:
    def test_path_basic(self):
        app = Rivex()

        @app.get("/items/{item_id}")
        async def get_item(item_id: int = Path(..., ge=1)):
            return {"item_id": item_id}

        resp = TestClient(app).get("/items/42")
        assert resp.status_code == 200
        assert resp.json() == {"item_id": 42}

    def test_path_validation_ge(self):
        app = Rivex()

        @app.get("/items/{item_id}")
        async def get_item(item_id: int = Path(..., ge=1)):
            return {"item_id": item_id}

        resp = TestClient(app).get("/items/0")
        assert resp.status_code == 422


# ── Header() extraction ──


class TestHeaderParam:
    def test_header_extraction(self):
        app = Rivex()

        @app.get("/check")
        async def check(x_token: str = Header(...)):
            return {"token": x_token}

        resp = TestClient(app).get("/check", headers={"x-token": "abc123"})
        assert resp.status_code == 200
        assert resp.json() == {"token": "abc123"}

    def test_header_default(self):
        app = Rivex()

        @app.get("/check")
        async def check(x_token: str = Header("default")):
            return {"token": x_token}

        resp = TestClient(app).get("/check")
        assert resp.status_code == 200
        assert resp.json() == {"token": "default"}

    def test_header_required_missing(self):
        app = Rivex()

        @app.get("/check")
        async def check(x_token: str = Header(...)):
            return {"token": x_token}

        resp = TestClient(app).get("/check")
        assert resp.status_code == 422


# ── Cookie() extraction ──


class TestCookieParam:
    def test_cookie_extraction(self):
        app = Rivex()

        @app.get("/me")
        async def me(session_id: str = Cookie(...)):
            return {"session_id": session_id}

        resp = TestClient(app).get("/me", headers={"cookie": "session_id=abc123"})
        assert resp.status_code == 200
        assert resp.json() == {"session_id": "abc123"}

    def test_cookie_default(self):
        app = Rivex()

        @app.get("/me")
        async def me(session_id: str = Cookie("guest")):
            return {"session_id": session_id}

        resp = TestClient(app).get("/me")
        assert resp.status_code == 200
        assert resp.json() == {"session_id": "guest"}

    def test_cookie_missing_required(self):
        app = Rivex()

        @app.get("/me")
        async def me(session_id: str = Cookie(...)):
            return {"session_id": session_id}

        resp = TestClient(app).get("/me")
        assert resp.status_code == 422


# ── Body() annotation ──


class TestBodyParam:
    def test_body_embed(self):
        app = Rivex()

        @app.post("/items")
        async def create(name: str = Body(..., embed=True)):
            return {"name": name}

        resp = TestClient(app).post("/items", json={"name": "Widget"})
        assert resp.status_code == 200
        assert resp.json() == {"name": "Widget"}


# ── FileResponse ──


class TestFileResponse:
    def test_file_response(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("Hello, World!")
            path = f.name

        try:
            app = Rivex()

            @app.get("/download")
            async def download():
                return FileResponse(path, filename="hello.txt")

            resp = TestClient(app).get("/download")
            assert resp.status_code == 200
            assert resp.text == "Hello, World!"
            assert "attachment" in resp.headers.get("content-disposition", "")
        finally:
            os.unlink(path)


# ── Response cookies ──


class TestResponseCookies:
    def test_set_cookie(self):
        app = Rivex()

        @app.get("/login")
        async def login():
            resp = Response(content="ok", status_code=200, media_type="text/plain")
            resp.set_cookie("session", "abc123", httponly=True, secure=True)
            return resp

        result = TestClient(app).get("/login")
        assert result.status_code == 200
        assert "set-cookie" in result.headers

    def test_delete_cookie(self):
        app = Rivex()

        @app.get("/logout")
        async def logout():
            resp = Response(content="bye", status_code=200, media_type="text/plain")
            resp.delete_cookie("session")
            return resp

        result = TestClient(app).get("/logout")
        assert result.status_code == 200
        cookie = result.headers.get("set-cookie", "")
        assert "Max-Age=0" in cookie


# ── Dependency overrides ──


class TestDependencyOverrides:
    def test_override(self):
        app = Rivex()

        def get_db():
            return "real_db"

        @app.get("/db")
        async def use_db(db: str = Depends(get_db)):
            return {"db": db}

        app.dependency_overrides[get_db] = lambda: "test_db"

        resp = TestClient(app).get("/db")
        assert resp.status_code == 200
        assert resp.json() == {"db": "test_db"}

        app.dependency_overrides.clear()

    def test_override_cleared(self):
        app = Rivex()

        def get_db():
            return "real_db"

        @app.get("/db")
        async def use_db(db: str = Depends(get_db)):
            return {"db": db}

        resp = TestClient(app).get("/db")
        assert resp.json() == {"db": "real_db"}


# ── Yield dependencies ──


class TestYieldDependencies:
    def test_sync_yield_dep(self):
        cleanup_ran = []

        def get_resource():
            resource = "my_resource"
            yield resource
            cleanup_ran.append(True)

        app = Rivex()

        @app.get("/resource")
        async def use_resource(r: str = Depends(get_resource)):
            return {"resource": r}

        resp = TestClient(app).get("/resource")
        assert resp.status_code == 200
        assert resp.json() == {"resource": "my_resource"}
        assert cleanup_ran == [True]

    def test_async_yield_dep(self):
        cleanup_ran = []

        async def get_resource():
            resource = "async_resource"
            yield resource
            cleanup_ran.append(True)

        app = Rivex()

        @app.get("/resource")
        async def use_resource(r: str = Depends(get_resource)):
            return {"resource": r}

        resp = TestClient(app).get("/resource")
        assert resp.status_code == 200
        assert resp.json() == {"resource": "async_resource"}
        assert cleanup_ran == [True]


# ── RequestValidationError ──


class TestRequestValidationError:
    def test_validation_error_format(self):
        app = Rivex()

        @app.get("/items/{item_id}")
        async def get_item(item_id: int = Path(..., ge=1)):
            return {"item_id": item_id}

        resp = TestClient(app).get("/items/0")
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body

    def test_custom_validation_error_handler(self):
        app = Rivex()

        @app.exception_handler(RequestValidationError)
        async def custom_handler(request, exc):
            from rivex import JSONResponse

            return JSONResponse(
                content={"errors": exc.errors_list, "custom": True},
                status_code=422,
            )

        @app.get("/items")
        async def list_items(q: str = Query(...)):
            return {"q": q}

        resp = TestClient(app).get("/items")
        assert resp.status_code == 422
        body = resp.json()
        assert body["custom"] is True


# ── HTTPSRedirectMiddleware ──


class TestHTTPSRedirectMiddleware:
    def test_redirects_http(self):
        app = Rivex()
        app.add_middleware(HTTPSRedirectMiddleware)

        @app.get("/secure")
        async def secure():
            return {"ok": True}

        resp = TestClient(app).get("/secure", headers={"host": "example.com"})
        assert resp.status_code == 307
        assert resp.headers["location"] == "https://example.com/secure"

    def test_passes_https(self):
        app = Rivex()
        app.add_middleware(HTTPSRedirectMiddleware)

        @app.get("/secure")
        async def secure():
            return {"ok": True}

        resp = TestClient(app).get(
            "/secure",
            headers={"host": "example.com", "x-forwarded-proto": "https"},
        )
        assert resp.status_code == 200


# ── Security Schemes ──


class TestAPIKeyQuery:
    def test_api_key_from_query(self):
        app = Rivex()
        api_key_query = APIKeyQuery(name="api_key")

        @app.get("/data")
        async def data(key: str = Depends(api_key_query)):
            return {"key": key}

        resp = TestClient(app).get("/data", params={"api_key": "secret"})
        assert resp.status_code == 200
        assert resp.json() == {"key": "secret"}

    def test_api_key_query_missing(self):
        app = Rivex()
        api_key_query = APIKeyQuery(name="api_key")

        @app.get("/data")
        async def data(key: str = Depends(api_key_query)):
            return {"key": key}

        resp = TestClient(app).get("/data")
        assert resp.status_code == 401


class TestAPIKeyCookie:
    def test_api_key_from_cookie(self):
        app = Rivex()
        api_key_cookie = APIKeyCookie(name="session")

        @app.get("/data")
        async def data(key: str = Depends(api_key_cookie)):
            return {"key": key}

        resp = TestClient(app).get("/data", headers={"cookie": "session=abc"})
        assert resp.status_code == 200
        assert resp.json() == {"key": "abc"}

    def test_api_key_cookie_missing(self):
        app = Rivex()
        api_key_cookie = APIKeyCookie(name="session")

        @app.get("/data")
        async def data(key: str = Depends(api_key_cookie)):
            return {"key": key}

        resp = TestClient(app).get("/data")
        assert resp.status_code == 401


class TestHTTPBasic:
    def test_valid_credentials(self):
        import base64

        app = Rivex()
        security = HTTPBasic()

        @app.get("/users/me")
        async def me(credentials: HTTPBasicCredentials = Depends(security)):
            return {"username": credentials.username}

        encoded = base64.b64encode(b"admin:password").decode()
        resp = TestClient(app).get("/users/me", headers={"authorization": f"Basic {encoded}"})
        assert resp.status_code == 200
        assert resp.json() == {"username": "admin"}

    def test_missing_auth(self):
        app = Rivex()
        security = HTTPBasic()

        @app.get("/users/me")
        async def me(credentials: HTTPBasicCredentials = Depends(security)):
            return {"username": credentials.username}

        resp = TestClient(app).get("/users/me")
        assert resp.status_code == 401


class TestOAuth2AuthorizationCodeBearer:
    def test_valid_token(self):
        app = Rivex()
        oauth2 = OAuth2AuthorizationCodeBearer(
            authorizationUrl="/authorize",
            tokenUrl="/token",
        )

        @app.get("/data")
        async def data(token: str = Depends(oauth2)):
            return {"token": token}

        resp = TestClient(app).get("/data", headers={"authorization": "Bearer mytoken"})
        assert resp.status_code == 200
        assert resp.json() == {"token": "mytoken"}

    def test_missing_token(self):
        app = Rivex()
        oauth2 = OAuth2AuthorizationCodeBearer(
            authorizationUrl="/authorize",
            tokenUrl="/token",
        )

        @app.get("/data")
        async def data(token: str = Depends(oauth2)):
            return {"token": token}

        resp = TestClient(app).get("/data")
        assert resp.status_code == 401


class TestSecurityScopes:
    def test_scopes(self):
        scopes = SecurityScopes(scopes=["read", "write"])
        assert scopes.scopes == ["read", "write"]
        assert scopes.scope_str == "read write"

    def test_empty_scopes(self):
        scopes = SecurityScopes()
        assert scopes.scopes == []
        assert scopes.scope_str == ""


class TestOAuth2PasswordRequestForm:
    def test_from_request(self):
        app = Rivex()

        @app.post("/token")
        async def login(request: Request):
            form = OAuth2PasswordRequestForm._from_request(request)
            return {"username": form.username, "grant_type": form.grant_type}

        resp = TestClient(app).post(
            "/token",
            data={"username": "admin", "password": "secret", "grant_type": "password"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"username": "admin", "grant_type": "password"}


# ── StaticFiles ──


class TestStaticFiles:
    def test_serves_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "style.css")
            with open(filepath, "w") as f:
                f.write("body { color: red; }")

            from rivex.web.staticfiles import StaticFiles

            static = StaticFiles(directory=tmpdir)

            import asyncio

            result = asyncio.run(static({"path": "/style.css", "headers": []}))
            assert result["status"] == 200
            assert b"body { color: red; }" in result["body"]

    def test_missing_file_404(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from rivex.web.staticfiles import StaticFiles

            static = StaticFiles(directory=tmpdir)

            import asyncio

            result = asyncio.run(static({"path": "/missing.txt", "headers": []}))
            assert result["status"] == 404

    def test_directory_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from rivex.web.staticfiles import StaticFiles

            static = StaticFiles(directory=tmpdir)

            import asyncio

            result = asyncio.run(static({"path": "/../../../etc/passwd", "headers": []}))
            assert result["status"] == 404


# ── WebSocket disconnect exception ──


class TestWebSocketDisconnect:
    def test_disconnect_exception(self):
        exc = WebSocketDisconnect(code=1001, reason="going away")
        assert exc.code == 1001
        assert exc.reason == "going away"


# ── OpenAPI schema for new params ──


class TestOpenAPINewParams:
    def test_query_param_in_openapi(self):
        from rivex.openapi.openapi import generate_openapi
        from rivex.web.routing import RouteRecord

        async def endpoint(q: str = Query(..., description="Search query", min_length=1)):
            pass

        routes = [
            RouteRecord(
                method="GET",
                path="/search",
                endpoint=endpoint,
                status_code=200,
                tags=[],
                include_in_schema=True,
            )
        ]
        spec = generate_openapi(title="Test", version="1.0", routes=routes)
        params = spec["paths"]["/search"]["get"]["parameters"]
        assert len(params) == 1
        p = params[0]
        assert p["name"] == "q"
        assert p["in"] == "query"
        assert p["required"] is True
        assert p["description"] == "Search query"
        assert p["schema"]["minLength"] == 1

    def test_header_param_in_openapi(self):
        from rivex.openapi.openapi import generate_openapi
        from rivex.web.routing import RouteRecord

        async def endpoint(x_token: str = Header(...)):
            pass

        routes = [
            RouteRecord(
                method="GET",
                path="/check",
                endpoint=endpoint,
                status_code=200,
                tags=[],
                include_in_schema=True,
            )
        ]
        spec = generate_openapi(title="Test", version="1.0", routes=routes)
        params = spec["paths"]["/check"]["get"]["parameters"]
        assert len(params) == 1
        assert params[0]["in"] == "header"
        assert params[0]["name"] == "x-token"

    def test_cookie_param_in_openapi(self):
        from rivex.openapi.openapi import generate_openapi
        from rivex.web.routing import RouteRecord

        async def endpoint(session: str = Cookie("guest")):
            pass

        routes = [
            RouteRecord(
                method="GET",
                path="/me",
                endpoint=endpoint,
                status_code=200,
                tags=[],
                include_in_schema=True,
            )
        ]
        spec = generate_openapi(title="Test", version="1.0", routes=routes)
        params = spec["paths"]["/me"]["get"]["parameters"]
        assert len(params) == 1
        assert params[0]["in"] == "cookie"
        assert params[0]["required"] is False

    def test_path_param_with_constraints_in_openapi(self):
        from rivex.openapi.openapi import generate_openapi
        from rivex.web.routing import RouteRecord

        async def endpoint(item_id: int = Path(..., ge=1, le=1000)):
            pass

        routes = [
            RouteRecord(
                method="GET",
                path="/items/{item_id}",
                endpoint=endpoint,
                status_code=200,
                tags=[],
                include_in_schema=True,
            )
        ]
        spec = generate_openapi(title="Test", version="1.0", routes=routes)
        params = spec["paths"]["/items/{item_id}"]["get"]["parameters"]
        assert len(params) == 1
        p = params[0]
        assert p["in"] == "path"
        assert p["schema"]["minimum"] == 1
        assert p["schema"]["maximum"] == 1000


# ── Param validation constraints ──


class TestParamValidation:
    def test_min_length(self):
        app = Rivex()

        @app.get("/items")
        async def search(q: str = Query(..., min_length=3)):
            return {"q": q}

        resp = TestClient(app).get("/items", params={"q": "ab"})
        assert resp.status_code == 422

        resp = TestClient(app).get("/items", params={"q": "abc"})
        assert resp.status_code == 200

    def test_max_length(self):
        app = Rivex()

        @app.get("/items")
        async def search(q: str = Query(..., max_length=5)):
            return {"q": q}

        resp = TestClient(app).get("/items", params={"q": "toolong"})
        assert resp.status_code == 422

    def test_pattern(self):
        app = Rivex()

        @app.get("/items")
        async def search(code: str = Query(..., pattern=r"^[A-Z]{3}$")):
            return {"code": code}

        resp = TestClient(app).get("/items", params={"code": "abc"})
        assert resp.status_code == 422

        resp = TestClient(app).get("/items", params={"code": "ABC"})
        assert resp.status_code == 200

    def test_gt(self):
        app = Rivex()

        @app.get("/items")
        async def search(price: float = Query(..., gt=0)):
            return {"price": price}

        resp = TestClient(app).get("/items", params={"price": "0"})
        assert resp.status_code == 422

        resp = TestClient(app).get("/items", params={"price": "1.5"})
        assert resp.status_code == 200

    def test_combined_ge_le(self):
        app = Rivex()

        @app.get("/items")
        async def search(page: int = Query(1, ge=1, le=100)):
            return {"page": page}

        resp = TestClient(app).get("/items", params={"page": "0"})
        assert resp.status_code == 422

        resp = TestClient(app).get("/items", params={"page": "101"})
        assert resp.status_code == 422

        resp = TestClient(app).get("/items", params={"page": "50"})
        assert resp.status_code == 200
