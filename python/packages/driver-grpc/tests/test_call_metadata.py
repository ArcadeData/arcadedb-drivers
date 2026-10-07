"""Per-call `metadata=` on the streaming wrappers, sync and async (issue #28).

The unary methods on the transaction handles took `timeout=` and `metadata=` from the
start; the twelve streaming wrappers below took only `timeout=`. Each case here drives
one of them against the recording servicer and asserts what arrived ON THE WIRE, through
a channel that also carries `bearer_auth`, so the same assertion proves both halves of the
contract: the caller's header reached the server, and it was APPENDED to the channel's
auth rather than replacing it. Each wrapper is also called with `metadata` omitted, the
spelling every existing caller uses, to pin that it still works unchanged.

The per-RPC record (`metadata_by_rpc`) is read rather than the last-call `metadata`
because the transaction handle's calls are bracketed by `BeginTransaction` and
`CommitTransaction`, and the commit would otherwise overwrite what the test needs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

import pytest
from arcadedb_driver_grpc import (
    ArcadeDBGrpcClient,
    InsertStreamRequest,
    TimeSeriesWriteStreamRequest,
    bearer_auth,
    create_client,
    messages,
)
from arcadedb_driver_grpc.aio import AsyncArcadeDBGrpcClient
from arcadedb_driver_grpc.aio import create_client as create_async_client

from .conftest import RecordingServicer

_Metadata = Sequence[tuple[str, str | bytes]] | None

_HEADER = ("x-test-header", "hello")
_AUTH = ("authorization", "Bearer t0ken")


def _insert_request() -> InsertStreamRequest:
    return InsertStreamRequest(database="db", chunks=[[messages.GrpcRecord(rid="#1:0")]])


def _ts_write_request() -> TimeSeriesWriteStreamRequest:
    return TimeSeriesWriteStreamRequest(
        database="db",
        type="cpu",
        precision=messages.TS_PRECISION_MILLISECONDS,
        chunks=[[messages.TimeSeriesPoint(type="cpu", timestamp=1)]],
    )


# --- sync ------------------------------------------------------------------------------


def _client_stream_query(client: ArcadeDBGrpcClient, metadata: _Metadata) -> None:
    list(client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1"), metadata=metadata))


def _client_insert_stream(client: ArcadeDBGrpcClient, metadata: _Metadata) -> None:
    client.insert_stream(_insert_request(), metadata=metadata)


def _client_time_series_query(client: ArcadeDBGrpcClient, metadata: _Metadata) -> None:
    list(client.time_series_query(messages.TimeSeriesQueryRequest(database="db", type="cpu"), metadata=metadata))


def _client_time_series_write_stream(client: ArcadeDBGrpcClient, metadata: _Metadata) -> None:
    client.time_series_write_stream(_ts_write_request(), metadata=metadata)


def _handle_stream_query(client: ArcadeDBGrpcClient, metadata: _Metadata) -> None:
    with client.transaction("db") as tx:
        list(tx.stream_query(messages.StreamQueryRequest(query="SELECT 1"), metadata=metadata))


def _handle_time_series_query(client: ArcadeDBGrpcClient, metadata: _Metadata) -> None:
    with client.transaction("db") as tx:
        list(tx.time_series_query(messages.TimeSeriesQueryRequest(type="cpu"), metadata=metadata))


_SYNC_CASES: list[tuple[Callable[[ArcadeDBGrpcClient, _Metadata], None], str]] = [
    (_client_stream_query, "StreamQuery"),
    (_client_insert_stream, "InsertStream"),
    (_client_time_series_query, "TimeSeriesQuery"),
    (_client_time_series_write_stream, "TimeSeriesWriteStream"),
    (_handle_stream_query, "StreamQuery"),
    (_handle_time_series_query, "TimeSeriesQuery"),
]
_SYNC_IDS = [call.__name__.lstrip("_") for call, _ in _SYNC_CASES]


@pytest.mark.parametrize(("call", "rpc"), _SYNC_CASES, ids=_SYNC_IDS)
def test_sync_per_call_metadata_reaches_the_server_alongside_channel_auth(
    fake_server: tuple[str, RecordingServicer],
    call: Callable[[ArcadeDBGrpcClient, _Metadata], None],
    rpc: str,
) -> None:
    target, servicer = fake_server
    with create_client(target, auth=bearer_auth("t0ken")) as client:
        # A list, not a tuple: `Sequence` is the public type, and the sync stub's tuple
        # requirement is the facade's to meet (`_as_metadata`), not the caller's.
        call(client, [_HEADER])
    assert _HEADER in servicer.metadata_by_rpc[rpc]
    assert _AUTH in servicer.metadata_by_rpc[rpc]


@pytest.mark.parametrize(("call", "rpc"), _SYNC_CASES, ids=_SYNC_IDS)
def test_sync_omitting_metadata_still_works(
    fake_server: tuple[str, RecordingServicer],
    call: Callable[[ArcadeDBGrpcClient, _Metadata], None],
    rpc: str,
) -> None:
    target, servicer = fake_server
    with create_client(target, auth=bearer_auth("t0ken")) as client:
        call(client, None)
    assert _HEADER not in servicer.metadata_by_rpc[rpc]
    assert _AUTH in servicer.metadata_by_rpc[rpc]


def test_sync_handle_metadata_cannot_rebind_the_transaction(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # Per-call metadata is headers; the binding is request FIELDS. A caller putting a
    # transaction-looking header on a bound call changes nothing `_bind` decided.
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        list(tx.stream_query(messages.StreamQueryRequest(query="SELECT 1"), metadata=[("x-transaction-id", "other")]))
    sent = servicer.stream_query_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.database == "db"
    assert ("x-transaction-id", "other") in servicer.metadata_by_rpc["StreamQuery"]


# --- async -----------------------------------------------------------------------------


async def _aclient_stream_query(client: AsyncArcadeDBGrpcClient, metadata: _Metadata) -> None:
    async for _ in client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1"), metadata=metadata):
        pass


async def _aclient_insert_stream(client: AsyncArcadeDBGrpcClient, metadata: _Metadata) -> None:
    await client.insert_stream(_insert_request(), metadata=metadata)


async def _aclient_time_series_query(client: AsyncArcadeDBGrpcClient, metadata: _Metadata) -> None:
    async for _ in client.time_series_query(
        messages.TimeSeriesQueryRequest(database="db", type="cpu"), metadata=metadata
    ):
        pass


async def _aclient_time_series_write_stream(client: AsyncArcadeDBGrpcClient, metadata: _Metadata) -> None:
    await client.time_series_write_stream(_ts_write_request(), metadata=metadata)


async def _ahandle_stream_query(client: AsyncArcadeDBGrpcClient, metadata: _Metadata) -> None:
    async with client.transaction("db") as tx:
        async for _ in tx.stream_query(messages.StreamQueryRequest(query="SELECT 1"), metadata=metadata):
            pass


async def _ahandle_time_series_query(client: AsyncArcadeDBGrpcClient, metadata: _Metadata) -> None:
    async with client.transaction("db") as tx:
        async for _ in tx.time_series_query(messages.TimeSeriesQueryRequest(type="cpu"), metadata=metadata):
            pass


_ASYNC_CASES: list[tuple[Callable[[AsyncArcadeDBGrpcClient, _Metadata], Awaitable[None]], str]] = [
    (_aclient_stream_query, "StreamQuery"),
    (_aclient_insert_stream, "InsertStream"),
    (_aclient_time_series_query, "TimeSeriesQuery"),
    (_aclient_time_series_write_stream, "TimeSeriesWriteStream"),
    (_ahandle_stream_query, "StreamQuery"),
    (_ahandle_time_series_query, "TimeSeriesQuery"),
]
_ASYNC_IDS = [call.__name__.lstrip("_") for call, _ in _ASYNC_CASES]


@pytest.mark.asyncio
@pytest.mark.parametrize(("call", "rpc"), _ASYNC_CASES, ids=_ASYNC_IDS)
async def test_async_per_call_metadata_reaches_the_server_alongside_channel_auth(
    async_fake_server: tuple[str, RecordingServicer],
    call: Callable[[AsyncArcadeDBGrpcClient, _Metadata], Awaitable[None]],
    rpc: str,
) -> None:
    target, servicer = async_fake_server
    async with create_async_client(target, auth=bearer_auth("t0ken")) as client:
        await call(client, [_HEADER])
    assert _HEADER in servicer.metadata_by_rpc[rpc]
    assert _AUTH in servicer.metadata_by_rpc[rpc]


@pytest.mark.asyncio
@pytest.mark.parametrize(("call", "rpc"), _ASYNC_CASES, ids=_ASYNC_IDS)
async def test_async_omitting_metadata_still_works(
    async_fake_server: tuple[str, RecordingServicer],
    call: Callable[[AsyncArcadeDBGrpcClient, _Metadata], Awaitable[None]],
    rpc: str,
) -> None:
    target, servicer = async_fake_server
    async with create_async_client(target, auth=bearer_auth("t0ken")) as client:
        await call(client, None)
    assert _HEADER not in servicer.metadata_by_rpc[rpc]
    assert _AUTH in servicer.metadata_by_rpc[rpc]


@pytest.mark.asyncio
async def test_async_handle_metadata_cannot_rebind_the_transaction(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    async with create_async_client(target) as client, client.transaction("db") as tx:
        async for _ in tx.stream_query(
            messages.StreamQueryRequest(query="SELECT 1"), metadata=[("x-transaction-id", "other")]
        ):
            pass
    sent = servicer.stream_query_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.database == "db"
    assert ("x-transaction-id", "other") in servicer.metadata_by_rpc["StreamQuery"]
