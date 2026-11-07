"""`create_client(options=, compression=)` reaches the grpc channel, sync and async."""

from __future__ import annotations

from typing import Any

import grpc
import pytest
from arcadedb_driver_grpc import create_client
from arcadedb_driver_grpc import messages as pb2
from arcadedb_driver_grpc.aio import create_client as create_async_client

from .conftest import RecordingServicer

_TINY_SEND_LIMIT = [("grpc.max_send_message_length", 100)]
_BIG_COMMAND = "x" * 1000


def test_options_reach_the_channel_and_change_behaviour(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    with create_client(target, options=_TINY_SEND_LIMIT) as client, pytest.raises(grpc.RpcError) as caught:
        client.raw.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command=_BIG_COMMAND))
    assert caught.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
    assert servicer.calls == []


def test_no_options_sends_the_same_message(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        client.raw.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command=_BIG_COMMAND))
    assert servicer.calls == ["ExecuteCommand"]


@pytest.mark.asyncio
async def test_async_options_reach_the_channel_and_change_behaviour(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    async with create_async_client(target, options=_TINY_SEND_LIMIT) as client:
        with pytest.raises(grpc.aio.AioRpcError) as caught:
            await client.raw.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command=_BIG_COMMAND))
    assert caught.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
    assert servicer.calls == []


@pytest.mark.asyncio
async def test_async_no_options_sends_the_same_message(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    async with create_async_client(target) as client:
        await client.raw.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command=_BIG_COMMAND))
    assert servicer.calls == ["ExecuteCommand"]


def _spy(monkeypatch: pytest.MonkeyPatch, owner: Any, name: str) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    real = getattr(owner, name)

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(owner, name, spy)
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("owner", "name", "factory", "extra"),
    [
        (grpc, "insecure_channel", create_client, {}),
        (grpc.aio, "insecure_channel", create_async_client, {}),
        (grpc, "secure_channel", create_client, {"credentials": grpc.local_channel_credentials()}),
        (grpc.aio, "secure_channel", create_async_client, {"credentials": grpc.local_channel_credentials()}),
    ],
)
async def test_options_and_compression_are_forwarded_and_default_to_none(
    monkeypatch: pytest.MonkeyPatch, owner: Any, name: str, factory: Any, extra: dict[str, Any]
) -> None:
    seen = _spy(monkeypatch, owner, name)
    factory("127.0.0.1:1", **extra)
    assert seen["options"] is None
    assert seen["compression"] is None

    seen = _spy(monkeypatch, owner, name)
    options = [("grpc.keepalive_time_ms", 30_000)]
    factory("127.0.0.1:1", options=options, compression=grpc.Compression.Gzip, **extra)
    assert seen["options"] == options
    assert seen["compression"] == grpc.Compression.Gzip
