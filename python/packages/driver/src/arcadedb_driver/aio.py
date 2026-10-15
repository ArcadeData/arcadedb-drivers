"""The asynchronous facade: `AsyncArcadeDBServer`, `AsyncArcadeDBDatabase`, `AsyncTransaction`.

Every generated operation emits both a `sync_detailed` and an `asyncio_detailed`
returning the SAME `Response`, so this module shares request building, envelope
normalisation and `unwrap` with the synchronous facade and differs only in which
call style it uses. The duplication that remains is mechanical and deliberate;
`unasync`-style single-source generation is a non-goal.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Callable, Iterable, Mapping, Sequence
from datetime import datetime
from functools import cached_property
from types import TracebackType
from typing import Any, Literal

import httpx

from ._generated.api.auth import list_sessions, login, logout
from ._generated.api.command import execute_command
from ._generated.api.database import check_database_exists, list_databases
from ._generated.api.health import check_health, check_ready
from ._generated.api.query import execute_query_post
from ._generated.api.security import (
    create_api_token,
    create_or_update_group,
    create_user,
    delete_api_token,
    delete_group,
    delete_user,
    list_api_tokens,
    list_groups,
    list_users,
    update_user,
)
from ._generated.api.server import get_server_info
from ._generated.api.transaction import begin_transaction as begin_op
from ._generated.api.transaction import commit_transaction as commit_op
from ._generated.api.transaction import rollback_transaction as rollback_op
from ._generated.client import Client
from ._generated.models.nd_json_query_event import NdJsonQueryEvent
from ._generated.models.query_response import QueryResponse
from ._generated.models.server_info import ServerInfo
from ._generated.types import Unset
from ._internal.batch_rows import EdgeRow, VertexRow
from ._internal.unwrap import is_success, unwrap
from .auth import basic_auth, bearer_auth
from .errors import ArcadeDBError, InsertSessionError
from .facade.admin import (
    SERVER_COMMAND_URL,
    check_database_name,
    create_user_request,
    groups_from,
    save_group_request,
    server_command_payload,
    server_command_response,
    update_user_request,
    users_from,
)
from .facade.batch import BatchOptions, abatch_load, abatch_load_stream
from .facade.dashboards import AsyncGrafanaNamespace, AsyncPromQLNamespace
from .facade.data import (
    SESSION_HEADER,
    QueryEnvelope,
    QueryLanguage,
    build_command_request,
    build_query_request,
    query_tag_kwarg,
    session_kwarg,
    to_envelope,
)
from .facade.insert_session import AsyncInsertSession
from .facade.session import (
    LOGIN_URL,
    APIToken,
    CreatedAPIToken,
    LoginResult,
    Session,
    api_tokens_from,
    check_session_token,
    check_token_hash,
    create_api_token_request,
    created_api_token_from,
    login_as_response,
    login_result,
    sessions_from,
    with_authorization,
)
from .facade.stream import astream_command, astream_query
from .facade.timeseries import AsyncTimeSeriesNamespace
from .facade.vector import AsyncVectorNamespace

__all__ = ["AsyncArcadeDBDatabase", "AsyncArcadeDBServer", "AsyncTransaction"]


async def begin_transaction(client: Client, database: str, query_tag: str | None = None) -> str:
    """Begins a transaction and returns its session id, read from the `arcadedb-session-id` response header.

    `query_tag`, when set, goes out as `X-ArcadeDB-Query-Tag` on this begin request only; the
    server applies it to every statement of the session that carries no label of its own.
    """
    response = await begin_op.asyncio_detailed(
        database, client=client, x_arcade_db_query_tag=query_tag_kwarg(query_tag)
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


async def commit_transaction(client: Client, database: str, session_id: str) -> None:
    """Commits the transaction identified by `session_id`."""
    unwrap(await commit_op.asyncio_detailed(database, client=client, arcadedb_session_id=session_id))


async def rollback_transaction(client: Client, database: str, session_id: str) -> None:
    """Rolls back the transaction identified by `session_id`."""
    unwrap(await rollback_op.asyncio_detailed(database, client=client, arcadedb_session_id=session_id))


class AsyncTransaction:
    """The async twin of `Transaction`; the same commit/rollback contract, awaited.

    - The block's exception always wins.
    - A rollback that fails after the block raised is attached as `__cause__` only
      when `__cause__` is unset, and the attach is swallowed if it fails.
    - A commit that fails still issues a best-effort rollback (its own failure
      discarded) before the commit error is re-raised, so the session is not left
      open until `arcadedb.server.httpSessionExpireTimeout` reaps it.

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

    def __init__(self, client: Client, database: str, query_tag: str | None = None) -> None:
        self._client = client
        self._database = database
        self._query_tag = query_tag
        self._session_id: str | None = None

    async def __aenter__(self) -> AsyncArcadeDBDatabase:
        self._session_id = await begin_transaction(self._client, self._database, self._query_tag)
        return AsyncArcadeDBDatabase(self._client, self._database, self._session_id)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        session_id = self._session_id
        assert session_id is not None

        if exc is not None:
            try:
                await rollback_transaction(self._client, self._database, session_id)
            except Exception as rollback_err:
                if exc.__cause__ is None:
                    # Some libraries intern frozen sentinel errors that cannot take a new
                    # attribute. The rollback failure is dropped in that case; `exc` is
                    # re-raised as itself either way.
                    with contextlib.suppress(Exception):
                        exc.__cause__ = rollback_err
            return False

        try:
            await commit_transaction(self._client, self._database, session_id)
        except Exception:
            # Best-effort: the commit error is what the caller needs to see, so the
            # rollback's own failure is deliberately discarded rather than chained.
            with contextlib.suppress(Exception):
                await rollback_transaction(self._client, self._database, session_id)
            raise
        return False


class AsyncArcadeDBDatabase:
    """A single database reached through an `AsyncArcadeDBServer`.

    When held as a transaction handle, `session_id` is set and every call made
    through THIS instance carries it. Calls through the outer database object do not
    take part in the transaction.
    """

    def __init__(self, client: Client, name: str, session_id: str | None = None) -> None:
        self._client = client
        self.name = name
        self._session_id = session_id

    async def query(
        self,
        *,
        language: QueryLanguage,
        command: str,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
        query_tag: str | None = None,
    ) -> QueryEnvelope:
        """Executes a read-or-write query and returns the whole result envelope - not just `result`.

        `limit` caps the rows serialized into the response. Omitted, a `LIMIT` stated
        by the query is honoured as written and only a query stating none is capped
        by the server default. `-1` means no cap. No value here widens a response
        past the server's hard ceiling: a result exceeding it is refused with 413
        rather than truncated, so raising `limit` is not always the fix for a
        `truncated` response.

        `query_tag` labels the statement: it is sent as the `X-ArcadeDB-Query-Tag` request header,
        `list queries` shows it, and `terminate queries tag <label>` stops every statement carrying
        it. No header is sent when it is `None` or empty. It is not checked here: the contract's
        cap of 256 printable characters is the server's rule, a second copy of it client-side would
        only drift from the first, and a 26.11.1-SNAPSHOT server was observed accepting a longer
        tag - so do not count on a refusal either way. Inside a transaction a per-call tag overrides
        the label the transaction's begin request set.
        """
        response = await execute_query_post.asyncio_detailed(
            self.name,
            client=self._client,
            body=build_query_request(language=language, command=command, params=params, limit=limit),
            arcadedb_session_id=session_kwarg(self._session_id),
            x_arcade_db_query_tag=query_tag_kwarg(query_tag),
        )
        data = unwrap(response)
        assert isinstance(data, QueryResponse)
        return to_envelope(data)

    async def command(
        self,
        *,
        language: QueryLanguage,
        command: str,
        params: dict[str, Any] | None = None,
        query_tag: str | None = None,
    ) -> QueryEnvelope:
        """Executes a command and returns the whole result envelope - not just `result`.

        `query_tag` labels the statement: it is sent as the `X-ArcadeDB-Query-Tag` request header,
        `list queries` shows it, and `terminate queries tag <label>` stops every statement carrying
        it. No header is sent when it is `None` or empty. It is not checked here: the contract's
        cap of 256 printable characters is the server's rule, a second copy of it client-side would
        only drift from the first, and a 26.11.1-SNAPSHOT server was observed accepting a longer
        tag - so do not count on a refusal either way. Inside a transaction a per-call tag overrides
        the label the transaction's begin request set.
        """
        response = await execute_command.asyncio_detailed(
            self.name,
            client=self._client,
            body=build_command_request(language=language, command=command, params=params),
            arcadedb_session_id=session_kwarg(self._session_id),
            x_arcade_db_query_tag=query_tag_kwarg(query_tag),
        )
        data = unwrap(response)
        assert isinstance(data, QueryResponse)
        return to_envelope(data)

    def query_stream(
        self,
        *,
        language: QueryLanguage,
        command: str,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
        query_tag: str | None = None,
    ) -> AsyncGenerator[NdJsonQueryEvent, None]:
        """Streams `POST /api/v1/query/{database}` as `application/x-ndjson` instead of a single
        buffered `QueryEnvelope`, yielding one `NdJsonQueryEvent` per line.

        Each event carries exactly one of `record` (one result row), `stats` (a trailer carrying
        the same `limit`/`returned`/`truncated` `query`'s `QueryEnvelope` reports at top level -
        always the last event of a complete stream), or `error`. Ignoring `stats` loses the same
        information ignoring `QueryEnvelope.truncated` loses on the buffered path: a caller cannot
        tell a complete result from one the server's row cap cut short.

        `error` is a failure the server can only report after the 200 status line was already
        sent - the status cannot be taken back once the stream has started, which is why the
        contract reports it in band rather than as an HTTP status. This method raises
        `ArcadeDBError` for it, exactly as `query` raises for a non-2xx response, so both paths
        fail the same way. Any event already yielded before the error stays delivered; the
        `ArcadeDBError` is raised from the iterator at the point the `error` event arrives.

        The raised error's `status` is the event's own `status` - the status the buffered
        encoding would have answered the same failure with (503 for a retryable conflict, 409
        for a duplicated key, ...) - and is 200 only when the event carries none. This is a
        breaking change: before issue #117 it was always 200. `error` is the event's classified
        label (its `message` when it has none); `exception`, `detail`, `exception_args` and
        `retry_after` are the event's own; `request_id` is the response's `X-Request-Id` header,
        else the event's `requestId`. `commit_index` stays `None`: the event carries none.

        `query_tag` labels the statement: it is sent as the `X-ArcadeDB-Query-Tag` request header,
        `list queries` shows it, and `terminate queries tag <label>` stops every statement carrying
        it. No header is sent when it is `None` or empty. It is not checked here: the contract's
        cap of 256 printable characters is the server's rule, a second copy of it client-side would
        only drift from the first, and a 26.11.1-SNAPSHOT server was observed accepting a longer
        tag - so do not count on a refusal either way. Inside a transaction a per-call tag overrides
        the label the transaction's begin request set.

        `query` itself is unaffected: it keeps returning `QueryEnvelope` and sending no `Accept`
        header. This is a separate method, not a mode.
        """
        return astream_query(
            self._client,
            self.name,
            self._session_id,
            language=language,
            command=command,
            params=params,
            limit=limit,
            query_tag=query_tag,
        )

    def command_stream(
        self,
        *,
        language: QueryLanguage,
        command: str,
        params: dict[str, Any] | None = None,
        query_tag: str | None = None,
    ) -> AsyncGenerator[NdJsonQueryEvent, None]:
        """Streams `POST /api/v1/command/{database}` as `application/x-ndjson` - the `command`
        twin of `query_stream`; see its docstring for what an event carries and why an in-band
        `error` raises `ArcadeDBError`.

        Only a READ-ONLY statement can stream: a mutating one (`UPDATE`, `INSERT`, DDL,
        `RETURN AFTER` included) is refused with an `ArcadeDBError` (HTTP 400) before it produces a
        row, because a streamed response starts sending rows before the transaction commits, and
        that commit can still roll back. Use `command` for a mutating statement.

        `query_tag` labels the statement: it is sent as the `X-ArcadeDB-Query-Tag` request header,
        `list queries` shows it, and `terminate queries tag <label>` stops every statement carrying
        it. No header is sent when it is `None` or empty. It is not checked here: the contract's
        cap of 256 printable characters is the server's rule, a second copy of it client-side would
        only drift from the first, and a 26.11.1-SNAPSHOT server was observed accepting a longer
        tag - so do not count on a refusal either way. Inside a transaction a per-call tag overrides
        the label the transaction's begin request set.
        """
        return astream_command(
            self._client,
            self.name,
            self._session_id,
            language=language,
            command=command,
            params=params,
            query_tag=query_tag,
        )

    async def batch_load(
        self,
        *,
        vertices: Iterable[VertexRow] = (),
        edges: Iterable[EdgeRow] = (),
        options: BatchOptions | None = None,
        query_tag: str | None = None,
    ) -> dict[str, Any]:
        """Bulk-loads vertices and edges via `POST /api/v1/batch/{database}`, buffering the
        whole response before returning. `serialize_rows` (via `vertices`/`edges`) always emits
        every vertex before any edge, because the server resolves an edge's `from_`/`to` against
        temporary ids declared earlier in the SAME payload only.

        A load is NOT atomic: the server commits every `options["commitEvery"]` records, so a
        failure partway through leaves earlier chunks durably committed - `ArcadeDBError` raised
        from a failed load still corresponds to real, already-durable data. Because temporary ids
        are not keys, retrying the whole payload after such a failure duplicates whatever already
        committed rather than resuming cleanly. Use `batch_load_stream` when the caller needs to
        see how far a load got before it failed.

        `query_tag` is sent as the `X-ArcadeDB-Query-Tag` request header - never as a query
        parameter, unlike `options` - so `list queries` shows the load and
        `terminate queries tag <label>` can stop it. No header is sent when it is `None` or
        empty; its length and characters are not checked client-side.
        """
        return await abatch_load(
            self._client, self.name, vertices=vertices, edges=edges, options=options, query_tag=query_tag
        )

    def batch_load_stream(
        self,
        *,
        vertices: Iterable[VertexRow] = (),
        edges: Iterable[EdgeRow] = (),
        options: BatchOptions | None = None,
        query_tag: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Streams the same bulk load as `batch_load`, but as `application/x-ndjson`: a
        `progress` event at every vertex commit and every `options["commitEvery"]` edges, then
        exactly one `summary` or `error` event carrying the same object the buffered call would
        otherwise have returned. An in-band `error` event raises `ArcadeDBError` instead of being
        yielded - see `facade/batch.py`'s `_raise_on_error_event` for why the two ways a load can
        fail (before vs. after the first acknowledgement) both end up on this one throwing path.
        A `progress` event's `idMapping` is only the fragment that chunk resolved - it is never
        merged across events, so a caller that needs the whole mapping must concatenate it
        themselves as they receive it.

        The raised error's `status` is the event's own (500 when it carries none), and it
        carries the event's `error`, `exception`, `exception_args`, `retry_after` and
        `commit_index`. `commit_index` is a valid read-after barrier even here: feed it back as
        `X-ArcadeDB-Read-After` to read at least the state the load had committed.

        `query_tag` is sent as the `X-ArcadeDB-Query-Tag` request header - never as a query
        parameter, unlike `options` - so `list queries` shows the load and
        `terminate queries tag <label>` can stop it. No header is sent when it is `None` or
        empty; its length and characters are not checked client-side.
        """
        return abatch_load_stream(
            self._client, self.name, vertices=vertices, edges=edges, options=options, query_tag=query_tag
        )

    def transaction(self, *, query_tag: str | None = None) -> AsyncTransaction:
        """Runs a block inside a server-side transaction; see `AsyncTransaction`.

        `query_tag` is sent as `X-ArcadeDB-Query-Tag` on the begin request only, and the server
        applies it to every statement of the transaction that carries no label of its own; a
        statement that passes its own `query_tag` through the handle overrides it. No header is
        sent when it is `None` or empty. The client does not check its length or characters (the
        256-character cap is the server's rule, and not one to count on a refusal from).
        """
        return AsyncTransaction(self._client, self.name, query_tag=query_tag)

    def insert_session(
        self,
        *,
        session_id: str | None = None,
        target_type: str | None = None,
        transaction_mode: str | None = None,
        conflict_mode: str | None = None,
        key_columns: Sequence[str] | None = None,
        update_columns_on_conflict: Sequence[str] | None = None,
        validate_only: bool = False,
        join_current_transaction: bool = False,
        on_batch_ack: Callable[[dict[str, Any]], None] | None = None,
        timeout: float = 60.0,
    ) -> AsyncInsertSession:
        """Prepares a duplex insert session on the server's `/ws` endpoint; see `AsyncInsertSession`.

        Nothing is connected until the result is entered (`async with db.insert_session(...) as s:`) or
        `await open()`ed. Options map onto the `start` frame: `target_type` is the default type of every
        record (a record's own `"@class"` overrides it); `transaction_mode` is one of `per_stream`
        (the default), `per_batch`, `per_row`, `none`; `conflict_mode` one of `error` (the
        default), `update`, `ignore`, `abort`, with `key_columns` / `update_columns_on_conflict`;
        `validate_only` has the rows received, parsed and counted but not written. `session_id`
        names the session; left out the server generates one, and a chosen one lives in a single
        server-wide namespace. `on_batch_ack` is called with every `batchAck` before `send_chunk`
        returns it. `timeout` bounds the handshake and each wait for an answer, in seconds.

        `join_current_transaction=True` writes into the transaction THIS handle carries - so it only
        works on the handle `async with db.transaction()` yields - and implies `transaction_mode="none"`;
        any other explicit mode raises `InsertSessionError`, as it does in the Go and TypeScript
        clients, rather than being silently overridden. With
        no open transaction there is nothing to join, and this raises `InsertSessionError` here
        rather than quietly opening a server-managed session on the outer handle.
        """
        transaction_id: str | None = None
        if join_current_transaction:
            if self._session_id is None:
                raise InsertSessionError(
                    "The database has no open transaction to join: call insert_session() on the handle"
                    " `async with db.transaction()` yields"
                )
            if transaction_mode not in (None, "none"):
                raise InsertSessionError(
                    f"join_current_transaction=True implies transaction_mode='none', not {transaction_mode!r}"
                )
            transaction_id = self._session_id
            transaction_mode = "none"
        return AsyncInsertSession(
            self._client,
            self.name,
            session_id=session_id,
            transaction_id=transaction_id,
            target_type=target_type,
            transaction_mode=transaction_mode,
            conflict_mode=conflict_mode,
            key_columns=key_columns,
            update_columns_on_conflict=update_columns_on_conflict,
            validate_only=validate_only,
            on_batch_ack=on_batch_ack,
            timeout=timeout,
        )

    @cached_property
    def ts(self) -> AsyncTimeSeriesNamespace:
        """Ingests and queries samples in a time-series type."""
        return AsyncTimeSeriesNamespace(self._client, self.name)

    @cached_property
    def grafana(self) -> AsyncGrafanaNamespace:
        """Grafana panel queries over a time-series type."""
        return AsyncGrafanaNamespace(self._client, self.name)

    @cached_property
    def promql(self) -> AsyncPromQLNamespace:
        """A Prometheus-compatible query surface over a time-series type."""
        return AsyncPromQLNamespace(self._client, self.name)

    @cached_property
    def vector(self) -> AsyncVectorNamespace:
        """kNN vector search, fused hybrid search, and full-text search."""
        return AsyncVectorNamespace(self._client, self.name)


class AsyncArcadeDBServer:
    """The async twin of `ArcadeDBServer`.

    An async context manager because the underlying `httpx.AsyncClient` owns a
    connection pool that must be released. Use `async with`, or `await aclose()`.

    `timeout` defaults to `None`, and in httpx an explicit `None` means NO
    TIMEOUT - not "use httpx's default", which is 5 seconds. Omitting `timeout`
    therefore leaves requests free to hang forever on a stalled connection. This
    is deliberate, not an oversight: the generated `Client` this facade wraps
    defaults its own timeout to `None` and forwards it exactly the same way, so
    changing only the facade's default would make `AsyncArcadeDBServer` and
    `.raw` disagree against the same server; it also matches `@arcadedb/driver`,
    where `fetch` has no default timeout either. Pass an `httpx.Timeout` to
    bound requests.
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        verify_ssl: bool = True,
    ) -> None:
        merged: dict[str, str] = {**(auth or {}), **(headers or {})}
        # Kept for `with_token` and `logout`; `raw`'s own copies are private to the generator.
        self._base_url = base_url
        self._headers = merged
        self._timeout = timeout
        self._verify_ssl = verify_ssl
        #: The generated client. Returns a `Response` and does NOT raise, unlike
        #: every method here.
        self.raw = Client(base_url=base_url, headers=merged, timeout=timeout, verify_ssl=verify_ssl)

    def db(self, name: str) -> AsyncArcadeDBDatabase:
        """Scopes subsequent calls to one database, reached through this server."""
        return AsyncArcadeDBDatabase(self.raw, name)

    async def list_databases(self) -> list[str]:
        """Lists the names of every database visible to the authenticated caller."""
        data = unwrap(await list_databases.asyncio_detailed(client=self.raw))
        result = getattr(data, "result", None)
        return [] if result is None or isinstance(result, Unset) else list(result)

    async def exists(self, name: str) -> bool:
        """Checks whether a database exists and is visible to the authenticated caller.

        `False` cannot distinguish absence from a lack of authorization; the server
        does not make that distinction, so this client cannot either.
        """
        data = unwrap(await check_database_exists.asyncio_detailed(name, client=self.raw))
        result = getattr(data, "result", None)
        return False if result is None or isinstance(result, Unset) else bool(result)

    async def server_info(self) -> ServerInfo:
        """Retrieves server status, version, and configuration information."""
        data = unwrap(await get_server_info.asyncio_detailed(client=self.raw))
        assert isinstance(data, ServerInfo)
        return data

    async def health(self) -> None:
        """Liveness probe. Raises `ArcadeDBError` if the server does not answer 204."""
        unwrap(await check_health.asyncio_detailed(client=self.raw))

    async def ready(self) -> bool:
        """Readiness probe. `False` on 503; any other failure raises `ArcadeDBError`."""
        response = await check_ready.asyncio_detailed(client=self.raw)
        if int(response.status_code) == 503:
            return False
        if not is_success(response):
            raise ArcadeDBError.from_response(response)
        return True

    async def server_command(self, command: str) -> dict[str, Any]:
        """Runs one command through `POST /api/v1/server` and returns the whole JSON body.

        Most server commands are root-only; the contract's `executeServerCommand` lists them
        and says which ones any user may run. The body is returned unaltered because its
        shape depends on the command: `{"result": "ok"}` for an administrative command, a
        list for `list databases`, other shapes for others. It is decoded here rather than by
        the generated model, which declares an array `result` and raises `ValueError` on
        `"ok"` - see `facade/admin.py`. Raises `ArcadeDBError` on a non-2xx status.

        The command is sent as given. Prefer `create_database` / `drop_database`, which refuse
        a name the server would silently trim, and the user and group methods, which use the
        dedicated endpoints with a structured body instead of a command string.
        """
        raw = await self.raw.get_async_httpx_client().post(SERVER_COMMAND_URL, json=server_command_payload(command))
        return server_command_response(raw)

    async def create_database(self, name: str) -> None:
        """Creates the named database (root only).

        There is no dedicated endpoint, so this sends `create database <name>` through
        `server_command`. A name that is empty or has leading or trailing white space raises
        `ValueError` before anything is sent: the server trims the name it reads out of the
        command, so it would create a database other than the one named. Anything else is sent
        as given, embedded spaces included, and the server takes the rest of the command as the
        name: one request runs one command, so a name cannot smuggle in a second one, but a
        name built from untrusted input should still be validated by the caller.

        A name that already exists raises `ArcadeDBError` with status **409** (`error`
        "Database already exists"), so a caller can treat 409 as "already there" to create a
        database only when it is missing. A server built before ArcadeData/arcadedb#10079
        answers 400 "Cannot execute command" instead, with the reason only in `detail`, which
        this client does not match on; against such a server, await `exists` first: as root it
        sees every database, so its `False` is reliable, although another client can still
        create the database between the two calls.
        """
        check_database_name(name)
        await self.server_command(f"create database {name}")

    async def drop_database(self, name: str) -> None:
        """Drops the named database and deletes its files (root only).

        There is no dedicated endpoint, so this sends `drop database <name>` through
        `server_command`. A name that is empty or has leading or trailing white space raises
        `ValueError` before anything is sent, as for `create_database`. A database that does
        not exist raises `ArcadeDBError` with status 400.
        """
        check_database_name(name)
        await self.server_command(f"drop database {name}")

    async def create_user(
        self, name: str, password: str, *, databases: Mapping[str, Sequence[str]] | None = None
    ) -> None:
        """Creates a server user (root only) through `POST /api/v1/server/users`.

        `databases` maps a database name, or `"*"` for every database, to the groups the user
        holds there; omitting it sends no assignment. The server refuses a blank name, a name
        starting with `apitoken:`, and a password shorter than 8 or longer than 256
        characters, each with a 400 `ArcadeDBError`.

        A name that already exists raises `ArcadeDBError` with status **409** (`error` "User
        already exists"), so a caller can treat 409 as "already there" to create a user only
        when it is missing. A server built before ArcadeData/arcadedb#10076 answers 403
        "Security error" instead, which is also what a non-root caller gets; against such a
        server, look for the user in `list_users` first rather than reading a 403 as "already
        exists".
        """
        unwrap(await create_user.asyncio_detailed(client=self.raw, body=create_user_request(name, password, databases)))

    async def update_user(
        self,
        name: str,
        *,
        password: str | None = None,
        databases: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        """Changes an existing user's password, database assignments, or both (root only),
        through `PUT /api/v1/server/users`.

        An argument left as `None` is not sent, and the server keeps that value. An empty
        `databases` mapping IS sent, and removes every assignment. A user that does not exist
        raises `ArcadeDBError` with status 404.
        """
        unwrap(
            await update_user.asyncio_detailed(
                client=self.raw, name=name, body=update_user_request(password, databases)
            )
        )

    async def drop_user(self, name: str) -> None:
        """Deletes a server user (root only) through `DELETE /api/v1/server/users`.

        A user that does not exist raises `ArcadeDBError` with status 404; root cannot be
        deleted (400).
        """
        unwrap(await delete_user.asyncio_detailed(client=self.raw, name=name))

    async def list_users(self) -> list[dict[str, Any]]:
        """Lists every server user (root only), each as `{"name": ..., "databases": {...}}`.

        `databases` maps a database name, or `"*"`, to the user's groups there. The password
        hash is never returned.
        """
        return users_from(unwrap(await list_users.asyncio_detailed(client=self.raw)))

    async def save_group(
        self,
        database: str,
        name: str,
        *,
        access: Sequence[str] | None = None,
        read_timeout: int | None = None,
        result_set_limit: int | None = None,
        types: Mapping[str, Any] | None = None,
    ) -> None:
        """Creates the named group on `database` (`"*"` for every database), or replaces it if
        it exists (root only), through `POST /api/v1/server/groups`. An argument left as
        `None` is not sent."""
        body = save_group_request(database, name, access, read_timeout, result_set_limit, types)
        unwrap(await create_or_update_group.asyncio_detailed(client=self.raw, body=body))

    async def delete_group(self, database: str, name: str) -> None:
        """Deletes one group of one database (root only) through
        `DELETE /api/v1/server/groups`. A group that does not exist raises `ArcadeDBError`
        with status 404."""
        unwrap(await delete_group.asyncio_detailed(client=self.raw, database=database, name=name))

    async def list_groups(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Lists every security group (root only) as plain dicts, keyed by database name
        (`"*"` covers every database) and then by group name. The group document's schema
        version is not returned."""
        return groups_from(unwrap(await list_groups.asyncio_detailed(client=self.raw)))

    async def login(self) -> LoginResult:
        """Opens a session with the client's own credentials through `POST /api/v1/login` and
        returns its token. The client itself is unchanged: present the token with `with_token`.

        Wrong Basic credentials raise `ArcadeDBError` with status **403** ("Security error"),
        not 401: the server answers a failed password check with 403 on every endpoint, so on
        `login` it cannot be told apart from a forbidden user (ArcadeData/arcadedb#10109). 401
        is what an invalid or expired bearer token gets. A server that has reached its limit of
        concurrent sessions answers 503.

        Each login opens a new session, and a user holds at most 100 by default
        (`arcadedb.server.httpAuthSessionMaxPerUser`): the next login silently evicts that
        user's oldest session, whose token then gets a 401. Log in once and reuse the token.
        """
        return login_result(unwrap(await login.asyncio_detailed(client=self.raw)))

    async def login_as(self, user: str, password: str) -> LoginResult:
        """Opens a session as `user`, whatever credentials the client is configured with, and
        returns its token, as `login` does and with the same failures. It is the way to act as
        one user from a client built for another: for per-user isolation, log in as the user
        once and keep `with_token(result.token)` rather than the user's password.

        The credentials go on this one request only; the client's own are unchanged, for this
        call and every other.
        """
        raw = await self.raw.get_async_httpx_client().post(LOGIN_URL, headers=basic_auth(user, password))
        return login_as_response(raw)

    def with_token(self, token: str) -> AsyncArcadeDBServer:
        """Returns a new `AsyncArcadeDBServer` that authenticates every request with `token` as a
        bearer token, and is otherwise configured like this one: the same base URL, extra
        headers, timeout and TLS verification. This server is unchanged. It performs no request.

        `token` is a session token from `login` or `login_as`, or an API token from
        `create_api_token`. The new server has its own connection pool, so close it (`aclose`, or
        an `async with` block) like any other; closing one does not close the other.
        """
        return AsyncArcadeDBServer(
            base_url=self._base_url,
            headers=with_authorization(self._headers, bearer_auth(token)["Authorization"]),
            timeout=self._timeout,
            verify_ssl=self._verify_ssl,
        )

    async def logout(self) -> None:
        """Invalidates the session token this client presents, through `POST /api/v1/logout`.

        A client that does not present a session token from `login` (Basic credentials, or an
        API token) raises `NotSessionTokenError` without a request: the server answers 204 to
        such a logout and invalidates nothing. A token that is no longer valid, because it was
        already logged out or has expired, raises `ArcadeDBError` with status 401. Once this
        returns, every request with the token, from any client, is a 401.
        """
        check_session_token(self._headers)
        unwrap(await logout.asyncio_detailed(client=self.raw))

    async def list_sessions(self) -> list[Session]:
        """Lists every authentication session the server holds (root only; any other user gets
        a 403 `ArcadeDBError`). Each carries its live token, so the result is as sensitive as
        the users' passwords."""
        return sessions_from(unwrap(await list_sessions.asyncio_detailed(client=self.raw)))

    async def create_api_token(
        self,
        name: str,
        *,
        database: str | None = None,
        expires_at: datetime | None = None,
        permissions: Mapping[str, Any] | None = None,
    ) -> CreatedAPIToken:
        """Issues an API token (root only) through `POST /api/v1/server/api-tokens`. The
        plaintext token is in the result's `token` and nowhere else, ever: see
        `CreatedAPIToken`.

        `database` scopes the token to one database; `None` means `"*"`, every database.
        `expires_at` is when the token stops authenticating, and `None` means never; it must be
        timezone-aware and after the Unix epoch, or `ValueError` is raised before anything is
        sent (the server reads an expiry of 0 as "never"). `permissions` takes the shape a
        group's `types` map takes (see `save_group`); `None` grants none.

        A name already in use raises `ArcadeDBError` with status 409, and a blank name a 400.
        The server refuses to send the token in the clear: unless the request arrives over
        HTTPS, from a loopback address, or through a trusted proxy that terminated TLS, it
        answers 412 and issues nothing when `arcadedb.server.apiTokenRequireSecureTransport` is
        on (the default from ArcadeDB 27.1.1).
        """
        body = create_api_token_request(name, database, expires_at, permissions)
        return created_api_token_from(unwrap(await create_api_token.asyncio_detailed(client=self.raw, body=body)))

    async def list_api_tokens(self) -> list[APIToken]:
        """Lists every issued API token as metadata (root only); never the token itself."""
        return api_tokens_from(unwrap(await list_api_tokens.asyncio_detailed(client=self.raw)))

    async def delete_api_token(self, token_hash: str) -> None:
        """Revokes the API token whose hash is `token_hash` (root only), through
        `DELETE /api/v1/server/api-tokens`.

        It takes the `token_hash` that `list_api_tokens` and `create_api_token` report, never
        the token: anything but 64 lowercase hexadecimal characters raises `ValueError` before
        it is sent, because the argument travels in the query string, which proxies and access
        logs record. The error does not repeat the argument. A hash no token has raises
        `ArcadeDBError` with status 404, a status the contract does not list
        (ArcadeData/arcadedb#10110).
        """
        check_token_hash(token_hash)
        unwrap(await delete_api_token.asyncio_detailed(client=self.raw, token=token_hash))

    async def aclose(self) -> None:
        """Closes the underlying httpx client and its connection pool."""
        await self.raw.get_async_httpx_client().aclose()

    async def __aenter__(self) -> AsyncArcadeDBServer:
        await self.raw.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.raw.__aexit__(exc_type, exc, tb)
