"""Python gRPC client for ArcadeDB's data plane, generated from ArcadeDB's protobuf contract."""

from __future__ import annotations

from collections.abc import Iterator
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

__version__ = "0.1.0"

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
    reaches without a wrapper. `raw_admin` is built from the SAME `channel` as `raw`, not
    a second one, so it shares this client's auth interceptor and TLS policy - including
    the #5048 refusal below - because there is only one channel, not because anything
    here re-implements that guard for a second one.

    A `grpc.Channel` must be closed, so this is a context manager. `@arcadedb/driver-grpc`
    has no counterpart because Connect's transport needs no teardown.
    """

    def __init__(self, channel: grpc.Channel) -> None:
        self._channel = channel
        self.raw = _pb2_grpc.ArcadeDbServiceStub(channel)
        self.raw_admin = _pb2_grpc.ArcadeDbAdminServiceStub(channel)

    def close(self) -> None:
        """Closes the underlying channel. Safe to call more than once."""
        self._channel.close()

    def stream_query(
        self, request: messages.StreamQueryRequest, *, timeout: float | None = None
    ) -> Iterator[messages.GrpcRecord]:
        """Streams a query's results row by row. See `stream.stream_query`."""
        return _stream_query(self.raw, request, timeout=timeout)

    def insert_stream(self, request: InsertStreamRequest, *, timeout: float | None = None) -> messages.InsertSummary:
        """Streams rows to the server in chunks. See `stream.insert_stream`."""
        return _insert_stream(self.raw, request, timeout=timeout)

    def time_series_query(
        self, request: messages.TimeSeriesQueryRequest, *, timeout: float | None = None
    ) -> Iterator[messages.TimeSeriesQueryResult]:
        """Streams a time-series answer message by message. See `stream.time_series_query`.

        Also reachable, bound to an open transaction, as `TransactionHandle.time_series_query`
        (see `transaction.py`), since `TimeSeriesQueryRequest` carries a `transaction` field.
        """
        return _time_series_query(self.raw, request, timeout=timeout)

    def time_series_write_stream(
        self, request: TimeSeriesWriteStreamRequest, *, timeout: float | None = None
    ) -> messages.TimeSeriesWriteSummary:
        """Streams points to `TimeSeriesWriteStream`, one wire chunk per input batch. See
        `stream.time_series_write_stream`.

        `TimeSeriesWrite` (the unary write) and `TimeSeriesLatest` carry no top-level
        wrapper of their own: `TimeSeriesWrite`'s request has no `transaction` field, so
        `raw.TimeSeriesWrite` already works unassisted, and `TimeSeriesLatest` is reachable
        only bound to a transaction, as `TransactionHandle.time_series_latest` - a bare stub
        drives both of those fine, so wrapping either would be a named passthrough adding
        nothing.
        """
        return _time_series_write_stream(self.raw, request, timeout=timeout)

    def transaction(self, database: str) -> Transaction:
        """Runs a server-side transaction: `with client.transaction("db") as tx:`."""
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
    return ArcadeDBGrpcClient(channel)
