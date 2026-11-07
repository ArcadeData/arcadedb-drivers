"""Tests for the `lines=` argument of `batch_load` / `batch_load_stream` (sync and async) and for
`iter_rows`: a request body that is generated while it is sent instead of built whole.

No network and no server: every case goes through a small mock transport (`_SyncTransport`,
`_AsyncTransport`, below) whose handler is given the real, unread `httpx.Request`. Its `stream`
attribute tells a streamed body from a buffered one: a `bytes` body becomes `httpx.ByteStream` and
carries a `Content-Length`; an iterator body becomes an iterator stream and carries
`Transfer-Encoding: chunked`. The handler walks that stream chunk by chunk, the way a transport
does, and records how many rows the caller's generator had produced at each step, which is how the
tests show the rows are pulled lazily.
"""

from __future__ import annotations

import io
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from arcadedb_driver import ArcadeDBDatabase, ArcadeDBServer, AsyncArcadeDBDatabase, AsyncArcadeDBServer, iter_rows
from arcadedb_driver._internal import batch_rows
from arcadedb_driver._internal.batch_rows import EdgeRow, VertexRow, aiter_body, iter_body, serialize_rows

BASE_URL = "http://db.test"
SUMMARY = {"verticesCreated": 3, "edgesCreated": 2}
FUNCTIONS = ["batch_load", "batch_load_stream"]


def vertex_rows(n: int) -> list[VertexRow]:
    return [{"type": "Person", "id": f"p{i}", "properties": {"name": f"n{i}", "note": "café ☃"}} for i in range(n)]


def edge_rows(n: int) -> list[EdgeRow]:
    return [{"type": "Knows", "from_": f"p{i}", "to": f"p{i + 1}", "properties": {"since": 2000 + i}} for i in range(n)]


@dataclass
class Counter:
    """Wraps rows so the test can see how many have been pulled."""

    pulled: int = 0

    def rows(self, rows: list[Any]) -> Iterator[Any]:
        for row in rows:
            self.pulled += 1
            yield row


@dataclass
class Seen:
    headers: httpx.Headers = field(default_factory=httpx.Headers)
    stream_type: type = object
    chunks: list[bytes] = field(default_factory=list)
    pulled_at_entry: int | None = None
    pulled_after_chunk: list[int] = field(default_factory=list)

    @property
    def body(self) -> bytes:
        return b"".join(self.chunks)


def _response(request: httpx.Request) -> httpx.Response:
    if request.headers.get("accept") == "application/x-ndjson":
        return httpx.Response(200, content=(json.dumps({"summary": SUMMARY}) + "\n").encode())
    return httpx.Response(200, json=SUMMARY)


def _record_start(seen: Seen, request: httpx.Request, counter: Counter | None) -> None:
    seen.headers = request.headers
    seen.stream_type = type(request.stream)
    seen.pulled_at_entry = counter.pulled if counter else None


class _SyncTransport(httpx.BaseTransport):
    """Like `httpx.MockTransport`, except that the handler gets the request UNREAD:
    `MockTransport.handle_request` calls `request.read()` first, which joins an iterator body into
    one `bytes` before any handler sees it and would hide exactly what these tests look at."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self._handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self._handler(request)


class _AsyncTransport(httpx.AsyncBaseTransport):
    """The async twin of `_SyncTransport`."""

    def __init__(self, handler: Callable[[httpx.Request], Awaitable[httpx.Response]]) -> None:
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self._handler(request)


def sync_db(seen: Seen, counter: Counter | None = None) -> ArcadeDBDatabase:
    def handle(request: httpx.Request) -> httpx.Response:
        _record_start(seen, request, counter)
        assert isinstance(request.stream, httpx.SyncByteStream)
        for chunk in request.stream:
            seen.chunks.append(chunk)
            if counter:
                seen.pulled_after_chunk.append(counter.pulled)
        return _response(request)

    srv = ArcadeDBServer(base_url=BASE_URL)
    srv.raw.set_httpx_client(httpx.Client(base_url=BASE_URL, transport=_SyncTransport(handle)))
    return srv.db("mydb")


def async_db(seen: Seen, counter: Counter | None = None) -> AsyncArcadeDBDatabase:
    async def handle(request: httpx.Request) -> httpx.Response:
        _record_start(seen, request, counter)
        assert isinstance(request.stream, httpx.AsyncByteStream)
        async for chunk in request.stream:
            seen.chunks.append(chunk)
            if counter:
                seen.pulled_after_chunk.append(counter.pulled)
        return _response(request)

    srv = AsyncArcadeDBServer(base_url=BASE_URL)
    srv.raw.set_async_httpx_client(httpx.AsyncClient(base_url=BASE_URL, transport=_AsyncTransport(handle)))
    return srv.db("mydb")


def run(db: ArcadeDBDatabase, fn: str, **kwargs: Any) -> Any:
    result = getattr(db, fn)(**kwargs)
    return list(result) if fn.endswith("_stream") else result


async def arun(db: AsyncArcadeDBDatabase, fn: str, **kwargs: Any) -> Any:
    result = getattr(db, fn)(**kwargs)
    if fn.endswith("_stream"):
        return [event async for event in result]
    return await result


def old_payload(n_vertices: int = 3, n_edges: int = 2) -> bytes:
    return serialize_rows(vertex_rows(n_vertices), edge_rows(n_edges)).encode("utf-8")


# ---- the bytes on the wire ---------------------------------------------------------------------


@pytest.mark.parametrize("fn", FUNCTIONS)
class TestWireSync:
    def test_the_default_path_is_still_one_buffered_body_with_a_content_length(self, fn: str) -> None:
        seen = Seen()
        run(sync_db(seen), fn, vertices=vertex_rows(3), edges=edge_rows(2))
        assert seen.stream_type is httpx.ByteStream
        assert seen.headers["content-length"] == str(len(old_payload()))
        assert "transfer-encoding" not in seen.headers
        assert seen.body == old_payload()

    def test_iter_rows_as_lines_sends_the_bytes_the_default_path_sends(self, fn: str) -> None:
        seen = Seen()
        run(sync_db(seen), fn, lines=iter_rows(vertex_rows(3), edge_rows(2)))
        assert seen.body == old_payload()

    def test_the_body_is_streamed_and_chunked_not_a_bytes_object(self, fn: str) -> None:
        seen = Seen()
        run(sync_db(seen), fn, lines=iter_rows(vertex_rows(3), edge_rows(2)))
        assert seen.stream_type is not httpx.ByteStream
        assert seen.headers["transfer-encoding"] == "chunked"
        assert "content-length" not in seen.headers
        assert seen.headers["content-type"] == "application/x-ndjson"

    def test_str_lines_without_newlines_and_a_binary_file_give_the_same_bytes(self, fn: str) -> None:
        text_lines = [line.decode().rstrip("\n") for line in iter_rows(vertex_rows(3), edge_rows(2))]
        for lines in (text_lines, io.BytesIO(old_payload())):
            seen = Seen()
            run(sync_db(seen), fn, lines=lines)
            assert seen.body == old_payload()

    def test_an_empty_line_is_skipped(self, fn: str) -> None:
        seen = Seen()
        run(sync_db(seen), fn, lines=['{"@type":"vertex","@class":"A"}', "", b"", b"\n"])
        assert seen.body == b'{"@type":"vertex","@class":"A"}\n\n'

    def test_the_answer_is_unchanged(self, fn: str) -> None:
        result = run(sync_db(Seen()), fn, lines=iter_rows(vertex_rows(3), edge_rows(2)))
        assert result == ([{"summary": SUMMARY}] if fn.endswith("_stream") else SUMMARY)

    def test_options_and_query_tag_still_travel_with_lines(self, fn: str) -> None:
        seen = Seen()
        run(sync_db(seen), fn, lines=[b"{}\n"], options={"commitEvery": 5}, query_tag="load-1")
        assert seen.headers["x-arcadedb-query-tag"] == "load-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("fn", FUNCTIONS)
class TestWireAsync:
    async def test_the_default_path_is_still_one_buffered_body_with_a_content_length(self, fn: str) -> None:
        seen = Seen()
        await arun(async_db(seen), fn, vertices=vertex_rows(3), edges=edge_rows(2))
        assert seen.stream_type is httpx.ByteStream
        assert seen.headers["content-length"] == str(len(old_payload()))
        assert seen.body == old_payload()

    async def test_iter_rows_as_lines_sends_the_bytes_the_default_path_sends(self, fn: str) -> None:
        seen = Seen()
        await arun(async_db(seen), fn, lines=iter_rows(vertex_rows(3), edge_rows(2)))
        assert seen.body == old_payload()

    async def test_the_body_is_streamed_and_chunked_not_a_bytes_object(self, fn: str) -> None:
        seen = Seen()
        await arun(async_db(seen), fn, lines=iter_rows(vertex_rows(3), edge_rows(2)))
        assert seen.stream_type is not httpx.ByteStream
        assert seen.headers["transfer-encoding"] == "chunked"
        assert "content-length" not in seen.headers

    async def test_a_binary_file_gives_the_same_bytes(self, fn: str) -> None:
        seen = Seen()
        await arun(async_db(seen), fn, lines=io.BytesIO(old_payload()))
        assert seen.body == old_payload()

    async def test_an_async_iterable_of_lines_gives_the_same_bytes(self, fn: str) -> None:
        async def lines() -> AsyncIterator[str]:
            for line in iter_rows(vertex_rows(3), edge_rows(2)):
                yield line.decode().rstrip("\n")

        seen = Seen()
        await arun(async_db(seen), fn, lines=lines())
        assert seen.body == old_payload()

    async def test_the_answer_is_unchanged(self, fn: str) -> None:
        result = await arun(async_db(Seen()), fn, lines=iter_rows(vertex_rows(3), edge_rows(2)))
        assert result == ([{"summary": SUMMARY}] if fn.endswith("_stream") else SUMMARY)


# ---- lazy: rows are pulled while the body is sent ----------------------------------------------


@pytest.fixture
def one_row_per_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    # A chunk ends at the first line that reaches CHUNK_BYTES, so 1 byte means one line per chunk.
    monkeypatch.setattr(batch_rows, "CHUNK_BYTES", 1)


@pytest.mark.parametrize("fn", FUNCTIONS)
def test_no_row_is_pulled_before_the_transport_reads_and_each_chunk_pulls_one_sync(
    fn: str, one_row_per_chunk: None
) -> None:
    seen, counter = Seen(), Counter()
    run(sync_db(seen, counter), fn, lines=iter_rows(counter.rows(vertex_rows(3)), counter.rows(edge_rows(2))))
    assert seen.pulled_at_entry == 0
    assert seen.pulled_after_chunk == [1, 2, 3, 4, 5]
    assert len(seen.chunks) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("fn", FUNCTIONS)
async def test_no_row_is_pulled_before_the_transport_reads_and_each_chunk_pulls_one_async(
    fn: str, one_row_per_chunk: None
) -> None:
    seen, counter = Seen(), Counter()
    await arun(async_db(seen, counter), fn, lines=iter_rows(counter.rows(vertex_rows(3)), counter.rows(edge_rows(2))))
    assert seen.pulled_at_entry == 0
    assert seen.pulled_after_chunk == [1, 2, 3, 4, 5]


def test_the_buffered_default_pulls_every_row_before_the_transport_sees_the_request() -> None:
    # The contrast the lazy tests rest on: the rows path builds the payload first.
    seen, counter = Seen(), Counter()
    run(sync_db(seen, counter), "batch_load", vertices=counter.rows(vertex_rows(3)), edges=counter.rows(edge_rows(2)))
    assert seen.pulled_at_entry == 5


def test_no_chunk_is_larger_than_the_chunk_size_plus_one_line() -> None:
    n = 3000
    seen = Seen()
    run(sync_db(seen), "batch_load", lines=iter_rows(vertex_rows(n), edge_rows(n - 1)))
    longest_line = max(len(line) for line in iter_rows(vertex_rows(n), edge_rows(n - 1)))
    assert len(seen.chunks) > 3
    assert max(len(chunk) for chunk in seen.chunks) < batch_rows.CHUNK_BYTES + longest_line
    assert seen.body == serialize_rows(vertex_rows(n), edge_rows(n - 1)).encode("utf-8")


def test_a_body_that_fails_midway_surfaces_the_error_to_the_caller() -> None:
    def lines() -> Iterator[bytes]:
        yield b'{"@type":"vertex","@class":"A"}\n'
        raise RuntimeError("the source broke")

    with pytest.raises(RuntimeError, match="the source broke"):
        run(sync_db(Seen()), "batch_load", lines=lines())


# ---- argument rules -----------------------------------------------------------------------------


@pytest.mark.parametrize("fn", FUNCTIONS)
def test_lines_together_with_rows_raises_value_error_at_the_call_sync(fn: str) -> None:
    db = sync_db(Seen())
    for extra in ({"vertices": vertex_rows(1)}, {"edges": edge_rows(1)}, {"vertices": iter(vertex_rows(1))}):
        with pytest.raises(ValueError, match="lines"):
            getattr(db, fn)(lines=[b"{}\n"], **extra)  # raised by the call itself, not by iterating


@pytest.mark.parametrize("fn", FUNCTIONS)
def test_empty_rows_beside_lines_are_not_an_error(fn: str) -> None:
    seen = Seen()
    run(sync_db(seen), fn, lines=[b"{}\n"], vertices=[], edges=())
    assert seen.body == b"{}\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("fn", FUNCTIONS)
async def test_lines_together_with_rows_raises_value_error_at_the_call_async(fn: str) -> None:
    db = async_db(Seen())
    with pytest.raises(ValueError, match="lines"):
        result = getattr(db, fn)(lines=[b"{}\n"], vertices=vertex_rows(1))
        if not fn.endswith("_stream"):  # a stream call must already have raised, before any iteration
            await result


def test_a_line_that_is_not_str_or_bytes_is_a_type_error() -> None:
    with pytest.raises(TypeError, match="str or bytes"):
        list(iter_body([1]))  # type: ignore[list-item]


@pytest.mark.asyncio
async def test_a_line_that_is_not_str_or_bytes_is_a_type_error_async() -> None:
    with pytest.raises(TypeError, match="str or bytes"):
        [chunk async for chunk in aiter_body([1])]  # type: ignore[list-item]


def test_iter_rows_yields_the_lines_serialize_rows_joins() -> None:
    assert b"".join(iter_rows(vertex_rows(3), edge_rows(2))) == old_payload()
    assert list(iter_rows([], [])) == []


def test_iter_rows_is_lazy() -> None:
    counter = Counter()
    lines = iter_rows(counter.rows(vertex_rows(3)), [])
    assert counter.pulled == 0
    next(lines)
    assert counter.pulled == 1
