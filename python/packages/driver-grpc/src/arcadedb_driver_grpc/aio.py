"""The async facade: the same surface as the package root, over `grpc.aio`.

Two hand-written facades over one generated layer, as `python/CLAUDE.md` documents for
`arcadedb-driver`. Not `unasync` or any other single-source generation.

The reasoning behind each wrapper is repeated here rather than cross-referenced,
deliberately: a reader of this module should not have to open `stream.py` and
`transaction.py` to learn what the contract is. What IS shared with the sync facade is
the code that has no I/O in it at all - `_build_chunk`, `_build_time_series_chunk` and the
`_EndOfStream` sentinel - because only the *iteration* genuinely differs between the two.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator, Iterable, Sequence
from types import TracebackType
from typing import TYPE_CHECKING, TypeVar

import grpc

from ._generated import arcadedb_server_pb2 as messages
from ._generated import arcadedb_server_pb2_grpc as _pb2_grpc
from .auth import Auth, async_interceptors
from .errors import InsecureChannelError
from .stream import (
    _END_OF_STREAM,
    InsertStreamRequest,
    TimeSeriesWriteStreamRequest,
    _build_chunk,
    _build_time_series_chunk,
    _EndOfStream,
)

if TYPE_CHECKING:
    # `ArcadeDbServiceAsyncStub` exists ONLY in the generated .pyi - mypy-protobuf models
    # the async stub as its own class, but grpc constructs the SAME class for both channel
    # kinds, so the runtime .py defines no such name. Importing it here rather than at
    # module scope is what keeps that a typing-only fiction.
    from ._generated.arcadedb_server_pb2_grpc import ArcadeDbServiceAsyncStub

__all__ = [
    "AsyncArcadeDBGrpcClient",
    "AsyncTransaction",
    "AsyncTransactionHandle",
    "create_client",
]

_Request = TypeVar(
    "_Request",
    messages.ExecuteQueryRequest,
    messages.ExecuteCommandRequest,
    messages.CreateRecordRequest,
    messages.UpdateRecordRequest,
    messages.DeleteRecordRequest,
    messages.LookupByRidRequest,
    messages.StreamQueryRequest,
    messages.VectorSearchRequest,
    messages.HybridSearchRequest,
    messages.FullTextSearchRequest,
    messages.TimeSeriesQueryRequest,
    messages.TimeSeriesLatestRequest,
)

_Row = TypeVar("_Row")


async def _stream_query(
    raw: ArcadeDbServiceAsyncStub,
    request: messages.StreamQueryRequest,
    *,
    timeout: float | None = None,
) -> AsyncIterator[messages.GrpcRecord]:
    """Streams a query's results row by row.

    Wraps the server-streaming `StreamQuery`, flattening the batching the wire protocol
    uses: the server sends `QueryResult` batches, this yields each `GrpcRecord` on its own.

    Thin by design. `retrieval_mode` and `batch_size` pass through to the server exactly
    as given and this wrapper picks no defaults for either, because CURSOR,
    MATERIALIZE_ALL and PAGED have materially different memory and consistency behaviour
    that only the caller can judge.
    """
    async for result in raw.StreamQuery(request, timeout=timeout):
        for record in result.records:
            yield record


async def _time_series_query(
    raw: ArcadeDbServiceAsyncStub,
    request: messages.TimeSeriesQueryRequest,
    *,
    timeout: float | None = None,
) -> AsyncIterator[messages.TimeSeriesQueryResult]:
    """Streams a time-series answer message by message.

    Wraps the server-streaming `TimeSeriesQuery`. Deliberately THINNER than `_stream_query`
    above, which flattens `QueryResult` batches into individual `GrpcRecord`s:
    `TimeSeriesQueryResult` cannot be flattened the same way. `truncated` and `last` are
    carried per-message (`truncated` is only meaningful on the message where `last` is
    true), and a raw answer's `rows` versus an aggregated answer's `buckets` are shaped
    differently. Flattening either away would throw away the information a caller needs to
    tell "the stream ended" from "the stream ended early because of `limit`" - so this
    yields the messages exactly as the server sent them.

    Also reachable, bound to an open transaction, as
    `AsyncTransactionHandle.time_series_query` below, since `TimeSeriesQueryRequest`
    carries a `transaction` field (issue #7370): a query naming an open transaction runs on
    that transaction's own thread and observes its uncommitted points, where a query with
    no transaction runs on a gRPC worker and sees only committed data.

    `request.tags` and `request.limit` pass straight through, including their server-side
    enforcement: an unknown tag name in `tags` and a `limit` above
    `arcadedb.server.grpcTimeSeriesMaxResultRows` are both refused by the server, not by
    this package - see the README's "Time series" section.
    """
    async for result in raw.TimeSeriesQuery(request, timeout=timeout):
        yield result


async def _aiter_chunks(
    chunks: Iterable[Sequence[_Row]] | AsyncIterable[Sequence[_Row]],
) -> AsyncGenerator[Sequence[_Row], None]:
    """Normalises either half of a `chunks` union (`InsertStreamRequest.chunks` or
    `TimeSeriesWriteStreamRequest.chunks`) into one async source.

    The async facade accepts BOTH halves of the declared union, unlike the sync facade,
    which genuinely cannot consume the async half and rejects it eagerly with a message
    pointing here. A caller who already has a list should not have to wrap it in an async
    generator just to reach this facade.

    Generic over the row type (`_Row`) rather than duplicated per caller: the normalisation
    and closing logic below has no dependency on what a "row batch" contains, and it is
    exactly the closing behaviour - subtle enough that `insert_stream`'s own tests exist to
    pin it - that duplicating this function per message type would risk letting drift.

    The parameter is `AsyncIterable`, not `AsyncIterator`, because that is what both
    `chunks` fields declare: an object with `__aiter__` but no `__anext__` of its own is a
    legitimate caller value, and narrowing this would reject it.

    Both branches FORWARD THE CLOSE to the source they were handed, and that is the whole
    reason this is a `try/finally` rather than two plain loops. `_envelope_chunks` closes
    this wrapper, but closing the wrapper does not close what the wrapper is iterating:
    `aclose()` throws `GeneratorExit` at the `yield` below, which unwinds out of the loop,
    and neither `for` nor `async for` ever closes its iterator. Without these two
    `finally`s the caller's own generator is left SUSPENDED, its `finally` deferred to a
    garbage collection that never comes - `InsertStreamRequest.chunks` still holds a
    strong reference to it - so the file handle or cursor they wrapped it in is never
    released. The sync facade has no equivalent hazard because it closes the caller's
    iterator directly (`iter(g) is g` for a generator).

    Both branches also take the ITERATOR first (`iter()` / `aiter()`) and close THAT,
    never the `Iterable`/`AsyncIterable` they were handed. For a bare generator the two
    are the same object, but for a class whose `__aiter__` is an async generator function
    they are not: `async for` would build a fresh async generator, abandoning it would
    leave it suspended, and `getattr(chunks, "aclose", None)` on the class instance is
    `None` - so the close would be forwarded to nothing and the caller's `finally` would
    never run. Same story for `__iter__` on the sync half.

    `getattr` plus `callable(...)` rather than a bare call in both cases: an arbitrary
    `Iterable` or `AsyncIterable` need not be a generator, and only generators are
    required to have `close`/`aclose`. Checking `callable(...)` rather than merely
    `is not None` matters too - a custom iterable that happens to carry a non-callable
    attribute named `close` or `aclose` (a plain data field, unrelated to generator
    cleanup) would otherwise make this raise `TypeError` while trying to call it, which
    is worse than the missing cleanup this guard exists to provide.
    """
    if isinstance(chunks, Iterable):
        iterator = iter(chunks)
        try:
            for chunk in iterator:
                yield chunk
        finally:
            close = getattr(iterator, "close", None)
            if callable(close):
                close()
        return

    aiterator = aiter(chunks)
    try:
        async for chunk in aiterator:
            yield chunk
    finally:
        aclose = getattr(aiterator, "aclose", None)
        if callable(aclose):
            await aclose()


async def _envelope_chunks(request: InsertStreamRequest, session_id: str) -> AsyncGenerator[messages.InsertChunk, None]:
    """Turns `request.chunks` into wire `InsertChunk`s, adding the envelope bookkeeping.

    One `session_id` stable for the whole stream, `chunk_seq` starting at 1, `database` on
    the first chunk only (per the .proto contract, and mirrored into `options.database`
    there too - on 26.8.1 and earlier the server builds its `InsertContext` from
    `InsertOptions.database` ALONE and never reads `InsertChunk.database`, so without the
    mirror a stream inserts nothing: `inserted=0`, or a deferred-commit failure with
    "Invalid database name: name is required"; ArcadeData/arcadedb#6597, fixed in 26.9.1),
    and `last=True` on the final chunk only.

    The source is pulled MANUALLY rather than with a plain `async for`, because knowing
    which chunk is last needs one-element lookahead. That has two consequences this
    function has to handle:

    - End-of-stream needs a sentinel that cannot collide with a real value. `anext(source,
      None)` would conflate a `None` row batch - easy to produce from a `dict.get()` in a
      batching helper - with genuine end-of-stream, silently dropping every chunk after
      it: the server would report a smaller `received` and nothing would raise anywhere.
      `stream._END_OF_STREAM` is that sentinel, shared with the sync facade so the two
      cannot drift apart on it.
    - Finalisation is not automatic. If this generator is abandoned early - the RPC aborts
      mid-stream, or the caller stops consuming - nothing would otherwise close the
      caller's own generator, and any `finally` they wrote around it (closing a file
      handle, a cursor) would never run. The `try/finally` makes that cleanup happen on
      every exit path, not only on normal completion. `source` is always an async
      generator (it is `_aiter_chunks`'s own return value), so `aclose()` is always there.

    Unlike `stream._envelope_chunks` this function carries no eager-validation split of its
    own - but that is not because there is nothing to reject. Both halves of the DECLARED
    union are accepted here, yet a value in neither half still has to be refused, and this
    is an async generator, so a `raise` in its body would not fire until grpc pulls the
    first chunk to open the RPC - where grpc swallows it and re-raises an opaque
    `_InactiveRpcError` instead, exactly as it did on the sync side before the split. The
    check therefore lives in `AsyncArcadeDBGrpcClient.insert_stream`, which is a plain
    `async def` and so raises in the caller's own frame with no split needed.
    """
    source = _aiter_chunks(request.chunks)
    try:
        current = await anext(source, _END_OF_STREAM)
        if isinstance(current, _EndOfStream):
            # An empty stream is a legitimate outcome, not an error: a filter that matched
            # nothing produces one. Send a single empty final chunk and hand back whatever
            # summary the server gives, rather than raising or inventing a result.
            # Verified against a real server during M1b.
            yield _build_chunk(request, session_id, 1, [], last=True)
            return

        seq = 1
        while True:
            nxt = await anext(source, _END_OF_STREAM)
            yield _build_chunk(request, session_id, seq, current, last=isinstance(nxt, _EndOfStream))
            if isinstance(nxt, _EndOfStream):
                return
            current = nxt
            seq += 1
    finally:
        await source.aclose()


async def _envelope_time_series_chunks(
    request: TimeSeriesWriteStreamRequest,
) -> AsyncGenerator[messages.TimeSeriesWriteChunk, None]:
    """Turns `request.chunks` into wire `TimeSeriesWriteChunk`s.

    No session/sequence/last envelope here, unlike `_envelope_chunks` above:
    `TimeSeriesWriteChunk` declares no such fields, so `database`, `credentials`, `type` and
    `precision` are simply set on every chunk (see `stream._build_time_series_chunk`) and no
    one-element lookahead is needed to know which chunk is last.

    The `try/finally` still matters even without that lookahead: `source` (an async
    generator, `_aiter_chunks`'s own return value) must be closed if this generator is
    abandoned early - the RPC aborts mid-stream, or the caller stops consuming - otherwise
    the caller's own generator is left suspended and any `finally` they wrote around it
    (closing a file handle, a cursor) never runs. `async for` alone does not close its
    source on early exit, which is exactly the hazard `_aiter_chunks`'s own docstring
    documents.

    Carries no eager-validation split of its own, for the same reason `_envelope_chunks`
    above does not: a `chunks` value in neither half of the declared union still has to be
    refused, and refusing it here (inside an async generator whose body does not run until
    grpc pulls the first chunk) would let grpc swallow the `TypeError` and re-raise its own
    opaque error instead. The check lives in
    `AsyncArcadeDBGrpcClient.time_series_write_stream`, a plain `async def` that raises in
    the caller's own frame.
    """
    source = _aiter_chunks(request.chunks)
    try:
        async for points in source:
            yield _build_time_series_chunk(request, points)
    finally:
        await source.aclose()


class AsyncTransactionHandle:
    """Every call made through this object carries the bound transaction's id.

    Calls made through the outer client do NOT take part in the transaction - the same
    distinction `arcadedb-driver`'s `Transaction` documents for its second
    `ArcadeDBDatabase`.
    """

    def __init__(self, raw: ArcadeDbServiceAsyncStub, database: str, transaction_id: str) -> None:
        self._raw = raw
        self._database = database
        self._transaction_id = transaction_id

    def _bind(self, request: _Request) -> _Request:
        """Returns a COPY of `request` with `database` and `transaction` forced onto it.

        The override is the mechanism, not a detail: it is what makes the 2026-07 gRPC
        audit's #5040-#5042 unrepeatable. A request that arrived naming another database,
        or carrying another transaction id, leaves here naming this one.

        The caller's own object is LEFT ALONE. Binding in place would let this handle's
        transaction id outlive the transaction: after `async with client.transaction("db")
        as tx: await tx.execute_command(req)` the caller's `req` would permanently carry
        `database="db"` and a now-committed transaction's id, and reusing it - through
        `client.raw`, or in a later transaction before `_bind` runs - would send that dead
        id to the server. That is #5040's shape reached by aliasing, in the module built to
        make it unrepeatable.

        `CopyFrom`, never `MergeFrom`, for the transaction field: `TransactionContext` also
        carries inline `begin`/`commit`/`rollback`/`read_only` flags, and a merge would
        correct the id while letting a caller-supplied `rollback=True` ride through into a
        call this handle is meant to have full control over.
        """
        bound = type(request)()
        bound.CopyFrom(request)
        bound.database = self._database
        bound.transaction.CopyFrom(
            messages.TransactionContext(transaction_id=self._transaction_id, database=self._database)
        )
        return bound

    async def execute_query(
        self,
        request: messages.ExecuteQueryRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.ExecuteQueryResponse:
        return await self._raw.ExecuteQuery(self._bind(request), timeout=timeout, metadata=metadata)

    async def execute_command(
        self,
        request: messages.ExecuteCommandRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.ExecuteCommandResponse:
        return await self._raw.ExecuteCommand(self._bind(request), timeout=timeout, metadata=metadata)

    async def create_record(
        self,
        request: messages.CreateRecordRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.CreateRecordResponse:
        return await self._raw.CreateRecord(self._bind(request), timeout=timeout, metadata=metadata)

    async def update_record(
        self,
        request: messages.UpdateRecordRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.UpdateRecordResponse:
        return await self._raw.UpdateRecord(self._bind(request), timeout=timeout, metadata=metadata)

    async def delete_record(
        self,
        request: messages.DeleteRecordRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.DeleteRecordResponse:
        return await self._raw.DeleteRecord(self._bind(request), timeout=timeout, metadata=metadata)

    async def lookup_by_rid(
        self,
        request: messages.LookupByRidRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.LookupByRidResponse:
        return await self._raw.LookupByRid(self._bind(request), timeout=timeout, metadata=metadata)

    def stream_query(
        self, request: messages.StreamQueryRequest, *, timeout: float | None = None
    ) -> AsyncIterator[messages.GrpcRecord]:
        """Streams a bound query's results row by row: `async for r in tx.stream_query(...)`.

        A plain `def` returning the async generator `_stream_query` produces, rather than
        an `async def` that re-yields it: the caller gets the same directly-`async for`-able
        object either way, and this spelling keeps the flattening in exactly one place.
        """
        return _stream_query(self._raw, self._bind(request), timeout=timeout)

    async def vector_search(
        self,
        request: messages.VectorSearchRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.VectorSearchResponse:
        return await self._raw.VectorSearch(self._bind(request), timeout=timeout, metadata=metadata)

    async def hybrid_search(
        self,
        request: messages.HybridSearchRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.HybridSearchResponse:
        return await self._raw.HybridSearch(self._bind(request), timeout=timeout, metadata=metadata)

    async def full_text_search(
        self,
        request: messages.FullTextSearchRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.FullTextSearchResponse:
        return await self._raw.FullTextSearch(self._bind(request), timeout=timeout, metadata=metadata)

    def time_series_query(
        self, request: messages.TimeSeriesQueryRequest, *, timeout: float | None = None
    ) -> AsyncIterator[messages.TimeSeriesQueryResult]:
        """Streams a bound time-series answer message by message: `async for r in
        tx.time_series_query(...)`.

        A plain `def` returning the async generator `_time_series_query` produces, rather
        than an `async def` that re-yields it - the same spelling `stream_query` above
        uses, and for the same reason: the caller gets the same directly-`async for`-able
        object either way, and `_bind` runs eagerly at the call rather than lazily on the
        first pull. `TimeSeriesQueryRequest` carries a `transaction` field (issue #7370: a
        query naming an open transaction runs on that transaction's own thread and observes
        its uncommitted points), the same reason `stream_query` is offered here.
        """
        return _time_series_query(self._raw, self._bind(request), timeout=timeout)

    async def time_series_latest(
        self,
        request: messages.TimeSeriesLatestRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.TimeSeriesLatestResponse:
        """Reads the latest sample bound to this transaction.

        `TimeSeriesLatestRequest` also carries a `transaction` field, for the same #7370
        reason as `time_series_query` above - but `TimeSeriesLatest` is unary, so there is
        no batching or flattening for a wrapper to own, and this is bound directly through
        `self._raw.TimeSeriesLatest` rather than through a stream-shaped helper.
        """
        return await self._raw.TimeSeriesLatest(self._bind(request), timeout=timeout, metadata=metadata)


class AsyncTransaction:
    """A server-side transaction, begun on `__aenter__` and ended on `__aexit__`.

    Spelled as a context manager rather than a callback for the same reason
    `transaction.Transaction` is: a caller moving between the two Python drivers should
    not have to relearn the shape. The inline `begin`/`commit`/`rollback` flags on
    `TransactionContext` stay reachable by setting the field directly; this wrapper covers
    only the EXPLICIT model, which is the one that needs the safety.
    """

    def __init__(self, raw: ArcadeDbServiceAsyncStub, database: str) -> None:
        self._raw = raw
        self._database = database
        self._transaction_id = ""

    async def __aenter__(self) -> AsyncTransactionHandle:
        begun = await self._raw.BeginTransaction(messages.BeginTransactionRequest(database=self._database))
        if not begun.transaction_id.strip():
            # Running the caller's writes outside a real transaction while implying
            # otherwise is the worst outcome available here, so this refuses before the
            # body runs rather than binding a blank id to every subsequent call.
            raise RuntimeError(
                f'transaction: BeginTransaction did not return a transaction id for database "{self._database}" - '
                "refusing to run the body outside a real transaction."
            )
        self._transaction_id = begun.transaction_id
        return AsyncTransactionHandle(self._raw, self._database, self._transaction_id)

    def _context(self) -> messages.TransactionContext:
        return messages.TransactionContext(transaction_id=self._transaction_id, database=self._database)

    async def _rollback(self) -> None:
        await self._raw.RollbackTransaction(messages.RollbackTransactionRequest(transaction=self._context()))

    async def _safe_rollback(self) -> None:
        """Rolls back, swallowing its own failure.

        Used on the commit-failure path only: the commit error is what the caller needs to
        see, and without this attempt the server holds the transaction open until it is
        reaped.
        """
        with contextlib.suppress(Exception):  # see the docstring; the commit error wins
            await self._rollback()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commits on a clean exit, rolls back on any other.

        Returns None, not a bool: a falsy return does not suppress the body's exception,
        and an exception raised in here (the failed-commit check below) propagates.

        Cancellation DOES roll back, contrary to what the obvious reading suggests. The
        guard below is `if exc is not None`, not `isinstance(exc, Exception)`, so an
        `asyncio.CancelledError` - a `BaseException`, not an `Exception`, since 3.8 -
        takes the rollback branch like any other failure. Nor does the `await` inside
        `_rollback()` re-raise immediately: after a single `task.cancel()` the
        `CancelledError` has already been delivered and the task's `_must_cancel` flag
        cleared, so the rollback runs to completion. `test_aio.py`'s
        `test_cancelling_the_body_still_rolls_back` observes exactly that -
        `servicer.calls == ["BeginTransaction", "RollbackTransaction"]`.

        KNOWN LIMITATION - a SECOND cancellation, arriving while `_rollback()` is still in
        flight, is not survived. That `CancelledError` is raised at the `await` and escapes
        `__aexit__` uncaught, replacing whatever the body raised; the rollback never
        reaches the server and the transaction is left open until
        `arcadedb.server.httpTxExpireTimeout` reaps it - the ArcadeData/arcadedb#5042
        shape this module otherwise exists to prevent. `_safe_rollback`, on the
        commit-failure path, has the narrower version of the same gap: its
        `contextlib.suppress(Exception)` does not cover `CancelledError`, so a cancellation
        landing there replaces the commit error the caller was meant to see.

        This is accepted rather than overlooked. The fix would be a shielded rollback
        (`asyncio.shield`, or a rollback issued from `asyncio.CancelledError`'s handler
        with the cancellation re-raised afterwards), and a shielded await during
        cancellation carries its own hang risk against an unresponsive server - trading a
        reaped transaction for a task that will not die. Choosing between those is a
        design decision for this repository's owner, not something to settle silently
        here. A caller who needs the rollback to be certain even under repeated
        cancellation should issue it themselves rather than relying on this context
        manager.
        """
        if exc is not None:
            # Roll back, then let the original exception propagate. A rollback failure
            # attaches as __cause__ rather than replacing what the caller actually hit.
            try:
                await self._rollback()
            except Exception as rollback_error:
                if exc.__cause__ is None:
                    exc.__cause__ = rollback_error
            return

        try:
            committed = await self._raw.CommitTransaction(
                messages.CommitTransactionRequest(transaction=self._context())
            )
        except Exception:
            await self._safe_rollback()
            raise

        if not committed.committed:
            # `committed`, NOT `success`: success=true with committed=false and no error
            # status is what a server answers for a transaction it already reaped.
            # Checking `success` alone would report success and silently lose the
            # caller's writes.
            raise RuntimeError(
                f'transaction: commit for database "{self._database}" '
                f"(transaction_id={self._transaction_id}) did not take effect: "
                f"{committed.message or 'no message from server'}"
            )


class AsyncArcadeDBGrpcClient:
    """ArcadeDB's async gRPC data-plane client.

    `raw` is the generated stub for `com.arcadedb.grpc.ArcadeDbService`; every RPC the
    facade does not wrap is reached through it, already authenticated - which is why the
    auth interceptors are attached to the CHANNEL and not passed as per-call metadata.

    A `grpc.aio.Channel` must be closed, so this is an async context manager.
    """

    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._channel = channel
        # ONE runtime class serves both channel kinds - grpc constructs `ArcadeDbServiceStub`
        # whether the channel is sync or async, and `ArcadeDbServiceAsyncStub` exists only in
        # the generated .pyi, which marks it `@type_check_only`. No cast is needed to reach
        # the async types: that .pyi overloads `ArcadeDbServiceStub.__new__` on the channel
        # type, so passing a `grpc.aio.Channel` already types this as the async stub. The
        # annotation below is written out because `raw` is public API - and a `cast()` here
        # would be flagged redundant, besides having to spell the type as a STRING (`cast`
        # evaluates its first argument at runtime, where that name does not exist).
        self.raw: ArcadeDbServiceAsyncStub = _pb2_grpc.ArcadeDbServiceStub(channel)

    async def close(self) -> None:
        """Closes the underlying channel."""
        await self._channel.close(grace=None)

    async def __aenter__(self) -> AsyncArcadeDBGrpcClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    def stream_query(
        self, request: messages.StreamQueryRequest, *, timeout: float | None = None
    ) -> AsyncIterator[messages.GrpcRecord]:
        """Streams a query's results row by row, flattening the wire batching.

        `async for record in client.stream_query(...)`: the return value is an async
        generator, not a coroutine, so it is iterated directly rather than awaited first.

        `retrieval_mode` and `batch_size` pass through unchanged; this wrapper picks no
        default for either, because CURSOR, MATERIALIZE_ALL and PAGED have materially
        different memory and consistency behaviour that only the caller can judge.
        """
        return _stream_query(self.raw, request, timeout=timeout)

    async def insert_stream(
        self, request: InsertStreamRequest, *, timeout: float | None = None
    ) -> messages.InsertSummary:
        """Streams rows to the server in chunks and returns the server's `InsertSummary`.

        Handles the envelope bookkeeping a caller would otherwise hand-roll: one
        `session_id` (a fresh UUID) stable for the whole stream, `chunk_seq` from 1,
        `database` on the first chunk only and mirrored into `options.database` there too
        (ArcadeData/arcadedb#6597), and `last=True` on the final chunk only.

        `request.chunks` may be a sync OR an async iterable here - both halves of the
        declared union work, unlike on the sync facade.

        An empty `request.chunks` sends a single chunk with zero rows and `last=True`
        rather than raising: a filter that matched nothing is a legitimate outcome.

        NOT available on `AsyncTransactionHandle`: on 26.8.1 and earlier,
        ArcadeData/arcadedb#6607 had the server ignoring `TransactionContext` here, so
        offering it there would have implied a transactional guarantee the server did not
        honour. That fix shipped in 26.9.1, so the omission is now removable - see
        `InsertStreamRequest` in `stream.py` for the measurement and why lifting it is a
        follow-up.

        A `chunks` value in NEITHER half of the union is rejected here, before the RPC is
        opened. This method being a plain `async def` is what makes that cheap: the check
        runs in the caller's own frame the moment the coroutine is awaited. Left to
        `_envelope_chunks` - an async generator, whose body does not run until grpc pulls
        the first chunk - the same `TypeError` would be raised inside grpc's request loop,
        which catches it and re-raises an opaque `_InactiveRpcError` ("Exception iterating
        requests!") instead. That is the failure mode the sync facade's eager-validation
        split closed; this is the async facade's cheaper form of the same guard.
        """
        if not isinstance(request.chunks, Iterable | AsyncIterable):
            raise TypeError(
                "insert_stream: `chunks` must be an iterable or an async iterable of row batches, "
                f"not {type(request.chunks).__name__}."
            )
        return await self.raw.InsertStream(_envelope_chunks(request, str(uuid.uuid4())), timeout=timeout)

    def time_series_query(
        self, request: messages.TimeSeriesQueryRequest, *, timeout: float | None = None
    ) -> AsyncIterator[messages.TimeSeriesQueryResult]:
        """Streams a time-series answer message by message.

        `async for result in client.time_series_query(...)`: the return value is an async
        generator, not a coroutine, so it is iterated directly rather than awaited first.

        Deliberately THINNER than `stream_query` above, which flattens `QueryResult`
        batches into individual `GrpcRecord`s: `TimeSeriesQueryResult` cannot be flattened
        the same way. `truncated` and `last` are carried per-message (`truncated` is only
        meaningful on the message where `last` is true), and a raw answer's `rows` versus
        an aggregated answer's `buckets` are shaped differently. Flattening either away
        would throw away the information a caller needs to tell "the stream ended" from
        "the stream ended early because of `limit`" - so this yields the messages exactly
        as the server sent them.

        Also reachable, bound to an open transaction, as
        `AsyncTransactionHandle.time_series_query`, since `TimeSeriesQueryRequest` carries a
        `transaction` field (issue #7370).
        """
        return _time_series_query(self.raw, request, timeout=timeout)

    async def time_series_write_stream(
        self, request: TimeSeriesWriteStreamRequest, *, timeout: float | None = None
    ) -> messages.TimeSeriesWriteSummary:
        """Streams points to the server in chunks and returns the server's
        `TimeSeriesWriteSummary`.

        Sets `database`, `credentials`, `type` and `precision` on EVERY wire chunk - unlike
        `insert_stream`'s first-chunk-only `database` mirror, `TimeSeriesWriteChunk` has no
        session/sequence/last fields forcing that special case (see
        `TimeSeriesWriteStreamRequest` in `stream.py`).

        `request.chunks` may be a sync OR an async iterable here - both halves of the
        declared union work, unlike on the sync facade.

        An empty `request.chunks` sends ZERO wire chunks, rather than `insert_stream`'s
        single-empty-chunk special case. What the server does with a stream that never told
        it `database`, `type` or `precision` is now MEASURED against a real server, not
        guessed at: it does NOT raise. The awaited call is accepted cleanly and returns an
        all-zero `TimeSeriesWriteSummary` - `received == written == dropped == 0`, with
        `unknown_types`, `non_time_series_types` and `unavailable_types` all empty. This
        wrapper still invents nothing; it hands back whatever summary the server sent.

        Returns the server's `TimeSeriesWriteSummary` WHOLE (D-M6-3): `received`,
        `written`, `dropped`, `unknown_types`, `non_time_series_types`, `unavailable_types`
        and `execution_time_ms` all survive unchanged. A write is NOT atomic - each
        measurement's batch commits its own shard transaction as it is appended - so a
        SUCCESSFUL call can still report `written < received`. A caller who checks only
        that the awaited call did not raise has not checked that its data landed; this
        wrapper never reduces the summary to a boolean or a count.

        NOT available on `AsyncTransactionHandle`: `TimeSeriesWriteChunk` carries no
        `transaction` field on the wire at all, so there is nothing to bind.
        `TimeSeriesWrite` (the unary write) needs no wrapper either - its request has no
        `transaction` field, so `raw.TimeSeriesWrite` already works unassisted.

        A `chunks` value in NEITHER half of the union is rejected here, before the RPC is
        opened - the same eager guard `insert_stream` above carries, and for the same
        reason: this method being a plain `async def` is what makes the check run in the
        caller's own frame, rather than inside `_envelope_time_series_chunks` - an async
        generator whose body does not run until grpc pulls the first chunk, where the
        `TypeError` would otherwise be swallowed and replaced with grpc's own opaque
        `_InactiveRpcError`.
        """
        if not isinstance(request.chunks, Iterable | AsyncIterable):
            raise TypeError(
                "time_series_write_stream: `chunks` must be an iterable or an async iterable of point batches, "
                f"not {type(request.chunks).__name__}."
            )
        return await self.raw.TimeSeriesWriteStream(_envelope_time_series_chunks(request), timeout=timeout)

    def transaction(self, database: str) -> AsyncTransaction:
        """Runs a server-side transaction: `async with client.transaction("db") as tx:`."""
        return AsyncTransaction(self.raw, database)


def create_client(
    target: str,
    *,
    auth: Auth | None = None,
    credentials: grpc.ChannelCredentials | None = None,
    insecure: bool = False,
) -> AsyncArcadeDBGrpcClient:
    """Creates an async gRPC data-plane client.

    `target` is gRPC's native `host:port` form, e.g. `"localhost:50051"` - not a URL.

    Refuses to pair `password_auth` with an insecure channel unless `insecure=True` is
    passed explicitly: sending a password in cleartext metadata is a credential-exposure
    hazard (issue #5048). The check keys on whether channel `credentials` were supplied,
    which is stated outright rather than inferred.

    The guard is written out here rather than factored into a helper shared with the sync
    `create_client`: one duplicated `if` is cheaper to read than an indirection, and this
    is the check people audit.
    """
    if credentials is None and not insecure and auth is not None and auth.sends_plaintext_password:
        raise InsecureChannelError(
            f'create_client: refusing to send a plaintext password over an insecure channel to "{target}". '
            "Pass credentials=grpc.ssl_channel_credentials(), switch to bearer_auth, "
            "or pass insecure=True to opt in explicitly."
        )

    # `interceptors=` is a keyword argument on both constructors; grpc.aio has no
    # equivalent of the sync `grpc.intercept_channel`, so the channel is built with them
    # already attached rather than wrapped afterwards.
    interceptors = async_interceptors(auth)
    channel = (
        grpc.aio.insecure_channel(target, interceptors=interceptors)
        if credentials is None
        else grpc.aio.secure_channel(target, credentials, interceptors=interceptors)
    )
    return AsyncArcadeDBGrpcClient(channel)
