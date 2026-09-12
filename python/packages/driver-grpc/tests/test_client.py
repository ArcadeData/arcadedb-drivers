from __future__ import annotations

import grpc
import pytest
from arcadedb_driver_grpc import ArcadeDBGrpcClient, InsecureChannelError, create_client
from arcadedb_driver_grpc._generated import arcadedb_server_pb2 as pb2
from arcadedb_driver_grpc._generated import arcadedb_server_pb2_grpc as _pb2_grpc
from arcadedb_driver_grpc.auth import bearer_auth, password_auth

from .conftest import RecordingAdminServicer, RecordingServicer


def test_raw_reaches_the_server(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        client.raw.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command="SELECT 1"))
    assert servicer.calls == ["ExecuteCommand"]


def test_raw_is_authenticated_too(fake_server: tuple[str, RecordingServicer]) -> None:
    # The reason auth is a CHANNEL interceptor. Of the 14 data-plane RPCs the facade
    # wraps five, so 9 are reachable only through `raw` outside a transaction and 3
    # (BulkInsert, InsertBidirectional, GraphBatchLoad) even inside one; per-call
    # metadata on the facade would leave every one of them anonymous.
    target, servicer = fake_server
    with create_client(target, auth=bearer_auth("t0ken")) as client:
        client.raw.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command="SELECT 1"))
    assert ("authorization", "Bearer t0ken") in servicer.metadata


def test_password_auth_over_an_insecure_channel_is_refused() -> None:
    # Also pins that adding `raw_admin` did not move this #5048 guard: it still runs
    # BEFORE any client - and therefore before any `raw_admin` - is constructed at all.
    with pytest.raises(InsecureChannelError):
        create_client("127.0.0.1:50051", auth=password_auth("root", "playwithdata"))


def test_password_auth_over_an_insecure_channel_is_allowed_when_opted_into(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, _ = fake_server
    with create_client(target, auth=password_auth("root", "playwithdata"), insecure=True) as client:
        assert client.raw is not None


def test_bearer_auth_over_an_insecure_channel_is_not_refused(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # A bearer token is not a password. The guard is specifically about plaintext
    # passwords, so it must not fire here or callers will pass insecure=True by reflex.
    target, _ = fake_server
    with create_client(target, auth=bearer_auth("t0ken")) as client:
        assert client.raw is not None


def test_password_auth_over_a_secure_channel_is_not_refused() -> None:
    client = create_client(
        "127.0.0.1:50051",
        auth=password_auth("root", "playwithdata"),
        credentials=grpc.ssl_channel_credentials(),
    )
    client.close()


def test_close_is_idempotent(fake_server: tuple[str, RecordingServicer]) -> None:
    # `auth=` on purpose: `create_client` skips `grpc.intercept_channel` entirely when
    # `auth is None`, so an un-authenticated client closes a bare `grpc.Channel` while
    # every authenticated one closes the interceptor WRAPPER `intercept_channel` returns.
    # Only the second is the path a real caller takes, and only the second exercises
    # whether that wrapper forwards `close()` idempotently.
    target, _ = fake_server
    client = create_client(target, auth=bearer_auth("t0ken"))
    client.close()
    client.close()


def test_raw_admin_reaches_the_server(fake_admin_server: tuple[str, RecordingAdminServicer]) -> None:
    # insecure=True: this test is about reaching the admin server, not the insecure-channel
    # guard on `raw_admin` itself - which is covered separately below.
    target, servicer = fake_admin_server
    with create_client(target, insecure=True) as client:
        client.raw_admin.Ping(pb2.PingRequest())
    assert servicer.calls == ["Ping"]


def test_channel_auth_metadata_also_reaches_an_admin_rpc(
    fake_admin_server: tuple[str, RecordingAdminServicer],
) -> None:
    # Channel metadata arrives at an admin RPC same as a data-plane one - it just doesn't
    # authenticate the RPC, since 42 of 44 admin RPCs check `DatabaseCredentials` in the
    # request body instead. Asserts on `servicer.metadata`, not on anything in the request.
    target, servicer = fake_admin_server
    with create_client(target, auth=bearer_auth("t0ken"), insecure=True) as client:
        client.raw_admin.Ping(pb2.PingRequest())
    assert ("authorization", "Bearer t0ken") in servicer.metadata


def test_raw_and_raw_admin_are_built_from_the_same_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    # The property that matters is not "both exist" - a client built from two SEPARATE
    # channels would pass that check too, and would silently escape the auth/TLS
    # guarantees this task exists to preserve. This proves the shared channel directly by
    # recording the exact `channel` object each generated stub constructor received.
    real_stub = _pb2_grpc.ArcadeDbServiceStub
    real_admin_stub = _pb2_grpc.ArcadeDbAdminServiceStub
    channels_seen: list[grpc.Channel] = []

    def spy_stub(channel: grpc.Channel) -> _pb2_grpc.ArcadeDbServiceStub:
        channels_seen.append(channel)
        return real_stub(channel)

    def spy_admin_stub(channel: grpc.Channel) -> _pb2_grpc.ArcadeDbAdminServiceStub:
        channels_seen.append(channel)
        return real_admin_stub(channel)

    monkeypatch.setattr(_pb2_grpc, "ArcadeDbServiceStub", spy_stub)
    monkeypatch.setattr(_pb2_grpc, "ArcadeDbAdminServiceStub", spy_admin_stub)

    # insecure=True: this test is about the shared channel/transport, not the
    # insecure-channel guard on `raw_admin` itself - which needs `client.raw_admin` to be
    # reachable in order to compare it against `client.raw` below.
    client = create_client("127.0.0.1:50051", insecure=True)
    try:
        assert len(channels_seen) == 2
        assert channels_seen[0] is channels_seen[1]
        # Different generated stub classes, so mypy sees no possible overlap between
        # them - this identity check is exactly the point, hence the ignore.
        assert client.raw is not client.raw_admin  # type: ignore[comparison-overlap]
    finally:
        client.close()


def test_close_closes_the_channel_raw_admin_shares_with_raw(
    fake_admin_server: tuple[str, RecordingAdminServicer],
) -> None:
    target, _ = fake_admin_server
    client = create_client(target, insecure=True)
    client.raw_admin.Ping(pb2.PingRequest())  # works before close
    client.close()
    client.close()  # idempotent, same as `test_close_is_idempotent` above
    with pytest.raises(ValueError, match="closed channel"):
        client.raw_admin.Ping(pb2.PingRequest())


def test_raw_admin_over_an_insecure_channel_is_refused_without_opt_in() -> None:
    # The property that matters here: construction itself must NOT raise (a data-plane-only
    # caller building a client over plain HTTP must be unaffected) - only READING
    # `raw_admin` does. This is the regression guard for "the guard moved to the wrong
    # place."
    client = create_client("127.0.0.1:50051")  # must not raise
    try:
        with pytest.raises(InsecureChannelError, match=r"credentials|insecure"):
            client.raw_admin  # noqa: B018 - accessing the property IS the assertion
    finally:
        client.close()


def test_raw_admin_over_an_insecure_channel_is_allowed_when_opted_into(
    fake_admin_server: tuple[str, RecordingAdminServicer],
) -> None:
    target, _ = fake_admin_server
    client = create_client(target, insecure=True)
    assert client.raw_admin is not None
    client.close()


def test_raw_admin_over_a_secure_channel_is_not_refused() -> None:
    client = create_client("127.0.0.1:50051", credentials=grpc.ssl_channel_credentials())
    assert client.raw_admin is not None
    client.close()


def test_raw_admin_is_blocked_by_default_on_direct_construction_even_over_a_secure_channel() -> None:
    # `ArcadeDBGrpcClient(channel)` bypasses `create_client` entirely, so nothing computed
    # `credentials is not None or insecure` on this caller's behalf. This class cannot
    # inspect an arbitrary `grpc.Channel` for encryption, so the only safe default is to
    # block regardless - even a channel built with genuine TLS credentials, as here, stays
    # blocked until `allow_admin=True` is passed explicitly. Pins the class docstring's
    # corrected claim, not just the keyword default.
    channel = grpc.secure_channel("127.0.0.1:50051", grpc.ssl_channel_credentials())
    client = ArcadeDBGrpcClient(channel)
    try:
        with pytest.raises(InsecureChannelError, match="allow_admin"):
            client.raw_admin  # noqa: B018 - accessing the property IS the assertion
    finally:
        client.close()


def test_raw_still_works_over_an_insecure_channel_with_no_auth(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # The over-guarding regression check: a caller who never touches `raw_admin` must not
    # be newly broken by this guard. `raw` keeps working over plain HTTP exactly as before.
    target, servicer = fake_server
    with create_client(target) as client:
        client.raw.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command="SELECT 1"))
    assert servicer.calls == ["ExecuteCommand"]
