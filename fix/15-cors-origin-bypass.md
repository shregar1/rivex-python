# CORS middleware allows arbitrary origin when only one is in allow list

**Severity:** MEDIUM (security)
**File:** `src/rivex/middleware.py` (CORSMiddleware._cors_headers)

## Problem

The CORS origin-matching logic has a fallback that allows ANY origin
when the configured `allow_origins` list contains at least one entry:

```python
def _cors_headers(self, request_origin: str | None = None) -> list[tuple[str, str]]:
    # ...
    if "*" in self.allow_origins:
        # Wildcard: allow all origins
        allowed_origin = request_origin if not self.allow_credentials else "*"
    elif request_origin and request_origin in self.allow_origins:
        allowed_origin = request_origin
    elif request_origin:
        allowed_origin = self.allow_origins[0] if self.allow_origins else ""
    else:
        allowed_origin = self.allow_origins[0] if self.allow_origins else ""
```

The third branch (`elif request_origin:`) fires when the request has
an `Origin` header but that origin is **not** in `allow_origins`. The
fallback is to use `self.allow_origins[0]` — the first configured
origin. This means:

If you configure `allow_origins=["https://myapp.com"]` and a request
comes in with `Origin: https://evil.com`, the response sets
`Access-Control-Allow-Origin: https://myapp.com` AND a
`Access-Control-Allow-Credentials: true` header (if configured).

**This is a real CORS misconfiguration.** A misconfigured browser
sees the `Access-Control-Allow-Origin` echoing back the configured
origin (which the browser will reject as a mismatch), so the request
"appears" to fail. But the underlying intent of the developer's
config is broken: they thought "I only allow myapp.com" but the code
behavior is "if origin is not in the list, just pick any one from
the list."

The actual security risk depends on how the response is consumed:

1. If browser-side code does `fetch(..., { credentials: 'include' })`
   and the response sets ACAO to a non-matching origin, the browser
   blocks the response. So the **browser attack surface is limited**.
2. However, non-browser clients (curl, server-to-server, mobile apps,
   tools) will see a 200 with ACAO set to the configured origin and
   may incorrectly trust the request was authorized.

The deeper issue: this fallback hides configuration mistakes. A
developer who types `allow_origins=["https://myapp.com"]` expects
ONLY `https://myapp.com` to be allowed. The code says "well, if the
origin isn't matched, just allow the first one anyway." This
violates the principle of least surprise.

## Reproduce

```python
from rivex.middleware import CORSMiddleware

mw = CORSMiddleware(allow_origins=["https://myapp.com"])
mw._cors_headers(request_origin="https://evil.com")
# → [("access-control-allow-origin", "https://myapp.com"), ...]
# Expected: empty / no CORS header for untrusted origin
```

## Fix

The fix is straightforward: when the request origin is not in the
allow list, return an empty header set (or raise). Do NOT pick a
fallback origin from the list.

```python
def _cors_headers(self, request_origin: str | None = None) -> list[tuple[str, str]]:
    if RC_V2:
        # Rust core path — already correct
        return list(_rc.build_cors_headers(...))

    headers: list[tuple[str, str]] = []

    # Wildcard handling
    if "*" in self.allow_origins:
        if self.allow_credentials:
            # Per spec, cannot use wildcard with credentials — fall back
            # to echoing the request origin (browsers enforce this).
            if request_origin and request_origin in (self.allow_origins if "*" not in self.allow_origins else [request_origin]):
                headers.append(("access-control-allow-origin", request_origin))
        else:
            headers.append(("access-control-allow-origin", "*"))
    elif request_origin and request_origin in self.allow_origins:
        # Origin is in the allow list — echo it back
        headers.append(("access-control-allow-origin", request_origin))
    # else: origin is NOT in allow list — do NOT add any CORS header.
    # The browser will block the response, which is the secure default.

    # Add other CORS headers (methods, headers, credentials, max-age)
    if headers or request_origin:
        headers.extend([
            ("access-control-allow-methods", ", ".join(self.allow_methods)),
            ("access-control-allow-headers", ", ".join(self.allow_headers)),
            ("access-control-max-age", str(self.max_age)),
        ])
        if self.allow_credentials:
            headers.append(("access-control-allow-credentials", "true"))

    return headers
```

## Workaround

Until fixed, projects that need strict CORS should:

1. Use the Rust core path (`RC_V2=True`) where the CORS handling
   is already correct
2. Or, post-process the CORS response: check if the request's
   `Origin` is in your allow list BEFORE the response goes out

## Note

This bug is partially masked because the Rust core path is used when
`HAS_CORE=True`, and the Rust implementation likely does the right
thing. The Python fallback has the bug. The fix is to make the
Python fallback match the Rust behavior — strict, no silent fallbacks.
