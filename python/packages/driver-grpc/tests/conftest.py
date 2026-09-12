"""Fixtures for the unit suite: a real in-process gRPC server with a recording servicer.

Deliberately not a mocked stub. gRPC has no `respx` equivalent, and mocking the stub
would skip the two properties most worth asserting - that channel interceptors really
do put `x-arcade-user` on the wire, and that `insert_stream` emits the exact envelope
sequence. A fake servicer records what actually arrived.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from concurrent import futures

import grpc
import pytest
import pytest_asyncio
from arcadedb_driver_grpc._generated import arcadedb_server_pb2 as pb2
from arcadedb_driver_grpc._generated import arcadedb_server_pb2_grpc as pb2_grpc


class RecordingServicer(pb2_grpc.ArcadeDbServiceServicer):
    """Records what each RPC received and answers with whatever the test configured."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        # grpc-stubs types real invocation metadata values as `str | bytes`
        # (grpc.Metadata), not plain `str` - every value this fixture actually sees
        # is `str`, but the declared type has to match what `invocation_metadata()`
        # can return.
        self.metadata: list[tuple[str, str | bytes]] = []
        self.insert_chunks: list[pb2.InsertChunk] = []
        self.command_requests: list[pb2.ExecuteCommandRequest] = []
        self.stream_query_requests: list[pb2.StreamQueryRequest] = []
        self.rollback_requests: list[pb2.RollbackTransactionRequest] = []
        self.vector_requests: list[pb2.VectorSearchRequest] = []
        self.hybrid_requests: list[pb2.HybridSearchRequest] = []
        self.fulltext_requests: list[pb2.FullTextSearchRequest] = []
        self.ts_chunks: list[pb2.TimeSeriesWriteChunk] = []
        self.ts_query_requests: list[pb2.TimeSeriesQueryRequest] = []
        self.ts_latest_requests: list[pb2.TimeSeriesLatestRequest] = []
        # `time_remaining()` is how a call's `timeout=` reaching the server is observed:
        # `grpc._server`'s sync `ServicerContext` returns a huge sentinel float (~9.2e18)
        # when no deadline was set and the actual remaining seconds otherwise; `grpc.aio`'s
        # returns `None` in the no-deadline case and a float otherwise. Either way, a small
        # bounded value here is only reachable by a caller-supplied `timeout=`.
        self.time_remaining: float | None = None
        # Per-ExecuteCommand-call metadata/deadline, index-aligned with `command_requests`.
        # A transaction test's `ExecuteCommand` is never the LAST call on the wire - the
        # `with` block's `CommitTransaction` follows it and would overwrite `self.metadata`
        # / `self.time_remaining` above before the test gets to look at them. These two
        # lists are what a test asserting a specific call's timeout/metadata should read.
        self.command_metadata: list[list[tuple[str, str | bytes]]] = []
        self.command_time_remaining: list[float | None] = []
        # Configurable responses.
        self.transaction_id = "tx-1"
        self.commit_committed = True
        self.commit_message = ""
        self.commit_raises = False
        self.rollback_raises = False
        self.stream_batches: list[list[str]] = [["a", "b"], ["c"]]
        self.ts_summary = pb2.TimeSeriesWriteSummary()
        self.ts_query_results: list[pb2.TimeSeriesQueryResult] = []
        self.ts_latest_response = pb2.TimeSeriesLatestResponse()

    def _record(self, name: str, context: grpc.ServicerContext) -> None:
        self.calls.append(name)
        self.metadata = [(k, v) for k, v in context.invocation_metadata()]
        self.time_remaining = context.time_remaining()

    def StreamQuery(self, request: pb2.StreamQueryRequest, context: grpc.ServicerContext) -> Iterator[pb2.QueryResult]:
        self._record("StreamQuery", context)
        self.stream_query_requests.append(request)
        for batch in self.stream_batches:
            yield pb2.QueryResult(records=[pb2.GrpcRecord(rid=rid) for rid in batch])

    def ExecuteCommand(
        self, request: pb2.ExecuteCommandRequest, context: grpc.ServicerContext
    ) -> pb2.ExecuteCommandResponse:
        self._record("ExecuteCommand", context)
        self.command_requests.append(request)
        self.command_metadata.append(list(context.invocation_metadata()))
        self.command_time_remaining.append(context.time_remaining())
        return pb2.ExecuteCommandResponse(success=True)

    def VectorSearch(self, request: pb2.VectorSearchRequest, context: grpc.ServicerContext) -> pb2.VectorSearchResponse:
        self._record("VectorSearch", context)
        self.vector_requests.append(request)
        return pb2.VectorSearchResponse(index_name=request.index_name)

    def HybridSearch(self, request: pb2.HybridSearchRequest, context: grpc.ServicerContext) -> pb2.HybridSearchResponse:
        self._record("HybridSearch", context)
        self.hybrid_requests.append(request)
        return pb2.HybridSearchResponse(vector_index_name=request.vector_index_name)

    def FullTextSearch(
        self, request: pb2.FullTextSearchRequest, context: grpc.ServicerContext
    ) -> pb2.FullTextSearchResponse:
        self._record("FullTextSearch", context)
        self.fulltext_requests.append(request)
        return pb2.FullTextSearchResponse(index_name=request.index_name)

    def InsertStream(
        self, request_iterator: Iterator[pb2.InsertChunk], context: grpc.ServicerContext
    ) -> pb2.InsertSummary:
        self._record("InsertStream", context)
        received = 0
        for chunk in request_iterator:
            self.insert_chunks.append(chunk)
            received += len(chunk.rows)
        return pb2.InsertSummary(received=received, inserted=received)

    def TimeSeriesWriteStream(
        self, request_iterator: Iterator[pb2.TimeSeriesWriteChunk], context: grpc.ServicerContext
    ) -> pb2.TimeSeriesWriteSummary:
        self._record("TimeSeriesWriteStream", context)
        for chunk in request_iterator:
            self.ts_chunks.append(chunk)
        return self.ts_summary

    def TimeSeriesQuery(
        self, request: pb2.TimeSeriesQueryRequest, context: grpc.ServicerContext
    ) -> Iterator[pb2.TimeSeriesQueryResult]:
        self._record("TimeSeriesQuery", context)
        self.ts_query_requests.append(request)
        yield from self.ts_query_results

    def TimeSeriesLatest(
        self, request: pb2.TimeSeriesLatestRequest, context: grpc.ServicerContext
    ) -> pb2.TimeSeriesLatestResponse:
        self._record("TimeSeriesLatest", context)
        self.ts_latest_requests.append(request)
        return self.ts_latest_response

    def BeginTransaction(
        self, request: pb2.BeginTransactionRequest, context: grpc.ServicerContext
    ) -> pb2.BeginTransactionResponse:
        self._record("BeginTransaction", context)
        return pb2.BeginTransactionResponse(transaction_id=self.transaction_id)

    def CommitTransaction(
        self, request: pb2.CommitTransactionRequest, context: grpc.ServicerContext
    ) -> pb2.CommitTransactionResponse:
        self._record("CommitTransaction", context)
        if self.commit_raises:
            context.abort(grpc.StatusCode.INTERNAL, "commit failed")
            raise AssertionError("unreachable - context.abort raises")
        return pb2.CommitTransactionResponse(success=True, committed=self.commit_committed, message=self.commit_message)

    def RollbackTransaction(
        self, request: pb2.RollbackTransactionRequest, context: grpc.ServicerContext
    ) -> pb2.RollbackTransactionResponse:
        self._record("RollbackTransaction", context)
        self.rollback_requests.append(request)
        if self.rollback_raises:
            context.abort(grpc.StatusCode.INTERNAL, "rollback failed")
            raise AssertionError("unreachable - context.abort raises")
        return pb2.RollbackTransactionResponse(success=True, rolled_back=True)


@pytest.fixture
def fake_server() -> Iterator[tuple[str, RecordingServicer]]:
    """Yields `(target, servicer)` for a server on an ephemeral loopback port."""
    # mypy-protobuf's generated .pyi marks every RPC on the servicer base class
    # `abstractmethod` for typing purposes; the runtime .py does not, and this
    # fixture legitimately implements only the RPCs its tests exercise.
    servicer = RecordingServicer()  # type: ignore[abstract]
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pb2_grpc.add_ArcadeDbServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        yield f"127.0.0.1:{port}", servicer
    finally:
        server.stop(grace=None)


class RecordingAdminServicer(pb2_grpc.ArcadeDbAdminServiceServicer):
    """Records what each RPC received, for the ADMIN (control-plane) service.

    Separate from `RecordingServicer` above rather than one class implementing both:
    `ArcadeDbServiceServicer` and `ArcadeDbAdminServiceServicer` are two distinct generated
    base classes, so nothing could inherit from both and dispatch correctly to
    `add_..._to_server` for each. `Ping` is the only RPC implemented here - the fixtures
    below exist to prove the data plane's auth interceptors and shared channel also reach
    the admin service, not to re-test every one of its 44 RPCs (that is the bare stub's
    job, not this fixture's).
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.metadata: list[tuple[str, str | bytes]] = []

    def _record(self, name: str, context: grpc.ServicerContext) -> None:
        self.calls.append(name)
        self.metadata = [(k, v) for k, v in context.invocation_metadata()]

    def Ping(self, request: pb2.PingRequest, context: grpc.ServicerContext) -> pb2.PingResponse:
        self._record("Ping", context)
        return pb2.PingResponse(ok=True)


@pytest.fixture
def fake_admin_server() -> Iterator[tuple[str, RecordingAdminServicer]]:
    """Yields `(target, servicer)` for a server hosting only `ArcadeDbAdminService`.

    A real ArcadeDB server hosts both `ArcadeDbService` and `ArcadeDbAdminService` on one
    port; this fixture hosts only the admin one because nothing in this suite needs the
    combination - each test drives whichever plane it is exercising.
    """
    servicer = RecordingAdminServicer()  # type: ignore[abstract]
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pb2_grpc.add_ArcadeDbAdminServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        yield f"127.0.0.1:{port}", servicer
    finally:
        server.stop(grace=None)


@pytest_asyncio.fixture
async def async_fake_admin_server() -> AsyncIterator[tuple[str, RecordingAdminServicer]]:
    """The `grpc.aio` twin of `fake_admin_server`. See `async_fake_server`'s docstring for
    why this needs `@pytest_asyncio.fixture` rather than the plain decorator.
    """
    servicer = RecordingAdminServicer()  # type: ignore[abstract]
    server = grpc.aio.server()
    pb2_grpc.add_ArcadeDbAdminServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        yield f"127.0.0.1:{port}", servicer
    finally:
        await server.stop(grace=None)


@pytest_asyncio.fixture
async def async_fake_server() -> AsyncIterator[tuple[str, RecordingServicer]]:
    """The `grpc.aio` twin of `fake_server`, yielding `(target, servicer)`.

    ONE servicer serves both suites. `RecordingServicer`'s methods are plain sync
    `def`s, and `grpc.aio` accepts them: it calls a non-coroutine handler directly and
    treats the generator a server-streaming handler returns as the response stream.
    Verified here for all three call shapes the async tests exercise - unary-unary
    (ExecuteCommand), unary-stream (StreamQuery) and stream-unary (InsertStream).
    Duplicating the recording logic into an async servicer would give the two suites
    two different notions of what "what arrived on the wire" means.

    `@pytest_asyncio.fixture`, not `@pytest.fixture`: under `asyncio_mode = "strict"`
    the plain decorator hands the test the un-awaited async generator object itself.
    """
    # Same `# type: ignore[abstract]` story as `fake_server` above: mypy-protobuf marks
    # every RPC on the generated servicer base `abstractmethod`, the runtime .py does not.
    servicer = RecordingServicer()  # type: ignore[abstract]
    server = grpc.aio.server()
    pb2_grpc.add_ArcadeDbServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        yield f"127.0.0.1:{port}", servicer
    finally:
        await server.stop(grace=None)
