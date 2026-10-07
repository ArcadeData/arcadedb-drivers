"""`query` and `command` skip the generated request and response models when the answer is the common one.

That is only safe if it changes nothing a caller or the server can see. These tests run each call twice, once
through the public facade (the hot path) and once the way the facade used to do it (the generated
`sync_detailed`, `unwrap`, `to_envelope`), against the same mocked transport. They compare what was SENT
(method, URL, header set, body bytes) and what came BACK (the envelope, or the exception and its fields).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from arcadedb_driver import (
    ArcadeDBDatabase,
    ArcadeDBError,
    ArcadeDBServer,
    AsyncArcadeDBServer,
    QueryEnvelope,
    basic_auth,
)
from arcadedb_driver._generated.api.command import execute_command
from arcadedb_driver._generated.api.query import execute_query_post
from arcadedb_driver._generated.client import Client
from arcadedb_driver._generated.models.query_response import QueryResponse
from arcadedb_driver._internal.unwrap import unwrap
from arcadedb_driver.facade.data import (
    build_command_request,
    build_query_request,
    session_kwarg,
    to_envelope,
)

BASE_URL = "http://db.test"
OK = {"result": [{"a": 1, "@rid": "#1:0"}, {"a": 2, "@rid": "#1:1"}], "limit": 20000, "returned": 2, "truncated": False}

Seen = list[tuple[str, str, list[tuple[str, str]], bytes]]


def snapshot(request: httpx.Request) -> tuple[str, str, list[tuple[str, str]], bytes]:
    """The request as the wire carries it: header names and values in order, so a reordering is a failure too."""
    headers = [(k.decode(), v.decode()) for k, v in request.headers.raw]
    return request.method, str(request.url), headers, request.read()


def handler_for(seen: Seen, response: Callable[[], httpx.Response]) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(snapshot(request))
        return response()

    return handle


def outcome(call: Callable[..., QueryEnvelope], *args: Any, **kw: Any) -> tuple[Any, ...]:
    """What a caller can observe: the envelope, or the exception type with every field it carries."""
    try:
        env = call(*args, **kw)
    except ArcadeDBError as err:
        return ("ArcadeDBError", err.status, err.error, err.detail, err.request_id, err.help_, str(err))
    except AssertionError:
        return (
            "AssertionError",
        )  # the facade's own `assert`; pytest rewrites the oracle's message, so only the type is comparable
    except Exception as err:  # the point is to compare whatever escaped
        return (type(err).__name__, str(err))
    return ("ok", env)


async def async_outcome(call: Callable[..., Awaitable[QueryEnvelope]], **kw: Any) -> tuple[Any, ...]:
    try:
        env = await call(**kw)
    except ArcadeDBError as err:
        return ("ArcadeDBError", err.status, err.error, err.detail, err.request_id, err.help_, str(err))
    except AssertionError:
        return ("AssertionError",)
    except Exception as err:  # the point is to compare whatever escaped
        return (type(err).__name__, str(err))
    return ("ok", env)


def legacy_query(client: Client, name: str, session_id: str | None, **kw: Any) -> QueryEnvelope:
    response = execute_query_post.sync_detailed(
        name,
        client=client,
        body=build_query_request(**kw),
        arcadedb_session_id=session_kwarg(session_id),
    )
    data = unwrap(response)
    assert isinstance(data, QueryResponse)
    return to_envelope(data)


def legacy_command(client: Client, name: str, session_id: str | None, **kw: Any) -> QueryEnvelope:
    response = execute_command.sync_detailed(
        name,
        client=client,
        body=build_command_request(**kw),
        arcadedb_session_id=session_kwarg(session_id),
    )
    data = unwrap(response)
    assert isinstance(data, QueryResponse)
    return to_envelope(data)


def server(handler: Callable[[httpx.Request], httpx.Response], base_url: str = BASE_URL) -> ArcadeDBServer:
    srv = ArcadeDBServer(base_url=base_url, auth=basic_auth("root", "pw"), headers={"X-Extra": "1"})
    srv.raw.set_httpx_client(
        httpx.Client(
            base_url=base_url,
            headers={"Authorization": basic_auth("root", "pw")["Authorization"], "X-Extra": "1"},
            transport=httpx.MockTransport(handler),
        )
    )
    return srv


CALLS: list[dict[str, Any]] = [
    {"language": "sql", "command": "SELECT 1"},
    {"language": "sql", "command": "SELECT FROM P WHERE a = :a", "params": {"a": 1}},
    {"language": "cypher", "command": "MATCH (n) RETURN n", "limit": -1},
    {
        "language": "sql",
        "command": "x",
        "params": {"s": "café ☃", "f": 1.5, "n": None, "l": [1, 2], "d": {"k": "v"}},
        "limit": 5,
    },
    {"language": "sql", "command": "x", "params": {}},
]

# every response shape the generated parse has an opinion about: it must produce the same outcome through the hot path
RESPONSES: dict[str, Callable[[], httpx.Response]] = {
    "ok": lambda: httpx.Response(200, json=OK),
    "ok_empty": lambda: httpx.Response(200, json={"result": [], "limit": 1, "returned": 0, "truncated": True}),
    "ok_extra_keys": lambda: httpx.Response(200, json={**OK, "future": {"x": 1}}),
    "ok_no_result": lambda: httpx.Response(200, json={"limit": 1, "returned": 0, "truncated": False}),
    "explain": lambda: httpx.Response(200, json={**OK, "result": [], "explain": "plan", "explainPlan": {"steps": []}}),
    "explain_text_only": lambda: httpx.Response(200, json={**OK, "explain": "plan"}),
    "graph_result": lambda: httpx.Response(200, json={**OK, "result": {"vertices": [], "edges": []}}),
    "missing_limit": lambda: httpx.Response(200, json={"result": [], "returned": 0, "truncated": False}),
    "empty_object": lambda: httpx.Response(200, json={}),
    "not_an_object": lambda: httpx.Response(200, json=[1, 2]),
    "rows_not_objects": lambda: httpx.Response(200, json={**OK, "result": [1, 2]}),
    "rows_mixed": lambda: httpx.Response(200, json={**OK, "result": [{"a": 1}, "x"]}),
    "row_pairs": lambda: httpx.Response(200, json={**OK, "result": [[["a", 1]]]}),
    "not_json": lambda: httpx.Response(200, content=b"<html>"),
    "empty_body": lambda: httpx.Response(200, content=b""),
    "no_content_204": lambda: httpx.Response(204),
    "created_201": lambda: httpx.Response(201, json=OK),
    "bad_request": lambda: httpx.Response(
        400, json={"error": "Invalid", "detail": "d"}, headers={"X-Request-Id": "r1"}
    ),
    "unauthorized": lambda: httpx.Response(401, json={"error": "no"}),
    "conflict": lambda: httpx.Response(409, json={"error": "c", "exception": "E", "help": "h"}),
    "too_large": lambda: httpx.Response(413, json={"error": "big"}),
    "server_error": lambda: httpx.Response(500, json={"error": "boom"}),
    "server_error_html": lambda: httpx.Response(500, content=b"<html>oops</html>"),
    "undocumented_418": lambda: httpx.Response(418, json={"error": "teapot"}),
    "non_standard_status": lambda: httpx.Response(599, json={"error": "x"}),
}


@pytest.mark.parametrize("name", list(RESPONSES))
@pytest.mark.parametrize("session_id", [None, "AS-1234"])
def test_sync_query_and_command_match_the_generated_path(name: str, session_id: str | None) -> None:
    seen_new: Seen = []
    seen_old: Seen = []
    new_srv = server(handler_for(seen_new, RESPONSES[name]))
    old_srv = server(handler_for(seen_old, RESPONSES[name]))
    with new_srv, old_srv:
        db = ArcadeDBDatabase(new_srv.raw, "my db", session_id)
        for kw in CALLS:
            old_kw = {"params": None, "limit": None, **kw}
            assert outcome(db.query, **kw) == outcome(legacy_query, old_srv.raw, "my db", session_id, **old_kw)
            ckw = {k: v for k, v in kw.items() if k != "limit"}
            old_ckw = {"params": None, **ckw}
            assert outcome(db.command, **ckw) == outcome(legacy_command, old_srv.raw, "my db", session_id, **old_ckw)
    assert seen_new == seen_old
    assert seen_new, "no request was sent"
    # the session id travels as the header, only inside a transaction
    for _method, _url, headers, _body in seen_new:
        assert (("arcadedb-session-id", "AS-1234") in headers) is (session_id is not None)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(RESPONSES))
async def test_async_query_matches_the_generated_path(name: str) -> None:
    """The async facade answers exactly what the generated path answers, request for request."""
    seen_sync: Seen = []
    seen_async: Seen = []
    sync_srv = server(handler_for(seen_sync, RESPONSES[name]))
    async_srv = AsyncArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "pw"), headers={"X-Extra": "1"})

    async def handle(request: httpx.Request) -> httpx.Response:
        seen_async.append(snapshot(request))
        return RESPONSES[name]()

    async_srv.raw.set_async_httpx_client(
        httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": basic_auth("root", "pw")["Authorization"], "X-Extra": "1"},
            transport=httpx.MockTransport(handle),
        )
    )
    with sync_srv:
        async with async_srv:
            for kw in CALLS:
                want = outcome(legacy_query, sync_srv.raw, "mydb", None, **{"params": None, "limit": None, **kw})
                got = await async_outcome(async_srv.db("mydb").query, **kw)
                assert got == want
                ckw = {k: v for k, v in kw.items() if k != "limit"}
                want = outcome(legacy_command, sync_srv.raw, "mydb", None, **{"params": None, **ckw})
                assert await async_outcome(async_srv.db("mydb").command, **ckw) == want
    assert seen_async == seen_sync
    assert len(seen_async) == 2 * len(CALLS)


def test_the_body_is_byte_identical_to_the_generated_one() -> None:
    seen_new: Seen = []
    seen_old: Seen = []
    new_srv = server(handler_for(seen_new, RESPONSES["ok"]))
    old_srv = server(handler_for(seen_old, RESPONSES["ok"]))
    with new_srv, old_srv:
        new_srv.db("d").query(language="sql", command="SELECT :a", params={"a": "é", "b": [1.0, 2]}, limit=3)
        legacy_query(
            old_srv.raw, "d", None, language="sql", command="SELECT :a", params={"a": "é", "b": [1.0, 2]}, limit=3
        )
    assert seen_new[0][3] == seen_old[0][3]
    assert json.loads(seen_new[0][3]) == {
        "command": "SELECT :a",
        "language": "sql",
        "limit": 3,
        "params": {"a": "é", "b": [1.0, 2]},
    }
    assert list(json.loads(seen_new[0][3])) == ["command", "language", "limit", "params"]


def test_rows_are_the_callers_own_and_the_params_are_not_aliased() -> None:
    seen: Seen = []
    srv = server(handler_for(seen, RESPONSES["ok"]))
    params: dict[str, Any] = {"a": 1}
    with srv:
        first = srv.db("d").query(language="sql", command="x", params=params)
        second = srv.db("d").query(language="sql", command="x", params=params)
    first.result[0]["a"] = 99
    assert second.result[0]["a"] == 1
    assert params == {"a": 1}


def test_the_resolved_url_follows_a_base_url_prefix_and_a_swapped_client() -> None:
    seen: Seen = []
    srv = server(handler_for(seen, RESPONSES["ok"]), base_url="http://h.test/prefix")
    with srv:
        db = srv.db("a/b")
        db.query(language="sql", command="x")
        db.command(language="sql", command="x")
        srv.raw.set_httpx_client(
            httpx.Client(
                base_url="http://other.test:2480", transport=httpx.MockTransport(handler_for(seen, RESPONSES["ok"]))
            )
        )
        db.query(language="sql", command="x")
    assert [url for _m, url, _h, _b in seen] == [
        "http://h.test/prefix/api/v1/query/a%2Fb",
        "http://h.test/prefix/api/v1/command/a%2Fb",
        "http://other.test:2480/api/v1/query/a%2Fb",
    ]


def test_a_renamed_database_is_honoured() -> None:
    seen: Seen = []
    srv = server(handler_for(seen, RESPONSES["ok"]))
    with srv:
        db = srv.db("first")
        db.query(language="sql", command="x")
        db.name = "second"
        db.command(language="sql", command="x")
    assert [url for _m, url, _h, _b in seen] == [f"{BASE_URL}/api/v1/query/first", f"{BASE_URL}/api/v1/command/second"]


def test_client_headers_added_after_construction_still_travel() -> None:
    seen: Seen = []
    srv = server(handler_for(seen, RESPONSES["ok"]))
    with srv:
        db = srv.db("d")
        db.query(language="sql", command="x")
        srv.raw.with_headers({"X-Trace": "t1"})
        db.query(language="sql", command="x")
    assert ("X-Trace", "t1") not in seen[0][2]
    assert ("X-Trace", "t1") in seen[1][2]
    assert ("X-Extra", "1") in seen[1][2]
    assert any(k == "Authorization" for k, _v in seen[1][2])
