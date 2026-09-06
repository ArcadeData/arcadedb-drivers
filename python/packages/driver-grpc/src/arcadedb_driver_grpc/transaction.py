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
from collections.abc import Iterator, Sequence
from types import TracebackType
from typing import TypeVar

from ._generated import arcadedb_server_pb2 as messages
from ._generated.arcadedb_server_pb2_grpc import ArcadeDbServiceStub
from .stream import stream_query as _stream_query

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
)


def _as_metadata(
    metadata: Sequence[tuple[str, str | bytes]] | None,
) -> tuple[tuple[str, str | bytes], ...] | None:
    """Adapts this facade's public `Sequence` parameter to the sync stub's own type.

    `grpc-stubs` types the SYNC `UnaryUnaryMultiCallable.__call__`'s `metadata` as
    `tuple[tuple[str, str | bytes], ...] | None` - a concrete homogeneous tuple, not
    `Sequence` - while `grpc.aio`'s equivalent accepts the broader
    `Metadata | Sequence[MetadatumType]`, which is why `aio.py`'s `AsyncTransactionHandle`
    needs no equivalent conversion. Narrowing this handle's own public parameter to a
    tuple would fix the mismatch too, but `Sequence` is what a caller most naturally has
    on hand (a list built up in a loop) and is already the shape `auth.Auth.metadata`
    documents, so the conversion happens here instead of pushing a tuple requirement onto
    every caller.
    """
    return None if metadata is None else tuple(metadata)


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
        """
        bound = type(request)()
        bound.CopyFrom(request)
        bound.database = self._database
        bound.transaction.CopyFrom(
            messages.TransactionContext(transaction_id=self._transaction_id, database=self._database)
        )
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
        self, request: messages.StreamQueryRequest, *, timeout: float | None = None
    ) -> Iterator[messages.GrpcRecord]:
        return _stream_query(self._raw, self._bind(request), timeout=timeout)


class Transaction:
    """A server-side transaction, begun on `__enter__` and ended on `__exit__`."""

    def __init__(self, raw: ArcadeDbServiceStub, database: str) -> None:
        self._raw = raw
        self._database = database
        self._transaction_id = ""

    def __enter__(self) -> TransactionHandle:
        begun = self._raw.BeginTransaction(messages.BeginTransactionRequest(database=self._database))
        if not begun.transaction_id.strip():
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
            # success=true, committed=false with no error status is what a server answers
            # for a transaction it already reaped. Reporting success would silently lose
            # the caller's writes.
            raise RuntimeError(
                f'transaction: commit for database "{self._database}" '
                f"(transaction_id={self._transaction_id}) did not take effect: "
                f"{committed.message or 'no message from server'}"
            )
