from rivex import APIKeyHeader, Depends, HTTPBearer, OAuth2PasswordBearer, Rivex, TestClient


def test_api_key_header_dependency():
    app = Rivex()
    api_key = APIKeyHeader(name="x-api-key")

    @app.get("/secure")
    async def secure(key: str = Depends(api_key)):
        return {"key": key}

    response = TestClient(app).get("/secure", headers={"x-api-key": "secret"})

    assert response.status_code == 200
    assert response.json() == {"key": "secret"}


def test_api_key_header_missing_returns_401():
    app = Rivex()
    api_key = APIKeyHeader(name="x-api-key")

    @app.get("/secure")
    async def secure(key: str = Depends(api_key)):
        return {"key": key}

    response = TestClient(app).get("/secure")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_http_bearer_dependency():
    app = Rivex()
    bearer = HTTPBearer()

    @app.get("/secure")
    async def secure(credentials=Depends(bearer)):
        return {
            "scheme": credentials.scheme,
            "credentials": credentials.credentials,
        }

    response = TestClient(app).get(
        "/secure",
        headers={"authorization": "Bearer abc123"},
    )

    assert response.status_code == 200
    assert response.json() == {"scheme": "Bearer", "credentials": "abc123"}


def test_oauth2_password_bearer_returns_token():
    app = Rivex()
    oauth2 = OAuth2PasswordBearer(tokenUrl="/token")

    @app.get("/me")
    async def me(token: str = Depends(oauth2)):
        return {"token": token}

    response = TestClient(app).get("/me", headers={"authorization": "Bearer jwt"})

    assert response.status_code == 200
    assert response.json() == {"token": "jwt"}
