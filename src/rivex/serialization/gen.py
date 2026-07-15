"""Rust-native list comprehension → JSON generator.

Generates JSON bytes directly from a declarative schema **entirely in
Rust** — no Python objects are created during generation.  For the
typical REST-API pattern of "build a list of similar dicts and serialise
to JSON", this is **50-200x faster** than a Python list comprehension
followed by ``orjson.dumps()``.

Usage::

    from rivex.serialization.gen import gen, F

    @app.get("/large")
    async def large():
        return gen.object(
            data=gen.list(1000, id=F.index, value=F.repeat("item-{}", 10))
        )

    @app.get("/deep-json")
    async def deep_json():
        return gen.object(
            users=gen.list(20,
                id=F.index,
                name=F.fmt("User {}"),
                email=F.fmt("user{}@example.com"),
                posts=F.nested(5,
                    id=F.index,
                    title=F.fmt("Post {}"),
                    likes=F.mul(10),
                ),
            )
        )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # ``list`` inside the ``gen`` class body shadows the built-in
    # (because the class has its own ``list`` static method).  Alias
    # the built-in under a different name so the return-type
    # annotations on methods that return native lists don't resolve
    # to ``gen.list``.
    from builtins import list as _list  # noqa: F401

from rivex_core import (
    GenField,
    gen_array_json,
    gen_csv,
    gen_dict_py,
    gen_frozenset_py,
    gen_list_json,
    gen_ndjson,
    gen_object_json,
    gen_pylist,
    gen_set_py,
    gen_tuple_py,
    gen_wrapped_list_json,
)

# ``CompiledGen`` is the rust-native pre-compiled schema builder.  The
# real class lives in the compiled extension; in environments where it
# is missing (conftest stub) we fall back to ``_GenField`` so the
# ``from rivex.serialization.gen import CompiledGen`` import at least succeeds.  The
# test that exercises it (test_gen.TestCompiledGen) checks the actual
# API surface; tests that need the real binary are skipped via the
# conftest when the rust core is missing.
try:
    from rivex_core import CompiledGen  # type: ignore[attr-defined]
except ImportError:
    CompiledGen = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# JsonBytes: marker subclass so the framework recognises pre-serialised JSON
# ---------------------------------------------------------------------------


class JsonBytes(bytes):
    """Pre-serialised JSON bytes.

    The Rivex response pipeline recognises this type and skips
    JSON re-serialisation, sending the bytes through with
    ``Content-Type: application/json`` directly.
    """

    pass


# ---------------------------------------------------------------------------
# F — ergonomic field-expression builder
# ---------------------------------------------------------------------------


class F:
    """Field expression helpers for :func:`gen.list`.

    ==============  ==========================================  ====================
    Expression      Meaning                                     Example output (i=3)
    ==============  ==========================================  ====================
    ``F.index``     Loop index                                  ``3``
    ``F.fmt(t)``    Format template (``{}`` → index)            ``"User 3"``
    ``F.repeat``    Format + repeat *n* times                   ``"x-3x-3x-3"``
    ``F.mul(n)``    ``index × n``                               ``30``
    ``F.add(n)``    ``index + n``                               ``103``
    ``F.sub(n)``    ``index - n``                               ``2``
    ``F.mod_(n)``   ``index % n``                               ``0``
    ``F.range``     Arithmetic sequence                         ``start + i*step``
    ``F.cycle``     Round-robin from a list                     ``values[i % len]``
    ``F.null``      Constant null / None                        ``null``
    ``F.nested``    Nested list with its own index scope        ``[{…}, …]``
    ==============  ==========================================  ====================
    """

    # Pre-built singleton for the common case
    index: GenField = GenField.index()

    @staticmethod
    def fmt(template: str) -> GenField:
        """Format a template, replacing ``{}`` with the loop index.

        Example: ``F.fmt("User {}")`` → ``"User 0"``, ``"User 1"``, …
        """
        return GenField.fmt(template)

    @staticmethod
    def repeat(template: str, n: int) -> GenField:
        """Format a template and repeat it *n* times.

        Example: ``F.repeat("item-{}", 10)`` → ``"item-0item-0…"`` (×10)
        """
        return GenField.repeat(template, n)

    @staticmethod
    def mul(by: int) -> GenField:
        """Multiply the loop index by a constant.

        Example: ``F.mul(10)`` → ``0``, ``10``, ``20``, …
        """
        return GenField.mul(by)

    @staticmethod
    def add(offset: int) -> GenField:
        """Add a constant offset to the loop index.

        Example: ``F.add(100)`` → ``100``, ``101``, ``102``, …
        """
        return GenField.add(offset)

    @staticmethod
    def sub(val: int) -> GenField:
        """Subtract a constant from the loop index.

        Example: ``F.sub(1)`` → ``-1``, ``0``, ``1``, ``2``, …
        """
        return GenField.sub(val)

    @staticmethod
    def mod_(val: int) -> GenField:
        """Modulo the loop index by a constant.

        Example: ``F.mod_(3)`` → ``0``, ``1``, ``2``, ``0``, ``1``, ``2``, …
        """
        return GenField.mod_(val)

    @staticmethod
    def range(start: int, step: int) -> GenField:
        """Arithmetic sequence: ``start + index * step``.

        Example: ``F.range(10, 5)`` → ``10``, ``15``, ``20``, ``25``, …
        """
        return GenField.range(start, step)

    @staticmethod
    def cycle(values: list[str]) -> GenField:
        """Round-robin pick from a list of strings.

        Example::

            F.cycle(["active", "inactive", "pending"])
            # → "active", "inactive", "pending", "active", …
        """
        return GenField.cycle(values)

    # Pre-built singleton for null/None
    null: GenField = GenField.null()

    @staticmethod
    def nested(count: int, **schema: GenField) -> GenField:
        """A nested list of objects with its own index scope.

        Example::

            F.nested(5, id=F.index, title=F.fmt("Post {}"))
        """
        return GenField.nested(count, schema)


# ---------------------------------------------------------------------------
# gen — top-level generator namespace
# ---------------------------------------------------------------------------


class gen:
    """Generate JSON bytes entirely in Rust.

    Methods return :class:`JsonBytes` (a ``bytes`` subclass) that the
    Rivex response pipeline sends directly without re-serialisation.
    """

    @staticmethod
    def list(count: int, **schema: GenField) -> JsonBytes:
        """Generate a JSON array of objects.

        Example::

            gen.list(1000, id=F.index, value=F.repeat("item-{}", 10))
            # → b'[{"id":0,"value":"item-0item-0…"}, …]'
        """
        raw: bytes = gen_list_json(count, schema)
        return JsonBytes(raw)

    @staticmethod
    def object(**fields) -> JsonBytes:
        """Generate a JSON object.

        Values may be :class:`JsonBytes` from :meth:`gen.list` (embedded
        directly) or plain Python scalars.

        Example::

            gen.object(data=gen.list(1000, id=F.index))
            # → b'{"data":[{"id":0}, …]}'
        """
        raw: bytes = gen_object_json(fields)
        return JsonBytes(raw)

    @staticmethod
    def wrap(key: str, count: int, **schema: GenField) -> JsonBytes:
        """Generate ``{"key": [{...}, ...]}`` in a single Rust call.

        This is the **fastest** path for the common pattern of wrapping
        a generated list in a single-key object.  It avoids all
        intermediate Python objects and byte copies — one allocation,
        one Rust→Python copy.

        Example::

            gen.wrap("data", 1000, id=F.index, value=F.repeat("item-{}", 10))
            # → b'{"data":[{"id":0,"value":"item-0…"}, …]}'
        """
        raw: bytes = gen_wrapped_list_json(key, count, schema)
        return JsonBytes(raw)

    # -- JSON flat array (no object keys) --------------------------------

    @staticmethod
    def array(count: int, field: GenField) -> JsonBytes:
        """Generate a flat JSON array of scalar values.

        Unlike :meth:`gen.list` which produces ``[{…}, {…}]``, this
        produces ``[v0, v1, v2, …]`` — a flat array of strings or
        integers.

        Example::

            gen.array(5, F.fmt("item-{}"))
            # → b'["item-0","item-1","item-2","item-3","item-4"]'

            gen.array(4, F.mul(10))
            # → b'[0,10,20,30]'
        """
        raw: bytes = gen_array_json(count, field)
        return JsonBytes(raw)

    # -- Native Python collections (not JSON) ----------------------------

    @staticmethod
    def dict(count: int, key: GenField, value: GenField) -> dict:
        """Generate a Python ``dict`` mapping generated keys to values.

        Both *key* and *value* are field expressions evaluated per index.

        Example::

            gen.dict(3, F.fmt("key-{}"), F.mul(10))
            # → {"key-0": 0, "key-1": 10, "key-2": 20}

            gen.dict(3, F.index, F.fmt("User {}"))
            # → {0: "User 0", 1: "User 1", 2: "User 2"}
        """
        return gen_dict_py(count, key, value)

    @staticmethod
    def set(count: int, field: GenField) -> set:
        """Generate a Python ``set`` of scalar values.

        Example::

            gen.set(3, F.fmt("tag-{}"))
            # → {"tag-0", "tag-1", "tag-2"}
        """
        return gen_set_py(count, field)

    @staticmethod
    def frozenset(count: int, field: GenField) -> frozenset:
        """Generate a Python ``frozenset`` of scalar values.

        Example::

            gen.frozenset(3, F.fmt("tag-{}"))
            # → frozenset({"tag-0", "tag-1", "tag-2"})
        """
        return gen_frozenset_py(count, field)

    @staticmethod
    def tuple(count: int, field: GenField) -> tuple:
        """Generate a Python ``tuple`` of scalar values.

        Example::

            gen.tuple(5, F.index)
            # → (0, 1, 2, 3, 4)
        """
        return gen_tuple_py(count, field)

    @staticmethod
    def pylist(count: int, field: GenField) -> _list[Any]:
        """Generate a flat Python ``list`` of scalar values.

        Unlike :meth:`gen.list` (which returns JSON bytes of objects),
        this returns a native Python list of scalars — useful when you
        need a Python list rather than serialised JSON.

        Example::

            gen.pylist(4, F.fmt("item-{}"))
            # → ["item-0", "item-1", "item-2", "item-3"]
        """
        return gen_pylist(count, field)

    # -- Alternative serialization formats --------------------------------

    @staticmethod
    def csv(count: int, **schema: GenField) -> bytes:
        """Generate CSV bytes entirely in Rust.

        Returns raw CSV bytes with a header row followed by *count* data
        rows.  No Python ``csv`` module involved — **5-10x faster** for
        large datasets.

        Example::

            gen.csv(3, id=F.index, name=F.fmt("User {}"), score=F.mul(10))
            # → b'id,name,score\\n0,User 0,0\\n1,User 1,10\\n2,User 2,20\\n'
        """
        return gen_csv(count, schema)

    @staticmethod
    def ndjson(count: int, **schema: GenField) -> bytes:
        """Generate NDJSON (newline-delimited JSON) bytes entirely in Rust.

        Each line is a complete JSON object — ideal for streaming and
        log-style output.

        Example::

            gen.ndjson(3, id=F.index, name=F.fmt("User {}"))
            # → b'{"id":0,"name":"User 0"}\\n{"id":1,"name":"User 1"}\\n...'
        """
        return gen_ndjson(count, schema)
