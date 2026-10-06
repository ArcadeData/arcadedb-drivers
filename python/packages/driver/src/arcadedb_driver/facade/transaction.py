"""Transaction primitives and the synchronous transaction context manager."""

from __future__ import annotations

import contextlib
from types import TracebackType
from typing import TYPE_CHECKING, Literal

from .._generated.api.transaction import begin_transaction as begin_op
from .._generated.api.transaction import commit_transaction as commit_op
from .._generated.api.transaction import rollback_transaction as rollback_op
from .._generated.client import Client
from .._internal.unwrap import is_success, unwrap
from ..errors import ArcadeDBError
from .data import SESSION_HEADER

if TYPE_CHECKING:
    from .. import ArcadeDBDatabase


def begin_transaction(client: Client, database: str) -> str:
    """Begins a transaction and returns its session id.

    The endpoint answers 204 with no body and carries the id in the
    `arcadedb-session-id` RESPONSE header, so this reads `headers` rather than
    `parsed`. Threading that id onto every subsequent call is what keeps those calls
    inside the transaction.
    """
    response = begin_op.sync_detailed(database, client=client)
    if not is_success(response):
        raise ArcadeDBError.from_response(response)
    session_id = response.headers.get(SESSION_HEADER)
    if not session_id:
        raise ArcadeDBError(
            int(response.status_code),
            {"error": "begin_transaction did not return a session id"},
        )
    return session_id


def commit_transaction(client: Client, database: str, session_id: str) -> None:
    """Commits the transaction identified by `session_id`. The endpoint answers 204 with no body."""
    unwrap(commit_op.sync_detailed(database, client=client, arcadedb_session_id=session_id))


def rollback_transaction(client: Client, database: str, session_id: str) -> None:
    """Rolls back the transaction identified by `session_id`. The endpoint answers 204 with no body."""
    unwrap(rollback_op.sync_detailed(database, client=client, arcadedb_session_id=session_id))


class Transaction:
    """Runs a block inside a server-side transaction.

    `__enter__` begins the transaction and returns a SECOND `ArcadeDBDatabase`
    carrying the session id, so every call made through that handle - not through
    the outer database object - takes part in the transaction. Commits when the
    block exits cleanly; rolls back and re-raises when it raises.

    Two failure paths beyond the block raising are handled explicitly, so the
    server-side session is never left open and the caller's real error is never
    swallowed:

    - If the block raises and the resulting rollback ALSO fails, the rollback's
      error is attached as `__cause__` on the block's exception rather than
      replacing it - the block's error is what the caller asked about. The attach is
      skipped when `__cause__` is already set (a caller-set causal chain is never
      overwritten) and swallowed if it fails.
    - If the commit itself fails, a best-effort rollback is issued to release the
      session (its own failure discarded - the commit error is what the caller needs
      to see) before the commit error is re-raised. Without this a failed commit
      leaves the session open server-side until `arcadedb.server.httpSessionExpireTimeout`
      reaps it.
    """

    def __init__(self, client: Client, database: str) -> None:
        self._client = client
        self._database = database
        self._session_id: str | None = None

    def __enter__(self) -> ArcadeDBDatabase:
        from .. import ArcadeDBDatabase

        self._session_id = begin_transaction(self._client, self._database)
        return ArcadeDBDatabase(self._client, self._database, self._session_id)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        session_id = self._session_id
        assert session_id is not None

        if exc is not None:
            try:
                rollback_transaction(self._client, self._database, session_id)
            except Exception as rollback_err:
                if exc.__cause__ is None:
                    # Some libraries intern frozen sentinel errors that cannot take a new
                    # attribute. The rollback failure is dropped in that case; `exc` is
                    # re-raised as itself either way.
                    with contextlib.suppress(Exception):
                        exc.__cause__ = rollback_err
            return False

        try:
            commit_transaction(self._client, self._database, session_id)
        except Exception:
            # Best-effort: the commit error is what the caller needs to see, so the
            # rollback's own failure is deliberately discarded rather than chained.
            with contextlib.suppress(Exception):
                rollback_transaction(self._client, self._database, session_id)
            raise
        return False
