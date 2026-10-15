import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer

BASE_URL = "http://db.test"
SERVER = f"{BASE_URL}/api/v1/server"
USERS = f"{BASE_URL}/api/v1/server/users"
GROUPS = f"{BASE_URL}/api/v1/server/groups"

GROUP_LIST = {
    "result": {
        "version": 1,
        "databases": {
            "*": {
                "groups": {
                    "admin": {"access": ["updateSecurity"], "readTimeout": -1, "resultSetLimit": -1, "types": {}}
                }
            }
        },
    }
}


def sent_json(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


# --- sqlscript ---------------------------------------------------------------------


@respx.mock
def test_sqlscript_reaches_the_wire() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/command/db").mock(
        return_value=httpx.Response(200, json={"result": [], "limit": -1, "returned": 0, "truncated": False})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.db("db").command(language="sqlscript", command="LET a = 1; RETURN $a")
    assert sent_json(route)["language"] == "sqlscript"


# --- databases and server commands ---------------------------------------------------


@respx.mock
@pytest.mark.parametrize(
    ("method", "verb"), [("create_database", "create database"), ("drop_database", "drop database")]
)
def test_create_and_drop_database_send_a_server_command(method: str, verb: str) -> None:
    # The server's real answer: a string result where the contract declares an array.
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        assert getattr(srv, method)("tenant_a") is None
    assert sent_json(route) == {"command": f"{verb} tenant_a", "language": "sql"}


@respx.mock
@pytest.mark.parametrize("method", ["create_database", "drop_database"])
def test_create_and_drop_database_raise_arcadedb_error(method: str) -> None:
    respx.post(SERVER).mock(
        return_value=httpx.Response(
            400, json={"error": "Cannot execute command", "detail": "Database 'db' already exists"}
        )
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as info:
        getattr(srv, method)("db")
    assert info.value.status == 400
    assert info.value.detail == "Database 'db' already exists"


@respx.mock
@pytest.mark.parametrize("name", ["", " ", " db", "db ", "\tdb", "db\n"])
def test_a_database_name_the_server_would_trim_is_refused_before_any_request(name: str) -> None:
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        for call in (srv.create_database, srv.drop_database):
            with pytest.raises(ValueError, match="database name"):
                call(name)
    assert not route.called


@respx.mock
def test_server_command_returns_the_whole_body() -> None:
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": ["a", "b"]}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        assert srv.server_command("list databases") == {"result": ["a", "b"]}
    assert sent_json(route) == {"command": "list databases", "language": "sql"}


@respx.mock
@pytest.mark.parametrize(
    ("status", "message"), [(400, "Server command not valid"), (403, "Security error"), (503, "x")]
)
def test_server_command_raises_arcadedb_error(status: int, message: str) -> None:
    respx.post(SERVER).mock(return_value=httpx.Response(status, json={"error": message}))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as info:
        srv.server_command("whatever")
    assert (info.value.status, str(info.value)) == (status, message)


# --- users -----------------------------------------------------------------------------


@respx.mock
def test_create_user() -> None:
    route = respx.post(USERS).mock(return_value=httpx.Response(201, json={"result": "User 'alice' created"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.create_user("alice", "secret-pw", databases={"tenant_a": ["admin"]})
    assert sent_json(route) == {"name": "alice", "password": "secret-pw", "databases": {"tenant_a": ["admin"]}}


@respx.mock
def test_create_user_without_databases_sends_none() -> None:
    route = respx.post(USERS).mock(return_value=httpx.Response(201, json={"result": "User 'bob' created"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.create_user("bob", "secret-pw")
    assert sent_json(route) == {"name": "bob", "password": "secret-pw"}


@respx.mock
@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, {"error": "User password must be at least 8 characters"}),
        (403, {"error": "Security error"}),
        (409, {"error": "User already exists"}),
    ],
)
def test_create_user_raises_arcadedb_error(status: int, body: dict[str, str]) -> None:
    respx.post(USERS).mock(return_value=httpx.Response(status, json=body))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as info:
        srv.create_user("alice", "pw")
    assert info.value.status == status


@respx.mock
def test_update_user_sends_only_what_changes() -> None:
    route = respx.put(USERS, params={"name": "alice"}).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.update_user("alice", password="new-secret")
    assert sent_json(route) == {"password": "new-secret"}


@respx.mock
def test_update_user_with_empty_databases_clears_them() -> None:
    route = respx.put(USERS, params={"name": "alice"}).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.update_user("alice", databases={})
    assert sent_json(route) == {"databases": {}}


@respx.mock
def test_update_and_drop_a_missing_user_raise_404() -> None:
    respx.put(USERS).mock(return_value=httpx.Response(404, json={"error": "User 'ghost' not found"}))
    respx.delete(USERS).mock(return_value=httpx.Response(404, json={"error": "User 'ghost' not found"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        calls: list[Callable[[], None]] = [
            lambda: srv.update_user("ghost", password="x" * 8),
            lambda: srv.drop_user("ghost"),
        ]
        for call in calls:
            with pytest.raises(ArcadeDBError) as info:
                call()
            assert info.value.status == 404


@respx.mock
def test_drop_user_names_the_user_in_the_query() -> None:
    route = respx.delete(USERS).mock(return_value=httpx.Response(200, json={"result": "User 'a b' deleted"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.drop_user("a b")
    assert route.calls.last.request.url.params["name"] == "a b"


@respx.mock
def test_list_users_returns_plain_dicts() -> None:
    respx.get(USERS).mock(
        return_value=httpx.Response(
            200,
            json={"result": [{"name": "root", "databases": {"*": ["admin"]}}, {"name": "alice", "databases": {}}]},
        )
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        assert srv.list_users() == [
            {"name": "root", "databases": {"*": ["admin"]}},
            {"name": "alice", "databases": {}},
        ]


@respx.mock
def test_list_users_raises_arcadedb_error() -> None:
    respx.get(USERS).mock(return_value=httpx.Response(403, json={"error": "Security error"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as info:
        srv.list_users()
    assert info.value.status == 403


# --- groups ----------------------------------------------------------------------------


@respx.mock
def test_list_groups_keys_by_database_then_group() -> None:
    respx.get(GROUPS).mock(return_value=httpx.Response(200, json=GROUP_LIST))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        groups = srv.list_groups()
    assert groups["*"]["admin"]["access"] == ["updateSecurity"]
    assert groups["*"]["admin"]["readTimeout"] == -1


@respx.mock
def test_save_group_sends_only_what_is_given() -> None:
    route = respx.post(GROUPS).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.save_group("tenant_a", "reader", result_set_limit=100)
    assert sent_json(route) == {"database": "tenant_a", "name": "reader", "resultSetLimit": 100}


@respx.mock
def test_delete_group_names_database_and_group_in_the_query() -> None:
    route = respx.delete(GROUPS).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.delete_group("tenant_a", "reader")
    params = route.calls.last.request.url.params
    assert (params["database"], params["name"]) == ("tenant_a", "reader")


@respx.mock
def test_group_calls_raise_arcadedb_error() -> None:
    respx.route(url=GROUPS).mock(return_value=httpx.Response(404, json={"error": "Group 'x' not found"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        for call in (srv.list_groups, lambda: srv.save_group("db", "x"), lambda: srv.delete_group("db", "x")):
            with pytest.raises(ArcadeDBError) as info:
                call()
            assert info.value.status == 404


# --- async twins -------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_async_database_and_server_commands() -> None:
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        await srv.create_database("tenant_a")
        assert sent_json(route) == {"command": "create database tenant_a", "language": "sql"}
        await srv.drop_database("tenant_a")
        assert sent_json(route) == {"command": "drop database tenant_a", "language": "sql"}
        assert await srv.server_command("list databases") == {"result": "ok"}
        with pytest.raises(ValueError, match="database name"):
            await srv.create_database(" tenant_a")
    assert route.call_count == 3


@respx.mock
@pytest.mark.asyncio
async def test_async_errors_are_arcadedb_errors() -> None:
    respx.post(SERVER).mock(return_value=httpx.Response(400, json={"error": "Cannot execute command"}))
    respx.route(url__startswith=USERS).mock(return_value=httpx.Response(403, json={"error": "Security error"}))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        for call in (
            lambda: srv.create_database("db"),
            lambda: srv.server_command("x"),
            lambda: srv.create_user("a", "pw"),
            lambda: srv.update_user("a", password="x" * 8),
            lambda: srv.drop_user("a"),
            srv.list_users,
        ):
            with pytest.raises(ArcadeDBError):
                await call()


@respx.mock
@pytest.mark.asyncio
async def test_async_users_and_groups() -> None:
    created = respx.post(USERS).mock(return_value=httpx.Response(201, json={"result": "ok"}))
    updated = respx.put(USERS).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    dropped = respx.delete(USERS).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    respx.get(USERS).mock(return_value=httpx.Response(200, json={"result": [{"name": "alice", "databases": {}}]}))
    saved = respx.post(GROUPS).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    deleted = respx.delete(GROUPS).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    respx.get(GROUPS).mock(return_value=httpx.Response(200, json=GROUP_LIST))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        await srv.create_user("alice", "secret-pw", databases={"t": ["admin"]})
        await srv.update_user("alice", databases={})
        assert await srv.list_users() == [{"name": "alice", "databases": {}}]
        await srv.drop_user("alice")
        await srv.save_group("t", "reader", access=["readRecord"])
        assert (await srv.list_groups())["*"]["admin"]["readTimeout"] == -1
        await srv.delete_group("t", "reader")
    assert sent_json(created) == {"name": "alice", "password": "secret-pw", "databases": {"t": ["admin"]}}
    assert sent_json(updated) == {"databases": {}}
    assert dropped.calls.last.request.url.params["name"] == "alice"
    assert sent_json(saved) == {"database": "t", "name": "reader", "access": ["readRecord"]}
    assert deleted.calls.last.request.url.params["database"] == "t"


@respx.mock
def test_update_user_with_nothing_to_change_sends_an_empty_body() -> None:
    route = respx.put(USERS, params={"name": "alice"}).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.update_user("alice")
    assert sent_json(route) == {}


@respx.mock
def test_save_group_with_only_the_required_arguments() -> None:
    route = respx.post(GROUPS).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.save_group("tenant_a", "reader")
    assert sent_json(route) == {"database": "tenant_a", "name": "reader"}


@respx.mock
def test_a_database_name_with_embedded_space_is_sent_as_given() -> None:
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": "ok"}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.create_database("a b")
    assert sent_json(route)["command"] == "create database a b"
