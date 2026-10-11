"""In-band `error` events on the two streaming endpoints, mapped onto `ArcadeDBError` field by field.

- `query_stream` / `command_stream` (`NdJsonQueryEvent.error`): the raised status is the event's
  own `status`, falling back to 200 only when the event carries none; `error` is the classified
  label (falling back to `message`); `exception`, `detail`, `exception_args` and `retry_after` are
  copied across; `request_id` prefers the response's `X-Request-Id` header over the in-band one.
- `batch_load_stream` (`NdJsonBatchEvent.error`): keeps its existing status rule, and now carries
  `retry_after` and `commit_index` too.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer

BASE_URL = "http://db.test"
ROWS: dict[str, Any] = {"vertices": [{"type": "Person", "id": "a", "properties": {"name": "Ann"}}]}

FULL_QUERY_ERROR: dict[str, Any] = {
    "message": "Timeout on locking resource",
    "status": 503,
    "error": "Cannot execute the request yet",
    "exception": "com.arcadedb.exception.NeedRetryException",
    "detail": "lock wait exceeded",
    "exceptionArgs": "a|b",
    "requestId": "in-band-id",
    "retryAfter": 5,
}


def _lines(*events: dict[str, Any]) -> bytes:
    return b"".join((json.dumps(event) + "\n").encode() for event in events)


def _stream_response(error: dict[str, Any], headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(200, content=_lines({"record": {"a": 1}}, {"error": error}), headers=headers)


def _assert_full_mapping(err: ArcadeDBError, *, request_id: str) -> None:
    assert err.status == 503
    assert err.error == "Cannot execute the request yet"
    assert err.exception == "com.arcadedb.exception.NeedRetryException"
    assert err.detail == "lock wait exceeded"
    assert err.exception_args == "a|b"
    assert err.request_id == request_id
    assert err.retry_after == 5
    assert err.commit_index is None


# --- query_stream / command_stream, sync ------------------------------------------------------


@pytest.mark.parametrize("endpoint", ["query", "command"])
@respx.mock
def test_in_band_query_error_maps_every_field(endpoint: str) -> None:
    respx.post(f"{BASE_URL}/api/v1/{endpoint}/mydb").mock(return_value=_stream_response(FULL_QUERY_ERROR))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        db = srv.db("mydb")
        stream = db.query_stream if endpoint == "query" else db.command_stream
        list(stream(language="sql", command="SELECT FROM V"))
    _assert_full_mapping(caught.value, request_id="in-band-id")


@respx.mock
def test_in_band_query_error_prefers_the_response_request_id_header() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=_stream_response(FULL_QUERY_ERROR, headers={"X-Request-Id": "header-id"})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"))
    _assert_full_mapping(caught.value, request_id="header-id")


@respx.mock
def test_in_band_query_error_without_status_falls_back_to_200() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=_stream_response({"message": "boom"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"))
    assert caught.value.status == 200
    assert caught.value.error == "boom"
    assert caught.value.retry_after is None


@respx.mock
def test_in_band_query_error_falls_back_to_message_when_error_is_absent() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=_stream_response({"message": "duplicated key", "status": 409})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"))
    assert caught.value.status == 409
    assert caught.value.error == "duplicated key"


@respx.mock
def test_in_band_query_error_with_neither_error_nor_message_uses_the_default_text() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=_stream_response({"status": 500}))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"))
    assert caught.value.status == 500
    assert caught.value.error == "the stream reported an error"


# --- query_stream / command_stream, async -----------------------------------------------------


@pytest.mark.parametrize("endpoint", ["query", "command"])
@respx.mock
@pytest.mark.asyncio
async def test_async_in_band_query_error_maps_every_field(endpoint: str) -> None:
    respx.post(f"{BASE_URL}/api/v1/{endpoint}/mydb").mock(return_value=_stream_response(FULL_QUERY_ERROR))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        db = srv.db("mydb")
        stream = db.query_stream if endpoint == "query" else db.command_stream
        with pytest.raises(ArcadeDBError) as caught:
            async for _ in stream(language="sql", command="SELECT FROM V"):
                pass
    _assert_full_mapping(caught.value, request_id="in-band-id")


@respx.mock
@pytest.mark.asyncio
async def test_async_in_band_query_error_prefers_the_response_request_id_header() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=_stream_response(FULL_QUERY_ERROR, headers={"X-Request-Id": "header-id"})
    )
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async for _ in srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"):
                pass
    _assert_full_mapping(caught.value, request_id="header-id")


@respx.mock
@pytest.mark.asyncio
async def test_async_in_band_query_error_without_status_falls_back_to_200() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=_stream_response({"message": "boom"}))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async for _ in srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"):
                pass
    assert caught.value.status == 200
    assert caught.value.error == "boom"


@respx.mock
@pytest.mark.asyncio
async def test_async_in_band_query_error_falls_back_to_message_when_error_is_absent() -> None:
    respx.post(f"{BASE_URL}/api/v1/command/mydb").mock(
        return_value=_stream_response({"message": "duplicated key", "status": 409})
    )
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async for _ in srv.db("mydb").command_stream(language="sql", command="SELECT FROM V"):
                pass
    assert caught.value.status == 409
    assert caught.value.error == "duplicated key"


# --- batch_load_stream ------------------------------------------------------------------------

BATCH_ERROR: dict[str, Any] = {
    "error": "Cannot execute the request yet",
    "status": 503,
    "retryAfter": 7,
    "commitIndex": 1234,
}


@respx.mock
def test_in_band_batch_error_carries_retry_after_and_commit_index() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"error": BATCH_ERROR}))
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").batch_load_stream(**ROWS))
    assert caught.value.status == 503
    assert caught.value.error == "Cannot execute the request yet"
    assert caught.value.retry_after == 7
    assert caught.value.commit_index == 1234


@respx.mock
def test_in_band_batch_error_without_them_leaves_both_none() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"error": {"error": "boom", "status": 500}}))
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").batch_load_stream(**ROWS))
    assert caught.value.retry_after is None
    assert caught.value.commit_index is None


@respx.mock
@pytest.mark.asyncio
async def test_async_in_band_batch_error_carries_retry_after_and_commit_index() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"error": BATCH_ERROR}))
    )
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async for _ in srv.db("mydb").batch_load_stream(**ROWS):
                pass
    assert caught.value.status == 503
    assert caught.value.retry_after == 7
    assert caught.value.commit_index == 1234


# --- an in-band status that is not a positive whole number reads as absent ---------------------

MALFORMED_STATUSES: list[Any] = ["503", -1, 0, 503.5, True, None, {"code": 503}]


@pytest.mark.parametrize("status", MALFORMED_STATUSES)
@respx.mock
def test_in_band_query_error_with_a_malformed_status_falls_back_to_200(status: Any) -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=_stream_response({"message": "boom", "status": status})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"))
    assert caught.value.status == 200


@pytest.mark.parametrize("status", MALFORMED_STATUSES)
@respx.mock
def test_in_band_batch_error_with_a_malformed_status_falls_back_to_500(status: Any) -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"error": {"error": "boom", "status": status}}))
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").batch_load_stream(**ROWS))
    assert caught.value.status == 500
    assert caught.value.error == "boom"


@pytest.mark.parametrize("status", MALFORMED_STATUSES)
@respx.mock
@pytest.mark.asyncio
async def test_async_in_band_batch_error_with_a_malformed_status_falls_back_to_500(status: Any) -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"error": {"error": "boom", "status": status}}))
    )
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async for _ in srv.db("mydb").batch_load_stream(**ROWS):
                pass
    assert caught.value.status == 500
