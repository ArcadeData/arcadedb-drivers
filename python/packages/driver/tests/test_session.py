import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import (
    APIToken,
    ArcadeDBError,
    ArcadeDBServer,
    AsyncArcadeDBServer,
    LoginResult,
    NotSessionTokenError,
    basic_auth,
    bearer_auth,
)

BASE_URL = "http://db.test"
LOGIN = f"{BASE_URL}/api/v1/login"
LOGOUT = f"{BASE_URL}/api/v1/logout"
SESSIONS = f"{BASE_URL}/api/v1/sessions"
TOKENS = f"{BASE_URL}/api/v1/server/api-tokens"
DATABASES = f"{BASE_URL}/api/v1/databases"

SESSION_TOKEN = "AU-node-6f1c2d3e"
API_TOKEN = "at-0123456789abcdef"
HASH = "a" * 64
UTC = timezone.utc
DB_LIST = {"user": "root", "version": "26.11.1", "serverName": "s", "result": []}

TOKEN_FIELDS = {
    "name": "ci",
    "database": "tenant_a",
    "createdAt": 1_760_000_000_123,
    "expiresAt": 0,
    "permissions": {"types": {"*": {"access": ["readRecord"]}}},
    "tokenHash": HASH,
    "tokenSuffix": "cdef",
}


def authorization(route: respx.Route, call: int = -1) -> str | None:
    value: str | None = route.calls[call].request.headers.get("Authorization")
    return value


def sent_json(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


# --- login and login_as ---------------------------------------------------------------


@respx.mock
def test_login_uses_the_clients_own_credentials() -> None:
    route = respx.post(LOGIN).mock(return_value=httpx.Response(200, json={"token": SESSION_TOKEN, "user": "root"}))
    with ArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "pw-12345")) as srv:
        assert srv.login() == LoginResult(token=SESSION_TOKEN, user="root")
    assert authorization(route) == basic_auth("root", "pw-12345")["Authorization"]


@respx.mock
def test_login_as_sends_the_given_credentials_and_leaves_the_client_alone() -> None:
    login = respx.post(LOGIN).mock(return_value=httpx.Response(200, json={"token": SESSION_TOKEN, "user": "alice"}))
    dbs = respx.get(DATABASES).mock(return_value=httpx.Response(200, json=DB_LIST))
    with ArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "pw-12345")) as srv:
        assert srv.login_as("alice", "alice-pw").user == "alice"
        srv.list_databases()
    assert authorization(login) == basic_auth("alice", "alice-pw")["Authorization"]
    assert authorization(dbs) == basic_auth("root", "pw-12345")["Authorization"]


@respx.mock
@pytest.mark.parametrize("status", [401, 403, 503])
def test_a_refused_login_raises_arcadedb_error(status: int) -> None:
    respx.post(LOGIN).mock(return_value=httpx.Response(status, json={"error": "Security error"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        for call in (srv.login, lambda: srv.login_as("alice", "wrong")):
            with pytest.raises(ArcadeDBError) as info:
                call()
            assert info.value.status == status


def test_tokens_are_left_out_of_repr() -> None:
    assert SESSION_TOKEN not in repr(LoginResult(token=SESSION_TOKEN, user="alice"))


# --- with_token -----------------------------------------------------------------------


@respx.mock
def test_with_token_returns_a_new_server_and_leaves_the_original_alone() -> None:
    route = respx.get(DATABASES).mock(return_value=httpx.Response(200, json=DB_LIST))
    with ArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "pw-12345"), headers={"X-Tenant": "a"}) as srv:
        with srv.with_token(SESSION_TOKEN) as alice:
            alice.list_databases()
        srv.list_databases()
    first, second = route.calls[0].request.headers, route.calls[1].request.headers
    assert first["Authorization"] == f"Bearer {SESSION_TOKEN}"
    assert first["X-Tenant"] == "a"
    assert second["Authorization"] == basic_auth("root", "pw-12345")["Authorization"]


@respx.mock
def test_with_token_replaces_an_authorization_header_in_any_case() -> None:
    route = respx.get(DATABASES).mock(return_value=httpx.Response(200, json=DB_LIST))
    with (
        ArcadeDBServer(base_url=BASE_URL, headers={"authorization": "Basic old"}) as srv,
        srv.with_token(SESSION_TOKEN) as alice,
    ):
        alice.list_databases()
    assert route.calls.last.request.headers.get_list("Authorization") == [f"Bearer {SESSION_TOKEN}"]


# --- logout ---------------------------------------------------------------------------


@respx.mock
def test_logout_ends_a_session_token() -> None:
    route = respx.post(LOGOUT).mock(return_value=httpx.Response(204))
    with ArcadeDBServer(base_url=BASE_URL, auth=bearer_auth(SESSION_TOKEN)) as srv:
        srv.logout()
    assert authorization(route) == f"Bearer {SESSION_TOKEN}"


@respx.mock
@pytest.mark.parametrize(
    "auth", [None, basic_auth("root", "pw-12345"), bearer_auth(API_TOKEN), {"Authorization": "AU-not-bearer"}]
)
def test_logout_without_a_session_token_is_refused_unsent(auth: dict[str, str] | None) -> None:
    route = respx.post(LOGOUT).mock(return_value=httpx.Response(204))
    with ArcadeDBServer(base_url=BASE_URL, auth=auth) as srv, pytest.raises(NotSessionTokenError):
        srv.logout()
    assert not route.called


@respx.mock
def test_logout_of_a_dead_token_raises_401() -> None:
    respx.post(LOGOUT).mock(return_value=httpx.Response(401, json={"error": "Invalid token"}))
    with (
        ArcadeDBServer(base_url=BASE_URL, auth=bearer_auth(SESSION_TOKEN)) as srv,
        pytest.raises(ArcadeDBError) as info,
    ):
        srv.logout()
    assert info.value.status == 401


# --- list_sessions --------------------------------------------------------------------


@respx.mock
def test_list_sessions_maps_each_session() -> None:
    respx.get(SESSIONS).mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "result": [
                    {
                        "token": SESSION_TOKEN,
                        "user": "alice",
                        "createdAt": 1_760_000_000_000,
                        "lastUpdate": 1_760_000_060_500,
                        "elapsedMs": 1500,
                        "sourceIp": "10.0.0.1",
                        "userAgent": "curl/8",
                        "country": None,
                        "city": None,
                    },
                    {
                        "token": "AU-other",
                        "user": "bob",
                        "issuer": "node-2",
                        "createdAt": 0,
                        "lastUpdate": 0,
                        "elapsedMs": 0,
                        "sourceIp": None,
                        "userAgent": None,
                        "country": "IT",
                        "city": "Rome",
                    },
                ],
            },
        )
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        alice, bob = srv.list_sessions()
    assert alice.token == SESSION_TOKEN
    assert alice.user == "alice"
    assert alice.issuer is None
    assert alice.created_at == datetime(2025, 10, 9, 8, 53, 20, tzinfo=UTC)
    assert alice.last_update - alice.created_at == timedelta(seconds=60, milliseconds=500)
    assert alice.elapsed == timedelta(milliseconds=1500)
    assert (alice.source_ip, alice.user_agent, alice.country, alice.city) == ("10.0.0.1", "curl/8", None, None)
    assert (bob.issuer, bob.source_ip, bob.country, bob.city) == ("node-2", None, "IT", "Rome")
    assert SESSION_TOKEN not in repr(alice)


@respx.mock
def test_list_sessions_as_a_non_root_user_raises_403() -> None:
    respx.get(SESSIONS).mock(return_value=httpx.Response(403, json={"error": "Security error"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as info:
        srv.list_sessions()
    assert info.value.status == 403


# --- API tokens -----------------------------------------------------------------------


@respx.mock
def test_create_api_token_sends_only_what_was_given() -> None:
    route = respx.post(TOKENS).mock(
        return_value=httpx.Response(201, json={"result": {**TOKEN_FIELDS, "token": API_TOKEN}})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.create_api_token("ci")
        assert sent_json(route) == {"name": "ci"}
        created = srv.create_api_token(
            "ci",
            database="tenant_a",
            expires_at=datetime(2030, 1, 1, 1, tzinfo=timezone(timedelta(hours=1))),
            permissions={"types": {"*": {"access": ["readRecord"]}}},
        )
    assert sent_json(route) == {
        "name": "ci",
        "database": "tenant_a",
        "expiresAt": 1_893_456_000_000,
        "permissions": {"types": {"*": {"access": ["readRecord"]}}},
    }
    assert created.token == API_TOKEN
    assert created.name == "ci"
    assert created.database == "tenant_a"
    assert created.created_at == datetime(2025, 10, 9, 8, 53, 20, 123000, tzinfo=UTC)
    assert created.expires_at is None
    assert created.expired is False
    assert created.permissions == {"types": {"*": {"access": ["readRecord"]}}}
    assert (created.token_hash, created.token_suffix) == (HASH, "cdef")
    assert API_TOKEN not in repr(created)


@respx.mock
@pytest.mark.parametrize(
    "expires_at",
    [datetime(2030, 1, 1), datetime(1970, 1, 1, tzinfo=UTC), datetime(1969, 12, 31, tzinfo=UTC)],
    ids=["naive", "epoch", "before-epoch"],
)
def test_create_api_token_refuses_an_ambiguous_expiry_unsent(expires_at: datetime) -> None:
    route = respx.post(TOKENS).mock(return_value=httpx.Response(201))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ValueError, match="expires_at"):
        srv.create_api_token("ci", expires_at=expires_at)
    assert not route.called


@respx.mock
@pytest.mark.parametrize("status", [400, 409, 412])
def test_a_refused_create_api_token_raises_arcadedb_error(status: int) -> None:
    respx.post(TOKENS).mock(return_value=httpx.Response(status, json={"error": "refused"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as info:
        srv.create_api_token("ci")
    assert info.value.status == status


@respx.mock
def test_list_api_tokens_maps_expiry_and_the_expired_flag() -> None:
    respx.get(TOKENS).mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "result": [
                    TOKEN_FIELDS,
                    {**TOKEN_FIELDS, "name": "old", "expiresAt": 1_760_000_000_000, "expired": True},
                ],
            },
        )
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        never, old = srv.list_api_tokens()
    assert isinstance(never, APIToken)
    assert (never.expires_at, never.expired) == (None, False)
    assert (old.expires_at, old.expired) == (datetime(2025, 10, 9, 8, 53, 20, tzinfo=UTC), True)


@respx.mock
def test_delete_api_token_sends_the_hash() -> None:
    route = respx.delete(TOKENS).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.delete_api_token(HASH)
    assert route.calls.last.request.url.params["token"] == HASH


@respx.mock
@pytest.mark.parametrize("arg", [API_TOKEN, "", HASH.upper(), HASH[:-1], HASH + "0", "g" * 64, f" {HASH[1:]}"])
def test_delete_api_token_refuses_anything_but_a_hash_unsent(arg: str) -> None:
    route = respx.delete(TOKENS).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ValueError) as info:
        srv.delete_api_token(arg)
    assert not route.called
    if arg:
        assert arg not in str(info.value)


@respx.mock
def test_delete_an_unknown_hash_raises_404() -> None:
    respx.delete(TOKENS).mock(return_value=httpx.Response(404, json={"error": "Token not found"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as info:
        srv.delete_api_token(HASH)
    assert info.value.status == 404


# --- the async twin -------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_async_login_as_and_with_token() -> None:
    login = respx.post(LOGIN).mock(return_value=httpx.Response(200, json={"token": SESSION_TOKEN, "user": "alice"}))
    dbs = respx.get(DATABASES).mock(return_value=httpx.Response(200, json={**DB_LIST, "result": ["tenant_a"]}))
    async with AsyncArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "pw-12345")) as srv:
        result = await srv.login_as("alice", "alice-pw")
        async with srv.with_token(result.token) as alice:
            assert await alice.list_databases() == ["tenant_a"]
        await srv.list_databases()
    assert authorization(login) == basic_auth("alice", "alice-pw")["Authorization"]
    assert authorization(dbs, 0) == f"Bearer {SESSION_TOKEN}"
    assert authorization(dbs, 1) == basic_auth("root", "pw-12345")["Authorization"]


@respx.mock
@pytest.mark.asyncio
async def test_async_login_and_logout() -> None:
    respx.post(LOGIN).mock(return_value=httpx.Response(200, json={"token": SESSION_TOKEN, "user": "root"}))
    route = respx.post(LOGOUT).mock(return_value=httpx.Response(204))
    async with AsyncArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "pw-12345")) as srv:
        with pytest.raises(NotSessionTokenError):
            await srv.logout()
        assert not route.called
        token = (await srv.login()).token
        async with srv.with_token(token) as session:
            await session.logout()
    assert authorization(route) == f"Bearer {SESSION_TOKEN}"


@respx.mock
@pytest.mark.asyncio
async def test_async_sessions_and_api_tokens() -> None:
    respx.get(SESSIONS).mock(return_value=httpx.Response(200, json={"count": 0, "result": []}))
    respx.post(TOKENS).mock(return_value=httpx.Response(201, json={"result": {**TOKEN_FIELDS, "token": API_TOKEN}}))
    respx.get(TOKENS).mock(return_value=httpx.Response(200, json={"count": 1, "result": [TOKEN_FIELDS]}))
    delete = respx.delete(TOKENS).mock(return_value=httpx.Response(404, json={"error": "Token not found"}))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        assert await srv.list_sessions() == []
        created = await srv.create_api_token("ci")
        assert [t.token_hash for t in await srv.list_api_tokens()] == [created.token_hash]
        with pytest.raises(ValueError):
            await srv.delete_api_token(created.token)
        assert not delete.called
        with pytest.raises(ArcadeDBError) as info:
            await srv.delete_api_token(created.token_hash)
    assert info.value.status == 404
