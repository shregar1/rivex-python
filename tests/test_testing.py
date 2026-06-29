from contextlib import contextmanager

from pydantic import BaseModel

from rivex import Depends, HTTPException, PlainTextResponse, Rivex, TestClient


class UserOut(BaseModel):
    id: int
    name: str


def test_test_client_get_path_and_query_params():
    app = Rivex()

    @app.get("/items/{item_id}")
    async def read_item(item_id: int, debug: bool = False):
        return {"item_id": item_id, "debug": debug}

    client = TestClient(app)
    response = client.get("/items/42", params={"debug": "true"})

    assert response.status_code == 200
    assert response.json() == {"item_id": 42, "debug": True}


def test_test_client_post_json_body():
    app = Rivex()

    class UserIn(BaseModel):
        name: str

    @app.post("/users", status_code=201)
    async def create_user(user: UserIn):
        return {"name": user.name}

    client = TestClient(app)
    response = client.post("/users", json={"name": "Ada"})

    assert response.status_code == 201
    assert response.json() == {"name": "Ada"}


def test_test_client_applies_middleware_and_exception_handlers():
    app = Rivex()

    @app.middleware("http")
    async def add_header(request, call_next):
        response = await call_next(request)
        response["headers"] = response.get("headers", []) + [("x-test", "yes")]
        return response

    @app.exception_handler(ValueError)
    async def handle_value_error(request, exc):
        return PlainTextResponse("handled", status_code=418)

    @app.get("/fail")
    async def fail():
        raise ValueError("bad")

    response = TestClient(app).get("/fail")

    assert response.status_code == 418
    assert response.text == "handled"
    assert response.headers["x-test"] == "yes"


def test_test_client_not_found():
    response = TestClient(Rivex()).get("/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_response_model_filters_output():
    app = Rivex()

    @app.get("/users/{user_id}", response_model=UserOut)
    async def read_user(user_id: int):
        return {"id": user_id, "name": "Ada", "password": "hidden"}

    response = TestClient(app).get("/users/1")

    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Ada"}


def test_test_client_with_dependency():
    app = Rivex()

    def token(x_token: str):
        if x_token != "secret":
            raise HTTPException(403, detail="Forbidden")
        return x_token

    @app.get("/secure")
    async def secure(value: str = Depends(token)):
        return {"token": value}

    response = TestClient(app).get("/secure", params={"x_token": "secret"})

    assert response.status_code == 200
    assert response.json() == {"token": "secret"}


def test_test_client_context_runs_lifespan_and_events():
    events = []

    @contextmanager
    def lifespan(app):
        events.append("lifespan-start")
        yield
        events.append("lifespan-stop")

    app = Rivex(lifespan=lifespan)

    @app.on_event("startup")
    def startup():
        events.append("startup")

    @app.on_event("shutdown")
    def shutdown():
        events.append("shutdown")

    @app.get("/")
    async def root():
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/").json() == {"ok": True}
        assert events == ["lifespan-start", "startup"]

    assert events == ["lifespan-start", "startup", "shutdown", "lifespan-stop"]
