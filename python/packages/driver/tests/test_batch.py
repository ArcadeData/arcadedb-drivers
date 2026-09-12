"""Tests for `batch_load`/`batch_load_stream`, sync and async.

Follows `test_stream.py`'s httpx-mocking style: most cases feed the whole ndjson (or JSON) body as
one buffered `httpx.Response(content=...)` blob, which respx pre-reads. Almost none of these
cases are about chunk splitting itself - that behaviour lives in `_internal/ndjson.py` and is
already covered there and in `test_stream.py` - except the early-termination pair below, which
needs the same `_SyncChunks`/`_AsyncChunks` respx-bypass `test_stream.py` uses for its own
`close()`/`aclose()` tests: a body respx pre-reads is fully consumed before the facade ever gets a
chance to abandon it, so its `close()`/`aclose()` would always fire regardless of whether the
facade's own teardown does its job. Duplicated here rather than imported - `tests/` has no
`__init__.py`, so there is no package for `test_batch.py` to import `test_stream.py`'s classes
from.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer
from arcadedb_driver.facade import batch

BASE_URL = "http://db.test"

ROWS: dict[str, Any] = {
    "vertices": [{"type": "Person", "id": "a", "properties": {"name": "Ann"}}],
    "edges": [{"type": "Knows", "from_": "a", "to": "#1:7"}],
}


def server() -> ArcadeDBServer:
    return ArcadeDBServer(base_url=BASE_URL)


def async_server() -> AsyncArcadeDBServer:
    return AsyncArcadeDBServer(base_url=BASE_URL)


def _lines(*events: dict[str, Any]) -> bytes:
    return b"".join((json.dumps(event) + "\n").encode() for event in events)


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


# --- sync -----------------------------------------------------------------------------------


@respx.mock
def test_batch_load_posts_the_serialized_payload() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(200, json={"verticesCreated": 1, "edgesCreated": 1})
    )
    with server() as srv:
        srv.db("mydb").batch_load(**ROWS)

    request = route.calls.last.request
    assert request.headers["Content-Type"] == "application/x-ndjson"
    lines = [json.loads(line) for line in request.read().decode().split("\n") if line]
    assert lines == [
        {"@type": "vertex", "@class": "Person", "@id": "a", "name": "Ann"},
        {"@type": "edge", "@class": "Knows", "@from": "a", "@to": "#1:7"},
    ]


@respx.mock
def test_batch_load_passes_options_as_query_parameters() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(return_value=httpx.Response(200, json={}))
    with server() as srv:
        srv.db("mydb").batch_load(**ROWS, options={"commitEvery": 5000, "lightEdges": True})

    url = route.calls.last.request.url
    assert url.params["commitEvery"] == "5000"
    assert url.params["lightEdges"] == "true"


@respx.mock
def test_an_absent_option_sends_no_parameter_at_all() -> None:
    # Not an empty value - the parameter must be absent from the URL entirely, so the server
    # applies its own default rather than parsing "".
    route = respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(return_value=httpx.Response(200, json={}))
    with server() as srv:
        srv.db("mydb").batch_load(**ROWS, options={"commitEvery": 10})

    url = route.calls.last.request.url
    assert "commitEvery" in url.params
    assert "batchSize" not in url.params
    assert "wal" not in url.params


@respx.mock
def test_batch_load_raises_arcadedb_error_on_a_refused_load() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            400, json={"error": "Missing @class at line 1", "verticesCreated": 0, "partialCommit": False}
        )
    )
    with server() as srv, pytest.raises(ArcadeDBError) as caught:
        srv.db("mydb").batch_load(**ROWS)

    assert caught.value.status == 400
    assert caught.value.error == "Missing @class at line 1"


@respx.mock
def test_batch_load_stream_sends_accept_ndjson() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"summary": {"verticesCreated": 1}}))
    )
    with server() as srv:
        list(srv.db("mydb").batch_load_stream(**ROWS))

    assert route.calls.last.request.headers["Accept"] == "application/x-ndjson"


@respx.mock
def test_batch_load_stream_yields_progress_then_summary() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {"progress": {"phase": "vertices", "verticesCreated": 1, "idMapping": {"a": "#1:0"}}},
                {"progress": {"phase": "edges", "edgesCreated": 1}},
                {"summary": {"verticesCreated": 1, "edgesCreated": 1, "idMappingStreamed": True, "idMappingSize": 1}},
            ),
        )
    )
    with server() as srv:
        events = list(srv.db("mydb").batch_load_stream(**ROWS))

    assert len(events) == 3
    assert events[0]["progress"]["phase"] == "vertices"
    assert events[1]["progress"]["phase"] == "edges"
    assert events[2]["summary"]["idMappingStreamed"] is True


@respx.mock
def test_batch_load_stream_does_not_merge_id_mapping_fragments() -> None:
    # D5: the facade must NOT accumulate. The server streams the mapping precisely so a
    # million-vertex load never holds a million entries client-side.
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {"progress": {"idMapping": {"a": "#1:0"}}},
                {"progress": {"idMapping": {"b": "#1:1"}}},
                {"summary": {"idMappingStreamed": True, "idMappingSize": 2}},
            ),
        )
    )
    with server() as srv:
        events = list(srv.db("mydb").batch_load_stream(**ROWS))

    assert events[0]["progress"]["idMapping"] == {"a": "#1:0"}
    assert events[1]["progress"]["idMapping"] == {"b": "#1:1"}
    assert "idMapping" not in events[2]["summary"]


@respx.mock
def test_a_failure_before_the_stream_starts_raises() -> None:
    # D6 channel one: the status line has not been sent, so the server answers with a real HTTP
    # status and the buffered error body.
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(400, json={"error": "Missing @class at line 1"})
    )
    with server() as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").batch_load_stream(**ROWS))

    assert caught.value.status == 400


@respx.mock
def test_an_in_band_error_event_raises_with_its_own_status() -> None:
    # D6 channel two: once the 200 is on the wire it cannot be taken back, so the failure arrives
    # in band carrying the status the buffered encoding would have used.
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {"progress": {"verticesCreated": 1}},
                {"error": {"error": "boom", "status": 400, "partialCommit": True}},
            ),
        )
    )
    with server() as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").batch_load_stream(**ROWS))

    assert caught.value.status == 400
    assert caught.value.error == "boom"


@respx.mock
def test_events_before_an_in_band_error_are_yielded_first() -> None:
    # The throw must not swallow work the caller was already told about: a partial commit is
    # durable, and those progress counts are how a caller learns what may have landed.
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {"progress": {"verticesCreated": 2}},
                {"error": {"error": "boom", "status": 500}},
            ),
        )
    )
    seen: list[dict[str, Any]] = []
    with server() as srv, pytest.raises(ArcadeDBError):
        for event in srv.db("mydb").batch_load_stream(**ROWS):
            seen.append(event)

    assert len(seen) == 1
    assert seen[0]["progress"]["verticesCreated"] == 2


@respx.mock
def test_status_mapped_false_is_recorded_on_the_error() -> None:
    # The contract says to key on `exception` when statusMapped is false, because 500 is an
    # unclassified fallback rather than the status the buffered encoding would have chosen.
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {
                    "error": {
                        "error": "engine failure",
                        "status": 500,
                        "statusMapped": False,
                        "exception": "java.lang.IllegalStateException",
                    }
                }
            ),
        )
    )
    with server() as srv, pytest.raises(ArcadeDBError) as caught:
        list(srv.db("mydb").batch_load_stream(**ROWS))

    assert caught.value.status == 500
    assert caught.value.exception == "java.lang.IllegalStateException"


@respx.mock
def test_batch_load_stream_closes_the_response_when_the_caller_abandons_the_iterator() -> None:
    # This exact bug class bit this project before: an earlier milestone shipped a TypeScript
    # decoder that released its reader's lock without cancelling the response body, leaking the
    # connection - only a test that abandoned the stream would have caught it. `facade/batch.py`'s
    # `with ...stream()` is its own context manager, not shared code with `facade/stream.py`, so
    # nothing else in the suite pins its teardown.
    stream = _SyncChunks([b'{"progress":{"verticesCreated":1}}\n', b'{"progress":{"verticesCreated":2}}\n'])
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(return_value=httpx.Response(200, stream=stream))
    with server() as srv:
        events = srv.db("mydb").batch_load_stream(**ROWS)
        first = next(events)
        assert first["progress"]["verticesCreated"] == 1
        events.close()

    assert stream.closed is True


# --- async ----------------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_async_batch_load_posts_the_serialized_payload() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(200, json={"verticesCreated": 1, "edgesCreated": 1})
    )
    async with async_server() as srv:
        await srv.db("mydb").batch_load(**ROWS)

    request = route.calls.last.request
    assert request.headers["Content-Type"] == "application/x-ndjson"
    lines = [json.loads(line) for line in request.read().decode().split("\n") if line]
    assert lines == [
        {"@type": "vertex", "@class": "Person", "@id": "a", "name": "Ann"},
        {"@type": "edge", "@class": "Knows", "@from": "a", "@to": "#1:7"},
    ]


@respx.mock
@pytest.mark.asyncio
async def test_async_batch_load_passes_options_as_query_parameters() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(return_value=httpx.Response(200, json={}))
    async with async_server() as srv:
        await srv.db("mydb").batch_load(**ROWS, options={"commitEvery": 5000, "lightEdges": True})

    url = route.calls.last.request.url
    assert url.params["commitEvery"] == "5000"
    assert url.params["lightEdges"] == "true"


@respx.mock
@pytest.mark.asyncio
async def test_an_absent_option_sends_no_parameter_at_all_async() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(return_value=httpx.Response(200, json={}))
    async with async_server() as srv:
        await srv.db("mydb").batch_load(**ROWS, options={"commitEvery": 10})

    url = route.calls.last.request.url
    assert "commitEvery" in url.params
    assert "batchSize" not in url.params
    assert "wal" not in url.params


@respx.mock
@pytest.mark.asyncio
async def test_async_batch_load_raises_arcadedb_error_on_a_refused_load() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            400, json={"error": "Missing @class at line 1", "verticesCreated": 0, "partialCommit": False}
        )
    )
    async with async_server() as srv:
        with pytest.raises(ArcadeDBError) as caught:
            await srv.db("mydb").batch_load(**ROWS)

    assert caught.value.status == 400
    assert caught.value.error == "Missing @class at line 1"


@respx.mock
@pytest.mark.asyncio
async def test_async_batch_load_stream_sends_accept_ndjson() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(200, content=_lines({"summary": {"verticesCreated": 1}}))
    )
    async with async_server() as srv:
        events = [e async for e in srv.db("mydb").batch_load_stream(**ROWS)]

    assert len(events) == 1
    assert route.calls.last.request.headers["Accept"] == "application/x-ndjson"


@respx.mock
@pytest.mark.asyncio
async def test_async_batch_load_stream_yields_progress_then_summary() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {"progress": {"phase": "vertices", "verticesCreated": 1, "idMapping": {"a": "#1:0"}}},
                {"progress": {"phase": "edges", "edgesCreated": 1}},
                {"summary": {"verticesCreated": 1, "edgesCreated": 1, "idMappingStreamed": True, "idMappingSize": 1}},
            ),
        )
    )
    async with async_server() as srv:
        events = [e async for e in srv.db("mydb").batch_load_stream(**ROWS)]

    assert len(events) == 3
    assert events[0]["progress"]["phase"] == "vertices"
    assert events[1]["progress"]["phase"] == "edges"
    assert events[2]["summary"]["idMappingStreamed"] is True


@respx.mock
@pytest.mark.asyncio
async def test_async_batch_load_stream_does_not_merge_id_mapping_fragments() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {"progress": {"idMapping": {"a": "#1:0"}}},
                {"progress": {"idMapping": {"b": "#1:1"}}},
                {"summary": {"idMappingStreamed": True, "idMappingSize": 2}},
            ),
        )
    )
    async with async_server() as srv:
        events = [e async for e in srv.db("mydb").batch_load_stream(**ROWS)]

    assert events[0]["progress"]["idMapping"] == {"a": "#1:0"}
    assert events[1]["progress"]["idMapping"] == {"b": "#1:1"}
    assert "idMapping" not in events[2]["summary"]


@respx.mock
@pytest.mark.asyncio
async def test_an_async_failure_before_the_stream_starts_raises() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(400, json={"error": "Missing @class at line 1"})
    )
    async with async_server() as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async for _ in srv.db("mydb").batch_load_stream(**ROWS):
                pass

    assert caught.value.status == 400


@respx.mock
@pytest.mark.asyncio
async def test_an_async_in_band_error_event_raises_with_its_own_status() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {"progress": {"verticesCreated": 1}},
                {"error": {"error": "boom", "status": 400, "partialCommit": True}},
            ),
        )
    )
    async with async_server() as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async for _ in srv.db("mydb").batch_load_stream(**ROWS):
                pass

    assert caught.value.status == 400
    assert caught.value.error == "boom"


@respx.mock
@pytest.mark.asyncio
async def test_async_events_before_an_in_band_error_are_yielded_first() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {"progress": {"verticesCreated": 2}},
                {"error": {"error": "boom", "status": 500}},
            ),
        )
    )
    seen: list[dict[str, Any]] = []
    async with async_server() as srv:
        with pytest.raises(ArcadeDBError):
            async for event in srv.db("mydb").batch_load_stream(**ROWS):
                seen.append(event)

    assert len(seen) == 1
    assert seen[0]["progress"]["verticesCreated"] == 2


@respx.mock
@pytest.mark.asyncio
async def test_async_status_mapped_false_is_recorded_on_the_error() -> None:
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(
        return_value=httpx.Response(
            200,
            content=_lines(
                {
                    "error": {
                        "error": "engine failure",
                        "status": 500,
                        "statusMapped": False,
                        "exception": "java.lang.IllegalStateException",
                    }
                }
            ),
        )
    )
    async with async_server() as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async for _ in srv.db("mydb").batch_load_stream(**ROWS):
                pass

    assert caught.value.status == 500
    assert caught.value.exception == "java.lang.IllegalStateException"


@respx.mock
@pytest.mark.asyncio
async def test_async_batch_load_stream_closes_the_response_when_the_caller_abandons_the_iterator() -> None:
    stream = _AsyncChunks([b'{"progress":{"verticesCreated":1}}\n', b'{"progress":{"verticesCreated":2}}\n'])
    respx.post(f"{BASE_URL}/api/v1/batch/mydb").mock(return_value=httpx.Response(200, stream=stream))
    async with async_server() as srv:
        events = srv.db("mydb").batch_load_stream(**ROWS)
        first = await events.__anext__()
        assert first["progress"]["verticesCreated"] == 1
        await events.aclose()

    assert stream.closed is True


# --- docstring parity (issue #30) ------------------------------------------------------------


def test_sync_and_async_docstrings_match() -> None:
    # Issue #30: the twins are hand-maintained and drift silently. Compare each pair's
    # __doc__ directly instead of trusting a reviewer to diff two files by eye.
    for sync_name, async_name in [("batch_load", "abatch_load"), ("batch_load_stream", "abatch_load_stream")]:
        sync_doc = inspect.getdoc(getattr(batch, sync_name)) or ""
        async_doc = inspect.getdoc(getattr(batch, async_name)) or ""
        assert sync_doc == async_doc, f"{sync_name} and {async_name} docstrings have drifted"
