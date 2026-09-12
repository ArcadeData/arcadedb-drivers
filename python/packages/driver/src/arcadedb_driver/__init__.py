"""Python HTTP client for ArcadeDB, generated from ArcadeDB's OpenAPI contract."""

from __future__ import annotations

from collections.abc import Generator, Mapping
from functools import cached_property
from types import TracebackType
from typing import Any

import httpx

from ._generated.api.command import execute_command
from ._generated.api.database import check_database_exists, list_databases
from ._generated.api.health import check_health, check_ready
from ._generated.api.query import execute_query_post
from ._generated.api.server import get_server_info
from ._generated.client import Client
from ._generated.models.nd_json_query_event import NdJsonQueryEvent
from ._generated.models.query_response import QueryResponse
from ._generated.models.server_info import ServerInfo
from ._generated.types import Unset
from ._internal.unwrap import is_success, unwrap
from .aio import AsyncArcadeDBDatabase, AsyncArcadeDBServer, AsyncTransaction
from .auth import basic_auth, bearer_auth
from .errors import ArcadeDBError
from .facade.dashboards import GrafanaNamespace, PromQLNamespace
from .facade.data import (
    QueryEnvelope,
    QueryLanguage,
    build_command_request,
    build_query_request,
    session_kwarg,
    to_envelope,
)
from .facade.stream import stream_command, stream_query
from .facade.timeseries import TimeSeriesNamespace
from .facade.transaction import Transaction
from .facade.vector import VectorNamespace

__version__ = "0.1.0"

__all__ = [
    "ArcadeDBDatabase",
    "ArcadeDBError",
    "ArcadeDBServer",
    "AsyncArcadeDBDatabase",
    "AsyncArcadeDBServer",
    "AsyncTransaction",
    "QueryEnvelope",
    "QueryLanguage",
    "Transaction",
    "__version__",
    "basic_auth",
    "bearer_auth",
]


class ArcadeDBDatabase:
    """A single database reached through an `ArcadeDBServer`. Constructed by `ArcadeDBServer.db()`.

    When held as a transaction handle, `session_id` is set and every `query` /
    `command` call made through THIS instance carries it, which is what keeps those
    calls inside the transaction rather than auto-committing individually. Calls
    made through the outer database object do not take part in the transaction.
    """

    def __init__(self, client: Client, name: str, session_id: str | None = None) -> None:
        self._client = client
        self.name = name
        self._session_id = session_id

    def query(
        self,
        *,
        language: QueryLanguage,
        command: str,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> QueryEnvelope:
        """Executes a read-or-write query and returns the whole result envelope - not just `result`.

        `limit` caps the rows serialized into the response. Omitted, a `LIMIT` stated
        by the query is honoured as written and only a query stating none is capped
        by the server default. `-1` means no cap. No value here widens a response
        past the server's hard ceiling: a result exceeding it is refused with 413
        rather than truncated, so raising `limit` is not always the fix for a
        `truncated` response.
        """
        response = execute_query_post.sync_detailed(
            self.name,
            client=self._client,
            body=build_query_request(language=language, command=command, params=params, limit=limit),
            arcadedb_session_id=session_kwarg(self._session_id),
        )
        data = unwrap(response)
        # `unwrap` has already raised on any non-2xx, so the generated union's
        # ErrorResponse member cannot reach here; this narrows it for the typechecker.
        assert isinstance(data, QueryResponse)
        return to_envelope(data)

    def command(
        self,
        *,
        language: QueryLanguage,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> QueryEnvelope:
        """Executes a command and returns the whole result envelope - not just `result`."""
        response = execute_command.sync_detailed(
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
    ) -> Generator[NdJsonQueryEvent, None, None]:
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
        return stream_query(
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
    ) -> Generator[NdJsonQueryEvent, None, None]:
        """Streams `POST /api/v1/command/{database}` as `application/x-ndjson` - the `command`
        twin of `query_stream`; see its docstring for what an event carries and why an in-band
        `error` raises `ArcadeDBError`."""
        return stream_command(
            self._client, self.name, self._session_id, language=language, command=command, params=params
        )

    def transaction(self) -> Transaction:
        """Runs a block inside a server-side transaction; see `Transaction`."""
        return Transaction(self._client, self.name)

    @cached_property
    def ts(self) -> TimeSeriesNamespace:
        """Ingests and queries samples in a time-series type."""
        return TimeSeriesNamespace(self._client, self.name)

    @cached_property
    def grafana(self) -> GrafanaNamespace:
        """Grafana panel queries over a time-series type."""
        return GrafanaNamespace(self._client, self.name)

    @cached_property
    def promql(self) -> PromQLNamespace:
        """A Prometheus-compatible query surface over a time-series type."""
        return PromQLNamespace(self._client, self.name)

    @cached_property
    def vector(self) -> VectorNamespace:
        """kNN vector search, fused hybrid search, and full-text search."""
        return VectorNamespace(self._client, self.name)


class ArcadeDBServer:
    """A connection to one ArcadeDB server.

    Scoped to server-level operations (listing and checking databases, server info,
    health and readiness) plus `db()` to reach a specific database.

    This is a context manager because the underlying httpx client owns a connection
    pool that must be released - a concern `@arcadedb/driver` does not have, since
    `fetch` owns nothing. Use `with`, or call `close()` yourself.

    `timeout` defaults to `None`, and in httpx an explicit `None` means NO
    TIMEOUT - not "use httpx's default", which is 5 seconds. Omitting `timeout`
    therefore leaves requests free to hang forever on a stalled connection. This
    is deliberate, not an oversight: the generated `Client` this facade wraps
    defaults its own timeout to `None` and forwards it exactly the same way, so
    changing only the facade's default would make `ArcadeDBServer` and `.raw`
    disagree against the same server; it also matches `@arcadedb/driver`, where
    `fetch` has no default timeout either. Pass an `httpx.Timeout` to bound
    requests.
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
        #: The generated client this facade is built on. Its
        #: `raise_on_unexpected_status` is False, so it returns a `Response` and does
        #: NOT raise, unlike every method here. That asymmetry is deliberate: use
        #: `raw` when you want to handle an error condition yourself instead of via
        #: `try`/`except`.
        self.raw = Client(base_url=base_url, headers=merged, timeout=timeout, verify_ssl=verify_ssl)

    def db(self, name: str) -> ArcadeDBDatabase:
        """Scopes subsequent calls to one database, reached through this server."""
        return ArcadeDBDatabase(self.raw, name)

    def list_databases(self) -> list[str]:
        """Lists the names of every database visible to the authenticated caller."""
        data = unwrap(list_databases.sync_detailed(client=self.raw))
        result = getattr(data, "result", None)
        return [] if result is None or isinstance(result, Unset) else list(result)

    def exists(self, name: str) -> bool:
        """Checks whether a database exists and is visible to the authenticated caller.

        `False` cannot distinguish "the database does not exist" from "it exists, but
        the caller is not authorized to see it" - the server does not make that
        distinction in its response, so this client cannot either. Do not treat
        `False` as proof the database is absent.
        """
        data = unwrap(check_database_exists.sync_detailed(name, client=self.raw))
        result = getattr(data, "result", None)
        return False if result is None or isinstance(result, Unset) else bool(result)

    def server_info(self) -> ServerInfo:
        """Retrieves server status, version, and configuration information."""
        data = unwrap(get_server_info.sync_detailed(client=self.raw))
        assert isinstance(data, ServerInfo)
        return data

    def health(self) -> None:
        """Liveness probe. Performs no database I/O and requires no authentication.

        Raises `ArcadeDBError` if the server does not answer 204.
        """
        unwrap(check_health.sync_detailed(client=self.raw))

    def ready(self) -> bool:
        """Readiness probe.

        Returns `True` when the server is ready to accept requests and `False` when
        it answers 503 (still starting, not yet joined its Raft group, or catching up
        on replication). Any other failure still raises `ArcadeDBError`.
        """
        response = check_ready.sync_detailed(client=self.raw)
        if int(response.status_code) == 503:
            return False
        if not is_success(response):
            raise ArcadeDBError.from_response(response)
        return True

    def close(self) -> None:
        """Closes the underlying httpx client and its connection pool."""
        self.raw.get_httpx_client().close()

    def __enter__(self) -> ArcadeDBServer:
        self.raw.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.raw.__exit__(exc_type, exc, tb)
