"""End-to-end tests for arcadedb-driver-grpc against a real ArcadeDB server."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import grpc
import pytest
from arcadedb_driver_grpc import ArcadeDBGrpcClient, InsertStreamRequest, create_client, messages
from arcadedb_driver_grpc.auth import bearer_auth, password_auth, sync_interceptors

from .conftest import ROOT_PASSWORD


@pytest.fixture
def client(grpc_server: tuple[str, str], grpc_database: str) -> Iterator[ArcadeDBGrpcClient]:
    _, target = grpc_server
    with create_client(
        target,
        auth=password_auth("root", ROOT_PASSWORD, grpc_database),
        # The container speaks plaintext gRPC, so the guard has to be opted out of
        # explicitly. That it must be opted out of here IS the guard working.
        insecure=True,
    ) as grpc_client:
        yield grpc_client


def _person(name: str) -> messages.GrpcRecord:
    return messages.GrpcRecord(type="Person", properties={"name": messages.GrpcValue(string_value=name)})


class _CallRecorder(
    grpc.UnaryUnaryClientInterceptor,  # type: ignore[type-arg]  # not runtime-Generic, see auth.py
    grpc.UnaryStreamClientInterceptor,  # type: ignore[type-arg]
    grpc.StreamUnaryClientInterceptor,  # type: ignore[type-arg]
    grpc.StreamStreamClientInterceptor,  # type: ignore[type-arg]
):
    """Records each outgoing RPC's method name, then forwards the call unchanged.

    Used only by `test_transaction_rolls_back`, to assert the MECHANISM (that
    RollbackTransaction was actually issued and CommitTransaction was not) rather than
    only the row-absence outcome: an insert that silently failed - or a transaction that
    was simply abandoned, never committed and never rolled back - would also leave no
    rows, through ordinary isolation rather than cleanup. Row absence alone cannot tell
    those apart from a real rollback; this can.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _record(self, method: str) -> None:
        # client_call_details.method is the full "/package.Service/Method" path; only
        # the trailing segment is asserted on below.
        self.calls.append(method.rsplit("/", 1)[-1])

    def intercept_unary_unary(self, continuation: Any, client_call_details: Any, request: Any) -> Any:
        self._record(client_call_details.method)
        return continuation(client_call_details, request)

    def intercept_unary_stream(self, continuation: Any, client_call_details: Any, request: Any) -> Any:
        self._record(client_call_details.method)
        return continuation(client_call_details, request)

    def intercept_stream_unary(self, continuation: Any, client_call_details: Any, request_iterator: Any) -> Any:
        self._record(client_call_details.method)
        return continuation(client_call_details, request_iterator)

    def intercept_stream_stream(self, continuation: Any, client_call_details: Any, request_iterator: Any) -> Any:
        self._record(client_call_details.method)
        return continuation(client_call_details, request_iterator)


def _names(client: ArcadeDBGrpcClient, database: str, marker: str) -> list[str]:
    rows = client.stream_query(
        messages.StreamQueryRequest(
            database=database, language="sql", query=f"SELECT FROM Person WHERE name LIKE '{marker}%'"
        )
    )
    return sorted(r.properties["name"].string_value for r in rows)


def test_password_auth_reaches_the_server(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    response = client.raw.ExecuteQuery(
        messages.ExecuteQueryRequest(database=grpc_database, language="sql", query="SELECT FROM Person")
    )
    assert response is not None


def test_bearer_auth_reaches_the_server(grpc_server: tuple[str, str], grpc_database: str) -> None:
    # Both auth paths, exercised end to end. The token is minted over HTTP (there is no
    # data-plane RPC for it) and then presented as a gRPC bearer credential - proving the
    # same session token both drivers already share actually works against the real gRPC
    # service, not just against the fake server the unit suite uses.
    from arcadedb_driver import ArcadeDBServer, basic_auth
    from arcadedb_driver._generated.api.auth import login as http_login
    from arcadedb_driver._generated.models.login_response import LoginResponse

    http_url, target = grpc_server
    with ArcadeDBServer(base_url=http_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        login_response = http_login.sync_detailed(client=srv.raw)
        parsed = login_response.parsed
        assert isinstance(parsed, LoginResponse), parsed
        token = parsed.token
        assert isinstance(token, str)
        assert token.startswith("AU-")

    with create_client(target, auth=bearer_auth(token), insecure=True) as bearer_client:
        response = bearer_client.raw.ExecuteQuery(
            messages.ExecuteQueryRequest(database=grpc_database, language="sql", query="SELECT FROM Person")
        )
        assert response is not None


def test_stream_query_returns_rows(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"sq{uuid.uuid4().hex[:8]}"
    client.raw.ExecuteCommand(
        messages.ExecuteCommandRequest(
            database=grpc_database, language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'"
        )
    )
    assert _names(client, grpc_database, marker) == [f"{marker}-a"]


def test_insert_stream_inserts_rows(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    # THE test for the options.database mirroring. Against a real 26.9.1 server, an
    # insert_stream that does not mirror `database` into `options` fails at the deferred
    # commit with "Invalid database name: name is required". If this test fails that way,
    # the mirroring in stream.py has been removed - restore it, do not work around it.
    marker = f"is{uuid.uuid4().hex[:8]}"
    summary = client.insert_stream(
        InsertStreamRequest(
            database=grpc_database,
            options=messages.InsertOptions(target_class="Person"),
            chunks=[[_person(f"{marker}-a"), _person(f"{marker}-b")], [_person(f"{marker}-c")]],
        )
    )
    assert summary.inserted == 3
    assert _names(client, grpc_database, marker) == [f"{marker}-a", f"{marker}-b", f"{marker}-c"]


def test_an_empty_insert_stream_is_accepted(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    summary = client.insert_stream(
        InsertStreamRequest(database=grpc_database, options=messages.InsertOptions(target_class="Person"), chunks=[])
    )
    assert summary.inserted == 0
    assert summary.failed == 0


def test_transaction_commits(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"tc{uuid.uuid4().hex[:8]}"
    with client.transaction(grpc_database) as tx:
        tx.execute_command(
            messages.ExecuteCommandRequest(language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'")
        )
    assert _names(client, grpc_database, marker) == [f"{marker}-a"]


def test_transaction_rolls_back(grpc_server: tuple[str, str], grpc_database: str, client: ArcadeDBGrpcClient) -> None:
    # Asserts the MECHANISM, not only the row absence: an insert that silently failed -
    # or a transaction simply left open and never resolved either way - would also leave
    # no rows, through ordinary isolation rather than cleanup. So a separate, recorded
    # channel proves RollbackTransaction was actually issued and CommitTransaction was
    # not, in addition to the row-absence check below.
    _, target = grpc_server
    marker = f"tr{uuid.uuid4().hex[:8]}"
    recorder = _CallRecorder()
    auth_interceptors = sync_interceptors(password_auth("root", ROOT_PASSWORD, grpc_database))
    channel = grpc.intercept_channel(grpc.insecure_channel(target), recorder, *auth_interceptors)
    spied_client = ArcadeDBGrpcClient(channel)
    try:
        sentinel = RuntimeError("boom")
        with pytest.raises(RuntimeError) as caught, spied_client.transaction(grpc_database) as tx:
            tx.execute_command(
                messages.ExecuteCommandRequest(language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'")
            )
            raise sentinel
        assert caught.value is sentinel
    finally:
        spied_client.close()

    assert "RollbackTransaction" in recorder.calls
    assert "CommitTransaction" not in recorder.calls

    # Belt and suspenders, and the brief's explicit requirement: the row must also be
    # ABSENT, not merely that the exception propagated and RollbackTransaction fired.
    assert _names(client, grpc_database, marker) == []
