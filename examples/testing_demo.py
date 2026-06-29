"""In-process TestClient demo.

Run with: python examples/testing_demo.py

Builds a tiny Rivex app and exercises it without starting a real
server — the same pattern you'd use from a pytest module.
"""

from rivex import Body, Rivex, TestClient


def build_app() -> Rivex:
    app = Rivex(title="Testing Demo")

    @app.get("/hello/{name}")
    async def hello(name: str):
        return {"message": f"Hello, {name}!"}

    @app.post("/echo")
    async def echo(payload: dict = Body(...)):
        return payload

    return app


def main() -> None:
    app = build_app()
    client = TestClient(app)

    resp = client.get("/hello/Ada")
    print(f"GET /hello/Ada -> {resp.status_code}")
    print(f"  body={resp.text}")

    echo_resp = client.post("/echo", json={"hi": "there"})
    print(f"POST /echo -> {echo_resp.status_code}")
    print(f"  body={echo_resp.text}")

    missing = client.get("/does-not-exist")
    print(f"GET /does-not-exist -> {missing.status_code}")


if __name__ == "__main__":
    main()
