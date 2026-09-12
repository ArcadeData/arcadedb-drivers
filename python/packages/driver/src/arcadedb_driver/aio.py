"""The asynchronous facade: `AsyncArcadeDBServer`, `AsyncArcadeDBDatabase`, `AsyncTransaction`.

Every generated operation emits both a `sync_detailed` and an `asyncio_detailed`
returning the SAME `Response`, so this module shares request building, envelope
normalisation and `unwrap` with the synchronous facade and differs only in which
call style it uses. The duplication that remains is mechanical and deliberate;
`unasync`-style single-source generation is a non-goal.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Mapping
from functools import cached_property
from types import TracebackType
from typing import Any, Literal

import httpx

from ._generated.api.command import execute_command
from ._generated.api.database import check_database_exists, list_databases
from ._generated.api.health import check_health, check_ready
from ._generated.api.query import execute_query_post
from ._generated.api.server import get_server_info
from ._generated.api.transaction import begin_transaction as begin_op
from ._generated.api.transaction import commit_transaction as commit_op
from ._generated.api.transaction import rollback_transaction as rollback_op
from ._generated.client import Client
from ._generated.models.nd_json_query_event import NdJsonQueryEvent
from ._generated.models.query_response import QueryResponse
from ._generated.models.server_info import ServerInfo
from ._generated.types import Unset
from ._internal.unwrap import is_success, unwrap
from .errors import ArcadeDBError
from .facade.dashboards import AsyncGrafanaNamespace, AsyncPromQLNamespace
from .facade.data import (
    SESSION_HEADER,
    QueryEnvelope,
    QueryLanguage,
    build_command_request,
    build_query_request,
    session_kwarg,
    to_envelope,
)
from .facade.stream import astream_command, astream_query
from .facade.timeseries import AsyncTimeSeriesNamespace
from .facade.vector import AsyncVectorNamespace

__all__ = ["AsyncArcadeDBDatabase", "AsyncArcadeDBServer", "AsyncTransaction"]


async def begin_transaction(client: Client, database: str) -> str:
    """Begins a transaction and returns its session id, read from the `arcadedb-session-id` response header."""
    response = await begin_op.asyncio_detailed(database, client=client)
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
      open until `arcadedb.server.httpTxExpireTimeout` reaps it.
    """

    def __init__(self, client: Client, database: str) -> None:
        self._client = client
        self._database = database
        self._session_id: str | None = None

    async def __aenter__(self) -> AsyncArcadeDBDatabase:
        self._session_id = await begin_transaction(self._client, self._database)
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
    ) -> QueryEnvelope:
        """Executes a read-or-write query and returns the whole result envelope - not just `result`."""
        response = await execute_query_post.asyncio_detailed(
            self.name,
            client=self._client,
            body=build_query_request(language=language, command=command, params=params, limit=limit),
            arcadedb_session_id=session_kwarg(self._session_id),
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
    ) -> QueryEnvelope:
        """Executes a command and returns the whole result envelope - not just `result`."""
        response = await execute_command.asyncio_detailed(
            self.name,
            client=self._client,
            body=build_command_request(language=language, command=command, params=params),
            arcadedb_session_id=session_kwarg(self._session_id),
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
        )

    def command_stream(
        self,
        *,
        language: QueryLanguage,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> AsyncGenerator[NdJsonQueryEvent, None]:
        """Streams `POST /api/v1/command/{database}` as `application/x-ndjson` - the `command`
        twin of `query_stream`; see its docstring for what an event carries and why an in-band
        `error` raises `ArcadeDBError`.

        Only a READ-ONLY statement can stream: a mutating one (`UPDATE`, `INSERT`, DDL,
        `RETURN AFTER` included) is refused with an `ArcadeDBError` (HTTP 400) before it produces a
        row, because a streamed response starts sending rows before the transaction commits, and
        that commit can still roll back. Use `command` for a mutating statement.
        """
        return astream_command(
            self._client, self.name, self._session_id, language=language, command=command, params=params
        )

    def transaction(self) -> AsyncTransaction:
        """Runs a block inside a server-side transaction; see `AsyncTransaction`."""
        return AsyncTransaction(self._client, self.name)

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
