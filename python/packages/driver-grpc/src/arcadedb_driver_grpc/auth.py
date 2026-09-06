"""Authentication helpers for ArcadeDB's gRPC data plane.

`bearer_auth` and `password_auth` return a VALUE, not an interceptor. Sync and async
gRPC use different, incompatible interceptor base classes, so returning metadata plus
a marker lets one pair of public helpers serve both facades.

The interceptors are attached to the CHANNEL rather than passed as per-call
`metadata=`. That is not stylistic: a channel interceptor also authenticates calls
made through `client.raw`, and `raw` is where most of the 14 data-plane RPCs live.
The top-level facade wraps five of them - `StreamQuery`, `InsertStream`, and the
`Begin`/`Commit`/`Rollback` trio `transaction()` drives - leaving the other 9
reachable only through `raw`. Opening a transaction narrows that to 3: the six CRUD
RPCs gain a wrapper on the handle, while `BulkInsert`, `InsertBidirectional` and
`GraphBatchLoad` have none anywhere, ever. Per-call metadata on the wrappers would
leave every one of those calls silently anonymous.

Call credentials (`grpc.metadata_call_credentials`) are deliberately not used: they
require a secure channel, and password auth over an insecure channel is exactly the
configuration the e2e suite runs against a test container.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple, cast

import grpc

__all__ = ["Auth", "async_interceptors", "bearer_auth", "password_auth", "sync_interceptors"]


@dataclass(frozen=True)
class Auth:
    """Metadata to attach to every outgoing call, plus whether it carries a password."""

    metadata: tuple[tuple[str, str], ...]
    sends_plaintext_password: bool = False


def bearer_auth(token: str) -> Auth:
    """Authenticates with a bearer token: `authorization: Bearer <token>`."""
    return Auth(metadata=(("authorization", f"Bearer {token}"),))


def password_auth(user: str, password: str, database: str | None = None) -> Auth:
    """Authenticates with a username and password.

    Sets `x-arcade-user`, `x-arcade-password` and, when given, `x-arcade-database`.

    The password travels in plaintext metadata, so `create_client` refuses to pair
    this with an insecure channel unless `insecure=True` is passed explicitly.
    """
    metadata: list[tuple[str, str]] = [("x-arcade-user", user), ("x-arcade-password", password)]
    if database is not None:
        metadata.append(("x-arcade-database", database))
    return Auth(metadata=tuple(metadata), sends_plaintext_password=True)


class _CallDetails(NamedTuple):
    """A concrete `grpc.ClientCallDetails`.

    grpc-python passes an implementation-private namedtuple whose `_replace` is not
    part of the public API, so a portable interceptor builds its own.
    """

    method: str
    timeout: float | None
    # grpc-stubs types real metadata values as `str | bytes` (grpc.Metadata), not
    # plain `str` - broader than what this module ever sends, but `details.metadata`
    # (the caller's own per-call metadata, which this appends to) can carry either.
    metadata: Sequence[tuple[str, str | bytes]] | None
    credentials: grpc.CallCredentials | None
    wait_for_ready: bool | None
    compression: Any


def _augment(details: Any, extra: tuple[tuple[str, str], ...]) -> _CallDetails:
    # `details` is typed `Any` rather than `grpc.ClientCallDetails`: this helper is
    # shared by both the sync interceptor (`grpc.ClientCallDetails`) and the async
    # one (the distinct `grpc.aio.ClientCallDetails`) - the two classes have the
    # same shape but no common base in grpc-stubs, and both call sites already pass
    # their details straight to an equally `Any`-typed `continuation`.
    # APPEND, never replace: the caller may have set per-call metadata of their own,
    # and dropping it here would be a silent data-loss bug.
    merged: list[tuple[str, str | bytes]] = list(details.metadata or ()) + list(extra)
    return _CallDetails(
        method=details.method,
        timeout=details.timeout,
        metadata=merged,
        credentials=details.credentials,
        wait_for_ready=getattr(details, "wait_for_ready", None),
        compression=getattr(details, "compression", None),
    )


# grpc-stubs declares these four base classes `Generic[TRequest, TResponse]` for
# mypy's benefit, but the real runtime classes (grpc/__init__.py) only extend
# `abc.ABC` - they are not `typing.Generic` and cannot be subscripted at class
# definition time. Parameterizing them here would raise `TypeError: ... is not
# subscriptable` on import, so the `# type: ignore[type-arg]` per line accepts
# mypy's "missing type arguments" note instead of a runtime crash.
class _SyncAuthInterceptor(
    grpc.UnaryUnaryClientInterceptor,  # type: ignore[type-arg]
    grpc.UnaryStreamClientInterceptor,  # type: ignore[type-arg]
    grpc.StreamUnaryClientInterceptor,  # type: ignore[type-arg]
    grpc.StreamStreamClientInterceptor,  # type: ignore[type-arg]
):
    """One object implementing all four interceptor protocols.

    All four are needed: the data plane uses unary-unary (ExecuteQuery), unary-stream
    (StreamQuery), stream-unary (InsertStream) and stream-stream (InsertBidirectional).
    Implementing three of the four would leave one call shape unauthenticated.

    The four hooks are written out longhand rather than aliased to one shared
    `_intercept` (`intercept_unary_unary = _intercept`, etc.): each of the four base
    classes declares its own `continuation`/return signature, and mypy strict checks
    a simple attribute alias against those signatures as a plain assignment rather
    than as a method override, which fails even though the alias works fine at
    runtime. Four thin overrides sidestep that without weakening the checks.
    """

    def __init__(self, auth: Auth) -> None:
        self._extra = auth.metadata

    def intercept_unary_unary(
        self, continuation: Any, client_call_details: grpc.ClientCallDetails, request: Any
    ) -> Any:
        return continuation(_augment(client_call_details, self._extra), request)

    def intercept_unary_stream(
        self, continuation: Any, client_call_details: grpc.ClientCallDetails, request: Any
    ) -> Any:
        return continuation(_augment(client_call_details, self._extra), request)

    def intercept_stream_unary(
        self, continuation: Any, client_call_details: grpc.ClientCallDetails, request_iterator: Iterator[Any]
    ) -> Any:
        return continuation(_augment(client_call_details, self._extra), request_iterator)

    def intercept_stream_stream(
        self, continuation: Any, client_call_details: grpc.ClientCallDetails, request_iterator: Iterator[Any]
    ) -> Any:
        return continuation(_augment(client_call_details, self._extra), request_iterator)


# FOUR interceptor classes, one per RPC shape - NOT a single class implementing all
# four protocols the way `_SyncAuthInterceptor` above does. That difference is not
# stylistic; it is what makes streaming calls authenticated at all on this side.
#
# `grpc.aio.Channel.__init__` (`grpc/aio/_channel.py`) buckets every interceptor it is
# given with an `isinstance(...)`/`elif` chain - `UnaryUnaryClientInterceptor` first,
# then `UnaryStreamClientInterceptor`, then the other two - and stops at the FIRST
# match. An object that is an instance of more than one of the four (the shape a
# combined class necessarily has) lands in exactly one bucket and is silently never
# invoked for the other three call shapes; unlike the sync side, where
# `grpc._interceptor.intercept_channel` checks all four independently, so
# `_SyncAuthInterceptor`'s single combined class reaches every call shape there.
#
# A single `_AsyncAuthInterceptor` combining all four protocols - this module's
# original shape - authenticated ExecuteQuery/ExecuteCommand (unary-unary, the first
# bucket checked) while silently leaving StreamQuery (unary-stream), InsertStream
# (stream-unary) and InsertBidirectional (stream-stream) completely unauthenticated.
# This was found against a REAL server during M3b's e2e work: `stream_query` under
# `password_auth`/`bearer_auth` came back `UNAUTHENTICATED` even though `ExecuteCommand`
# on the very same client succeeded moments earlier. The in-process fake server the
# unit suite used until then only ever exercised bearer auth through `ExecuteCommand`
# (unary-unary) - never through a streaming call - so nothing had caught it; see
# `test_aio.py`'s `test_auth_reaches_every_rpc_shape_not_only_unary_unary` for the
# regression test this defect earned.
class _AsyncUnaryUnaryAuthInterceptor(grpc.aio.UnaryUnaryClientInterceptor):  # type: ignore[type-arg]
    """Authenticates unary-unary calls (ExecuteQuery, ExecuteCommand, CreateRecord, ...)."""

    def __init__(self, auth: Auth) -> None:
        self._extra = auth.metadata

    async def intercept_unary_unary(
        self, continuation: Any, client_call_details: grpc.aio.ClientCallDetails, request: Any
    ) -> Any:
        return await continuation(_augment(client_call_details, self._extra), request)


class _AsyncUnaryStreamAuthInterceptor(grpc.aio.UnaryStreamClientInterceptor):  # type: ignore[type-arg]
    """Authenticates unary-stream calls (StreamQuery)."""

    def __init__(self, auth: Auth) -> None:
        self._extra = auth.metadata

    async def intercept_unary_stream(
        self, continuation: Any, client_call_details: grpc.aio.ClientCallDetails, request: Any
    ) -> Any:
        return await continuation(_augment(client_call_details, self._extra), request)


class _AsyncStreamUnaryAuthInterceptor(grpc.aio.StreamUnaryClientInterceptor):  # type: ignore[type-arg]
    """Authenticates stream-unary calls (InsertStream, BulkInsert)."""

    def __init__(self, auth: Auth) -> None:
        self._extra = auth.metadata

    async def intercept_stream_unary(
        self, continuation: Any, client_call_details: grpc.aio.ClientCallDetails, request_iterator: Any
    ) -> Any:
        return await continuation(_augment(client_call_details, self._extra), request_iterator)


class _AsyncStreamStreamAuthInterceptor(grpc.aio.StreamStreamClientInterceptor):  # type: ignore[type-arg]
    """Authenticates stream-stream calls (InsertBidirectional)."""

    def __init__(self, auth: Auth) -> None:
        self._extra = auth.metadata

    async def intercept_stream_stream(
        self, continuation: Any, client_call_details: grpc.aio.ClientCallDetails, request_iterator: Any
    ) -> Any:
        return await continuation(_augment(client_call_details, self._extra), request_iterator)


def sync_interceptors(auth: Auth | None) -> list[grpc.Interceptor]:
    """Channel interceptors for a sync channel; empty when `auth` is None."""
    return [] if auth is None else [_SyncAuthInterceptor(auth)]


def async_interceptors(auth: Auth | None) -> list[grpc.aio.ClientInterceptor]:
    """Channel interceptors for an async channel; empty when `auth` is None.

    FOUR separate objects, not one combined interceptor - see the module-level
    comment above the four `_Async*AuthInterceptor` classes for why: a single object
    implementing all four protocols would authenticate only unary-unary calls under
    `grpc.aio`'s isinstance/elif interceptor bucketing, leaving every streaming RPC
    silently unauthenticated.
    """
    if auth is None:
        return []
    # grpc-stubs aliases `grpc.aio.ClientInterceptor` to a private sentinel type
    # (`_PartialStubMustCastOrIgnore`) that no concrete interceptor nominally
    # matches - the stub's own name says a cast is expected here.
    return cast(
        "list[grpc.aio.ClientInterceptor]",
        [
            _AsyncUnaryUnaryAuthInterceptor(auth),
            _AsyncUnaryStreamAuthInterceptor(auth),
            _AsyncStreamUnaryAuthInterceptor(auth),
            _AsyncStreamStreamAuthInterceptor(auth),
        ],
    )
