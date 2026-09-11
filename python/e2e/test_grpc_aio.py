"""End-to-end tests for arcadedb-driver-grpc's ASYNC facade against a real ArcadeDB server.

Companion to `test_grpc.py`, which exercises only the sync client. The async facade has
plumbing with no sync equivalent - `_AsyncAuthInterceptor`, `_aiter_chunks`,
`AsyncTransaction`, `AsyncTransactionHandle` - and none of it had ever been run against a
real server before this file existed; every other async-facade test (`test_aio.py`) runs
against `RecordingServicer`, an in-process fake.

Reuses the SAME `grpc_server`/`grpc_database` fixtures `test_grpc.py` uses, deliberately -
a second container here would test nothing about the async facade that a shared one
does not, and would double this suite's startup cost for no benefit.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

import grpc
import pytest
import pytest_asyncio
from arcadedb_driver_grpc import InsertStreamRequest, TimeSeriesWriteStreamRequest, messages
from arcadedb_driver_grpc.aio import AsyncArcadeDBGrpcClient, create_client
from arcadedb_driver_grpc.auth import async_interceptors, password_auth

from .conftest import ROOT_PASSWORD

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_client(grpc_server: tuple[str, str], grpc_database: str) -> AsyncIterator[AsyncArcadeDBGrpcClient]:
    _, target = grpc_server
    async with create_client(
        target,
        auth=password_auth("root", ROOT_PASSWORD, grpc_database),
        # The container speaks plaintext gRPC, so the guard has to be opted out of
        # explicitly. That it must be opted out of here IS the guard working.
        insecure=True,
    ) as client:
        yield client


def _person(name: str) -> messages.GrpcRecord:
    return messages.GrpcRecord(type="Person", properties={"name": messages.GrpcValue(string_value=name)})


# The `grpc.aio` twin of `test_grpc.py`'s `_CallRecorder`. Same story on the
# `# type: ignore[type-arg]`s: grpc-stubs declares these four base classes
# `Generic[TRequest, TResponse]` for mypy's benefit, but the real runtime classes are not
# `typing.Generic` and cannot be subscripted at class definition time.
class _AsyncCallRecorder(
    grpc.aio.UnaryUnaryClientInterceptor,  # type: ignore[type-arg]
    grpc.aio.UnaryStreamClientInterceptor,  # type: ignore[type-arg]
    grpc.aio.StreamUnaryClientInterceptor,  # type: ignore[type-arg]
    grpc.aio.StreamStreamClientInterceptor,  # type: ignore[type-arg]
):
    """Records each outgoing RPC's method name, then forwards the call unchanged.

    Used only by `test_async_transaction_rolls_back`, to assert the MECHANISM (that
    RollbackTransaction was actually issued and CommitTransaction was not) rather than
    only the row-absence outcome - exactly the reasoning `test_grpc.py`'s sync
    `_CallRecorder` documents.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _record(self, method: str | bytes) -> None:
        # grpc-stubs types `ClientCallDetails.method` as `str`, but against a real
        # `grpc.aio` channel it arrives as `bytes` - decoded here rather than narrowing
        # the parameter, so this tolerates whichever grpc actually hands it.
        name = method.decode() if isinstance(method, bytes) else method
        self.calls.append(name.rsplit("/", 1)[-1])

    async def intercept_unary_unary(self, continuation: Any, client_call_details: Any, request: Any) -> Any:
        self._record(client_call_details.method)
        return await continuation(client_call_details, request)

    async def intercept_unary_stream(self, continuation: Any, client_call_details: Any, request: Any) -> Any:
        self._record(client_call_details.method)
        return await continuation(client_call_details, request)

    async def intercept_stream_unary(self, continuation: Any, client_call_details: Any, request_iterator: Any) -> Any:
        self._record(client_call_details.method)
        return await continuation(client_call_details, request_iterator)

    async def intercept_stream_stream(self, continuation: Any, client_call_details: Any, request_iterator: Any) -> Any:
        self._record(client_call_details.method)
        return await continuation(client_call_details, request_iterator)


async def _names(client: AsyncArcadeDBGrpcClient, database: str, marker: str) -> list[str]:
    rows = [
        r
        async for r in client.stream_query(
            messages.StreamQueryRequest(
                database=database, language="sql", query=f"SELECT FROM Person WHERE name LIKE '{marker}%'"
            )
        )
    ]
    return sorted(r.properties["name"].string_value for r in rows)


async def test_async_raw_query_reaches_the_server(async_client: AsyncArcadeDBGrpcClient, grpc_database: str) -> None:
    response = await async_client.raw.ExecuteQuery(
        messages.ExecuteQueryRequest(database=grpc_database, language="sql", query="SELECT FROM Person")
    )
    assert response is not None


async def test_async_execute_command_inserts_a_row(async_client: AsyncArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"aac{uuid.uuid4().hex[:8]}"
    await async_client.raw.ExecuteCommand(
        messages.ExecuteCommandRequest(
            database=grpc_database, language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'"
        )
    )
    assert await _names(async_client, grpc_database, marker) == [f"{marker}-a"]


async def test_async_stream_query_returns_rows(async_client: AsyncArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"asq{uuid.uuid4().hex[:8]}"
    await async_client.raw.ExecuteCommand(
        messages.ExecuteCommandRequest(
            database=grpc_database, language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'"
        )
    )
    assert await _names(async_client, grpc_database, marker) == [f"{marker}-a"]


async def test_async_insert_stream_inserts_rows(async_client: AsyncArcadeDBGrpcClient, grpc_database: str) -> None:
    # Same defect this asserts against on the sync side (test_grpc.py's
    # test_insert_stream_inserts_rows): on a real 26.8.1 or earlier server, an insert_stream
    # that does not mirror `database` into `options` inserts nothing - inserted=0, or a
    # deferred-commit failure with "Invalid database name: name is required". As on the sync
    # side, the pinned 26.10.1-SNAPSHOT image carries the #6597 fix (released in 26.9.1), so
    # this test passes with or without the mirror; see the sync test for the separate
    # measurement that established that boundary. The async facade's own `insert_stream`
    # shares `stream._build_chunk` with the sync one, but had never been run against a real
    # server before this test.
    marker = f"ais{uuid.uuid4().hex[:8]}"

    async def chunks() -> AsyncIterator[list[messages.GrpcRecord]]:
        yield [_person(f"{marker}-a"), _person(f"{marker}-b")]
        yield [_person(f"{marker}-c")]

    summary = await async_client.insert_stream(
        InsertStreamRequest(
            database=grpc_database,
            options=messages.InsertOptions(target_class="Person"),
            chunks=chunks(),
        )
    )
    assert summary.inserted == 3
    assert await _names(async_client, grpc_database, marker) == [f"{marker}-a", f"{marker}-b", f"{marker}-c"]


async def test_async_transaction_commits(async_client: AsyncArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"atc{uuid.uuid4().hex[:8]}"
    async with async_client.transaction(grpc_database) as tx:
        await tx.execute_command(
            messages.ExecuteCommandRequest(language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'")
        )
    assert await _names(async_client, grpc_database, marker) == [f"{marker}-a"]


async def test_async_transaction_rolls_back(
    grpc_server: tuple[str, str], grpc_database: str, async_client: AsyncArcadeDBGrpcClient
) -> None:
    # Asserts the MECHANISM, not only the row absence - the same reasoning
    # `test_grpc.py`'s `test_transaction_rolls_back` documents at length: an insert that
    # silently failed, or a transaction simply left open and never resolved either way,
    # would also leave no rows through ordinary isolation rather than cleanup. A
    # separate, recorded channel proves RollbackTransaction was actually issued and
    # CommitTransaction was not, in addition to the row-absence check below.
    _, target = grpc_server
    marker = f"atr{uuid.uuid4().hex[:8]}"
    recorder = _AsyncCallRecorder()
    auth_interceptors = async_interceptors(password_auth("root", ROOT_PASSWORD, grpc_database))
    # grpc-stubs aliases `grpc.aio.ClientInterceptor` to a private sentinel type that no
    # concrete interceptor nominally matches - the same cast `auth.async_interceptors`
    # itself needs for the same reason.
    interceptors = cast("list[grpc.aio.ClientInterceptor]", [recorder, *auth_interceptors])
    channel = grpc.aio.insecure_channel(target, interceptors=interceptors)
    spied_client = AsyncArcadeDBGrpcClient(channel)
    try:
        sentinel = RuntimeError("boom")
        with pytest.raises(RuntimeError) as caught:
            async with spied_client.transaction(grpc_database) as tx:
                await tx.execute_command(
                    messages.ExecuteCommandRequest(
                        language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'"
                    )
                )
                raise sentinel
        assert caught.value is sentinel
    finally:
        await spied_client.close()

    assert "RollbackTransaction" in recorder.calls
    assert "CommitTransaction" not in recorder.calls

    # Belt and suspenders, and the brief's explicit requirement: the row must also be
    # ABSENT, not merely that the exception propagated and RollbackTransaction fired.
    assert await _names(async_client, grpc_database, marker) == []


async def test_async_vector_hybrid_and_fulltext_search_through_raw_and_the_handle(
    async_client: AsyncArcadeDBGrpcClient, grpc_database: str, grpc_vector_index: tuple[str, str]
) -> None:
    # Covers both reachability paths D-M5-1 describes, on the async facade: raw outside any
    # transaction, and bound to an open one through `AsyncTransactionHandle`. No top-level
    # `async_client.vector_search` alias exists either.
    vector_index_name, fulltext_index_name = grpc_vector_index

    raw_search = await async_client.raw.VectorSearch(
        messages.VectorSearchRequest(
            database=grpc_database, index_name=vector_index_name, query_vector=[1, 0, 0, 0], k=10
        )
    )
    assert len(raw_search.results) > 0
    assert raw_search.count == 3
    assert raw_search.truncated is False
    # Nearest first: the query vector IS `red-apple`'s embedding, so its distance is exactly 0.
    assert raw_search.results[0].distance == 0
    distances = [hit.distance for hit in raw_search.results]
    assert distances == sorted(distances)

    async with async_client.transaction(grpc_database) as tx:
        search = await tx.vector_search(
            messages.VectorSearchRequest(index_name=vector_index_name, query_vector=[1, 0, 0, 0], k=10)
        )
        hybrid = await tx.hybrid_search(
            messages.HybridSearchRequest(
                vector_index_name=vector_index_name,
                query_vector=[1, 0, 0, 0],
                fulltext_index_name=fulltext_index_name,
                fulltext_query="apple",
                k=10,
            )
        )
        fulltext = await tx.full_text_search(
            messages.FullTextSearchRequest(query_text="apple", index_name=fulltext_index_name)
        )

    assert len(search.results) > 0
    assert search.truncated is False
    assert len(hybrid.results) > 0
    assert hybrid.fused is True
    assert len(fulltext.results) > 0


async def test_async_time_series_write_stream_multi_chunk_then_query_and_latest_through_a_transaction(
    async_client: AsyncArcadeDBGrpcClient, grpc_database: str, grpc_timeseries_type: str
) -> None:
    """The async twin of `test_grpc.py`'s combined time-series test, same reasoning: done
    together in one test so none of the three assertions depends on execution order against
    the shared session-scoped database.

    1. A MULTI-CHUNK write stream (two chunks, via an async generator - the shape this
       facade's own `time_series_write_stream` had never been run against a real server
       through before this test) - proving the per-chunk envelope actually works end to end.
    2. `time_series_query` returns the points just written, non-empty.
    3. `time_series_latest`, bound to an open transaction handle, returns the most recent
       point.
    """
    marker_a = messages.GrpcValue(string_value="A")
    marker_b = messages.GrpcValue(string_value="B")

    async def chunks() -> AsyncIterator[list[messages.TimeSeriesPoint]]:
        yield [
            messages.TimeSeriesPoint(
                timestamp=1000, tags={"sensor": marker_a}, fields={"value": messages.GrpcValue(double_value=1.1)}
            ),
            messages.TimeSeriesPoint(
                timestamp=2000, tags={"sensor": marker_a}, fields={"value": messages.GrpcValue(double_value=1.2)}
            ),
        ]
        yield [
            messages.TimeSeriesPoint(
                timestamp=3000, tags={"sensor": marker_b}, fields={"value": messages.GrpcValue(double_value=2.1)}
            ),
        ]

    summary = await async_client.time_series_write_stream(
        TimeSeriesWriteStreamRequest(
            database=grpc_database,
            type=grpc_timeseries_type,
            precision=messages.TimeSeriesPrecision.TS_PRECISION_MILLISECONDS,
            chunks=chunks(),
        )
    )
    assert summary.received == 3
    assert summary.written == 3
    assert summary.dropped == 0

    results = [
        result
        async for result in async_client.time_series_query(
            messages.TimeSeriesQueryRequest(database=grpc_database, type=grpc_timeseries_type)
        )
    ]
    rows = [row for result in results for row in result.rows]
    assert len(rows) > 0

    async with async_client.transaction(grpc_database) as tx:
        latest = await tx.time_series_latest(messages.TimeSeriesLatestRequest(type=grpc_timeseries_type))

    assert latest.found is True
    ts_index = list(latest.columns).index("ts")
    assert latest.latest.values[ts_index].int64_value == 3000


async def test_async_empty_time_series_write_stream_is_accepted_with_an_all_zero_summary(
    async_client: AsyncArcadeDBGrpcClient, grpc_database: str, grpc_timeseries_type: str
) -> None:
    """The async twin of `test_grpc.py`'s empty-stream test - same server behaviour, reached
    through the async facade: an empty `chunks` sends zero wire chunks, and the server
    accepts a stream that never named `database`/`type`/`precision` cleanly, answering with
    every count at zero rather than raising.
    """
    summary = await async_client.time_series_write_stream(
        TimeSeriesWriteStreamRequest(
            database=grpc_database,
            type=grpc_timeseries_type,
            precision=messages.TimeSeriesPrecision.TS_PRECISION_MILLISECONDS,
            chunks=[],
        )
    )
    assert summary.received == 0
    assert summary.written == 0
    assert summary.dropped == 0
    assert list(summary.unknown_types) == []
    assert list(summary.non_time_series_types) == []
    assert list(summary.unavailable_types) == []
