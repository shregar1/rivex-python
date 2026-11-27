# High-Performance JSON

For endpoints that return large, regular JSON arrays, the bottleneck is rarely your logic — it's building thousands of Python dicts and serializing them.  `gen` API sidesteps that entirely: it constructs the JSON **in Rust**, producing finished bytes without ever materializing the intermediate Python objects.

## The idea

`gen` methods return `JsonBytes` — a `bytes` subclass that the response pipeline recognizes as already-serialized JSON and sends as-is (with `Content-Type: application/json`). You describe each field once with an `F` expression; Rust evaluates it per row.

```python
from rivex import Rivex
from rivex.gen import gen, F

app = Rivex()


@app.get("/items")
async def items():
    # 10,000 objects, generated and serialized entirely in Rust
    return gen.wrap(
        "items", 10_000,
        id=F.index,
        name=F.fmt("Item {}"),
        price=F.mul(10),
        category=F.cycle(["electronics", "books", "clothing"]),
    )
```

This returns `{"items": [{"id": 0, "name": "Item 0", "price": 0, "category": "electronics"}, …]}` — no Python list, no per-row dict.

## Field expressions (`F`)

Each `F` expression is evaluated with the current row index `i`:

| Expression | Result at row `i` | Example output |
| --- | --- | --- |
| `F.index` | `i` | `0, 1, 2, …` |
| `F.fmt("User {}")` | template with `i` | `"User 0"` |
| `F.repeat("x-{}", n)` | the formatted value repeated `n` times | `"x-0x-0"` |
| `F.mul(n)` / `F.add(n)` / `F.sub(n)` | arithmetic on `i` | `i*n`, `i+n`, `i-n` |
| `F.mod_(n)` | `i % n` | cycling integers |
| `F.range(start, step)` | `start + i*step` | `10, 15, 20, …` |
| `F.cycle([...])` | round-robin through the list | `"a", "b", "a", …` |
| `F.null` | constant `null` | |
| `F.nested(count, **schema)` | a nested array with its own index scope | sub-lists per row |

Static (non-`F`) values are emitted as constants on every row:

```python
gen.list(3, id=F.index, active=True, source="seed")
# [{"id":0,"active":true,"source":"seed"}, {"id":1,...}, {"id":2,...}]
```

Nested structures get their own index scope:

```python
gen.object(
    users=gen.list(
        100,
        id=F.index,
        name=F.fmt("User {}"),
        posts=F.nested(5, id=F.index, title=F.fmt("Post {}")),
    )
)
```

## The generator methods

| Method | Returns | Shape |
| --- | --- | --- |
| `gen.list(count, **schema)` | `JsonBytes` | `[{...}, {...}]` |
| `gen.object(**fields)` | `JsonBytes` | `{...}` (values may be other `gen` results) |
| `gen.wrap(key, count, **schema)` | `JsonBytes` | `{key: [{...}, …]}` — the fastest path |
| `gen.array(count, field)` | `JsonBytes` | `[v0, v1, …]` flat scalar array |
| `gen.csv(count, **schema)` | `bytes` | CSV rows (with header) |
| `gen.ndjson(count, **schema)` | `bytes` | newline-delimited JSON |

For when you actually want Python objects rather than JSON bytes, there are collection builders too: `gen.pylist`, `gen.dict`, `gen.set`, `gen.frozenset`, `gen.tuple`.

```python
gen.csv(3, id=F.index, name=F.fmt("User {}"), score=F.mul(10))
# b'id,name,score\n0,User 0,0\n1,User 1,10\n2,User 2,20\n'
```

## Content negotiation

Pair `gen` with  negotiation helpers to serve the format the client asked for:

```python
from rivex import Request
from rivex.negotiation import best_match


@app.get("/export")
async def export(request: Request):
    fmt = best_match(request.header("accept", "application/json"),
                     ["application/json", "text/csv"])
    if fmt == "text/csv":
        return gen.csv(1000, id=F.index, name=F.fmt("Row {}"))
    return gen.wrap("rows", 1000, id=F.index, name=F.fmt("Row {}"))
```

## When to reach for it

`gen` shines for **large, uniform** result sets — list endpoints, exports, seed/fixture data, load-test payloads. For small or highly irregular responses, plain dicts and models are simpler and the difference is negligible. Use `gen` where the row count is high and the structure is regular.

## Next

**OpenAPI & Interactive Docs** explains the schema and UIs Rivex generates for you.
