"""Tests for the per-call `timeout` argument of `query`, `command`, `query_stream` and
`command_stream`, sync and async.

No network and no server: every case goes through `httpx.MockTransport`. The transport cannot make
a real clock run out, but httpx hands it the timeout it resolved for the request as
`request.extensions["timeout"]` (a dict with the `connect`, `read`, `write` and `pool` phases), so
two things are checked from there: the exact value that reached httpx, and a handler that plays a
server needing `SERVER_DELAY_S` seconds to answer and raises `httpx.ReadTimeout` when the read
phase is shorter than that, which is what the real transport does when the wait runs out.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from arcadedb_driver import ArcadeDBDatabase, ArcadeDBError, ArcadeDBServer, AsyncArcadeDBDatabase, AsyncArcadeDBServer

BASE_URL = "http://db.test"
SERVER_DELAY_S = 5.0
CLIENT_TIMEOUT = httpx.Timeout(30.0)

ENVELOPE = {"result": [{"a": 1}], "limit": 100, "returned": 1, "truncated": False}
NDJSON = (
    json.dumps({"record": {"a": 1}}) + "\n" + json.dumps({"stats": {"limit": 100, "returned": 1, "truncated": False}})
).encode()

KINDS = ["query", "command", "query_stream", "command_stream"]

Seen = list[dict[str, float | None]]


def _handler(kind: str, seen: Seen) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        phases: dict[str, float | None] = request.extensions["timeout"]
        seen.append(phases)
        read = phases["read"]
        if read is not None and read < SERVER_DELAY_S:
            raise httpx.ReadTimeout("the server did not answer in time", request=request)
        if kind.endswith("_stream"):
            return httpx.Response(200, content=NDJSON, headers={"Content-Type": "application/x-ndjson"})
        return httpx.Response(200, json=ENVELOPE)

    return handle


def sync_db(kind: str, seen: Seen, client_timeout: httpx.Timeout | None) -> ArcadeDBDatabase:
    srv = ArcadeDBServer(base_url=BASE_URL, timeout=client_timeout)
    srv.raw.set_httpx_client(
        httpx.Client(base_url=BASE_URL, timeout=client_timeout, transport=httpx.MockTransport(_handler(kind, seen)))
    )
    return srv.db("mydb")


def async_db(kind: str, seen: Seen, client_timeout: httpx.Timeout | None) -> AsyncArcadeDBDatabase:
    srv = AsyncArcadeDBServer(base_url=BASE_URL, timeout=client_timeout)
    srv.raw.set_async_httpx_client(
        httpx.AsyncClient(
            base_url=BASE_URL, timeout=client_timeout, transport=httpx.MockTransport(_handler(kind, seen))
        )
    )
    return srv.db("mydb")


def call(db: ArcadeDBDatabase, kind: str, **kwargs: Any) -> object:
    result = getattr(db, kind)(language="sql", command="SELECT 1", **kwargs)
    return list(result) if kind.endswith("_stream") else result


async def acall(db: AsyncArcadeDBDatabase, kind: str, **kwargs: Any) -> object:
    result = getattr(db, kind)(language="sql", command="SELECT 1", **kwargs)
    if kind.endswith("_stream"):
        return [event async for event in result]
    return await result


def phases(value: float | None, **overrides: float | None) -> dict[str, float | None]:
    return {"connect": value, "read": value, "write": value, "pool": value, **overrides}


@pytest.mark.parametrize("kind", KINDS)
class TestSync:
    def test_a_float_sets_every_phase_for_that_call(self, kind: str) -> None:
        seen: Seen = []
        call(sync_db(kind, seen, CLIENT_TIMEOUT), kind, timeout=7.5)
        assert seen == [phases(7.5)]

    def test_an_httpx_timeout_keeps_its_phases_apart(self, kind: str) -> None:
        seen: Seen = []
        call(
            sync_db(kind, seen, CLIENT_TIMEOUT), kind, timeout=httpx.Timeout(connect=1.0, read=6.0, write=3.0, pool=4.0)
        )
        assert seen == [{"connect": 1.0, "read": 6.0, "write": 3.0, "pool": 4.0}]

    def test_none_removes_the_clients_timeout_for_that_call(self, kind: str) -> None:
        seen: Seen = []
        call(sync_db(kind, seen, CLIENT_TIMEOUT), kind, timeout=None)
        assert seen == [phases(None)]

    def test_the_per_call_value_does_not_stick(self, kind: str) -> None:
        seen: Seen = []
        db = sync_db(kind, seen, CLIENT_TIMEOUT)
        call(db, kind, timeout=7.5)
        call(db, kind)
        assert seen == [phases(7.5), phases(30.0)]

    def test_omitting_it_keeps_the_clients_timeout(self, kind: str) -> None:
        seen: Seen = []
        call(sync_db(kind, seen, CLIENT_TIMEOUT), kind)
        assert seen == [phases(30.0)]

    def test_omitting_it_on_a_client_without_a_timeout_stays_without_one(self, kind: str) -> None:
        seen: Seen = []
        call(sync_db(kind, seen, None), kind)
        assert seen == [phases(None)]

    def test_a_slow_server_and_a_short_per_call_timeout_raise_a_read_timeout(self, kind: str) -> None:
        seen: Seen = []
        with pytest.raises(httpx.ReadTimeout) as err:
            call(sync_db(kind, seen, None), kind, timeout=0.5)
        assert not isinstance(err.value, ArcadeDBError)
        assert seen == [phases(0.5)]

    def test_a_per_call_timeout_longer_than_the_server_needs_lets_the_call_through(self, kind: str) -> None:
        seen: Seen = []
        assert call(sync_db(kind, seen, None), kind, timeout=SERVER_DELAY_S + 1) != []

    def test_without_the_argument_the_same_slow_server_is_not_cut_short(self, kind: str) -> None:
        seen: Seen = []
        assert call(sync_db(kind, seen, None), kind) != []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
class TestAsync:
    async def test_a_float_sets_every_phase_for_that_call(self, kind: str) -> None:
        seen: Seen = []
        await acall(async_db(kind, seen, CLIENT_TIMEOUT), kind, timeout=7.5)
        assert seen == [phases(7.5)]

    async def test_an_httpx_timeout_keeps_its_phases_apart(self, kind: str) -> None:
        seen: Seen = []
        timeout = httpx.Timeout(connect=1.0, read=6.0, write=3.0, pool=4.0)
        await acall(async_db(kind, seen, CLIENT_TIMEOUT), kind, timeout=timeout)
        assert seen == [{"connect": 1.0, "read": 6.0, "write": 3.0, "pool": 4.0}]

    async def test_none_removes_the_clients_timeout_for_that_call(self, kind: str) -> None:
        seen: Seen = []
        await acall(async_db(kind, seen, CLIENT_TIMEOUT), kind, timeout=None)
        assert seen == [phases(None)]

    async def test_the_per_call_value_does_not_stick(self, kind: str) -> None:
        seen: Seen = []
        db = async_db(kind, seen, CLIENT_TIMEOUT)
        await acall(db, kind, timeout=7.5)
        await acall(db, kind)
        assert seen == [phases(7.5), phases(30.0)]

    async def test_omitting_it_keeps_the_clients_timeout(self, kind: str) -> None:
        seen: Seen = []
        await acall(async_db(kind, seen, CLIENT_TIMEOUT), kind)
        assert seen == [phases(30.0)]

    async def test_omitting_it_on_a_client_without_a_timeout_stays_without_one(self, kind: str) -> None:
        seen: Seen = []
        await acall(async_db(kind, seen, None), kind)
        assert seen == [phases(None)]

    async def test_a_slow_server_and_a_short_per_call_timeout_raise_a_read_timeout(self, kind: str) -> None:
        seen: Seen = []
        with pytest.raises(httpx.ReadTimeout) as err:
            await acall(async_db(kind, seen, None), kind, timeout=0.5)
        assert not isinstance(err.value, ArcadeDBError)
        assert seen == [phases(0.5)]

    async def test_a_per_call_timeout_longer_than_the_server_needs_lets_the_call_through(self, kind: str) -> None:
        seen: Seen = []
        assert await acall(async_db(kind, seen, None), kind, timeout=SERVER_DELAY_S + 1) != []

    async def test_without_the_argument_the_same_slow_server_is_not_cut_short(self, kind: str) -> None:
        seen: Seen = []
        assert await acall(async_db(kind, seen, None), kind) != []
