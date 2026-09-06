"""The async facade: the same surface as the package root, over `grpc.aio`.

Two hand-written facades over one generated layer, as `python/CLAUDE.md` documents for
`arcadedb-driver`. Not `unasync` or any other single-source generation.

The reasoning behind each wrapper is repeated here rather than cross-referenced,
deliberately: a reader of this module should not have to open `stream.py` and
`transaction.py` to learn what the contract is. What IS shared with the sync facade is
the code that has no I/O in it at all - `_build_chunk` and the `_EndOfStream` sentinel -
because only the *iteration* genuinely differs between the two.
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
from .stream import _END_OF_STREAM, InsertStreamRequest, _build_chunk, _EndOfStream

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
)


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


async def _aiter_chunks(
    chunks: Iterable[Sequence[messages.GrpcRecord]] | AsyncIterable[Sequence[messages.GrpcRecord]],
) -> AsyncGenerator[Sequence[messages.GrpcRecord], None]:
    """Normalises either half of `InsertStreamRequest.chunks` into one async source.

    The async facade accepts BOTH halves of the declared union, unlike the sync facade,
    which genuinely cannot consume the async half and rejects it eagerly with a message
    pointing here. A caller who already has a list should not have to wrap it in an async
    generator just to reach this facade.

    The parameter is `AsyncIterable`, not `AsyncIterator`, because that is what
    `InsertStreamRequest.chunks` declares: an object with `__aiter__` but no `__anext__`
    of its own is a legitimate caller value, and narrowing this would reject it.
    """
    if isinstance(chunks, Iterable):
        for chunk in chunks:
            yield chunk
        return
    async for chunk in chunks:
        yield chunk


async def _envelope_chunks(request: InsertStreamRequest, session_id: str) -> AsyncGenerator[messages.InsertChunk, None]:
    """Turns `request.chunks` into wire `InsertChunk`s, adding the envelope bookkeeping.

    One `session_id` stable for the whole stream, `chunk_seq` starting at 1, `database` on
    the first chunk only (per the .proto contract, and mirrored into `options.database`
    there too - on 26.9.1 and earlier the server builds its `InsertContext` from
    `InsertOptions.database` ALONE and never reads `InsertChunk.database`, so without the
    mirror every stream fails at the deferred commit with "Invalid database name: name is
    required"; ArcadeData/arcadedb#6597), and `last=True` on the final chunk only.

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

    Unlike `stream._envelope_chunks` there is no eager-validation split here: both halves
    of the `chunks` union are accepted, so there is nothing to reject before the RPC opens.
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
        """Forces `database` and `transaction` onto `request`, overriding the caller.

        The override is the mechanism, not a detail: it is what makes the 2026-07 gRPC
        audit's #5040-#5042 unrepeatable. A request that arrived naming another database,
        or carrying another transaction id, leaves here naming this one.

        `CopyFrom`, never `MergeFrom`: `TransactionContext` also carries inline
        `begin`/`commit`/`rollback`/`read_only` flags, and a merge would correct the id
        while letting a caller-supplied `rollback=True` ride through into a call this
        handle is meant to have full control over.
        """
        request.database = self._database
        request.transaction.CopyFrom(
            messages.TransactionContext(transaction_id=self._transaction_id, database=self._database)
        )
        return request

    async def execute_query(self, request: messages.ExecuteQueryRequest) -> messages.ExecuteQueryResponse:
        return await self._raw.ExecuteQuery(self._bind(request))

    async def execute_command(self, request: messages.ExecuteCommandRequest) -> messages.ExecuteCommandResponse:
        return await self._raw.ExecuteCommand(self._bind(request))

    async def create_record(self, request: messages.CreateRecordRequest) -> messages.CreateRecordResponse:
        return await self._raw.CreateRecord(self._bind(request))

    async def update_record(self, request: messages.UpdateRecordRequest) -> messages.UpdateRecordResponse:
        return await self._raw.UpdateRecord(self._bind(request))

    async def delete_record(self, request: messages.DeleteRecordRequest) -> messages.DeleteRecordResponse:
        return await self._raw.DeleteRecord(self._bind(request))

    async def lookup_by_rid(self, request: messages.LookupByRidRequest) -> messages.LookupByRidResponse:
        return await self._raw.LookupByRid(self._bind(request))

    def stream_query(
        self, request: messages.StreamQueryRequest, *, timeout: float | None = None
    ) -> AsyncIterator[messages.GrpcRecord]:
        """Streams a bound query's results row by row: `async for r in tx.stream_query(...)`.

        A plain `def` returning the async generator `_stream_query` produces, rather than
        an `async def` that re-yields it: the caller gets the same directly-`async for`-able
        object either way, and this spelling keeps the flattening in exactly one place.
        """
        return _stream_query(self._raw, self._bind(request), timeout=timeout)


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
        # Returns None, not a bool: a falsy return does not suppress the body's exception,
        # and an exception raised in here (the failed-commit check below) propagates.
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

        NOT available on `AsyncTransactionHandle`: ArcadeData/arcadedb#6607 has the server
        ignoring `TransactionContext` here, so offering it there would imply a
        transactional guarantee the server does not honour.
        """
        return await self.raw.InsertStream(_envelope_chunks(request, str(uuid.uuid4())), timeout=timeout)

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
