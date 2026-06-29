from pydantic import BaseModel

from rivex import CORSMiddleware, HTTPException, Rivex, Router

app = Rivex(title="Todo API", debug=True)
app.add_middleware(CORSMiddleware, allow_origins=["*"])

router = Router(prefix="/api/v1")


class TodoCreate(BaseModel):
    title: str
    completed: bool = False


class Todo(BaseModel):
    id: int
    title: str
    completed: bool


db: dict[int, Todo] = {}
next_id = 1


@router.get("/todos")
async def list_todos():
    return list(t.model_dump() for t in db.values())


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


app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(port=8000)
