from __future__ import annotations

import grpc
import pytest
from arcadedb_driver_grpc import InsecureChannelError, create_client
from arcadedb_driver_grpc._generated import arcadedb_server_pb2 as pb2
from arcadedb_driver_grpc.auth import bearer_auth, password_auth

from .conftest import RecordingServicer


def test_raw_reaches_the_server(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        client.raw.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command="SELECT 1"))
    assert servicer.calls == ["ExecuteCommand"]


def test_raw_is_authenticated_too(fake_server: tuple[str, RecordingServicer]) -> None:
    # The reason auth is a CHANNEL interceptor. `raw` is where 11 of the 14
    # data-plane RPCs live; per-call metadata on the facade would leave it anonymous.
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
    target, _ = fake_server
    client = create_client(target)
    client.close()
    client.close()
