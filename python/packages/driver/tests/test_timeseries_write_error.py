"""`TimeSeriesWriteError`: what `db.ts.write` raises when the server answers 400 with a JSON object.

A subclass of `ArcadeDBError`, so `except ArcadeDBError` still catches it, carrying the contract's
`TimeSeriesWriteError` body: `written`, `dropped` and the four reason lists. Every other failure
stays a plain `ArcadeDBError`.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer, TimeSeriesWriteError

BASE_URL = "http://db.test"
WRITE_URL = f"{BASE_URL}/api/v1/ts/mydb/write"

FULL_BODY: dict[str, Any] = {
    "written": 3,
    "dropped": 2,
    "error": "2 samples dropped",
    "requestId": "body-id",
    "unknownTypes": ["nosuch"],
    "nonTimeSeriesTypes": ["Person"],
    "unavailableTypes": ["busy"],
    "undeclaredKeys": ["cpu.extra", 7, "cpu.other"],
}
HEADERS = {"Retry-After": "2", "X-ArcadeDB-Commit-Index": "88", "X-Request-Id": "header-id"}


def _assert_full(err: TimeSeriesWriteError) -> None:
    assert isinstance(err, ArcadeDBError)
    assert err.status == 400
    assert err.error == "2 samples dropped"
    assert err.request_id == "header-id"
    assert err.retry_after == 2
    assert err.commit_index == 88
    assert err.written == 3
    assert err.dropped == 2
    assert err.unknown_types == ["nosuch"]
    assert err.non_time_series_types == ["Person"]
    assert err.unavailable_types == ["busy"]
    # A non-string element is dropped rather than coerced.
    assert err.undeclared_keys == ["cpu.extra", "cpu.other"]


def test_the_constructor_defaults_every_extra_field() -> None:
    err = TimeSeriesWriteError(400, {"error": "bad"})
    assert err.written is None
    assert err.dropped is None
    assert err.unknown_types == []
    assert err.non_time_series_types == []
    assert err.unavailable_types == []
    assert err.undeclared_keys == []


@pytest.mark.parametrize("value", ["3", 3.5, True, None, -1])
def test_a_non_integer_written_count_is_none(value: object) -> None:
    err = TimeSeriesWriteError(400, {"written": value, "dropped": value})
    assert err.written is None
    assert err.dropped is None


@pytest.mark.parametrize("value", ["nosuch", 3, {"a": 1}, None])
def test_a_reason_list_that_is_not_a_list_is_empty(value: object) -> None:
    assert TimeSeriesWriteError(400, {"unknownTypes": value}).unknown_types == []


# --- sync -------------------------------------------------------------------------------------


@respx.mock
def test_write_raises_time_series_write_error_on_a_400() -> None:
    respx.post(WRITE_URL).mock(return_value=httpx.Response(400, json=FULL_BODY, headers=HEADERS))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(TimeSeriesWriteError) as caught:
        srv.db("mydb").ts.write(line_protocol="nosuch value=1 1")
    _assert_full(caught.value)


@respx.mock
def test_write_falls_back_to_the_body_request_id_without_the_header() -> None:
    respx.post(WRITE_URL).mock(return_value=httpx.Response(400, json=FULL_BODY))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(TimeSeriesWriteError) as caught:
        srv.db("mydb").ts.write(line_protocol="nosuch value=1 1")
    assert caught.value.request_id == "body-id"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json=FULL_BODY),
        httpx.Response(403, json={"error": "forbidden"}),
        httpx.Response(400, content=b"not json"),
        httpx.Response(400, json=["not", "an", "object"]),
    ],
    ids=["500 with the same body", "403", "400 non-JSON", "400 JSON array"],
)
@respx.mock
def test_write_raises_a_plain_arcadedb_error_otherwise(response: httpx.Response) -> None:
    respx.post(WRITE_URL).mock(return_value=response)
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        srv.db("mydb").ts.write(line_protocol="cpu value=1 1")
    assert type(caught.value) is ArcadeDBError
    assert caught.value.status == response.status_code


# --- async ------------------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_async_write_raises_time_series_write_error_on_a_400() -> None:
    respx.post(WRITE_URL).mock(return_value=httpx.Response(400, json=FULL_BODY, headers=HEADERS))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(TimeSeriesWriteError) as caught:
            await srv.db("mydb").ts.write(line_protocol="nosuch value=1 1")
    _assert_full(caught.value)


@respx.mock
@pytest.mark.asyncio
async def test_async_write_raises_a_plain_arcadedb_error_on_a_non_400() -> None:
    respx.post(WRITE_URL).mock(return_value=httpx.Response(503, json={"error": "busy"}))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            await srv.db("mydb").ts.write(line_protocol="cpu value=1 1")
    assert type(caught.value) is ArcadeDBError
    assert caught.value.status == 503
