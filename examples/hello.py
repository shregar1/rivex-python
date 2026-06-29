from rivex import Rivex

app = Rivex()


@app.get("/")
async def index():
    return {"message": "Hello from Rivex!"}


@app.get("/hello/{name}")
async def greet(name: str):
    return {"message": f"Hello, {name}!"}


@app.get("/add")
def add(a: int = 0, b: int = 0):
    return {"result": a + b}


if __name__ == "__main__":
    app.run()
