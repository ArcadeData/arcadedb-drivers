"""`transaction(isolation_level=...)`: the level travels in the begin request's body (issue #152).

Absent, the begin request carries no body at all and the server uses the database's default
isolation level. A value outside the two the engine has is refused before anything is sent.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBServer, AsyncArcadeDBServer

BASE_URL = "http://db.test"
SESSION = "AS-0000-1111"
ENVELOPE = {"result": [], "limit": -1, "returned": 0, "truncated": False}


def _mock_transaction() -> tuple[respx.Route, respx.Route]:
    begin = respx.post(f"{BASE_URL}/api/v1/begin/mydb").mock(
        return_value=httpx.Response(204, headers={"arcadedb-session-id": SESSION})
    )
    command = respx.post(f"{BASE_URL}/api/v1/command/mydb").mock(return_value=httpx.Response(200, json=ENVELOPE))
    respx.post(f"{BASE_URL}/api/v1/commit/mydb").mock(return_value=httpx.Response(204))
    return begin, command


@respx.mock
def test_isolation_level_is_sent_in_the_begin_body_only() -> None:
    begin, command = _mock_transaction()
    with (
        ArcadeDBServer(base_url=BASE_URL) as srv,
        srv.db("mydb").transaction(isolation_level="REPEATABLE_READ") as tx,
    ):
        tx.command(language="sql", command="SELECT FROM V")

    assert json.loads(begin.calls.last.request.content) == {"isolationLevel": "REPEATABLE_READ"}
    assert "isolationLevel" not in json.loads(command.calls.last.request.content)


@respx.mock
def test_no_isolation_level_sends_no_begin_body() -> None:
    begin, _ = _mock_transaction()
    with ArcadeDBServer(base_url=BASE_URL) as srv, srv.db("mydb").transaction():
        pass

    assert begin.calls.last.request.content == b""


@respx.mock
def test_an_unsupported_isolation_level_is_refused_before_begin() -> None:
    begin, _ = _mock_transaction()
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ValueError, match="SERIALIZABLE"):
        srv.db("mydb").transaction(isolation_level="SERIALIZABLE")  # type: ignore[arg-type]

    assert not begin.called


@respx.mock
@pytest.mark.asyncio
async def test_async_isolation_level_is_sent_in_the_begin_body_only() -> None:
    begin, command = _mock_transaction()
    async with (
        AsyncArcadeDBServer(base_url=BASE_URL) as srv,
        srv.db("mydb").transaction(isolation_level="READ_COMMITTED") as tx,
    ):
        await tx.command(language="sql", command="SELECT FROM V")

    assert json.loads(begin.calls.last.request.content) == {"isolationLevel": "READ_COMMITTED"}
    assert "isolationLevel" not in json.loads(command.calls.last.request.content)


@respx.mock
@pytest.mark.asyncio
async def test_async_no_isolation_level_sends_no_begin_body() -> None:
    begin, _ = _mock_transaction()
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv, srv.db("mydb").transaction():
        pass

    assert begin.calls.last.request.content == b""


@respx.mock
@pytest.mark.asyncio
async def test_async_an_unsupported_isolation_level_is_refused_before_begin() -> None:
    begin, _ = _mock_transaction()
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ValueError, match="SERIALIZABLE"):
            srv.db("mydb").transaction(isolation_level="SERIALIZABLE")  # type: ignore[arg-type]

    assert not begin.called
