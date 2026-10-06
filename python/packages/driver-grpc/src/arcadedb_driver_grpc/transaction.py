"""The explicit-transaction wrapper.

`BeginTransaction` hands back a `transaction_id` that must be threaded into the
`TransactionContext` of every subsequent request and ended on both the success and the
failure path. That is the footgun the 2026-07 gRPC audit filed three times - transaction
hijack, silent data loss and leaked transactions, #5040 through #5042 - and this module
exists so a caller cannot reproduce them by ergonomics.

Spelled as a CONTEXT MANAGER rather than TypeScript's `transaction(database, fn)`
callback, because `arcadedb-driver` already spells it `with db.transaction() as tx:` and
a caller moving between the two Python drivers should not have to relearn the shape.

`TransactionContext` also carries inline `begin` / `commit` / `rollback` flags, letting a
single request open and commit a transaction on its own. This wrapper covers only the
EXPLICIT model; the inline flags stay reachable by setting the field directly. Wrapping
both would offer two ways to do one thing with different failure modes, and the explicit
one is the one that needs the safety.
"""

from __future__ import annotations

import contextlib
import dataclasses
from collections.abc import Iterator, Sequence
from types import TracebackType
from typing import TypeVar

from ._generated import arcadedb_server_pb2 as messages
from ._generated.arcadedb_server_pb2_grpc import ArcadeDbServiceStub
from .stream import InsertStreamRequest, _as_metadata
from .stream import insert_stream as _insert_stream
from .stream import stream_query as _stream_query
from .stream import time_series_query as _time_series_query

__all__ = ["Transaction", "TransactionHandle"]

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
    InsertStreamRequest,
)


class TransactionHandle:
    """Every call made through this object carries the bound transaction's id.

    Calls made through the outer client do NOT take part in the transaction - the same
    distinction `arcadedb-driver`'s `Transaction` documents for its second
    `ArcadeDBDatabase`.
    """

    def __init__(self, raw: ArcadeDbServiceStub, database: str, transaction_id: str) -> None:
        self._raw = raw
        self._database = database
        self._transaction_id = transaction_id

    def _bind(self, request: _Request) -> _Request:
        """Returns a COPY of `request` with `database` and `transaction` forced onto it.

        The override is the mechanism, not a detail: it is what makes #5040-#5042
        unrepeatable. A request that arrived naming another database, or carrying another
        transaction id, leaves here naming this one.

        The caller's own object is LEFT ALONE. Binding in place would let this handle's
        transaction id outlive the transaction: after `with client.transaction("db") as tx:
        tx.execute_command(req)` the caller's `req` would permanently carry `database="db"`
        and a now-committed transaction's id, and reusing it - through `client.raw`, or in a
        later transaction before `_bind` runs - would send that dead id to the server. That
        is #5040's shape reached by aliasing, in the module built to make it unrepeatable.

        `CopyFrom`, never `MergeFrom`, for the transaction field: `TransactionContext` also
        carries inline `begin`/`commit`/`rollback`/`read_only` flags, and a merge would
        correct the id while letting a caller-supplied `rollback=True` ride through into a
        call this handle is meant to have full control over.

        `InsertStreamRequest` is the one non-protobuf request bound here - it is this
        package's own dataclass, whose `chunks` cannot live in a message - so it is bound by
        `dataclasses.replace` instead: a new object with `database` replaced and
        `transaction` replaced by a FRESH `TransactionContext`, never merged into the
        caller's. `insert_stream`'s `_build_chunk` then `CopyFrom`s that context onto every
        chunk, so the same rule holds on the wire: the caller's flags and id do not survive.
        The copy is shallow; `chunks`, `options` and `credentials` are shared with the
        caller's object, which is safe because the envelope only reads them (`CopyFrom` into
        each chunk's own message) and the caller's iterable is consumed exactly as
        `client.insert_stream` would consume it.
        """
        context = messages.TransactionContext(transaction_id=self._transaction_id, database=self._database)
        if isinstance(request, InsertStreamRequest):
            return dataclasses.replace(request, database=self._database, transaction=context)
        bound = type(request)()
        bound.CopyFrom(request)
        bound.database = self._database
        bound.transaction.CopyFrom(context)
        return bound

    def execute_query(
        self,
        request: messages.ExecuteQueryRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.ExecuteQueryResponse:
        return self._raw.ExecuteQuery(self._bind(request), timeout=timeout, metadata=_as_metadata(metadata))

    def execute_command(
        self,
        request: messages.ExecuteCommandRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.ExecuteCommandResponse:
        return self._raw.ExecuteCommand(self._bind(request), timeout=timeout, metadata=_as_metadata(metadata))

    def create_record(
        self,
        request: messages.CreateRecordRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.CreateRecordResponse:
        return self._raw.CreateRecord(self._bind(request), timeout=timeout, metadata=_as_metadata(metadata))

    def update_record(
        self,
        request: messages.UpdateRecordRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.UpdateRecordResponse:
        return self._raw.UpdateRecord(self._bind(request), timeout=timeout, metadata=_as_metadata(metadata))

    def delete_record(
        self,
        request: messages.DeleteRecordRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.DeleteRecordResponse:
        return self._raw.DeleteRecord(self._bind(request), timeout=timeout, metadata=_as_metadata(metadata))

    def lookup_by_rid(
        self,
        request: messages.LookupByRidRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.LookupByRidResponse:
        return self._raw.LookupByRid(self._bind(request), timeout=timeout, metadata=_as_metadata(metadata))

    def stream_query(
        self,
        request: messages.StreamQueryRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> Iterator[messages.GrpcRecord]:
        """Streams a bound query's results row by row: `for r in tx.stream_query(...)`.

        Wraps the server-streaming `StreamQuery`, flattening the batching the wire protocol
        uses: the server sends `QueryResult` batches, this yields each `GrpcRecord` on its
        own. `retrieval_mode` and `batch_size` pass through unchanged; no default is picked
        for either, because CURSOR, MATERIALIZE_ALL and PAGED have materially different
        memory and consistency behaviour that only the caller can judge.

        A plain `def` returning the generator `stream.stream_query` produces, rather than a
        generator function that re-yields it: the caller gets the same directly-iterable
        object either way, `_bind` runs eagerly at the call rather than lazily on the first
        pull, and the flattening stays in exactly one place. The RPC itself is not opened
        until the first pull, because `stream.stream_query` is a generator function.

        `metadata` is per-call gRPC metadata, forwarded as the CRUD methods above forward
        it: appended to whatever the channel's auth interceptor adds, never a substitute
        for it, and unable to rebind the call - `database` and `transaction` are request
        fields `_bind` overwrites, not headers.
        """
        return _stream_query(self._raw, self._bind(request), timeout=timeout, metadata=metadata)

    def vector_search(
        self,
        request: messages.VectorSearchRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.VectorSearchResponse:
        return self._raw.VectorSearch(self._bind(request), timeout=timeout, metadata=_as_metadata(metadata))

    def hybrid_search(
        self,
        request: messages.HybridSearchRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.HybridSearchResponse:
        return self._raw.HybridSearch(self._bind(request), timeout=timeout, metadata=_as_metadata(metadata))

    def full_text_search(
        self,
        request: messages.FullTextSearchRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.FullTextSearchResponse:
        return self._raw.FullTextSearch(self._bind(request), timeout=timeout, metadata=_as_metadata(metadata))

    def time_series_query(
        self,
        request: messages.TimeSeriesQueryRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> Iterator[messages.TimeSeriesQueryResult]:
        """Streams a bound time-series answer message by message: `for r in
        tx.time_series_query(...)`.

        Not flattened, unlike `stream_query` above: `truncated` and `last` are carried
        per-message (`truncated` is only meaningful on the message where `last` is true),
        and a raw answer's `rows` and an aggregated answer's `buckets` are shaped
        differently, so the messages are yielded exactly as the server sent them.

        A plain `def` returning the generator `stream.time_series_query` produces, rather
        than a generator function that re-yields it - the same spelling `stream_query` above
        uses, and for the same reason: the caller gets the same directly-iterable object
        either way, and `_bind` runs eagerly at the call rather than lazily on the first
        pull. `TimeSeriesQueryRequest` carries a `transaction` field (issue #7370: a query
        naming an open transaction runs on that transaction's own thread and observes its
        uncommitted points), the same reason `stream_query` is offered here.

        `metadata` is forwarded exactly as `stream_query` above forwards it: per-call
        headers appended to the channel's auth, with no say over the bound transaction.
        """
        return _time_series_query(self._raw, self._bind(request), timeout=timeout, metadata=metadata)

    def time_series_latest(
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
        return self._raw.TimeSeriesLatest(self._bind(request), timeout=timeout, metadata=_as_metadata(metadata))

    def insert_stream(
        self,
        request: InsertStreamRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.InsertSummary:
        """Streams rows into this transaction in chunks; see `stream.insert_stream`.

        The request is bound by `_bind` like every other call here: `database` and
        `transaction` are REPLACED with this handle's, whatever the caller set, and the
        handle's `TransactionContext` (id and database only - no `begin`/`commit`/`rollback`
        flags) rides on every chunk. The envelope itself - `session_id`, `chunk_seq`,
        first-chunk-only `database`, final-chunk `last`, `options` and `credentials` on every
        chunk - is `stream.insert_stream`'s, reused rather than repeated.

        `request.chunks` must be a SYNCHRONOUS iterable on this facade. Anything else -
        including an async iterable, which only `AsyncTransactionHandle.insert_stream` can
        consume - raises `TypeError` in the caller's own frame before the RPC is opened:
        `stream._envelope_chunks` is a plain function that checks first and only then
        returns the generator grpc iterates, so the error is not swallowed into grpc's
        opaque `_InactiveRpcError`. An empty `chunks` sends a single zero-row chunk with
        `last=True` rather than raising.

        The rows commit or roll back with the transaction on 26.9.1 and later. Servers
        before 26.9.1, which are outside the compatibility table, ignored `TransactionContext`
        on `InsertStream` (ArcadeData/arcadedb#6607), so there the rows would survive a
        rollback.

        `BulkInsert` and `GraphBatchLoad` are not offered here; they stay reachable through
        `client.raw` only.
        """
        return _insert_stream(self._raw, self._bind(request), timeout=timeout, metadata=metadata)


class Transaction:
    """A server-side transaction, begun on `__enter__` and ended on `__exit__`.

    Spelled as a context manager rather than a callback so a caller moving between the two
    Python drivers does not have to relearn the shape (see the module docstring). The inline
    `begin`/`commit`/`rollback` flags on `TransactionContext` stay reachable by setting the
    field directly; this wrapper covers only the EXPLICIT model, which is the one that needs
    the safety.
    """

    def __init__(self, raw: ArcadeDbServiceStub, database: str) -> None:
        self._raw = raw
        self._database = database
        self._transaction_id = ""

    def __enter__(self) -> TransactionHandle:
        begun = self._raw.BeginTransaction(messages.BeginTransactionRequest(database=self._database))
        if not begun.transaction_id.strip():
            # Running the caller's writes outside a real transaction while implying
            # otherwise is the worst outcome available here, so this refuses before the
            # body runs rather than binding a blank id to every subsequent call.
            raise RuntimeError(
                f'transaction: BeginTransaction did not return a transaction id for database "{self._database}" - '
                "refusing to run the body outside a real transaction."
            )
        self._transaction_id = begun.transaction_id
        return TransactionHandle(self._raw, self._database, self._transaction_id)

    def _context(self) -> messages.TransactionContext:
        return messages.TransactionContext(transaction_id=self._transaction_id, database=self._database)

    def _rollback(self) -> None:
        self._raw.RollbackTransaction(messages.RollbackTransactionRequest(transaction=self._context()))

    def _safe_rollback(self) -> None:
        """Rolls back, swallowing its own failure.

        Used on the commit-failure path only: the commit error is what the caller needs
        to see, and without this attempt the server holds the transaction open until it
        is reaped.
        """
        with contextlib.suppress(Exception):  # see the docstring; the commit error wins
            self._rollback()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commits on a clean exit, rolls back on any other.

        Returns None, not a bool: a falsy return does not suppress the body's exception,
        and an exception raised in here (the failed-commit check below) propagates.

        On a failing body, the rollback is attempted and the body's exception then
        propagates unchanged. A rollback that itself fails with an `Exception` is attached
        as the body exception's `__cause__` - only if it has none already - rather than
        replacing what the caller actually hit.

        On a clean exit, `CommitTransaction` is sent. If that call raises, `_safe_rollback`
        makes a best-effort rollback, swallowing its own failure, and the COMMIT's error is
        re-raised - without that attempt the server would hold the transaction open until
        it is reaped. If the call returns but its `committed` flag is false, this raises
        `RuntimeError`: the check is on `committed`, NOT `success`, because success=true
        with committed=false and no error status is what a server answers for a
        transaction it already reaped, and checking `success` alone would report success
        and silently lose the caller's writes.

        A `KeyboardInterrupt` (or any other `BaseException`) raised in the body DOES roll
        back: the guard below is `if exc is not None`, not `isinstance(exc, Exception)`, so
        it takes the rollback branch like any other failure, and the interrupt then
        propagates. This is the sync counterpart of the async facade's cancellation
        handling; there is no task cancellation here.

        KNOWN LIMITATION - a `BaseException` that is not an `Exception`, such as a SECOND
        `KeyboardInterrupt`, raised while `_rollback()` is still in flight is not survived.
        The `except Exception` around the rollback does not catch it, so it escapes
        `__exit__` and replaces the body's exception (which survives only as its
        `__context__`); the rollback may never reach the server, leaving the transaction
        open until the server's idle reaper reclaims it (5 minutes idle by default) - the
        ArcadeData/arcadedb#5042 shape this module otherwise exists to prevent. The commit
        path has the same gap in two places: `_safe_rollback`'s
        `contextlib.suppress(Exception)` does not cover it, so one landing there replaces
        the commit error the caller was meant to see; and one landing during
        `CommitTransaction` itself is not caught by its `except Exception` either, so no
        rollback is attempted and whether the commit took effect is unknown to the caller.
        A caller who needs the rollback to be certain even then should issue it themselves
        rather than relying on this context manager.
        """
        if exc is not None:
            # Roll back, then let the original exception propagate. A rollback failure
            # attaches as __cause__ rather than replacing what the caller actually hit.
            try:
                self._rollback()
            except Exception as rollback_error:
                if exc.__cause__ is None:
                    exc.__cause__ = rollback_error
            return

        try:
            committed = self._raw.CommitTransaction(messages.CommitTransactionRequest(transaction=self._context()))
        except Exception:
            self._safe_rollback()
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
