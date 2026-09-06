from __future__ import annotations

import grpc
from arcadedb_driver_grpc._generated import arcadedb_server_pb2 as pb2
from arcadedb_driver_grpc._generated import arcadedb_server_pb2_grpc as pb2_grpc
from arcadedb_driver_grpc.auth import Auth, bearer_auth, password_auth, sync_interceptors

from .conftest import RecordingServicer


def _call(target: str, auth: Auth | None) -> None:
    channel = grpc.insecure_channel(target)
    intercepted = grpc.intercept_channel(channel, *sync_interceptors(auth))
    stub = pb2_grpc.ArcadeDbServiceStub(intercepted)
    stub.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command="SELECT 1"))
    channel.close()


def test_bearer_auth_sets_the_authorization_header(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    _call(target, bearer_auth("t0ken"))
    assert ("authorization", "Bearer t0ken") in servicer.metadata


def test_password_auth_sets_user_password_and_database(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    _call(target, password_auth("root", "playwithdata", "mydb"))
    assert ("x-arcade-user", "root") in servicer.metadata
    assert ("x-arcade-password", "playwithdata") in servicer.metadata
    assert ("x-arcade-database", "mydb") in servicer.metadata


def test_password_auth_omits_the_database_when_not_given(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    _call(target, password_auth("root", "playwithdata"))
    assert not any(key == "x-arcade-database" for key, _ in servicer.metadata)


def test_only_password_auth_is_marked_as_sending_a_plaintext_password() -> None:
    # This marker is what create_client's insecure guard reads. If it stops being
    # set, the guard silently stops guarding - hence a test on the marker itself.
    assert password_auth("root", "playwithdata").sends_plaintext_password is True
    assert bearer_auth("t0ken").sends_plaintext_password is False


def test_no_auth_produces_no_interceptors() -> None:
    assert sync_interceptors(None) == []


def test_interceptors_do_not_discard_metadata_the_caller_already_set(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # The interceptor APPENDS. Replacing client_call_details.metadata wholesale would
    # silently drop per-call metadata, which is a data-loss bug no auth test would catch.
    target, servicer = fake_server
    channel = grpc.insecure_channel(target)
    intercepted = grpc.intercept_channel(channel, *sync_interceptors(bearer_auth("t0ken")))
    stub = pb2_grpc.ArcadeDbServiceStub(intercepted)
    stub.ExecuteCommand(
        pb2.ExecuteCommandRequest(database="db", command="SELECT 1"),
        metadata=(("x-caller", "mine"),),
    )
    channel.close()
    assert ("x-caller", "mine") in servicer.metadata
    assert ("authorization", "Bearer t0ken") in servicer.metadata
