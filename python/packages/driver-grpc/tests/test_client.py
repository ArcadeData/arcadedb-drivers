from __future__ import annotations

import grpc
import pytest
from arcadedb_driver_grpc import InsecureChannelError, create_client
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


def test_password_auth_over_an_insecure_channel_is_refused_even_though_raw_admin_now_exists() -> None:
    # Pins that adding `raw_admin` did not move the #5048 guard: it still runs BEFORE
    # any client - and therefore before any `raw_admin` - is constructed at all.
    with pytest.raises(InsecureChannelError):
        create_client("127.0.0.1:50051", auth=password_auth("root", "playwithdata"))


def test_raw_admin_reaches_the_server(fake_admin_server: tuple[str, RecordingAdminServicer]) -> None:
    target, servicer = fake_admin_server
    with create_client(target) as client:
        client.raw_admin.Ping(pb2.PingRequest())
    assert servicer.calls == ["Ping"]


def test_raw_admin_is_authenticated_too(fake_admin_server: tuple[str, RecordingAdminServicer]) -> None:
    # The auth interceptor is attached to the CHANNEL, same as it is for `raw` - so an
    # admin RPC arrives authenticated exactly the same way a data-plane one does.
    target, servicer = fake_admin_server
    with create_client(target, auth=bearer_auth("t0ken")) as client:
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

    client = create_client("127.0.0.1:50051")
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
    client = create_client(target)
    client.raw_admin.Ping(pb2.PingRequest())  # works before close
    client.close()
    client.close()  # idempotent, same as `test_close_is_idempotent` above
    with pytest.raises(ValueError, match="closed channel"):
        client.raw_admin.Ping(pb2.PingRequest())
