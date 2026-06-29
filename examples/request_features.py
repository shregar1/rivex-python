from pydantic import BaseModel

from rivex import (
    APIStatus,
    Dependency,
    Depends,
    File,
    Form,
    HTTPException,
    HTTPMethod,
    Middleware,
    Request,
    Rivex,
    UploadFile,
)

app = Rivex(title="Rivex request features")


class ItemCreate(BaseModel):
    name: str
    price: float
    in_stock: bool = True


class CurrentUser(Dependency):
    def resolve(self, request: Request) -> dict:
        token = request.header("authorization", "").removeprefix("Bearer ")
        if token != "demo-token":
            raise HTTPException(APIStatus.UNAUTHORIZED, detail="Invalid token")
        return {"id": 1, "name": "Ada", "style": "class"}


class AuditContext(Dependency):
    def resolve(self, item_id: int, request: Request, debug: bool = False) -> dict:
        return {
            "item_id": item_id,
            "url": request.url,
            "debug": debug,
        }


class PoweredByMiddleware(Middleware):
    async def process(self, request_data: dict, call_next):
        response = await call_next(request_data)
        response["headers"] = response.get("headers", []) + [("x-powered-by", "RIVEX")]
        return response


def get_request_user(request: Request) -> dict:
    token = request.header("authorization", "").removeprefix("Bearer ")
    if token != "demo-token":
        raise HTTPException(APIStatus.UNAUTHORIZED, detail="Invalid token")
    return {"id": 1, "name": "Ada", "style": "function"}


@app.middleware("http")
async def powered_by_function(request: Request, call_next):
    response = await call_next(request)
    response["headers"] = response.get("headers", []) + [("x-middleware-style", "function")]
    return response


app.add_middleware(PoweredByMiddleware)


@app.get("/items/{item_id}")
async def read_item(
    item_id: int,
    q: str | None = None,
    limit: int = 10,
    audit: dict = Depends(AuditContext),
):
    return {
        "method": HTTPMethod.GET,
        "item_id": item_id,
        "q": q,
        "limit": limit,
        "audit": audit,
    }


@app.post("/items", status_code=APIStatus.CREATED)
async def create_item(item: ItemCreate):
    return item


@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    return {"username": username, "password_length": len(password)}


@app.post("/avatar")
async def upload_avatar(file: UploadFile = File(...)):
    content = await file.read()
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
    }


@app.get("/me")
async def me(user: dict = Depends(get_request_user)):
    return user


@app.get("/me/class")
async def me_class(user: dict = Depends(CurrentUser)):
    return user


if __name__ == "__main__":
    app.run(port=8000)
