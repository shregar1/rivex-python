"""Tests for rivex.gen — Rust-native list comprehension → JSON generator."""

import json

import pytest

from rivex.serialization.gen import CompiledGen, F, JsonBytes, gen
from rivex_core import GenField


class TestGenList:
    """gen.list() — generate JSON arrays of objects."""

    def test_basic_list(self):
        result = gen.list(3, id=F.index)
        assert isinstance(result, JsonBytes)
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert parsed == [{"id": 0}, {"id": 1}, {"id": 2}]

    def test_empty_list(self):
        result = gen.list(0, id=F.index)
        assert json.loads(result) == []

    def test_format_template(self):
        result = gen.list(3, name=F.fmt("User {}"))
        parsed = json.loads(result)
        assert parsed == [{"name": "User 0"}, {"name": "User 1"}, {"name": "User 2"}]

    def test_repeat_template(self):
        result = gen.list(2, val=F.repeat("x-{}", 3))
        parsed = json.loads(result)
        assert parsed[0]["val"] == "x-0x-0x-0"
        assert parsed[1]["val"] == "x-1x-1x-1"

    def test_multiply(self):
        result = gen.list(4, score=F.mul(10))
        parsed = json.loads(result)
        assert [item["score"] for item in parsed] == [0, 10, 20, 30]

    def test_add(self):
        result = gen.list(3, val=F.add(100))
        parsed = json.loads(result)
        assert [item["val"] for item in parsed] == [100, 101, 102]

    def test_static_values(self):
        result = gen.list(2, id=F.index, active=True, label="test", total=42)
        parsed = json.loads(result)
        assert parsed[0] == {"id": 0, "active": True, "label": "test", "total": 42}
        assert parsed[1] == {"id": 1, "active": True, "label": "test", "total": 42}

    def test_multiple_fields(self):
        result = gen.list(2, id=F.index, name=F.fmt("Item {}"), price=F.mul(5))
        parsed = json.loads(result)
        assert parsed == [
            {"id": 0, "name": "Item 0", "price": 0},
            {"id": 1, "name": "Item 1", "price": 5},
        ]

    def test_nested_list(self):
        result = gen.list(
            2,
            id=F.index,
            posts=F.nested(3, id=F.index, title=F.fmt("Post {}")),
        )
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert len(parsed[0]["posts"]) == 3
        assert parsed[1]["posts"][2] == {"id": 2, "title": "Post 2"}

    def test_json_escaping(self):
        """Strings with special characters should be properly escaped."""
        result = gen.list(1, val='hello "world"\nnewline')
        parsed = json.loads(result)
        assert parsed[0]["val"] == 'hello "world"\nnewline'


class TestGenObject:
    """gen.object() — wrap generated lists in JSON objects."""

    def test_basic_object(self):
        result = gen.object(data=gen.list(2, id=F.index))
        parsed = json.loads(result)
        assert parsed == {"data": [{"id": 0}, {"id": 1}]}

    def test_object_with_scalars(self):
        result = gen.object(
            count=42,
            items=gen.list(1, id=F.index),
        )
        parsed = json.loads(result)
        assert parsed["count"] == 42
        assert parsed["items"] == [{"id": 0}]


class TestGenWrap:
    """gen.wrap() — single-pass generation of {"key": [...]}."""

    def test_basic_wrap(self):
        result = gen.wrap("data", 3, id=F.index)
        parsed = json.loads(result)
        assert parsed == {"data": [{"id": 0}, {"id": 1}, {"id": 2}]}

    def test_large_pattern(self):
        """Match the /large benchmark endpoint pattern."""
        result = gen.wrap("data", 1000, id=F.index, value=F.repeat("item-{}", 10))
        parsed = json.loads(result)
        assert len(parsed["data"]) == 1000
        assert parsed["data"][0]["id"] == 0
        assert parsed["data"][42]["value"] == "item-42" * 10

    def test_deep_json_pattern(self):
        """Match the /deep-json benchmark endpoint pattern."""
        result = gen.wrap(
            "users",
            20,
            id=F.index,
            name=F.fmt("User {}"),
            email=F.fmt("user{}@example.com"),
            posts=F.nested(
                5,
                id=F.index,
                title=F.fmt("Post {}"),
                likes=F.mul(10),
            ),
        )
        parsed = json.loads(result)
        assert len(parsed["users"]) == 20
        user = parsed["users"][5]
        assert user["name"] == "User 5"
        assert user["email"] == "user5@example.com"
        assert len(user["posts"]) == 5
        assert user["posts"][3] == {"id": 3, "title": "Post 3", "likes": 30}


class TestCompiledGen:
    """CompiledGen — pre-compiled schema for maximum performance."""

    def test_basic_compiled(self):
        cg = CompiledGen(3, {"id": GenField.index()})
        result = cg.generate()
        parsed = json.loads(result)
        assert parsed == [{"id": 0}, {"id": 1}, {"id": 2}]

    def test_compiled_with_wrapper(self):
        cg = CompiledGen(3, {"id": GenField.index()}, "data")
        result = cg.generate()
        parsed = json.loads(result)
        assert parsed == {"data": [{"id": 0}, {"id": 1}, {"id": 2}]}

    def test_compiled_generate_response(self):
        cg = CompiledGen(2, {"id": GenField.index()}, "items")
        resp = cg.generate_response()
        assert resp["status"] == 200
        assert ("content-type", "application/json") in resp["headers"]
        parsed = json.loads(resp["body"])
        assert parsed == {"items": [{"id": 0}, {"id": 1}]}

    def test_compiled_reuse(self):
        """Same CompiledGen produces identical output on every call."""
        cg = CompiledGen(100, {"id": GenField.index(), "name": GenField.fmt("U{}")}, "users")
        r1 = cg.generate()
        r2 = cg.generate()
        assert r1 == r2


class TestGenArray:
    """gen.array() — generate flat JSON arrays of scalars."""

    def test_array_with_index(self):
        result = gen.array(5, F.index)
        assert isinstance(result, JsonBytes)
        parsed = json.loads(result)
        assert parsed == [0, 1, 2, 3, 4]

    def test_array_with_fmt(self):
        result = gen.array(3, F.fmt("item-{}"))
        parsed = json.loads(result)
        assert parsed == ["item-0", "item-1", "item-2"]

    def test_array_with_mul(self):
        result = gen.array(4, F.mul(10))
        parsed = json.loads(result)
        assert parsed == [0, 10, 20, 30]

    def test_array_with_add(self):
        result = gen.array(3, F.add(100))
        parsed = json.loads(result)
        assert parsed == [100, 101, 102]

    def test_array_with_repeat(self):
        result = gen.array(2, F.repeat("x{}", 3))
        parsed = json.loads(result)
        assert parsed == ["x0x0x0", "x1x1x1"]

    def test_empty_array(self):
        result = gen.array(0, F.index)
        parsed = json.loads(result)
        assert parsed == []


class TestGenDict:
    """gen.dict() — generate Python dict mapping key_expr → value_expr."""

    def test_basic_dict(self):
        result = gen.dict(3, F.fmt("key-{}"), F.mul(10))
        assert isinstance(result, dict)
        assert result == {"key-0": 0, "key-1": 10, "key-2": 20}

    def test_dict_index_to_fmt(self):
        result = gen.dict(3, F.index, F.fmt("User {}"))
        assert result == {0: "User 0", 1: "User 1", 2: "User 2"}

    def test_dict_fmt_to_add(self):
        result = gen.dict(3, F.fmt("item-{}"), F.add(100))
        assert result == {"item-0": 100, "item-1": 101, "item-2": 102}

    def test_empty_dict(self):
        result = gen.dict(0, F.index, F.fmt("v{}"))
        assert result == {}

    def test_dict_index_keys(self):
        result = gen.dict(4, F.index, F.mul(5))
        assert result == {0: 0, 1: 5, 2: 10, 3: 15}


class TestGenSet:
    """gen.set() — generate Python set of scalar values."""

    def test_set_with_fmt(self):
        result = gen.set(3, F.fmt("tag-{}"))
        assert isinstance(result, set)
        assert result == {"tag-0", "tag-1", "tag-2"}

    def test_set_with_index(self):
        result = gen.set(4, F.index)
        assert result == {0, 1, 2, 3}

    def test_set_with_mul(self):
        result = gen.set(3, F.mul(10))
        assert result == {0, 10, 20}

    def test_empty_set(self):
        result = gen.set(0, F.fmt("x{}"))
        assert result == set()


class TestGenFrozenset:
    """gen.frozenset() — generate Python frozenset of scalar values."""

    def test_frozenset_with_fmt(self):
        result = gen.frozenset(3, F.fmt("tag-{}"))
        assert isinstance(result, frozenset)
        assert result == frozenset({"tag-0", "tag-1", "tag-2"})

    def test_frozenset_with_index(self):
        result = gen.frozenset(4, F.index)
        assert result == frozenset({0, 1, 2, 3})

    def test_frozenset_is_immutable(self):
        result = gen.frozenset(3, F.index)
        with pytest.raises(AttributeError):
            result.add(99)

    def test_empty_frozenset(self):
        result = gen.frozenset(0, F.index)
        assert result == frozenset()


class TestGenTuple:
    """gen.tuple() — generate Python tuple of scalar values."""

    def test_tuple_with_index(self):
        result = gen.tuple(5, F.index)
        assert isinstance(result, tuple)
        assert result == (0, 1, 2, 3, 4)

    def test_tuple_with_fmt(self):
        result = gen.tuple(3, F.fmt("v{}"))
        assert result == ("v0", "v1", "v2")

    def test_tuple_with_mul(self):
        result = gen.tuple(4, F.mul(3))
        assert result == (0, 3, 6, 9)

    def test_empty_tuple(self):
        result = gen.tuple(0, F.index)
        assert result == ()

    def test_tuple_is_immutable(self):
        result = gen.tuple(3, F.index)
        with pytest.raises(TypeError):
            result[0] = 99


class TestGenPylist:
    """gen.pylist() — generate flat Python list of scalar values."""

    def test_pylist_with_fmt(self):
        result = gen.pylist(4, F.fmt("item-{}"))
        assert isinstance(result, list)
        assert result == ["item-0", "item-1", "item-2", "item-3"]

    def test_pylist_with_index(self):
        result = gen.pylist(5, F.index)
        assert result == [0, 1, 2, 3, 4]

    def test_pylist_with_mul(self):
        result = gen.pylist(3, F.mul(7))
        assert result == [0, 7, 14]

    def test_pylist_with_add(self):
        result = gen.pylist(3, F.add(50))
        assert result == [50, 51, 52]

    def test_pylist_with_repeat(self):
        result = gen.pylist(2, F.repeat("ab{}", 2))
        assert result == ["ab0ab0", "ab1ab1"]

    def test_empty_pylist(self):
        result = gen.pylist(0, F.index)
        assert result == []

    def test_pylist_is_mutable(self):
        result = gen.pylist(3, F.index)
        result.append(99)
        assert result == [0, 1, 2, 99]


class TestFieldExprSub:
    """F.sub() — subtract constant from index."""

    def test_sub_in_list(self):
        result = gen.list(4, val=F.sub(1))
        parsed = json.loads(result)
        assert [item["val"] for item in parsed] == [-1, 0, 1, 2]

    def test_sub_in_array(self):
        result = gen.array(3, F.sub(5))
        assert json.loads(result) == [-5, -4, -3]

    def test_sub_in_pylist(self):
        result = gen.pylist(3, F.sub(10))
        assert result == [-10, -9, -8]


class TestFieldExprMod:
    """F.mod_() — modulo index by constant."""

    def test_mod_in_list(self):
        result = gen.list(6, val=F.mod_(3))
        parsed = json.loads(result)
        assert [item["val"] for item in parsed] == [0, 1, 2, 0, 1, 2]

    def test_mod_in_array(self):
        result = gen.array(5, F.mod_(2))
        assert json.loads(result) == [0, 1, 0, 1, 0]

    def test_mod_in_set(self):
        result = gen.set(6, F.mod_(3))
        assert result == {0, 1, 2}


class TestFieldExprRange:
    """F.range() — arithmetic sequence."""

    def test_range_in_list(self):
        result = gen.list(4, val=F.range(10, 5))
        parsed = json.loads(result)
        assert [item["val"] for item in parsed] == [10, 15, 20, 25]

    def test_range_in_array(self):
        result = gen.array(5, F.range(100, -10))
        assert json.loads(result) == [100, 90, 80, 70, 60]

    def test_range_in_tuple(self):
        result = gen.tuple(3, F.range(0, 100))
        assert result == (0, 100, 200)


class TestFieldExprCycle:
    """F.cycle() — round-robin from a list of strings."""

    def test_cycle_in_list(self):
        result = gen.list(5, status=F.cycle(["active", "inactive"]))
        parsed = json.loads(result)
        statuses = [item["status"] for item in parsed]
        assert statuses == ["active", "inactive", "active", "inactive", "active"]

    def test_cycle_in_array(self):
        result = gen.array(6, F.cycle(["red", "green", "blue"]))
        parsed = json.loads(result)
        assert parsed == ["red", "green", "blue", "red", "green", "blue"]

    def test_cycle_in_set(self):
        result = gen.set(6, F.cycle(["a", "b", "c"]))
        assert result == {"a", "b", "c"}

    def test_cycle_in_pylist(self):
        result = gen.pylist(4, F.cycle(["x", "y"]))
        assert result == ["x", "y", "x", "y"]

    def test_cycle_three_values(self):
        result = gen.list(7, role=F.cycle(["admin", "user", "viewer"]))
        parsed = json.loads(result)
        roles = [item["role"] for item in parsed]
        assert roles == ["admin", "user", "viewer", "admin", "user", "viewer", "admin"]


class TestFieldExprNull:
    """F.null — constant null/None."""

    def test_null_in_list(self):
        result = gen.list(2, id=F.index, deleted_at=F.null)
        parsed = json.loads(result)
        assert parsed[0] == {"id": 0, "deleted_at": None}
        assert parsed[1] == {"id": 1, "deleted_at": None}

    def test_null_in_array(self):
        result = gen.array(3, F.null)
        assert json.loads(result) == [None, None, None]


class TestGenCsv:
    """gen.csv() — generate CSV bytes entirely in Rust."""

    def test_basic_csv(self):
        result = gen.csv(3, id=F.index, name=F.fmt("User {}"))
        assert isinstance(result, bytes)
        lines = result.decode().strip().split("\n")
        assert lines[0] == "id,name"
        assert lines[1] == "0,User 0"
        assert lines[2] == "1,User 1"
        assert lines[3] == "2,User 2"

    def test_csv_with_mul(self):
        result = gen.csv(3, id=F.index, score=F.mul(10))
        lines = result.decode().strip().split("\n")
        assert lines[0] == "id,score"
        assert lines[3] == "2,20"

    def test_csv_quoting(self):
        """Strings with commas should be quoted in CSV."""
        result = gen.csv(2, val="hello, world")
        lines = result.decode().strip().split("\n")
        assert lines[0] == "val"
        assert lines[1] == '"hello, world"'

    def test_csv_empty(self):
        result = gen.csv(0, id=F.index)
        lines = result.decode().strip().split("\n")
        assert lines[0] == "id"
        assert len(lines) == 1

    def test_csv_with_cycle(self):
        result = gen.csv(4, id=F.index, status=F.cycle(["on", "off"]))
        lines = result.decode().strip().split("\n")
        assert lines[1] == "0,on"
        assert lines[2] == "1,off"
        assert lines[3] == "2,on"
        assert lines[4] == "3,off"

    def test_csv_large(self):
        result = gen.csv(1000, id=F.index, name=F.fmt("User {}"), score=F.mul(5))
        lines = result.decode().strip().split("\n")
        assert len(lines) == 1001  # header + 1000 rows
        assert lines[0] == "id,name,score"
        assert lines[500] == "499,User 499,2495"


class TestGenNdjson:
    """gen.ndjson() — generate NDJSON bytes entirely in Rust."""

    def test_basic_ndjson(self):
        result = gen.ndjson(3, id=F.index, name=F.fmt("User {}"))
        assert isinstance(result, bytes)
        lines = result.decode().strip().split("\n")
        assert len(lines) == 3
        assert json.loads(lines[0]) == {"id": 0, "name": "User 0"}
        assert json.loads(lines[1]) == {"id": 1, "name": "User 1"}
        assert json.loads(lines[2]) == {"id": 2, "name": "User 2"}

    def test_ndjson_empty(self):
        result = gen.ndjson(0, id=F.index)
        assert result == b""

    def test_ndjson_with_nested(self):
        result = gen.ndjson(
            2,
            id=F.index,
            posts=F.nested(2, id=F.index, title=F.fmt("Post {}")),
        )
        lines = result.decode().strip().split("\n")
        assert len(lines) == 2
        obj = json.loads(lines[1])
        assert obj["id"] == 1
        assert obj["posts"] == [
            {"id": 0, "title": "Post 0"},
            {"id": 1, "title": "Post 1"},
        ]

    def test_ndjson_large(self):
        result = gen.ndjson(1000, id=F.index, val=F.mul(3))
        lines = result.decode().strip().split("\n")
        assert len(lines) == 1000
        assert json.loads(lines[999]) == {"id": 999, "val": 2997}

    def test_ndjson_with_cycle(self):
        result = gen.ndjson(4, id=F.index, level=F.cycle(["info", "warn", "error"]))
        lines = result.decode().strip().split("\n")
        assert json.loads(lines[0])["level"] == "info"
        assert json.loads(lines[1])["level"] == "warn"
        assert json.loads(lines[2])["level"] == "error"
        assert json.loads(lines[3])["level"] == "info"


class TestFieldExprCombined:
    """Test new field expressions combined in realistic patterns."""

    def test_realistic_user_list(self):
        """Simulate a realistic user list with status cycling."""
        result = gen.list(
            6,
            id=F.range(1000, 1),  # IDs starting at 1000
            name=F.fmt("User {}"),
            group=F.mod_(3),  # 3 groups: 0, 1, 2
            status=F.cycle(["active", "suspended"]),
        )
        parsed = json.loads(result)
        assert parsed[0] == {"id": 1000, "name": "User 0", "group": 0, "status": "active"}
        assert parsed[3] == {"id": 1003, "name": "User 3", "group": 0, "status": "suspended"}
        assert parsed[5] == {"id": 1005, "name": "User 5", "group": 2, "status": "suspended"}

    def test_csv_endpoint_pattern(self):
        """CSV response for data export endpoint."""
        result = gen.csv(
            5,
            id=F.range(1, 1),
            email=F.fmt("user{}@example.com"),
            role=F.cycle(["admin", "user", "viewer"]),
            score=F.mul(25),
        )
        lines = result.decode().strip().split("\n")
        assert lines[0] == "id,email,role,score"
        assert lines[1] == "1,user0@example.com,admin,0"
        assert lines[4] == "4,user3@example.com,admin,75"

    def test_ndjson_log_pattern(self):
        """NDJSON log-style output."""
        result = gen.ndjson(
            4,
            ts=F.range(1700000000, 1),
            level=F.cycle(["INFO", "WARN", "ERROR"]),
            msg=F.fmt("Event {}"),
        )
        lines = result.decode().strip().split("\n")
        first = json.loads(lines[0])
        assert first["ts"] == 1700000000
        assert first["level"] == "INFO"
        assert first["msg"] == "Event 0"


class TestJsonBytesIntegration:
    """JsonBytes type is recognized by the Rivex response pipeline."""

    def test_jsonbytes_is_bytes(self):
        jb = JsonBytes(b'{"test": true}')
        assert isinstance(jb, bytes)
        assert isinstance(jb, JsonBytes)

    def test_handler_returns_jsonbytes(self):
        """Framework should recognise JsonBytes and set JSON content-type."""
        from rivex import Rivex
        from rivex.testing.testing import TestClient

        app = Rivex()

        @app.get("/gen-test")
        async def gen_endpoint():
            return gen.wrap("items", 3, id=F.index, val=F.fmt("v{}"))

        client = TestClient(app)
        resp = client.get("/gen-test")
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/json"
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["items"][1] == {"id": 1, "val": "v1"}
