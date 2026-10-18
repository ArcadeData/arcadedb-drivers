"""`transaction(database, isolation_level=...)`: `BeginTransactionRequest.isolation` (issue #152).

Only `READ_COMMITTED` and `REPEATABLE_READ` are accepted: the server runs `READ_UNCOMMITTED` as
`READ_COMMITTED` and `SERIALIZABLE` as `REPEATABLE_READ` without saying so. Absent, the field is
left unset, which the server also begins at `READ_COMMITTED`.
"""

from __future__ import annotations

import pytest
from arcadedb_driver_grpc import create_client, messages
from arcadedb_driver_grpc.aio import create_client as create_async_client

from .conftest import RecordingServicer


def test_isolation_level_is_sent_on_begin(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        with client.transaction("db", isolation_level="REPEATABLE_READ"):
            pass
        with client.transaction("db", isolation_level="READ_COMMITTED"):
            pass
    assert [r.isolation for r in servicer.begin_requests] == [messages.REPEATABLE_READ, messages.READ_COMMITTED]


def test_no_isolation_level_leaves_the_field_unset(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    with create_client(target) as client, client.transaction("db"):
        pass
    assert servicer.begin_requests[0].isolation == messages.READ_UNCOMMITTED  # proto3's zero value: unset


def test_an_unsupported_isolation_level_is_refused_before_begin(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    with create_client(target) as client, pytest.raises(ValueError, match="SERIALIZABLE"):
        client.transaction("db", isolation_level="SERIALIZABLE")  # type: ignore[arg-type]
    assert servicer.calls == []


@pytest.mark.asyncio
async def test_async_isolation_level_is_sent_on_begin(async_fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = async_fake_server
    async with create_async_client(target) as client, client.transaction("db", isolation_level="REPEATABLE_READ"):
        pass
    assert servicer.begin_requests[0].isolation == messages.REPEATABLE_READ


@pytest.mark.asyncio
async def test_async_an_unsupported_isolation_level_is_refused_before_begin(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    async with create_async_client(target) as client:
        with pytest.raises(ValueError, match="SERIALIZABLE"):
            client.transaction("db", isolation_level="SERIALIZABLE")  # type: ignore[arg-type]
    assert servicer.calls == []
