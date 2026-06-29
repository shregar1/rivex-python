from rivex import APIStatus, Depends, HTTPBearer, HTTPException, Request, Rivex

app = Rivex(title="Auth Bearer Example")

# Hard-coded "user database" keyed by token. In a real app, verify a JWT
# signature or look the token up in a session store.
USERS: dict[str, dict] = {
    "demo-token": {"id": 1, "name": "Ada", "role": "admin"},
    "guest-token": {"id": 2, "name": "Guest", "role": "viewer"},
}

bearer = HTTPBearer()


def current_user(request: Request) -> dict:
    creds = bearer(request)
    if creds is None:
        raise HTTPException(APIStatus.UNAUTHORIZED, detail="Missing bearer token")
    user = USERS.get(creds.credentials)
    if user is None:
        raise HTTPException(APIStatus.UNAUTHORIZED, detail="Invalid bearer token")
    return user


@app.get("/public")
async def public():
    return {"message": "anyone can see this"}


@app.get("/me")
async def me(user: dict = Depends(current_user)):
    return user


@app.get("/admin")
async def admin(user: dict = Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(APIStatus.FORBIDDEN, detail="Admins only")
    return {"message": "welcome to the admin panel", "user": user}


if __name__ == "__main__":
    app.run(port=8000)
