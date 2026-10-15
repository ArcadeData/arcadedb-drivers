"""Server administration against a real server: databases, users, groups, server commands and
`sqlscript`. The statuses pinned here are what the README and the docstrings promise."""

import itertools
import uuid
from collections.abc import Callable

import pytest
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer, basic_auth

from .conftest import ROOT_PASSWORD

_counter = itertools.count()


def unique(prefix: str) -> str:
    return f"{prefix}{next(_counter)}{uuid.uuid4().hex[:6]}"


def root(base_url: str) -> ArcadeDBServer:
    return ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD))


def test_create_and_drop_database(base_url: str) -> None:
    name = unique("pyadmin")
    with root(base_url) as srv:
        srv.create_database(name)
        assert srv.exists(name)

        # 409 since ArcadeData/arcadedb#10079; earlier servers answered 400.
        with pytest.raises(ArcadeDBError) as info:
            srv.create_database(name)
        assert info.value.status == 409
        assert "already exists" in (info.value.detail or "")

        srv.drop_database(name)
        assert not srv.exists(name)
        with pytest.raises(ArcadeDBError) as info:
            srv.drop_database(name)
        assert info.value.status == 400


def test_server_command_list_databases(base_url: str, database: str) -> None:
    with root(base_url) as srv:
        assert database in srv.server_command("list databases")["result"]


def test_per_user_isolation(base_url: str, database: str) -> None:
    """The use case behind issue #122: a database per tenant, and a user who sees only theirs."""
    tenant, user = unique("pytenant"), unique("pyuser")
    with root(base_url) as srv:
        srv.create_database(tenant)
        try:
            srv.create_user(user, "first-password", databases={tenant: ["admin"]})
            try:
                listed = {u["name"]: u for u in srv.list_users()}
                assert listed[user]["databases"] == {tenant: ["admin"]}

                # 409 since ArcadeData/arcadedb#10076; earlier servers answered 403 "Security error".
                with pytest.raises(ArcadeDBError) as info:
                    srv.create_user(user, "first-password")
                assert info.value.status == 409
                assert "already exists" in str(info.value)

                with ArcadeDBServer(base_url=base_url, auth=basic_auth(user, "first-password")) as as_user:
                    visible = as_user.list_databases()
                assert tenant in visible
                assert database not in visible

                srv.update_user(user, password="second-password")
                with ArcadeDBServer(base_url=base_url, auth=basic_auth(user, "second-password")) as as_user:
                    as_user.list_databases()
            finally:
                srv.drop_user(user)

            missing: list[Callable[[], None]] = [
                lambda: srv.drop_user(user),
                lambda: srv.update_user(user, password="third-password"),
            ]
            for call in missing:
                with pytest.raises(ArcadeDBError) as info:
                    call()
                assert info.value.status == 404
        finally:
            srv.drop_database(tenant)


def test_group_lifecycle(base_url: str, database: str) -> None:
    with root(base_url) as srv:
        srv.save_group(database, "reader", result_set_limit=10)
        assert srv.list_groups()[database]["reader"]["resultSetLimit"] == 10
        srv.delete_group(database, "reader")
        assert "reader" not in srv.list_groups().get(database, {})


def test_sqlscript(base_url: str, database: str) -> None:
    with root(base_url) as srv:
        db = srv.db(database)
        db.command(
            language="sqlscript",
            command="CREATE DOCUMENT TYPE PyScript; INSERT INTO PyScript SET x = 1; INSERT INTO PyScript SET x = 2;",
        )
        assert db.query(language="sql", command="SELECT count(*) AS n FROM PyScript").result == [{"n": 2}]


@pytest.mark.asyncio
async def test_async_admin_round_trip(base_url: str) -> None:
    name, user = unique("pyaadmin"), unique("pyauser")
    async with AsyncArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        await srv.create_database(name)
        try:
            await srv.create_user(user, "first-password", databases={name: ["admin"]})
            assert user in {u["name"] for u in await srv.list_users()}
            with pytest.raises(ArcadeDBError) as info:
                await srv.create_user(user, "first-password")
            assert info.value.status == 409
            await srv.update_user(user, databases={})
            assert {u["name"]: u for u in await srv.list_users()}[user]["databases"] == {}
            await srv.drop_user(user)
            await srv.save_group(name, "reader", access=["readRecord"])
            assert "reader" in (await srv.list_groups())[name]
            await srv.delete_group(name, "reader")
            assert name in (await srv.server_command("list databases"))["result"]
        finally:
            await srv.drop_database(name)
        assert not await srv.exists(name)
