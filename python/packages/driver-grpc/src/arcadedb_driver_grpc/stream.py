"""The streaming wrappers: `stream_query`, `insert_stream`, `time_series_query` and
`time_series_write_stream`."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterable, Iterable, Iterator, Sequence
from dataclasses import dataclass

from ._generated import arcadedb_server_pb2 as messages
from ._generated.arcadedb_server_pb2_grpc import ArcadeDbServiceStub

__all__ = [
    "InsertStreamRequest",
    "TimeSeriesWriteStreamRequest",
    "insert_stream",
    "stream_query",
    "time_series_query",
    "time_series_write_stream",
]


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


def time_series_query(
    raw: ArcadeDbServiceStub,
    request: messages.TimeSeriesQueryRequest,
    *,
    timeout: float | None = None,
) -> Iterator[messages.TimeSeriesQueryResult]:
    """Streams a time-series answer message by message.

    Wraps the server-streaming `TimeSeriesQuery`. Deliberately THINNER than `stream_query`
    above, which flattens `QueryResult` batches into individual `GrpcRecord`s:
    `TimeSeriesQueryResult` cannot be flattened the same way. `truncated` and `last` are
    carried per-message (`truncated` is only meaningful on the message where `last` is
    true), and a raw answer's `rows` versus an aggregated answer's `buckets` are shaped
    differently. Flattening either away would throw away the information a caller needs to
    tell "the stream ended" from "the stream ended early because of `limit`" - so this
    yields the messages exactly as the server sent them.

    Also reachable, bound to an open transaction, as `TransactionHandle.time_series_query`
    (see `transaction.py`), since `TimeSeriesQueryRequest` carries a `transaction` field
    (issue #7370): a query naming an open transaction runs on that transaction's own
    thread and observes its uncommitted points, where a query with no transaction runs on
    a gRPC worker and sees only committed data.
    """
    yield from raw.TimeSeriesQuery(request, timeout=timeout)


@dataclass
class InsertStreamRequest:
    """A client-streaming insert.

    `chunks` is the sequence of row batches to send - each element becomes exactly one
    wire `InsertChunk`. This wrapper owns the envelope bookkeeping around those batches
    (`session_id`, `chunk_seq`, first-chunk-only `database`, final-chunk `last`); it does
    not decide how rows are batched, which is the caller's call.

    `transaction` IS FORWARDED. It is set on every chunk, exactly as the caller gave it,
    because the `.proto` declares the field. On 26.8.1 and earlier the server ignored
    `TransactionContext` for `InsertStream` entirely (ArcadeData/arcadedb#6607), so setting
    it bought no transactional guarantee; that is why `insert_stream` is not offered on
    `TransactionHandle` at all - there the omission makes the gap visible, whereas here the
    field is part of the wire message and cannot be hidden.

    #6607 HAS since landed (`79d931070b`, released in 26.9.1). Measured against real
    26.8.1, 26.9.1 and 26.10.1-SNAPSHOT servers - begin over `BeginTransaction`, insert
    with that server-issued `transaction_id`, then roll back - the rows survive the
    rollback on 26.8.1 and are correctly discarded on both later versions, with a commit
    persisting them on all three. So the guarantee IS honoured on every server version this
    package supports, and the `TransactionHandle` omission is now removable. Lifting it adds
    public surface, so it is tracked as a follow-up rather than done during a contract
    adoption.
    """

    database: str
    chunks: Iterable[Sequence[messages.GrpcRecord]] | AsyncIterable[Sequence[messages.GrpcRecord]]
    credentials: messages.DatabaseCredentials | None = None
    options: messages.InsertOptions | None = None
    transaction: messages.TransactionContext | None = None


def _first_chunk_options(request: InsertStreamRequest) -> messages.InsertOptions:
    """The caller's options with `database` forced onto them.

    Empirically established during M1b against a real server, and re-measured when this
    package adopted the 26.10.1-SNAPSHOT contract: on 26.8.1 and every earlier release the
    server builds its `InsertContext` from `InsertOptions.database` ALONE and never reads
    `InsertChunk.database` at all, despite the .proto documenting the latter as REQUIRED on
    the first chunk. Without this mirror a stream against such a server inserts nothing - it
    reports the rows as `received` with `inserted=0`, or fails at the deferred commit with
    "Invalid database name: name is required" - even though `database` was sent exactly as
    the contract specifies.

    A server carrying the fix for ArcadeData/arcadedb#6597 (`7ccade7348`, released in
    26.9.1) prefers a non-empty chunk `database` and falls back to this one, so setting both
    to the same value is correct on either side of that fix. Measured directly: a
    single-chunk stream with `options.database` left empty inserts 0 of 2 rows on 26.8.1 and
    2 of 2 on both 26.9.1 and 26.10.1-SNAPSHOT.

    Every server version this package supports (the README's compatibility table starts at
    26.9.1) therefore carries the fix, so this mirror is belt-and-braces rather than
    load-bearing today. It is kept because removing it is a behaviour change; retiring it is
    tracked as a follow-up.
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
        # `callable(...)`, not merely `is not None`: a custom iterable that happens to
        # carry a non-callable attribute named `close` (a plain data field, unrelated to
        # generator cleanup) would otherwise make this raise `TypeError` while trying to
        # call it, which is worse than the missing cleanup this guard exists to provide.
        close = getattr(iterator, "close", None)
        if callable(close):
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
      (26.8.1 and earlier; see `_first_chunk_options`)
    - `last=True` on the final chunk only

    An empty `request.chunks` sends a single chunk with zero rows and `last=True` rather
    than raising.

    NOT available on a `TransactionHandle`: on 26.8.1 and earlier, ArcadeData/arcadedb#6607
    had the server ignoring `TransactionContext` here, so offering it there would have
    implied a transactional guarantee the server did not honour. That fix shipped in 26.9.1
    and the omission is now removable - see `InsertStreamRequest` for the measurement and
    why lifting it is a follow-up rather than part of a contract adoption.
    """
    return raw.InsertStream(_envelope_chunks(request, str(uuid.uuid4())), timeout=timeout)


@dataclass
class TimeSeriesWriteStreamRequest:
    """A client-streaming time-series write.

    `chunks` is the sequence of point batches to send - each element becomes exactly one
    wire `TimeSeriesWriteChunk`. Unlike `InsertStreamRequest`, there is no
    session/sequence/last envelope for this wrapper to own: `TimeSeriesWriteChunk` declares
    only `database`, `credentials`, `type` and `precision` alongside its `points`, with no
    `session_id`, `chunk_seq` or `last` field on the message at all - so those four are
    simply repeated on every chunk (see `_build_time_series_chunk`). Do NOT port
    `insert_stream`'s first-chunk-only `database`-mirror-into-options workaround here: that
    exists for ArcadeData/arcadedb#6597, a bug confirmed specific to
    `InsertStream`/`InsertContext` (closed, fixed in 26.9.1); `TimeSeriesWriteChunk` was
    never shown to share it, and copying the workaround would be cargo-culting a fix onto
    an RPC that never needed one.

    Repeating the envelope on every chunk is a deliberate SIMPLIFICATION, not something the
    `.proto` asks for - an earlier version of this docstring claimed the contract required
    it, and the contract says the opposite. `TimeSeriesWriteChunk.database` is documented
    there as "REQUIRED on the first chunk; ignored on later ones (the server caches the
    first chunk's database)", so a first-chunk-only semantic DOES exist on this RPC.
    Sending `database` again on later chunks is harmless precisely because the server
    throws those copies away, and it spares this wrapper a first-chunk special case it has
    no other reason to carry. The repetition does cost one thing: the contract documents
    `type` as a per-CHUNK default and advertises switching measurement between chunks, so a
    single stream-wide `type` cannot express that. This wrapper does not expose the
    per-chunk default - a caller who needs to mix measurements sets `type` on each
    `TimeSeriesPoint` instead, which still works.

    `precision` is REQUIRED here, deliberately (D-M6-1) - the one place this wrapper
    diverges from "pass everything through unchanged". `TimeSeriesPrecision`'s proto3 zero
    value is `TS_PRECISION_MILLISECONDS` (0), and the wire cannot distinguish "the caller
    omitted precision" from "the caller explicitly chose milliseconds". The HTTP
    `/ts/{database}/write` endpoint speaks InfluxDB Line Protocol, whose omitted-precision
    default is NANOSECONDS - a factor of 10**6 away. A caller porting a working HTTP ingest
    to gRPC who drops this field would have every timestamp misread by that factor,
    silently, with no error on either side. Requiring the field on this dataclass (no
    default) removes that failure mode by construction rather than documenting around it.

    `transaction` is NOT a field here, unlike `InsertStreamRequest` - `TimeSeriesWriteChunk`
    carries no `transaction` field on the wire at all, so there is nothing to forward and
    `time_series_write_stream` is correspondingly never offered on `TransactionHandle`.
    """

    database: str
    type: str
    precision: messages.TimeSeriesPrecision.ValueType
    chunks: Iterable[Sequence[messages.TimeSeriesPoint]] | AsyncIterable[Sequence[messages.TimeSeriesPoint]]
    credentials: messages.DatabaseCredentials | None = None


def _build_time_series_chunk(
    request: TimeSeriesWriteStreamRequest, points: Sequence[messages.TimeSeriesPoint]
) -> messages.TimeSeriesWriteChunk:
    """Builds one wire `TimeSeriesWriteChunk`, setting `database`, `type` and `precision`
    from `request` on EVERY chunk - see `TimeSeriesWriteStreamRequest` for why this,
    unlike `insert_stream`'s envelope, needs no first-chunk-only special case."""
    chunk = messages.TimeSeriesWriteChunk(
        database=request.database, type=request.type, precision=request.precision, points=points
    )
    if request.credentials is not None:
        chunk.credentials.CopyFrom(request.credentials)
    return chunk


def _time_series_chunks_inner(request: TimeSeriesWriteStreamRequest) -> Iterator[messages.TimeSeriesWriteChunk]:
    """The chunk-by-chunk iteration itself, once `_envelope_time_series_chunks` has
    confirmed `request.chunks` is synchronous.

    No one-element lookahead is needed here, unlike `_envelope_chunks_inner`: there is no
    `last` flag to compute, so a plain `for` loop suffices. That loop does NOT, by itself,
    close `request.chunks` if this generator is abandoned early (a plain Python `for` never
    closes the iterable it consumes on early exit - unlike a JS `for await...of`, whose
    IteratorClose semantics give the TypeScript twin this behaviour for free without a
    try/finally of its own). The try/finally below is what makes that cleanup happen here
    too, exactly as `_envelope_chunks_inner` does for `insert_stream`.
    """
    # `request.chunks` is a synchronous `Iterable` here - `_envelope_time_series_chunks`
    # already checked - but mypy cannot see that guarantee across the function boundary.
    iterator = iter(request.chunks)  # type: ignore[arg-type]
    try:
        for points in iterator:
            yield _build_time_series_chunk(request, points)
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            close()


def _envelope_time_series_chunks(request: TimeSeriesWriteStreamRequest) -> Iterator[messages.TimeSeriesWriteChunk]:
    """Turns `request.chunks` into wire `TimeSeriesWriteChunk`s.

    Validates `request.chunks` EAGERLY, in this function's own (non-generator) body,
    exactly as `_envelope_chunks` does for `insert_stream` and for the same reason: a
    generator's body does not run at all until the first `next()` pull, which for this RPC
    happens only once grpc itself starts consuming the request iterator - a `raise` written
    inside that generator would not reach the caller, since grpc catches it there and
    re-raises its own opaque `_InactiveRpcError` instead.
    """
    if not isinstance(request.chunks, Iterable):
        raise TypeError(
            "time_series_write_stream: `chunks` is an async iterable, which the sync facade cannot consume. "
            "Use arcadedb_driver_grpc.aio.create_client, or pass a synchronous iterable."
        )
    return _time_series_chunks_inner(request)


def time_series_write_stream(
    raw: ArcadeDbServiceStub,
    request: TimeSeriesWriteStreamRequest,
    *,
    timeout: float | None = None,
) -> messages.TimeSeriesWriteSummary:
    """Streams points to the server in chunks and returns the server's `TimeSeriesWriteSummary`.

    Sets `database`, `credentials`, `type` and `precision` on EVERY wire chunk - see
    `TimeSeriesWriteStreamRequest` for why there is no first-chunk-only mirror to write here,
    unlike `insert_stream`.

    An empty `request.chunks` sends ZERO wire chunks, rather than `insert_stream`'s
    single-empty-chunk special case: `TimeSeriesWriteChunk` has no `last`/first-chunk field
    forcing that workaround. What the server does with a stream that never told it
    `database`, `type` or `precision` is now MEASURED against a real server, not guessed at:
    it does NOT raise. The call is accepted cleanly and returns an all-zero
    `TimeSeriesWriteSummary` - `received == written == dropped == 0`, with
    `unknown_types`, `non_time_series_types` and `unavailable_types` all empty. This
    wrapper still invents nothing; it hands back whatever summary the server sent.

    Returns the server's `TimeSeriesWriteSummary` WHOLE (D-M6-3): `received`, `written`,
    `dropped`, `unknown_types`, `non_time_series_types`, `unavailable_types` and
    `execution_time_ms` all survive unchanged. A write is NOT atomic - each measurement's
    batch commits its own shard transaction as it is appended - so a SUCCESSFUL call can
    still report `written < received`. A caller who checks only that this returned without
    raising has not checked that its data landed; this wrapper never reduces the summary to
    a boolean or a count.

    NOT available on a `TransactionHandle`: `TimeSeriesWriteChunk` carries no `transaction`
    field on the wire at all (unlike `TimeSeriesQueryRequest`/`TimeSeriesLatestRequest`), so
    there is nothing to bind. `TimeSeriesWrite` (the unary write) needs no wrapper either -
    its request has no `transaction` field, so `raw.TimeSeriesWrite` already works
    unassisted.
    """
    return raw.TimeSeriesWriteStream(_envelope_time_series_chunks(request), timeout=timeout)
