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
from .data import SESSION_HEADER, IsolationLevel, begin_request, query_tag_kwarg

if TYPE_CHECKING:
    from .. import ArcadeDBDatabase


def begin_transaction(
    client: Client, database: str, query_tag: str | None = None, isolation_level: IsolationLevel | None = None
) -> str:
    """Begins a transaction and returns its session id.

    The endpoint answers 204 with no body and carries the id in the
    `arcadedb-session-id` RESPONSE header, so this reads `headers` rather than
    `parsed`. Threading that id onto every subsequent call is what keeps those calls
    inside the transaction.

    `query_tag`, when set, goes out as `X-ArcadeDB-Query-Tag` on this begin request
    only; the server applies it to every statement of the session that carries no
    label of its own.

    `isolation_level`, when set, is the request's only body (`{"isolationLevel": ...}`);
    with none there is no body and the server uses the database's default level. A
    value other than `READ_COMMITTED` or `REPEATABLE_READ` raises `ValueError` unsent.
    """
    response = begin_op.sync_detailed(
        database,
        client=client,
        body=begin_request(isolation_level),
        x_arcade_db_query_tag=query_tag_kwarg(query_tag),
    )
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

    `isolation_level` is `READ_COMMITTED` or `REPEATABLE_READ`, sent in the begin
    request's body; `None` sends no body, and the server begins at the database's default
    level. Under `REPEATABLE_READ` a record the block has read keeps the value it was read
    with even after another session commits a change to it; under `READ_COMMITTED` a second
    read sees the change. Any other value raises `ValueError` when the transaction is
    created, before anything is sent.

    `query_tag` is sent as `X-ArcadeDB-Query-Tag` on the begin request ONLY - never on
    the statements, the commit or the rollback. The server labels every statement of
    the session that carries no label of its own with it, so `list queries` shows them
    and `terminate queries tag <label>` stops them. A statement that passes its own
    `query_tag` through the handle sends its own header, which overrides the
    session's label for that statement.

    **Partial commits.** A statement inside the block that publishes a commit while it
    runs - an explicit `BATCH n` boundary, or a statement with its own `COMMIT` - makes
    part of the transaction durable before the block ends, and a rollback cannot undo
    that part. The server flags such a response with
    `arcadedb-session-partial-commit: true`; this class does not surface the header
    (it is reachable through `raw`). A caller that replays a transaction block on
    conflict must not replay one that partially committed.
    """

    def __init__(
        self,
        client: Client,
        database: str,
        query_tag: str | None = None,
        isolation_level: IsolationLevel | None = None,
    ) -> None:
        begin_request(isolation_level)  # refuses an unsupported level now, before the block runs
        self._client = client
        self._database = database
        self._query_tag = query_tag
        self._isolation_level = isolation_level
        self._session_id: str | None = None

    def __enter__(self) -> ArcadeDBDatabase:
        from .. import ArcadeDBDatabase

        self._session_id = begin_transaction(self._client, self._database, self._query_tag, self._isolation_level)
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
