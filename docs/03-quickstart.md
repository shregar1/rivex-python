# Quickstart

Let's build a small but complete JSON API — a todo service — and run it. This touches routing, request bodies, validation, error handling, and the auto-generated docs. It mirrors the framework's own `examples/todo_api.py`.

## 1. Create the app

```python
# main.py
from pydantic import BaseModel

from rivex import CORSMiddleware, HTTPException, Rivex, Router

app = Rivex(title="Todo API", version="1.0.0", debug=True)
app.add_middleware(CORSMiddleware, allow_origins=["*"])
```

`Rivex(...)` builds the application. `add_middleware` attaches behaviour to every request — here, permissive CORS so a browser front-end can call the API.

## 2. Define models

Rivex uses your type annotations to parse and validate input. A Pydantic model as a parameter is treated as the JSON request body.

```python
class TodoCreate(BaseModel):
    title: str
    completed: bool = False


class Todo(BaseModel):
    id: int
    title: str
    completed: bool


db: dict[int, Todo] = {}
next_id = 1
```

## 3. Add routes with a Router

A `Router` groups related endpoints under a shared prefix. Path parameters in `{braces}` are matched to handler arguments and converted using the annotation (`todo_id: int`).

```python
router = Router(prefix="/api/v1")


@router.get("/todos")
async def list_todos():
    return [t.model_dump() for t in db.values()]


@router.get("/todos/{todo_id}")
async def get_todo(todo_id: int):
    if todo_id not in db:
        raise HTTPException(404, detail="Todo not found")
    return db[todo_id]


@router.post("/todos", status_code=201)
async def create_todo(todo: TodoCreate):
    global next_id
    new = Todo(id=next_id, **todo.model_dump())
    db[next_id] = new
    next_id += 1
    return new


@router.put("/todos/{todo_id}")
async def update_todo(todo_id: int, todo: TodoCreate):
    if todo_id not in db:
        raise HTTPException(404, detail="Todo not found")
    db[todo_id] = Todo(id=todo_id, **todo.model_dump())
    return db[todo_id]


@router.delete("/todos/{todo_id}")
async def delete_todo(todo_id: int):
    if todo_id not in db:
        raise HTTPException(404, detail="Todo not found")
    del db[todo_id]
```

Note the patterns:

- **`status_code=201`** sets the success status for creation.
- **`raise HTTPException(404, detail=...)`** returns a clean error response.
- **Returning a model or dict** is auto-serialized to JSON.
- A handler that returns nothing yields an empty `204`-style body with the route's status.

## 4. Mount the router and finish the app

```python
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(port=8000)
```

## 5. Run it

```bash
python main.py
# or, with live reload during development:
rivex run main:app --reload
```

The server listens on `http://127.0.0.1:8000`.

## 6. Try it out

```bash
# Create a todo
curl -X POST http://127.0.0.1:8000/api/v1/todos \
  -H "Content-Type: application/json" \
  -d '{"title": "Write docs"}'
# → {"id": 1, "title": "Write docs", "completed": false}

# List todos
curl http://127.0.0.1:8000/api/v1/todos

# Fetch a missing todo
curl -i http://127.0.0.1:8000/api/v1/todos/999
# → HTTP/1.1 404 Not Found  {"detail": "Todo not found"}
```

Send a malformed body (e.g. `title` as a number) and Rivex returns **422 Unprocessable Entity** automatically, with details about which field failed — you didn't write any validation code.

## 7. Read the generated docs

Open these in a browser:

- **`http://127.0.0.1:8000/docs`** — interactive Swagger UI
- **`http://127.0.0.1:8000/redoc`** — ReDoc reference
- **`http://127.0.0.1:8000/openapi.json`** — the raw OpenAPI 3.1 schema

Every route, parameter, and model you defined is already documented.

## Where to go next

- **Routing** — controllers, route groups, reverse URLs
- **Parameters & Validation** — fine-grained control over inputs
- **Dependency Injection** — share auth, DB sessions, and config across routes
