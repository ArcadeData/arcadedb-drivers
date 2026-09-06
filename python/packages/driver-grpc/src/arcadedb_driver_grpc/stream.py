"""The two streaming wrappers: `stream_query` and `insert_stream`."""

from __future__ import annotations

from collections.abc import Iterator

from ._generated import arcadedb_server_pb2 as messages
from ._generated.arcadedb_server_pb2_grpc import ArcadeDbServiceStub

__all__ = ["stream_query"]


def stream_query(
    raw: ArcadeDbServiceStub,
    request: messages.StreamQueryRequest,
    *,
    timeout: float | None = None,
) -> Iterator[messages.GrpcRecord]:
    """Streams a query's results row by row.

    Wraps the server-streaming `StreamQuery`, flattening the batching the wire protocol
    uses: the server sends `QueryResult` batches, this yields each `GrpcRecord` on its own.

    Thin by design. `retrieval_mode` and `batch_size` pass through to the server exactly
    as given and this wrapper picks no defaults for either, because CURSOR,
    MATERIALIZE_ALL and PAGED have materially different memory and consistency behaviour
    that only the caller can judge.
    """
    for result in raw.StreamQuery(request, timeout=timeout):
        yield from result.records
