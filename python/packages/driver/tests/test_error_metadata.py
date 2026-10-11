"""`ArcadeDBError.retry_after` / `commit_index` from the `Retry-After` and `X-ArcadeDB-Commit-Index`
response headers, on every entry point that builds an error from a non-2xx response - buffered and
streaming, sync and async.

The streaming entry points only take part here through their non-2xx branch (the failure arrives
before the 200 status line). Their in-band errors are covered in `test_in_band_errors.py`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import (
    ArcadeDBDatabase,
    ArcadeDBError,
    ArcadeDBServer,
    AsyncArcadeDBDatabase,
    AsyncArcadeDBServer,
)
from arcadedb_driver._generated.types import Response
from arcadedb_driver.errors import parse_header_int

BASE_URL = "http://db.test"

REFUSAL_HEADERS = {"Retry-After": "3", "X-ArcadeDB-Commit-Index": "42", "X-Request-Id": "req-7"}
ROWS: dict[str, Any] = {"vertices": [{"type": "Person", "id": "a", "properties": {"name": "Ann"}}]}


def _refusal() -> httpx.Response:
    return httpx.Response(503, json={"error": "not ready"}, headers=REFUSAL_HEADERS)


def _assert_refusal(err: ArcadeDBError) -> None:
    assert err.status == 503
    assert err.error == "not ready"
    assert err.request_id == "req-7"
    assert err.retry_after == 3
    assert err.commit_index == 42


# --- parsing ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5", 5),
        (" 7 ", 7),
        ("0", 0),
        ("120", 120),
        (None, None),
        ("", None),
        ("   ", None),
        ("-1", None),
        ("+5", None),
        ("1.5", None),
        ("abc", None),
        ("Wed, 21 Oct 2026 07:28:00 GMT", None),
        ("٣", None),  # ARABIC-INDIC DIGIT THREE: str.isdigit() says yes, base-10 ASCII says no
    ],
)
def test_parse_header_int_accepts_only_non_negative_base_10_integers(raw: str | None, expected: int | None) -> None:
    assert parse_header_int(raw) == expected


def test_the_constructor_carries_retry_after_and_commit_index() -> None:
    err = ArcadeDBError(503, {"error": "busy"}, retry_after=2, commit_index=9)
    assert err.retry_after == 2
    assert err.commit_index == 9


def test_both_fields_default_to_none() -> None:
    err = ArcadeDBError(500)
    assert err.retry_after is None
    assert err.commit_index is None


def test_from_response_reads_both_headers() -> None:
    response: Response[Any] = Response(
        status_code=HTTPStatus(409),
        content=b'{"error":"in flight"}',
        headers=httpx.Headers({"retry-after": " 4 ", "x-arcadedb-commit-index": "17"}),
        parsed=None,
    )
    err = ArcadeDBError.from_response(response)
    assert err.retry_after == 4
    assert err.commit_index == 17


def test_from_response_reads_both_headers_from_a_plain_mapping_in_any_case() -> None:
    response: Response[Any] = Response(
        status_code=HTTPStatus(409),
        content=b"{}",
        headers={"retry-after": "4", "x-arcadedb-commit-index": "17"},
        parsed=None,
    )
    err = ArcadeDBError.from_response(response)
    assert err.retry_after == 4
    assert err.commit_index == 17


def test_from_response_never_raises_on_unparsable_headers() -> None:
    response: Response[Any] = Response(
        status_code=HTTPStatus(503),
        content=b"",
        headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT", "X-ArcadeDB-Commit-Index": "not-a-number"},
        parsed=None,
    )
    err = ArcadeDBError.from_response(response)
    assert err.retry_after is None
    assert err.commit_index is None


# --- every sync entry point ------------------------------------------------------------------

SyncCall = Callable[[ArcadeDBDatabase], object]


def _sync_transaction(db: ArcadeDBDatabase) -> None:
    with db.transaction():
        pass


SYNC_CALLS: list[tuple[str, str, SyncCall]] = [
    ("query", "/api/v1/query/mydb", lambda db: db.query(language="sql", command="SELECT 1")),
    ("command", "/api/v1/command/mydb", lambda db: db.command(language="sql", command="SELECT 1")),
    ("transaction begin", "/api/v1/begin/mydb", _sync_transaction),
    ("batch_load", "/api/v1/batch/mydb", lambda db: db.batch_load(**ROWS)),
    ("ts.write", "/api/v1/ts/mydb/write", lambda db: db.ts.write(line_protocol="cpu value=1 1")),
    ("query_stream", "/api/v1/query/mydb", lambda db: list(db.query_stream(language="sql", command="SELECT 1"))),
    (
        "command_stream",
        "/api/v1/command/mydb",
        lambda db: list(db.command_stream(language="sql", command="SELECT 1")),
    ),
    ("batch_load_stream", "/api/v1/batch/mydb", lambda db: list(db.batch_load_stream(**ROWS))),
]


@pytest.mark.parametrize(("name", "path", "call"), SYNC_CALLS, ids=[c[0] for c in SYNC_CALLS])
@respx.mock
def test_sync_entry_point_error_carries_retry_after_and_commit_index(name: str, path: str, call: SyncCall) -> None:
    respx.post(f"{BASE_URL}{path}").mock(return_value=_refusal())
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        call(srv.db("mydb"))
    _assert_refusal(caught.value)


@respx.mock
def test_sync_error_without_the_headers_leaves_both_fields_none() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(500, json={"error": "boom"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        srv.db("mydb").query(language="sql", command="SELECT 1")
    assert caught.value.retry_after is None
    assert caught.value.commit_index is None


@respx.mock
def test_sync_ts_query_error_carries_retry_after_and_commit_index() -> None:
    respx.post(f"{BASE_URL}/api/v1/ts/mydb/query").mock(return_value=_refusal())
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        srv.db("mydb").ts.query(body={"type": "cpu"})
    _assert_refusal(caught.value)


# --- every async entry point -----------------------------------------------------------------

AsyncCall = Callable[[AsyncArcadeDBDatabase], Awaitable[object]]


async def _async_transaction(db: AsyncArcadeDBDatabase) -> None:
    async with db.transaction():
        pass


async def _async_query_stream(db: AsyncArcadeDBDatabase) -> None:
    async for _ in db.query_stream(language="sql", command="SELECT 1"):
        pass


async def _async_command_stream(db: AsyncArcadeDBDatabase) -> None:
    async for _ in db.command_stream(language="sql", command="SELECT 1"):
        pass


async def _async_batch_load_stream(db: AsyncArcadeDBDatabase) -> None:
    async for _ in db.batch_load_stream(**ROWS):
        pass


ASYNC_CALLS: list[tuple[str, str, AsyncCall]] = [
    ("query", "/api/v1/query/mydb", lambda db: db.query(language="sql", command="SELECT 1")),
    ("command", "/api/v1/command/mydb", lambda db: db.command(language="sql", command="SELECT 1")),
    ("transaction begin", "/api/v1/begin/mydb", _async_transaction),
    ("batch_load", "/api/v1/batch/mydb", lambda db: db.batch_load(**ROWS)),
    ("ts.write", "/api/v1/ts/mydb/write", lambda db: db.ts.write(line_protocol="cpu value=1 1")),
    ("query_stream", "/api/v1/query/mydb", _async_query_stream),
    ("command_stream", "/api/v1/command/mydb", _async_command_stream),
    ("batch_load_stream", "/api/v1/batch/mydb", _async_batch_load_stream),
]


@pytest.mark.parametrize(("name", "path", "call"), ASYNC_CALLS, ids=[c[0] for c in ASYNC_CALLS])
@respx.mock
@pytest.mark.asyncio
async def test_async_entry_point_error_carries_retry_after_and_commit_index(
    name: str, path: str, call: AsyncCall
) -> None:
    respx.post(f"{BASE_URL}{path}").mock(return_value=_refusal())
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            await call(srv.db("mydb"))
    _assert_refusal(caught.value)


@respx.mock
@pytest.mark.asyncio
async def test_async_ts_query_error_carries_retry_after_and_commit_index() -> None:
    respx.post(f"{BASE_URL}/api/v1/ts/mydb/query").mock(return_value=_refusal())
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            await srv.db("mydb").ts.query(body={"type": "cpu"})
    _assert_refusal(caught.value)
