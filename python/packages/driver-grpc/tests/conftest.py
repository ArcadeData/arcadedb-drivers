"""Fixtures for the unit suite: a real in-process gRPC server with a recording servicer.

Deliberately not a mocked stub. gRPC has no `respx` equivalent, and mocking the stub
would skip the two properties most worth asserting - that channel interceptors really
do put `x-arcade-user` on the wire, and that `insert_stream` emits the exact envelope
sequence. A fake servicer records what actually arrived.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent import futures

import grpc
import pytest
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
        # Configurable responses.
        self.transaction_id = "tx-1"
        self.commit_committed = True
        self.commit_message = ""
        self.commit_raises = False
        self.rollback_raises = False
        self.stream_batches: list[list[str]] = [["a", "b"], ["c"]]

    def _record(self, name: str, context: grpc.ServicerContext) -> None:
        self.calls.append(name)
        self.metadata = [(k, v) for k, v in context.invocation_metadata()]

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
        return pb2.ExecuteCommandResponse(success=True)

    def InsertStream(
        self, request_iterator: Iterator[pb2.InsertChunk], context: grpc.ServicerContext
    ) -> pb2.InsertSummary:
        self._record("InsertStream", context)
        received = 0
        for chunk in request_iterator:
            self.insert_chunks.append(chunk)
            received += len(chunk.rows)
        return pb2.InsertSummary(received=received, inserted=received)

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
