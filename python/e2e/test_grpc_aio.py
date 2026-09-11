"""End-to-end tests for arcadedb-driver-grpc's ASYNC facade against a real ArcadeDB server.

Companion to `test_grpc.py`, which exercises only the sync client. The async facade has
plumbing with no sync equivalent - `_AsyncAuthInterceptor`, `_aiter_chunks`,
`AsyncTransaction`, `AsyncTransactionHandle` - and none of it had ever been run against a
real server before this file existed; every other async-facade test (`test_aio.py`) runs
against `RecordingServicer`, an in-process fake.

Reuses the SAME `grpc_server`/`grpc_database` fixtures `test_grpc.py` uses, deliberately -
a second container here would test nothing about the async facade that a shared one
does not, and would double this suite's startup cost for no benefit.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

import grpc
import pytest
import pytest_asyncio
from arcadedb_driver_grpc import InsertStreamRequest, messages
from arcadedb_driver_grpc.aio import AsyncArcadeDBGrpcClient, create_client
from arcadedb_driver_grpc.auth import async_interceptors, password_auth

from .conftest import ROOT_PASSWORD

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_client(grpc_server: tuple[str, str], grpc_database: str) -> AsyncIterator[AsyncArcadeDBGrpcClient]:
    _, target = grpc_server
    async with create_client(
        target,
        auth=password_auth("root", ROOT_PASSWORD, grpc_database),
        # The container speaks plaintext gRPC, so the guard has to be opted out of
        # explicitly. That it must be opted out of here IS the guard working.
        insecure=True,
    ) as client:
        yield client


def _person(name: str) -> messages.GrpcRecord:
    return messages.GrpcRecord(type="Person", properties={"name": messages.GrpcValue(string_value=name)})


# The `grpc.aio` twin of `test_grpc.py`'s `_CallRecorder`. Same story on the
# `# type: ignore[type-arg]`s: grpc-stubs declares these four base classes
# `Generic[TRequest, TResponse]` for mypy's benefit, but the real runtime classes are not
# `typing.Generic` and cannot be subscripted at class definition time.
class _AsyncCallRecorder(
    grpc.aio.UnaryUnaryClientInterceptor,  # type: ignore[type-arg]
    grpc.aio.UnaryStreamClientInterceptor,  # type: ignore[type-arg]
    grpc.aio.StreamUnaryClientInterceptor,  # type: ignore[type-arg]
    grpc.aio.StreamStreamClientInterceptor,  # type: ignore[type-arg]
):
    """Records each outgoing RPC's method name, then forwards the call unchanged.

    Used only by `test_async_transaction_rolls_back`, to assert the MECHANISM (that
    RollbackTransaction was actually issued and CommitTransaction was not) rather than
    only the row-absence outcome - exactly the reasoning `test_grpc.py`'s sync
    `_CallRecorder` documents.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _record(self, method: str | bytes) -> None:
        # grpc-stubs types `ClientCallDetails.method` as `str`, but against a real
        # `grpc.aio` channel it arrives as `bytes` - decoded here rather than narrowing
        # the parameter, so this tolerates whichever grpc actually hands it.
        name = method.decode() if isinstance(method, bytes) else method
        self.calls.append(name.rsplit("/", 1)[-1])

    async def intercept_unary_unary(self, continuation: Any, client_call_details: Any, request: Any) -> Any:
        self._record(client_call_details.method)
        return await continuation(client_call_details, request)

    async def intercept_unary_stream(self, continuation: Any, client_call_details: Any, request: Any) -> Any:
        self._record(client_call_details.method)
        return await continuation(client_call_details, request)

    async def intercept_stream_unary(self, continuation: Any, client_call_details: Any, request_iterator: Any) -> Any:
        self._record(client_call_details.method)
        return await continuation(client_call_details, request_iterator)

    async def intercept_stream_stream(self, continuation: Any, client_call_details: Any, request_iterator: Any) -> Any:
        self._record(client_call_details.method)
        return await continuation(client_call_details, request_iterator)


async def _names(client: AsyncArcadeDBGrpcClient, database: str, marker: str) -> list[str]:
    rows = [
        r
        async for r in client.stream_query(
            messages.StreamQueryRequest(
                database=database, language="sql", query=f"SELECT FROM Person WHERE name LIKE '{marker}%'"
            )
        )
    ]
    return sorted(r.properties["name"].string_value for r in rows)


async def test_async_raw_query_reaches_the_server(async_client: AsyncArcadeDBGrpcClient, grpc_database: str) -> None:
    response = await async_client.raw.ExecuteQuery(
        messages.ExecuteQueryRequest(database=grpc_database, language="sql", query="SELECT FROM Person")
    )
    assert response is not None


async def test_async_execute_command_inserts_a_row(async_client: AsyncArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"aac{uuid.uuid4().hex[:8]}"
    await async_client.raw.ExecuteCommand(
        messages.ExecuteCommandRequest(
            database=grpc_database, language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'"
        )
    )
    assert await _names(async_client, grpc_database, marker) == [f"{marker}-a"]


async def test_async_stream_query_returns_rows(async_client: AsyncArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"asq{uuid.uuid4().hex[:8]}"
    await async_client.raw.ExecuteCommand(
        messages.ExecuteCommandRequest(
            database=grpc_database, language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'"
        )
    )
    assert await _names(async_client, grpc_database, marker) == [f"{marker}-a"]


async def test_async_insert_stream_inserts_rows(async_client: AsyncArcadeDBGrpcClient, grpc_database: str) -> None:
    # Same defect this asserts against on the sync side (test_grpc.py's
    # test_insert_stream_inserts_rows): an insert_stream that does not mirror `database`
    # into `options` fails at the deferred commit on a real 26.10.1-SNAPSHOT server with "Invalid
    # database name: name is required". The async facade's own `insert_stream` shares
    # `stream._build_chunk` with the sync one, but had never been run against a real
    # server before this test.
    marker = f"ais{uuid.uuid4().hex[:8]}"

    async def chunks() -> AsyncIterator[list[messages.GrpcRecord]]:
        yield [_person(f"{marker}-a"), _person(f"{marker}-b")]
        yield [_person(f"{marker}-c")]

    summary = await async_client.insert_stream(
        InsertStreamRequest(
            database=grpc_database,
            options=messages.InsertOptions(target_class="Person"),
            chunks=chunks(),
        )
    )
    assert summary.inserted == 3
    assert await _names(async_client, grpc_database, marker) == [f"{marker}-a", f"{marker}-b", f"{marker}-c"]


async def test_async_transaction_commits(async_client: AsyncArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"atc{uuid.uuid4().hex[:8]}"
    async with async_client.transaction(grpc_database) as tx:
        await tx.execute_command(
            messages.ExecuteCommandRequest(language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'")
        )
    assert await _names(async_client, grpc_database, marker) == [f"{marker}-a"]


async def test_async_transaction_rolls_back(
    grpc_server: tuple[str, str], grpc_database: str, async_client: AsyncArcadeDBGrpcClient
) -> None:
    # Asserts the MECHANISM, not only the row absence - the same reasoning
    # `test_grpc.py`'s `test_transaction_rolls_back` documents at length: an insert that
    # silently failed, or a transaction simply left open and never resolved either way,
    # would also leave no rows through ordinary isolation rather than cleanup. A
    # separate, recorded channel proves RollbackTransaction was actually issued and
    # CommitTransaction was not, in addition to the row-absence check below.
    _, target = grpc_server
    marker = f"atr{uuid.uuid4().hex[:8]}"
    recorder = _AsyncCallRecorder()
    auth_interceptors = async_interceptors(password_auth("root", ROOT_PASSWORD, grpc_database))
    # grpc-stubs aliases `grpc.aio.ClientInterceptor` to a private sentinel type that no
    # concrete interceptor nominally matches - the same cast `auth.async_interceptors`
    # itself needs for the same reason.
    interceptors = cast("list[grpc.aio.ClientInterceptor]", [recorder, *auth_interceptors])
    channel = grpc.aio.insecure_channel(target, interceptors=interceptors)
    spied_client = AsyncArcadeDBGrpcClient(channel)
    try:
        sentinel = RuntimeError("boom")
        with pytest.raises(RuntimeError) as caught:
            async with spied_client.transaction(grpc_database) as tx:
                await tx.execute_command(
                    messages.ExecuteCommandRequest(
                        language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'"
                    )
                )
                raise sentinel
        assert caught.value is sentinel
    finally:
        await spied_client.close()

    assert "RollbackTransaction" in recorder.calls
    assert "CommitTransaction" not in recorder.calls

    # Belt and suspenders, and the brief's explicit requirement: the row must also be
    # ABSENT, not merely that the exception propagated and RollbackTransaction fired.
    assert await _names(async_client, grpc_database, marker) == []
