"""`httpx_args` reaches the httpx client the facade owns, and the default changes nothing."""

import httpx
import pytest
from arcadedb_driver import ArcadeDBServer, AsyncArcadeDBServer

BASE_URL = "http://db.test"


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(204)


def _server_with_hooks(seen: list[str]) -> ArcadeDBServer:
    return ArcadeDBServer(
        base_url=BASE_URL,
        httpx_args={
            "transport": httpx.MockTransport(_ok),
            "event_hooks": {"request": [lambda request: seen.append(str(request.url))]},
        },
    )


def test_httpx_args_reach_the_sync_client() -> None:
    seen: list[str] = []
    with _server_with_hooks(seen) as srv:
        assert srv.ready() is True
    assert seen == [f"{BASE_URL}/api/v1/ready"]


def test_with_token_keeps_httpx_args() -> None:
    seen: list[str] = []
    with _server_with_hooks(seen) as srv, srv.with_token("AU-token") as other:
        assert other.ready() is True
    assert seen == [f"{BASE_URL}/api/v1/ready"]


def test_default_httpx_args_leave_the_client_as_before() -> None:
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        client = srv.raw.get_httpx_client()
        assert client.event_hooks == {"request": [], "response": []}
        assert client.follow_redirects is False
        assert str(client.base_url) == BASE_URL
    with ArcadeDBServer(base_url=BASE_URL, httpx_args=None) as srv:
        assert srv.raw.get_httpx_client().event_hooks == {"request": [], "response": []}


@pytest.mark.asyncio
async def test_httpx_args_reach_the_async_client() -> None:
    seen: list[str] = []
    async with AsyncArcadeDBServer(
        base_url=BASE_URL,
        httpx_args={
            "transport": httpx.MockTransport(_ok),
            "event_hooks": {"request": [lambda request: _record(seen, request)]},
        },
    ) as srv:
        assert await srv.ready() is True
    assert seen == [f"{BASE_URL}/api/v1/ready"]


async def _record(seen: list[str], request: httpx.Request) -> None:
    seen.append(str(request.url))


@pytest.mark.asyncio
async def test_async_with_token_keeps_httpx_args() -> None:
    seen: list[str] = []
    async with (
        AsyncArcadeDBServer(
            base_url=BASE_URL,
            httpx_args={
                "transport": httpx.MockTransport(_ok),
                "event_hooks": {"request": [lambda request: _record(seen, request)]},
            },
        ) as srv,
        srv.with_token("AU-token") as other,
    ):
        assert await other.ready() is True
    assert seen == [f"{BASE_URL}/api/v1/ready"]


@pytest.mark.asyncio
async def test_default_async_client_is_unchanged() -> None:
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        client = srv.raw.get_async_httpx_client()
        assert client.event_hooks == {"request": [], "response": []}
        assert str(client.base_url) == BASE_URL
