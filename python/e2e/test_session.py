"""Login sessions and API tokens against a real server (issue #123). The statuses pinned here
are what the README and the docstrings promise, each measured rather than read off the contract."""

import contextlib
import itertools
import uuid

import pytest
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer, NotSessionTokenError, basic_auth

from .conftest import ROOT_PASSWORD

_counter = itertools.count()


def unique(prefix: str) -> str:
    return f"{prefix}{next(_counter)}{uuid.uuid4().hex[:6]}"


def root(base_url: str) -> ArcadeDBServer:
    return ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD))


def test_login_query_logout(base_url: str) -> None:
    """Issue #123's acceptance path: log in as a user, act as that user with the token alone,
    log out, and see the token refused."""
    tenant, other, user = unique("pysesstenant"), unique("pysessother"), unique("pysessuser")
    with root(base_url) as srv:
        srv.create_database(tenant)
        srv.create_database(other)
        try:
            srv.create_user(user, "session-password", databases={tenant: ["admin"]})
            try:
                # 403, not 401: the server answers every failed Basic check so (arcadedb#10109).
                with pytest.raises(ArcadeDBError) as info:
                    srv.login_as(user, "wrong-password")
                assert info.value.status == 403

                login = srv.login_as(user, "session-password")
                assert login.user == user
                assert login.token.startswith("AU-")

                with srv.with_token(login.token) as as_user:
                    visible = as_user.list_databases()
                    assert tenant in visible
                    assert other not in visible
                    assert as_user.db(tenant).query(language="sql", command="SELECT 1 AS one").result == [{"one": 1}]

                    assert any(s.token == login.token and s.user == user for s in srv.list_sessions())
                    with pytest.raises(ArcadeDBError) as info:
                        as_user.list_sessions()
                    assert info.value.status == 403

                    with pytest.raises(NotSessionTokenError):
                        srv.logout()
                    as_user.logout()
                    with pytest.raises(ArcadeDBError) as info:
                        as_user.list_databases()
                    assert info.value.status == 401
                    with pytest.raises(ArcadeDBError) as info:
                        as_user.logout()
                    assert info.value.status == 401
            finally:
                srv.drop_user(user)
        finally:
            srv.drop_database(tenant)
            srv.drop_database(other)


def test_api_token_lifecycle(base_url: str, database: str) -> None:
    name = unique("pytoken")
    with root(base_url) as srv:
        created = srv.create_api_token(name, database=database)
        try:
            assert created.token.startswith("at-")
            assert created.token.endswith(created.token_suffix)
            assert (created.name, created.database) == (name, database)
            assert created.expires_at is None
            assert created.expired is False

            listed = {t.name: t for t in srv.list_api_tokens()}
            assert listed[name].token_hash == created.token_hash
            assert listed[name].token_suffix == created.token_suffix

            # A taken name is a 409; the docstring and the README rely on it.
            with pytest.raises(ArcadeDBError) as info:
                srv.create_api_token(name)
            assert info.value.status == 409

            with srv.with_token(created.token) as with_token:
                with_token.list_databases()
                with pytest.raises(NotSessionTokenError):
                    with_token.logout()

                with pytest.raises(ValueError):
                    srv.delete_api_token(created.token)
                srv.delete_api_token(created.token_hash)
                # 404 is not in the contract's list for deleteApiToken (arcadedb#10110); measured here.
                with pytest.raises(ArcadeDBError) as info:
                    srv.delete_api_token(created.token_hash)
                assert info.value.status == 404
                with pytest.raises(ArcadeDBError) as info:
                    with_token.list_databases()
                assert info.value.status == 401
        finally:
            with contextlib.suppress(ArcadeDBError):
                srv.delete_api_token(created.token_hash)


@pytest.mark.asyncio
async def test_async_login_query_logout(base_url: str, database: str) -> None:
    async with AsyncArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        login = await srv.login()
        assert login.user == "root"
        async with srv.with_token(login.token) as session:
            assert database in await session.list_databases()
            await session.logout()
            with pytest.raises(ArcadeDBError) as info:
                await session.list_databases()
            assert info.value.status == 401
