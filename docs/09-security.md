# Security & Authentication

Rivex covers the whole authentication and authorization stack: pluggable security schemes you inject like any dependency, JWT encode/decode, Rust-backed password hashing, route guards, and per-user throttling. The cryptographic primitives run in Rust for speed and correctness.

## Security schemes

Each scheme is a callable you construct once and inject with `Depends()`. With `auto_error=True` (the default) a missing credential yields a `401`; set it `False` to handle absence yourself.

```python
from rivex import APIKeyHeader, Depends, HTTPBearer, OAuth2PasswordBearer

api_key = APIKeyHeader(name="x-api-key")
bearer = HTTPBearer()
oauth2 = OAuth2PasswordBearer(tokenUrl="/token")


@app.get("/by-key")
async def by_key(key: str = Depends(api_key)):
    return {"key": key}


@app.get("/by-bearer")
async def by_bearer(creds = Depends(bearer)):
    return {"scheme": creds.scheme, "token": creds.credentials}


@app.get("/by-oauth")
async def by_oauth(token: str = Depends(oauth2)):
    return {"token": token}
```

| Scheme | Reads from | Yields |
| --- | --- | --- |
| `APIKeyHeader(name=...)` | a request header | `str` |
| `APIKeyQuery(name=...)` | a query parameter | `str` |
| `APIKeyCookie(name=...)` | a cookie | `str` |
| `HTTPBearer()` | `Authorization: Bearer …` | `HTTPAuthorizationCredentials(scheme, credentials)` |
| `HTTPBasic(realm=...)` | `Authorization: Basic …` | `HTTPBasicCredentials(username, password)` |
| `OAuth2PasswordBearer(tokenUrl=...)` | Bearer token (password flow) | `str` |
| `OAuth2AuthorizationCodeBearer(...)` | Bearer token (auth-code flow) | `str` |

These schemes also advertise themselves in the OpenAPI schema, so the `/docs` UI shows an **Authorize** button.

### HTTP Basic example

```python
from rivex import Depends, HTTPBasic, HTTPException

basic = HTTPBasic(realm="Admin")


@app.get("/admin")
async def admin(creds = Depends(basic)):
    if creds.username != "admin" or creds.password != "secret":
        raise HTTPException(401, detail="Invalid credentials")
    return {"user": creds.username}
```

### OAuth2 password flow

`OAuth2PasswordRequestForm` parses the standard token-endpoint form body:

```python
from rivex import Depends, OAuth2PasswordRequestForm
from rivex.jwt import encode


@app.post("/token")
async def token(form: OAuth2PasswordRequestForm = Depends()):
    if not authenticate(form.username, form.password):
        raise HTTPException(401, detail="Bad credentials")
    jwt = encode({"sub": form.username}, "secret", expires_in=3600)
    return {"access_token": jwt, "token_type": "bearer"}
```

## JWT

`rivex.jwt` provides HS256 encode/decode (Rust-backed when available) and a ready-made `JWTBearer` dependency.

```python
from rivex.jwt import encode, decode, JWTBearer, ExpiredTokenError, InvalidTokenError, Depends

# Issue a token (expires_in adds an `exp` claim, in seconds)
token = encode({"sub": "user-42", "role": "admin"}, "secret", expires_in=3600)

# Verify a token
try:
    claims = decode(token, "secret")
except ExpiredTokenError:
    ...   # token expired
except InvalidTokenError:
    ...   # bad signature / malformed
```

Guard routes by injecting `JWTBearer`, which extracts the Bearer token, verifies it, and hands you the decoded payload:

```python
auth = JWTBearer(secret="secret")


@app.get("/protected")
async def protected(claims: dict = Depends(auth)):
    return {"user": claims["sub"]}
```

## Password hashing

Use the Rust-backed helpers — never store plaintext. `hash_password` defaults to Argon2; bcrypt is available too.

```python
from rivex import hash_password, verify_password

digest = hash_password("s3cret!")            # Argon2 by default
ok = verify_password("s3cret!", digest)      # True

# Explicit algorithms
from rivex import hash_argon2, hash_bcrypt
```

## Built-in validators

`rivex` re-exports a battery of Rust-native validators — handy for sanitizing input cheaply:

```python
from rivex import (
    validate_email, validate_url, validate_ip, validate_uuid, validate_phone,
    validate_iban, format_iban, luhn_check, is_ascii,
    sanitize_html, strip_html_tags,
)

validate_email("ada@example.com")   # True
luhn_check("4111111111111111")      # credit-card checksum
sanitize_html(user_supplied)        # strip dangerous tags/attrs
```

## Guards

Guards enforce coarse access rules at the middleware layer. Combine them with `GuardMiddleware`:

```python
from rivex import GuardMiddleware, IsAuthenticated, RequiresRoles

app.add_middleware(
    GuardMiddleware,
    guards=[IsAuthenticated(), RequiresRoles("admin")],
)
```

Built-in guards: `IsAuthenticated`, `RequiresRoles(*roles)`, `AllowAll`, `DenyAll`. Subclass `Guard` for custom logic — return `True` to allow or raise `HTTPException` to deny.

## Throttling

Beyond the IP-based `RateLimitMiddleware`, the throttling module distinguishes anonymous from authenticated callers:

```python
from rivex import ThrottleMiddleware, AnonRateThrottle, UserRateThrottle

app.add_middleware(
    ThrottleMiddleware,
    throttle_classes=[AnonRateThrottle, UserRateThrottle],
)
```

`AnonRateThrottle` defaults to `100/hour` keyed by IP; `UserRateThrottle` to `1000/hour` keyed by user. Subclass `ScopedRateThrottle` to define per-scope rates. Exceeding a limit returns `429` with a `Retry-After` header.

## Webhook signature verification

Verify incoming webhooks (Stripe, GitHub, or generic HMAC-SHA256) before trusting them:

```python
from rivex.webhooks import verify_signature, WebhookVerificationError


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    try:
        verify_signature(
            payload=request.body(),
            signature=request.header("stripe-signature"),
            secret="whsec_…",
            provider="stripe",
        )
    except WebhookVerificationError:
        raise HTTPException(401, detail="Invalid signature")
    return {"received": True}
```

A `WebhookGuard(secret=..., provider=...)` dependency is available for the same check inline.

## Putting it together

```python
from rivex import Depends, Rivex
from rivex.jwt import JWTBearer

app = Rivex()
auth = JWTBearer(secret="secret")


@app.get("/account")
async def account(claims: dict = Depends(auth)):
    return {"user_id": claims["sub"], "role": claims.get("role", "member")}
```

## Next

**WebSockets** covers real-time connections and broadcast rooms.
