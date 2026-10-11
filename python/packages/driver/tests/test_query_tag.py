"""`query_tag`: the `X-ArcadeDB-Query-Tag` request header, sync and async.

Sent by `query`, `command`, `query_stream`, `command_stream`, `transaction()` (on the begin request
only - statements inside inherit the label server-side) and `batch_load` / `batch_load_stream` (as a
header, never a query parameter). Omitted entirely when the tag is `None` or empty.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import (
    ArcadeDBDatabase,
    ArcadeDBServer,
    AsyncArcadeDBDatabase,
    AsyncArcadeDBServer,
)

BASE_URL = "http://db.test"
HEADER = "X-ArcadeDB-Query-Tag"
SESSION = "AS-0000-1111"
ROWS: dict[str, Any] = {"vertices": [{"type": "Person", "id": "a", "properties": {"name": "Ann"}}]}
ENVELOPE = {"result": [], "limit": 20000, "returned": 0, "truncated": False}
STATS = (json.dumps({"stats": {"limit": 20000, "returned": 0, "truncated": False}}) + "\n").encode()
SUMMARY = (json.dumps({"summary": {"verticesCreated": 1}}) + "\n").encode()


SyncCall = Callable[[ArcadeDBDatabase, "str | None"], object]
AsyncCall = Callable[[AsyncArcadeDBDatabase, "str | None"], Awaitable[object]]

# (name, path, response factory, call) - a factory, because a streamed body is consumed once.
SYNC_CALLS: list[tuple[str, str, Callable[[], httpx.Response], SyncCall]] = [
    (
        "query",
        "/api/v1/query/mydb",
        lambda: httpx.Response(200, json=ENVELOPE),
        lambda db, tag: db.query(language="sql", command="SELECT 1", query_tag=tag),
    ),
    (
        "command",
        "/api/v1/command/mydb",
        lambda: httpx.Response(200, json=ENVELOPE),
        lambda db, tag: db.command(language="sql", command="SELECT 1", query_tag=tag),
    ),
    (
        "query_stream",
        "/api/v1/query/mydb",
        lambda: httpx.Response(200, content=STATS),
        lambda db, tag: list(db.query_stream(language="sql", command="SELECT 1", query_tag=tag)),
    ),
    (
        "command_stream",
        "/api/v1/command/mydb",
        lambda: httpx.Response(200, content=STATS),
        lambda db, tag: list(db.command_stream(language="sql", command="SELECT 1", query_tag=tag)),
    ),
    (
        "batch_load",
        "/api/v1/batch/mydb",
        lambda: httpx.Response(200, json={"verticesCreated": 1}),
        lambda db, tag: db.batch_load(**ROWS, query_tag=tag),
    ),
    (
        "batch_load_stream",
        "/api/v1/batch/mydb",
        lambda: httpx.Response(200, content=SUMMARY),
        lambda db, tag: list(db.batch_load_stream(**ROWS, query_tag=tag)),
    ),
]


@pytest.mark.parametrize(("name", "path", "response", "call"), SYNC_CALLS, ids=[c[0] for c in SYNC_CALLS])
@respx.mock
def test_sync_query_tag_is_sent_as_a_header(
    name: str, path: str, response: Callable[[], httpx.Response], call: SyncCall
) -> None:
    route = respx.post(f"{BASE_URL}{path}").mock(return_value=response())
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        call(srv.db("mydb"), "nightly-report")
    request = route.calls.last.request
    assert request.headers[HEADER] == "nightly-report"
    assert "nightly-report" not in str(request.url)


@pytest.mark.parametrize("tag", [None, ""])
@pytest.mark.parametrize(("name", "path", "response", "call"), SYNC_CALLS, ids=[c[0] for c in SYNC_CALLS])
@respx.mock
def test_sync_no_header_without_a_tag(
    name: str, path: str, response: Callable[[], httpx.Response], call: SyncCall, tag: str | None
) -> None:
    route = respx.post(f"{BASE_URL}{path}").mock(return_value=response())
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        call(srv.db("mydb"), tag)
    assert HEADER not in route.calls.last.request.headers


def _mock_transaction() -> tuple[respx.Route, respx.Route, respx.Route]:
    begin = respx.post(f"{BASE_URL}/api/v1/begin/mydb").mock(
        return_value=httpx.Response(204, headers={"arcadedb-session-id": SESSION})
    )
    command = respx.post(f"{BASE_URL}/api/v1/command/mydb").mock(return_value=httpx.Response(200, json=ENVELOPE))
    commit = respx.post(f"{BASE_URL}/api/v1/commit/mydb").mock(return_value=httpx.Response(204))
    return begin, command, commit


@respx.mock
def test_transaction_query_tag_is_sent_on_begin_only() -> None:
    begin, command, commit = _mock_transaction()
    with ArcadeDBServer(base_url=BASE_URL) as srv, srv.db("mydb").transaction(query_tag="etl") as tx:
        tx.command(language="sql", command="INSERT INTO P SET n = 1")

    assert begin.calls.last.request.headers[HEADER] == "etl"
    assert HEADER not in command.calls.last.request.headers
    assert HEADER not in commit.calls.last.request.headers


@respx.mock
def test_a_per_call_tag_inside_a_transaction_sends_its_own_header() -> None:
    begin, command, _ = _mock_transaction()
    with ArcadeDBServer(base_url=BASE_URL) as srv, srv.db("mydb").transaction(query_tag="etl") as tx:
        tx.command(language="sql", command="INSERT INTO P SET n = 1", query_tag="step-2")

    assert begin.calls.last.request.headers[HEADER] == "etl"
    assert command.calls.last.request.headers[HEADER] == "step-2"


@respx.mock
def test_transaction_without_a_tag_sends_no_header_on_begin() -> None:
    begin, _, _ = _mock_transaction()
    with ArcadeDBServer(base_url=BASE_URL) as srv, srv.db("mydb").transaction() as tx:
        tx.command(language="sql", command="INSERT INTO P SET n = 1")
    assert HEADER not in begin.calls.last.request.headers


# --- async ------------------------------------------------------------------------------------


async def _drain_query_stream(db: AsyncArcadeDBDatabase, tag: str | None) -> None:
    async for _ in db.query_stream(language="sql", command="SELECT 1", query_tag=tag):
        pass


async def _drain_command_stream(db: AsyncArcadeDBDatabase, tag: str | None) -> None:
    async for _ in db.command_stream(language="sql", command="SELECT 1", query_tag=tag):
        pass


async def _drain_batch_stream(db: AsyncArcadeDBDatabase, tag: str | None) -> None:
    async for _ in db.batch_load_stream(**ROWS, query_tag=tag):
        pass


ASYNC_CALLS: list[tuple[str, str, Callable[[], httpx.Response], AsyncCall]] = [
    (
        "query",
        "/api/v1/query/mydb",
        lambda: httpx.Response(200, json=ENVELOPE),
        lambda db, tag: db.query(language="sql", command="SELECT 1", query_tag=tag),
    ),
    (
        "command",
        "/api/v1/command/mydb",
        lambda: httpx.Response(200, json=ENVELOPE),
        lambda db, tag: db.command(language="sql", command="SELECT 1", query_tag=tag),
    ),
    ("query_stream", "/api/v1/query/mydb", lambda: httpx.Response(200, content=STATS), _drain_query_stream),
    ("command_stream", "/api/v1/command/mydb", lambda: httpx.Response(200, content=STATS), _drain_command_stream),
    (
        "batch_load",
        "/api/v1/batch/mydb",
        lambda: httpx.Response(200, json={"verticesCreated": 1}),
        lambda db, tag: db.batch_load(**ROWS, query_tag=tag),
    ),
    ("batch_load_stream", "/api/v1/batch/mydb", lambda: httpx.Response(200, content=SUMMARY), _drain_batch_stream),
]


@pytest.mark.parametrize(("name", "path", "response", "call"), ASYNC_CALLS, ids=[c[0] for c in ASYNC_CALLS])
@respx.mock
@pytest.mark.asyncio
async def test_async_query_tag_is_sent_as_a_header(
    name: str, path: str, response: Callable[[], httpx.Response], call: AsyncCall
) -> None:
    route = respx.post(f"{BASE_URL}{path}").mock(return_value=response())
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        await call(srv.db("mydb"), "nightly-report")
    request = route.calls.last.request
    assert request.headers[HEADER] == "nightly-report"
    assert "nightly-report" not in str(request.url)


@pytest.mark.parametrize("tag", [None, ""])
@pytest.mark.parametrize(("name", "path", "response", "call"), ASYNC_CALLS, ids=[c[0] for c in ASYNC_CALLS])
@respx.mock
@pytest.mark.asyncio
async def test_async_no_header_without_a_tag(
    name: str, path: str, response: Callable[[], httpx.Response], call: AsyncCall, tag: str | None
) -> None:
    route = respx.post(f"{BASE_URL}{path}").mock(return_value=response())
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        await call(srv.db("mydb"), tag)
    assert HEADER not in route.calls.last.request.headers


@respx.mock
@pytest.mark.asyncio
async def test_async_transaction_query_tag_is_sent_on_begin_only() -> None:
    begin, command, commit = _mock_transaction()
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv, srv.db("mydb").transaction(query_tag="etl") as tx:
        await tx.command(language="sql", command="INSERT INTO P SET n = 1")

    assert begin.calls.last.request.headers[HEADER] == "etl"
    assert HEADER not in command.calls.last.request.headers
    assert HEADER not in commit.calls.last.request.headers


@respx.mock
@pytest.mark.asyncio
async def test_async_a_per_call_tag_inside_a_transaction_sends_its_own_header() -> None:
    begin, command, _ = _mock_transaction()
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv, srv.db("mydb").transaction(query_tag="etl") as tx:
        await tx.command(language="sql", command="INSERT INTO P SET n = 1", query_tag="step-2")

    assert begin.calls.last.request.headers[HEADER] == "etl"
    assert command.calls.last.request.headers[HEADER] == "step-2"
