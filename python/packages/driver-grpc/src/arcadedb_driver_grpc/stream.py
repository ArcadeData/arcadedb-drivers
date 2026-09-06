"""The two streaming wrappers: `stream_query` and `insert_stream`."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterable, Iterable, Iterator, Sequence
from dataclasses import dataclass

from ._generated import arcadedb_server_pb2 as messages
from ._generated.arcadedb_server_pb2_grpc import ArcadeDbServiceStub

__all__ = ["InsertStreamRequest", "insert_stream", "stream_query"]


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


@dataclass
class InsertStreamRequest:
    """A client-streaming insert.

    `chunks` is the sequence of row batches to send - each element becomes exactly one
    wire `InsertChunk`. This wrapper owns the envelope bookkeeping around those batches
    (`session_id`, `chunk_seq`, first-chunk-only `database`, final-chunk `last`); it does
    not decide how rows are batched, which is the caller's call.

    `transaction` IS FORWARDED BUT NOT HONOURED. It is set on every chunk, exactly as the
    caller gave it, because the `.proto` declares the field - but on 26.9.1 and earlier the
    server ignores `TransactionContext` for `InsertStream` entirely
    (ArcadeData/arcadedb#6607), so setting it buys no transactional guarantee. That is the
    same reason `insert_stream` is not offered on `TransactionHandle` at all: there the
    omission makes the gap visible, whereas here the field is part of the wire message and
    cannot be hidden. Do not rely on it until #6607 lands.
    """

    database: str
    chunks: Iterable[Sequence[messages.GrpcRecord]] | AsyncIterable[Sequence[messages.GrpcRecord]]
    credentials: messages.DatabaseCredentials | None = None
    options: messages.InsertOptions | None = None
    transaction: messages.TransactionContext | None = None


def _first_chunk_options(request: InsertStreamRequest) -> messages.InsertOptions:
    """The caller's options with `database` forced onto them.

    Empirically established during M1b against a real server: on 26.9.1 and every
    earlier release the server builds its `InsertContext` from `InsertOptions.database`
    ALONE and never reads `InsertChunk.database` at all, despite the .proto documenting
    the latter as REQUIRED on the first chunk. Without this mirror every stream against
    such a server fails at the deferred commit with "Invalid database name: name is
    required", even though `database` was sent exactly as the contract specifies.

    A server carrying the fix for ArcadeData/arcadedb#6597 prefers a non-empty chunk
    `database` and falls back to this one, so setting both to the same value is correct
    on either side of that fix.
    """
    options = messages.InsertOptions()
    if request.options is not None:
        options.CopyFrom(request.options)
    options.database = request.database
    return options


def _build_chunk(
    request: InsertStreamRequest,
    session_id: str,
    seq: int,
    rows: Sequence[messages.GrpcRecord],
    *,
    last: bool,
) -> messages.InsertChunk:
    chunk = messages.InsertChunk(session_id=session_id, chunk_seq=seq, rows=rows, last=last)
    if request.credentials is not None:
        chunk.credentials.CopyFrom(request.credentials)
    if request.transaction is not None:
        chunk.transaction.CopyFrom(request.transaction)
    if seq == 1:
        # `database` on the first chunk only, per the .proto contract, and mirrored
        # into options there too - see `_first_chunk_options`.
        chunk.database = request.database
        chunk.options.CopyFrom(_first_chunk_options(request))
    elif request.options is not None:
        chunk.options.CopyFrom(request.options)
    return chunk


class _EndOfStream:
    """Sentinel distinguishing "no more chunks" from a row batch that happens to be `None`.

    `next(iterator, None)` would conflate the two: a caller whose generator yields `None` -
    easy to produce from a `dict.get()` in a batching helper - would have the REST OF THE
    STREAM SILENTLY DROPPED, because the lookahead below would mistake that `None` batch for
    end-of-stream. The server would then report a smaller `received` than the caller sent and
    nothing would raise anywhere: a silent partial insert, the worst failure mode this wrapper
    could have. A private sentinel object (never equal or identical to any real value the
    caller could produce) closes that hole.
    """


_END_OF_STREAM = _EndOfStream()


def _envelope_chunks(request: InsertStreamRequest, session_id: str) -> Iterator[messages.InsertChunk]:
    """Turns `request.chunks` into wire `InsertChunk`s, adding the envelope bookkeeping.

    Validates `request.chunks` EAGERLY, in this function's own body, rather than inside the
    generator that does the actual iterating (`_envelope_chunks_inner`). A generator's body
    does not run AT ALL until the first `next()` pull - for `insert_stream`, that pull happens
    only once grpc itself starts consuming the request iterator to open the RPC. A `raise`
    written inside that generator would not fire until then, and grpc catches it there and
    re-raises its own opaque `_InactiveRpcError` (`StatusCode.UNKNOWN`, "Exception iterating
    requests!") instead of this function's message ever reaching the caller - verified against
    a real in-process server. Splitting the eager check into this plain (non-generator)
    function, which merely returns the generator `_envelope_chunks_inner` produces, is what
    makes the `TypeError` below raise synchronously in the caller's own stack frame, before any
    RPC is opened at all.
    """
    if not isinstance(request.chunks, Iterable):
        raise TypeError(
            "insert_stream: `chunks` is an async iterable, which the sync facade cannot consume. "
            "Use arcadedb_driver_grpc.aio.create_client, or pass a synchronous iterable."
        )
    return _envelope_chunks_inner(request, session_id)


def _envelope_chunks_inner(request: InsertStreamRequest, session_id: str) -> Iterator[messages.InsertChunk]:
    """The chunk-by-chunk iteration itself, once `_envelope_chunks` has confirmed `request.chunks`
    is synchronous."""
    # `request.chunks` is a synchronous `Iterable` here - `_envelope_chunks` already checked -
    # but mypy cannot see that guarantee across the function boundary, so the declared type is
    # still the full sync/async union. `iter()` only accepts the synchronous half of it.
    iterator = iter(request.chunks)  # type: ignore[arg-type]

    # The iterator is pulled MANUALLY rather than with a plain `for`, because knowing
    # which chunk is last needs one-element lookahead. Manual pulling means finalisation
    # is not automatic: if this generator is abandoned early - the RPC aborts mid-stream,
    # or the caller stops consuming - nothing would otherwise close the caller's own
    # iterator, and any `finally` they wrote around it (closing a file handle, a database
    # cursor) would never run. The try/finally makes that cleanup happen on every exit
    # path, not only on normal completion.
    try:
        current = next(iterator, _END_OF_STREAM)
        if isinstance(current, _EndOfStream):
            # An empty stream is a legitimate outcome, not an error: a filter that matched
            # nothing produces one. Send a single empty final chunk and let the server
            # answer with whatever summary it likes, rather than inventing a result or
            # raising. Verified against a real server during M1b.
            yield _build_chunk(request, session_id, 1, [], last=True)
            return

        seq = 1
        while True:
            nxt = next(iterator, _END_OF_STREAM)
            yield _build_chunk(request, session_id, seq, current, last=isinstance(nxt, _EndOfStream))
            if isinstance(nxt, _EndOfStream):
                return
            current = nxt
            seq += 1
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            close()


def insert_stream(
    raw: ArcadeDbServiceStub,
    request: InsertStreamRequest,
    *,
    timeout: float | None = None,
) -> messages.InsertSummary:
    """Streams rows to the server in chunks and returns the server's single `InsertSummary`.

    Handles the `session_id` / `chunk_seq` / `database` / `last` envelope bookkeeping a
    caller would otherwise hand-roll:

    - one `session_id` (a fresh UUID), stable for the whole stream
    - `chunk_seq` starting at 1 and incrementing by 1
    - `database` on the first chunk only, per the .proto contract, mirrored into
      `options.database` there too for compatibility with servers predating #6597
    - `last=True` on the final chunk only

    An empty `request.chunks` sends a single chunk with zero rows and `last=True` rather
    than raising.

    NOT available on a `TransactionHandle`: ArcadeData/arcadedb#6607 has the server
    ignoring `TransactionContext` here, so offering it there would imply a transactional
    guarantee the server does not honour.
    """
    return raw.InsertStream(_envelope_chunks(request, str(uuid.uuid4())), timeout=timeout)
