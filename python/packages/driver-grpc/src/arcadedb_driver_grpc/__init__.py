"""Python gRPC client for ArcadeDB's data plane, generated from ArcadeDB's protobuf contract."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterator, Sequence
from types import TracebackType

import grpc

from ._generated import arcadedb_server_pb2 as messages
from ._generated import arcadedb_server_pb2_grpc as _pb2_grpc
from .aio import AsyncArcadeDBGrpcClient, AsyncTransaction, AsyncTransactionHandle
from .auth import Auth, bearer_auth, password_auth, sync_interceptors
from .errors import InsecureChannelError
from .stream import InsertStreamRequest, TimeSeriesWriteStreamRequest
from .stream import insert_stream as _insert_stream
from .stream import stream_query as _stream_query
from .stream import time_series_query as _time_series_query
from .stream import time_series_write_stream as _time_series_write_stream
from .transaction import Transaction, TransactionHandle

# Read from the installed distribution's metadata, never written here: pyproject.toml's
# [project] version is the one place a release sets (set-release-version.sh), and a literal
# here would escape both `set` and `check` - a wheel published as a new version would go on
# reporting the old one.
__version__ = importlib.metadata.version("arcadedb-driver-grpc")

__all__ = [
    "ArcadeDBGrpcClient",
    "AsyncArcadeDBGrpcClient",
    "AsyncTransaction",
    "AsyncTransactionHandle",
    "Auth",
    "InsecureChannelError",
    "InsertStreamRequest",
    "TimeSeriesWriteStreamRequest",
    "Transaction",
    "TransactionHandle",
    "__version__",
    "bearer_auth",
    "create_client",
    "messages",
    "password_auth",
]


class ArcadeDBGrpcClient:
    """ArcadeDB's gRPC data-plane client.

    `raw` is the generated stub for `com.arcadedb.grpc.ArcadeDbService`; every RPC the
    facade does not wrap is reached through it, already authenticated.

    `raw_admin` is the generated stub for `com.arcadedb.grpc.ArcadeDbAdminService` - the
    control plane (database lifecycle, users, groups, API tokens, settings, backups, the
    profiler, server shutdown/cluster operations, `Health`/`Ready`). No facade wraps any
    of its 44 RPCs: each is a one-line stub call, exactly like the data-plane RPCs `raw`
    reaches without a wrapper.

    `raw_admin` is built from the SAME `channel` as `raw`, so it shares this client's TLS
    policy - but NOT its authentication. 42 of the 44 admin RPCs (everything but `Health`
    and `Ready`) authenticate from a `DatabaseCredentials` field INSIDE the request
    message, not from the channel's auth interceptor, so `bearer_auth`/`password_auth` do
    nothing for them. Reading `raw_admin` raises `InsecureChannelError` unless
    `allow_admin=True` was passed to this constructor: those in-body credentials would
    otherwise travel in cleartext regardless of any auth interceptor, the same hazard
    #5048 closed for the data plane's password auth. `create_client` computes that
    argument for its own callers (`credentials is not None or insecure`), but a caller
    constructing this class directly gets no such help: this class cannot inspect an
    arbitrary `grpc.Channel` for encryption, so even a channel built with genuine TLS
    transport credentials leaves `raw_admin` blocked until `allow_admin=True` is passed
    explicitly. The check runs on ACCESS, not in `__init__`, so a client built over an
    insecure channel for the data plane keeps working unchanged - only reading `raw_admin`
    requires the opt-in. `Health` and `Ready` carry no credentials at all and are
    still refused by this guard: it protects the stub as a whole, not a per-RPC list, so
    there is deliberately no special case carving the two credential-free RPCs back out.

    A `grpc.Channel` must be closed, so this is a context manager. `@arcadedb/driver-grpc`
    has no counterpart because Connect's transport needs no teardown.
    """

    def __init__(self, channel: grpc.Channel, *, allow_admin: bool = False) -> None:
        self._channel = channel
        self.raw = _pb2_grpc.ArcadeDbServiceStub(channel)
        self._raw_admin_stub = _pb2_grpc.ArcadeDbAdminServiceStub(channel)
        # Whether `raw_admin` may be read despite the channel possibly being insecure.
        # `create_client` computes this the same way it decides its own #5048 guard
        # (`credentials is not None or insecure`); a caller constructing this class
        # directly, bypassing `create_client`, gets the safe default - `raw_admin` is
        # blocked until they say otherwise, since this class cannot itself inspect
        # whether an arbitrary `grpc.Channel` it was handed is actually encrypted.
        self._allow_admin = allow_admin

    @property
    def raw_admin(self) -> _pb2_grpc.ArcadeDbAdminServiceStub:
        """The admin (control-plane) stub - see the class docstring. Raises
        `InsecureChannelError` on read if `allow_admin` was not set; never raises at
        construction time.
        """
        if not self._allow_admin:
            raise InsecureChannelError(
                "raw_admin: refusing to expose ArcadeDbAdminService over a channel that may be "
                "insecure. 42 of its 44 RPCs (everything but Health and Ready) carry "
                "DatabaseCredentials in the request body, which would travel in cleartext "
                "regardless of any auth interceptor. Pass credentials=grpc.ssl_channel_credentials() "
                "or insecure=True to create_client, or allow_admin=True to this class's "
                "constructor if you built the channel yourself."
            )
        return self._raw_admin_stub

    def close(self) -> None:
        """Closes the underlying channel. Safe to call more than once."""
        self._channel.close()

    def stream_query(
        self,
        request: messages.StreamQueryRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> Iterator[messages.GrpcRecord]:
        """Streams a query's results row by row, flattening the wire batching.

        `for record in client.stream_query(...)`: the return value is a generator, iterated
        directly. The RPC is not opened until the first pull, because `stream.stream_query`
        is a generator function; this method merely returns the generator it produces.

        `retrieval_mode` and `batch_size` pass through unchanged; this wrapper picks no
        default for either, because CURSOR, MATERIALIZE_ALL and PAGED have materially
        different memory and consistency behaviour that only the caller can judge.

        Also reachable, bound to an open transaction, as `TransactionHandle.stream_query`.

        `metadata` is per-call gRPC metadata, appended to the headers the channel's auth
        interceptor adds rather than replacing them.
        """
        return _stream_query(self.raw, request, timeout=timeout, metadata=metadata)

    def insert_stream(
        self,
        request: InsertStreamRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.InsertSummary:
        """Streams rows to the server in chunks and returns the server's `InsertSummary`.

        Handles the envelope bookkeeping a caller would otherwise hand-roll: one
        `session_id` (a fresh UUID) stable for the whole stream, `chunk_seq` from 1,
        `database` on the first chunk only (per the .proto contract), and `last=True` on the
        final chunk only. `options` is sent as given on every chunk and `options.database` is
        never set: a server before 26.9.1 reads the database only from there
        (ArcadeData/arcadedb#6597) and reports the rows as `received` with `inserted=0` in a
        SUCCESSFUL call, but such servers are outside the supported range.

        `request.chunks` must be a SYNCHRONOUS iterable here, unlike on the async facade,
        which accepts both halves of the declared union. Anything else - an async iterable
        included - is rejected with `TypeError` before the RPC is opened. That needs an
        eager-validation split: the chunk generator's body does not run until grpc pulls the
        first chunk to open the RPC, and a `raise` there would be caught by grpc and
        re-raised as an opaque `_InactiveRpcError` ("Exception iterating requests!"). So
        `stream._envelope_chunks` is a plain function that checks first and only then
        returns the generator, and the `TypeError` raises in the caller's own frame.

        An empty `request.chunks` sends a single chunk with zero rows and `last=True`
        rather than raising: a filter that matched nothing is a legitimate outcome.

        The chunk generator closes the caller's iterator on every exit path, including
        when it is abandoned early because the RPC aborted mid-stream, so a `finally` the
        caller wrote around their own generator (closing a file handle, a cursor) still
        runs.

        To insert inside a transaction, call `TransactionHandle.insert_stream`: it replaces
        `database` and `transaction` with the handle's own, so the rows commit or roll back
        with the transaction. A `transaction` set on the request here is sent as given,
        flags and all. Servers before 26.9.1, which are outside the compatibility table,
        ignored `TransactionContext` on `InsertStream` (ArcadeData/arcadedb#6607), so there
        the rows would survive a rollback.

        `metadata` is per-call gRPC metadata, appended to the headers the channel's auth
        interceptor adds rather than replacing them.
        """
        return _insert_stream(self.raw, request, timeout=timeout, metadata=metadata)

    def time_series_query(
        self,
        request: messages.TimeSeriesQueryRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> Iterator[messages.TimeSeriesQueryResult]:
        """Streams a time-series answer message by message.

        `for result in client.time_series_query(...)`: the return value is a generator,
        iterated directly.

        Deliberately THINNER than `stream_query` above, which flattens `QueryResult`
        batches into individual `GrpcRecord`s: `TimeSeriesQueryResult` cannot be flattened
        the same way. `truncated` and `last` are carried per-message (`truncated` is only
        meaningful on the message where `last` is true), and a raw answer's `rows` versus
        an aggregated answer's `buckets` are shaped differently. Flattening either away
        would throw away the information a caller needs to tell "the stream ended" from
        "the stream ended early because of `limit`" - so this yields the messages exactly
        as the server sent them.

        Also reachable, bound to an open transaction, as `TransactionHandle.time_series_query`,
        since `TimeSeriesQueryRequest` carries a `transaction` field (issue #7370).

        `metadata` is per-call gRPC metadata, appended to the headers the channel's auth
        interceptor adds rather than replacing them.
        """
        return _time_series_query(self.raw, request, timeout=timeout, metadata=metadata)

    def time_series_write_stream(
        self,
        request: TimeSeriesWriteStreamRequest,
        *,
        timeout: float | None = None,
        metadata: Sequence[tuple[str, str | bytes]] | None = None,
    ) -> messages.TimeSeriesWriteSummary:
        """Streams points to `TimeSeriesWriteStream`, one wire chunk per input batch, and
        returns the server's `TimeSeriesWriteSummary`.

        Sets `database`, `credentials`, `type` and `precision` on EVERY wire chunk - unlike
        `insert_stream`, which sends `database` on the first chunk only,
        `TimeSeriesWriteChunk` has no session/sequence/last fields forcing that special case
        (see `TimeSeriesWriteStreamRequest` in `stream.py`).

        `request.chunks` must be a SYNCHRONOUS iterable here, unlike on the async facade.
        Anything else is rejected with `TypeError` before the RPC is opened, by the same
        eager-validation split `insert_stream` above uses and for the same reason: raised
        inside the chunk generator, the error would be swallowed by grpc and replaced with
        its own opaque `_InactiveRpcError`.

        An empty `request.chunks` sends ZERO wire chunks, rather than `insert_stream`'s
        single-empty-chunk special case. What the server does with a stream that never told
        it `database`, `type` or `precision` is MEASURED against a real server, not guessed
        at: it does NOT raise. The call is accepted cleanly and returns an all-zero
        `TimeSeriesWriteSummary` - `received == written == dropped == 0`, with
        `unknown_types`, `non_time_series_types` and `unavailable_types` all empty. This
        wrapper still invents nothing; it hands back whatever summary the server sent.

        Returns the server's `TimeSeriesWriteSummary` WHOLE (D-M6-3): `received`,
        `written`, `dropped`, `unknown_types`, `non_time_series_types`, `unavailable_types`
        and `execution_time_ms` all survive unchanged. A write is NOT atomic - each
        measurement's batch commits its own shard transaction as it is appended - so a
        SUCCESSFUL call can still report `written < received`. A caller who checks only that
        this returned without raising has not checked that its data landed; this wrapper
        never reduces the summary to a boolean or a count.

        NOT available on `TransactionHandle`: `TimeSeriesWriteChunk` carries no
        `transaction` field on the wire at all, so there is nothing to bind.

        `TimeSeriesWrite` (the unary write) and `TimeSeriesLatest` carry no top-level
        wrapper of their own: `TimeSeriesWrite`'s request has no `transaction` field, so
        `raw.TimeSeriesWrite` already works unassisted, and `TimeSeriesLatest` is reachable
        only bound to a transaction, as `TransactionHandle.time_series_latest` - a bare stub
        drives both of those fine, so wrapping either would be a named passthrough adding
        nothing.

        `metadata` is per-call gRPC metadata, appended to the headers the channel's auth
        interceptor adds rather than replacing them.
        """
        return _time_series_write_stream(self.raw, request, timeout=timeout, metadata=metadata)

    def transaction(self, database: str) -> Transaction:
        """Runs a server-side transaction: `with client.transaction("db") as tx:`.

        Returns a `Transaction` without contacting the server; `BeginTransaction` is sent on
        `__enter__`, which refuses to run the body (raising `RuntimeError`) if the server
        hands back a blank transaction id. The body gets a `TransactionHandle`, and only
        calls made through that handle take part in the transaction - each is bound by its
        `_bind`, which forces this transaction's `database` and id onto a copy of the
        request. Calls made through this client, or through `raw`, do NOT.

        A clean exit commits, and raises `RuntimeError` if the server reports the commit did
        not take effect; any exception from the body rolls back and propagates. See
        `Transaction.__exit__` for the failure paths and the one known gap.
        """
        return Transaction(self.raw, database)

    def __enter__(self) -> ArcadeDBGrpcClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def create_client(
    target: str,
    *,
    auth: Auth | None = None,
    credentials: grpc.ChannelCredentials | None = None,
    insecure: bool = False,
) -> ArcadeDBGrpcClient:
    """Creates a gRPC data-plane client.

    `target` is gRPC's native `host:port` form, e.g. `"localhost:50051"` - not a URL.

    Refuses to pair `password_auth` with an insecure channel unless `insecure=True` is
    passed explicitly: sending a password in cleartext metadata is a credential-exposure
    hazard (issue #5048). The check keys on whether channel `credentials` were supplied,
    which is stated outright rather than inferred - the TypeScript client has to defend
    against `new URL("localhost:50051").protocol` evaluating to `"localhost:"` instead
    of `"http:"`, and Python has no such trap.

    `raw_admin` carries its own, separate insecure-channel guard - see
    `ArcadeDBGrpcClient.raw_admin` - that fires on READING the property, not here. It uses
    the same `credentials is not None or insecure` test this function applies to its own
    guard above, but unconditionally on `auth`: the admin hazard is credentials inside an
    admin RPC's request body, not anything an auth interceptor puts on the wire.
    """
    if credentials is None and not insecure and auth is not None and auth.sends_plaintext_password:
        raise InsecureChannelError(
            f'create_client: refusing to send a plaintext password over an insecure channel to "{target}". '
            "Pass credentials=grpc.ssl_channel_credentials(), switch to bearer_auth, "
            "or pass insecure=True to opt in explicitly."
        )

    interceptors = sync_interceptors(auth)
    channel = grpc.insecure_channel(target) if credentials is None else grpc.secure_channel(target, credentials)
    if interceptors:
        channel = grpc.intercept_channel(channel, *interceptors)
    return ArcadeDBGrpcClient(channel, allow_admin=credentials is not None or insecure)
