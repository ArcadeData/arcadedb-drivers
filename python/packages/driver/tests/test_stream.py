"""Tests for `query_stream`/`command_stream`, sync and async.

Most cases feed the whole ndjson body as one buffered `httpx.Response(json=...)`-style
`content=` blob - respx pre-reads that (`httpx.ByteStream`), but the decoder still splits it into
events correctly regardless of how many chunks it arrived in, so this proves nothing about chunk
boundaries specifically.

Two cases need real control over chunking and need to know when the connection is released, and
both go around respx's default pre-reading: passing a custom `httpx.SyncByteStream` /
`httpx.AsyncByteStream` (NOT `httpx.ByteStream`) as `httpx.Response(status, stream=...)` is what
respx's own router checks for (`isinstance(response.stream, httpx.ByteStream)`) before deciding to
pre-read - a plain `SyncByteStream`/`AsyncByteStream` subclass is left alone, so its `__iter__`/
`__aiter__` chunks are delivered as given and its `close()`/`aclose()` is observable.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer
from arcadedb_driver._generated.models.nd_json_query_event import NdJsonQueryEvent
from arcadedb_driver._generated.types import Unset

BASE_URL = "http://db.test"


def server() -> ArcadeDBServer:
    return ArcadeDBServer(base_url=BASE_URL)


def async_server() -> AsyncArcadeDBServer:
    return AsyncArcadeDBServer(base_url=BASE_URL)


def _lines(*events: dict[str, Any]) -> bytes:
    return b"".join((json.dumps(event) + "\n").encode() for event in events)


def _record(event: NdJsonQueryEvent) -> dict[str, Any]:
    assert not isinstance(event.record, Unset)
    return event.record.to_dict()


def _stats(event: NdJsonQueryEvent) -> dict[str, Any]:
    assert not isinstance(event.stats, Unset)
    return event.stats.to_dict()


class _SyncChunks(httpx.SyncByteStream):
    """A byte stream respx will NOT pre-read - see the module docstring."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class _AsyncChunks(httpx.AsyncByteStream):
    """The async twin of `_SyncChunks`."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


# --- sync ---------------------------------------------------------------------------------------


@respx.mock
def test_query_stream_sends_accept_ndjson_and_posts_the_same_body_query_builds() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, content=_lines()))
    with server() as srv:
        list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V", params={"x": 1}, limit=5))

    request = route.calls.last.request
    assert request.headers["Accept"] == "application/x-ndjson"
    body = json.loads(request.read())
    assert body == {"language": "sql", "command": "SELECT FROM V", "params": {"x": 1}, "limit": 5}


@respx.mock
def test_query_stream_yields_each_event_in_order_including_the_stats_trailer() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {"record": {"a": 1}},
                {"record": {"a": 2}},
                {"stats": {"limit": 100, "returned": 2, "truncated": False}},
            ),
        )
    )
    with server() as srv:
        events = list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"))

    assert len(events) == 3
    assert _record(events[0]) == {"a": 1}
    assert _record(events[1]) == {"a": 2}
    assert _stats(events[2]) == {"limit": 100, "returned": 2, "truncated": False}


@respx.mock
def test_query_stream_reassembles_a_line_split_across_two_chunks() -> None:
    # The decoder's `remainder` owns this - `facade/stream.py` splits lines itself rather than
    # leaning on `iter_lines()`, so nothing else is buffering the half-line for it.
    stream = _SyncChunks([b'{"record":{"a":', b"1}}\n"])
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, stream=stream))
    with server() as srv:
        events = list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"))

    assert [_record(e) for e in events] == [{"a": 1}]


@respx.mock
def test_query_stream_keeps_a_record_containing_u2028_intact() -> None:
    # U+2028 (and U+0085, U+2029) are legal raw characters inside a JSON string, but
    # `str.splitlines()` - and therefore httpx's `iter_lines()` - treats all three as line
    # terminators. Routing this body through `iter_lines()` cuts the record in two and raises
    # `json.JSONDecodeError` on both halves. Splitting on "\n" alone keeps it whole.
    line = '{"record": {"text": "a\u2028b"}}\n'.encode()
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, content=line))
    with server() as srv:
        events = list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"))

    assert [_record(e) for e in events] == [{"text": "a\u2028b"}]


@respx.mock
def test_query_stream_yields_nothing_and_does_not_raise_for_an_empty_stream() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, content=b""))
    with server() as srv:
        events = list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"))

    assert events == []


@respx.mock
def test_query_stream_raises_arcadedb_error_on_an_in_band_error_event_after_delivering_prior_events() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"record": {"a": 1}}, {"error": {"message": "boom"}}))
    )
    seen: list[NdJsonQueryEvent] = []
    with server() as srv, pytest.raises(ArcadeDBError) as caught:
        for event in srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"):
            seen.append(event)

    assert [_record(e) for e in seen] == [{"a": 1}]
    assert caught.value.status == 200
    assert caught.value.error == "boom"


@respx.mock
def test_query_stream_raises_arcadedb_error_with_the_servers_detail_on_a_non_2xx_response() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(400, json={"error": "bad request"}, headers={"X-Request-Id": "req-1"})
    )
    with server() as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"))

    assert caught.value.status == 400
    assert caught.value.error == "bad request"
    assert caught.value.request_id == "req-1"


@respx.mock
def test_query_stream_sends_the_session_header_when_called_through_a_transaction_handle() -> None:
    respx.post(f"{BASE_URL}/api/v1/begin/mydb").mock(
        return_value=httpx.Response(204, headers={"arcadedb-session-id": "AS-1"})
    )
    route = respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, content=_lines()))
    respx.post(f"{BASE_URL}/api/v1/commit/mydb").mock(return_value=httpx.Response(204))

    with server() as srv, srv.db("mydb").transaction() as tx:
        list(tx.query_stream(language="sql", command="SELECT FROM V"))

    assert route.calls.last.request.headers["arcadedb-session-id"] == "AS-1"


@respx.mock
def test_query_stream_closes_the_response_when_the_caller_abandons_the_iterator() -> None:
    stream = _SyncChunks([b'{"record":{"a":1}}\n', b'{"record":{"a":2}}\n'])
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, stream=stream))
    with server() as srv:
        events = srv.db("mydb").query_stream(language="sql", command="SELECT FROM V")
        first = next(events)
        assert _record(first) == {"a": 1}
        events.close()

    assert stream.closed is True


@respx.mock
def test_command_stream_reaches_the_command_endpoint() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/command/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"stats": {"limit": -1, "returned": 0, "truncated": False}}))
    )
    with server() as srv:
        events = list(srv.db("mydb").command_stream(language="sql", command="SELECT FROM V"))

    assert route.calls.last.request.headers["Accept"] == "application/x-ndjson"
    assert _stats(events[0]) == {"limit": -1, "returned": 0, "truncated": False}


# --- async ----------------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_async_query_stream_sends_accept_ndjson_and_posts_the_same_body_query_builds() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, content=_lines()))
    async with async_server() as srv:
        events = [e async for e in srv.db("mydb").query_stream(language="sql", command="SELECT FROM V", limit=5)]

    assert events == []
    request = route.calls.last.request
    assert request.headers["Accept"] == "application/x-ndjson"
    assert json.loads(request.read()) == {"language": "sql", "command": "SELECT FROM V", "limit": 5}


@respx.mock
@pytest.mark.asyncio
async def test_async_query_stream_yields_each_event_in_order_including_the_stats_trailer() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {"record": {"a": 1}},
                {"record": {"a": 2}},
                {"stats": {"limit": 100, "returned": 2, "truncated": False}},
            ),
        )
    )
    async with async_server() as srv:
        events = [e async for e in srv.db("mydb").query_stream(language="sql", command="SELECT FROM V")]

    assert len(events) == 3
    assert _record(events[0]) == {"a": 1}
    assert _record(events[1]) == {"a": 2}
    assert _stats(events[2]) == {"limit": 100, "returned": 2, "truncated": False}


@respx.mock
@pytest.mark.asyncio
async def test_async_query_stream_reassembles_a_line_split_across_two_chunks() -> None:
    stream = _AsyncChunks([b'{"record":{"a":', b"1}}\n"])
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, stream=stream))
    async with async_server() as srv:
        events = [e async for e in srv.db("mydb").query_stream(language="sql", command="SELECT FROM V")]

    assert [_record(e) for e in events] == [{"a": 1}]


@respx.mock
@pytest.mark.asyncio
async def test_async_query_stream_keeps_a_record_containing_u2028_intact() -> None:
    """The async twin of the sync U+2028 case - see it for why this character matters."""
    line = '{"record": {"text": "a\u2028b"}}\n'.encode()
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, content=line))
    async with async_server() as srv:
        events = [e async for e in srv.db("mydb").query_stream(language="sql", command="SELECT FROM V")]

    assert [_record(e) for e in events] == [{"text": "a\u2028b"}]


@respx.mock
@pytest.mark.asyncio
async def test_async_query_stream_raises_arcadedb_error_on_an_in_band_error_event() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"record": {"a": 1}}, {"error": {"message": "boom"}}))
    )
    seen: list[NdJsonQueryEvent] = []
    async with async_server() as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async for event in srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"):
                seen.append(event)

    assert [_record(e) for e in seen] == [{"a": 1}]
    assert caught.value.status == 200
    assert caught.value.error == "boom"


@respx.mock
@pytest.mark.asyncio
async def test_async_query_stream_raises_arcadedb_error_with_the_servers_detail_on_a_non_2xx_response() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(400, json={"error": "bad request"}, headers={"X-Request-Id": "req-1"})
    )
    async with async_server() as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async for _ in srv.db("mydb").query_stream(language="sql", command="SELECT FROM V"):
                pass

    assert caught.value.status == 400
    assert caught.value.error == "bad request"
    assert caught.value.request_id == "req-1"


@respx.mock
@pytest.mark.asyncio
async def test_async_query_stream_closes_the_response_when_the_caller_abandons_the_iterator() -> None:
    stream = _AsyncChunks([b'{"record":{"a":1}}\n', b'{"record":{"a":2}}\n'])
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, stream=stream))
    async with async_server() as srv:
        events = srv.db("mydb").query_stream(language="sql", command="SELECT FROM V")
        first = await events.__anext__()
        assert _record(first) == {"a": 1}
        await events.aclose()

    assert stream.closed is True


@respx.mock
@pytest.mark.asyncio
async def test_async_command_stream_reaches_the_command_endpoint() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/command/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"stats": {"limit": -1, "returned": 0, "truncated": False}}))
    )
    async with async_server() as srv:
        events = [e async for e in srv.db("mydb").command_stream(language="sql", command="SELECT FROM V")]

    assert route.calls.last.request.headers["Accept"] == "application/x-ndjson"
    assert _stats(events[0]) == {"limit": -1, "returned": 0, "truncated": False}
