import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer

BASE_URL = "http://db.test"
SESSION = "AS-0000-1111"


def mock_begin(session_id: str = SESSION) -> None:
    respx.post(f"{BASE_URL}/api/v1/begin/mydb").mock(
        return_value=httpx.Response(204, headers={"arcadedb-session-id": session_id})
    )


@respx.mock
def test_commits_on_a_clean_exit_and_threads_the_session_id() -> None:
    mock_begin()
    command = respx.post(f"{BASE_URL}/api/v1/command/mydb").mock(
        return_value=httpx.Response(200, json={"result": [], "limit": 20000, "returned": 0, "truncated": False})
    )
    commit = respx.post(f"{BASE_URL}/api/v1/commit/mydb").mock(return_value=httpx.Response(204))
    rollback = respx.post(f"{BASE_URL}/api/v1/rollback/mydb").mock(return_value=httpx.Response(204))

    with ArcadeDBServer(base_url=BASE_URL) as srv, srv.db("mydb").transaction() as tx:
        tx.command(language="sql", command="INSERT INTO Person SET name = 'Ada'")

    assert command.calls.last.request.headers["arcadedb-session-id"] == SESSION
    assert commit.called
    assert not rollback.called


@respx.mock
def test_calls_outside_the_handle_do_not_join_the_transaction() -> None:
    mock_begin()
    command = respx.post(f"{BASE_URL}/api/v1/command/mydb").mock(
        return_value=httpx.Response(200, json={"result": [], "limit": 20000, "returned": 0, "truncated": False})
    )
    respx.post(f"{BASE_URL}/api/v1/commit/mydb").mock(return_value=httpx.Response(204))

    with ArcadeDBServer(base_url=BASE_URL) as srv:
        db = srv.db("mydb")
        with db.transaction():
            db.command(language="sql", command="INSERT INTO P SET n = 1")

    assert "arcadedb-session-id" not in command.calls.last.request.headers


@respx.mock
def test_rolls_back_and_reraises_when_the_body_raises() -> None:
    mock_begin()
    rollback = respx.post(f"{BASE_URL}/api/v1/rollback/mydb").mock(return_value=httpx.Response(204))
    commit = respx.post(f"{BASE_URL}/api/v1/commit/mydb").mock(return_value=httpx.Response(204))

    sentinel = RuntimeError("body failed")
    with (
        ArcadeDBServer(base_url=BASE_URL) as srv,
        pytest.raises(RuntimeError) as caught,
        srv.db("mydb").transaction(),
    ):
        raise sentinel

    assert caught.value is sentinel
    assert rollback.called
    assert not commit.called


@respx.mock
def test_a_failed_rollback_is_attached_as_cause_not_substituted() -> None:
    mock_begin()
    respx.post(f"{BASE_URL}/api/v1/rollback/mydb").mock(
        return_value=httpx.Response(500, json={"error": "rollback failed"})
    )

    sentinel = RuntimeError("body failed")
    with (
        ArcadeDBServer(base_url=BASE_URL) as srv,
        pytest.raises(RuntimeError) as caught,
        srv.db("mydb").transaction(),
    ):
        raise sentinel

    # The body's error is what the caller asked about, so it wins; the rollback
    # failure rides along rather than replacing it.
    assert caught.value is sentinel
    assert isinstance(caught.value.__cause__, ArcadeDBError)


@respx.mock
def test_an_existing_cause_is_never_overwritten() -> None:
    mock_begin()
    respx.post(f"{BASE_URL}/api/v1/rollback/mydb").mock(
        return_value=httpx.Response(500, json={"error": "rollback failed"})
    )

    original_cause = ValueError("the real reason")
    with (
        ArcadeDBServer(base_url=BASE_URL) as srv,
        pytest.raises(RuntimeError) as caught,
        srv.db("mydb").transaction(),
    ):
        raise RuntimeError("body failed") from original_cause

    assert caught.value.__cause__ is original_cause


@respx.mock
def test_a_failed_commit_still_issues_a_rollback_and_raises_the_commit_error() -> None:
    mock_begin()
    respx.post(f"{BASE_URL}/api/v1/commit/mydb").mock(return_value=httpx.Response(500, json={"error": "commit failed"}))
    rollback = respx.post(f"{BASE_URL}/api/v1/rollback/mydb").mock(return_value=httpx.Response(204))

    with (
        ArcadeDBServer(base_url=BASE_URL) as srv,
        pytest.raises(ArcadeDBError) as caught,
        srv.db("mydb").transaction(),
    ):
        pass

    # Without the best-effort rollback the session leaks server-side until
    # arcadedb.server.httpTxExpireTimeout reaps it.
    assert caught.value.error == "commit failed"
    assert rollback.called


@respx.mock
def test_a_rollback_failing_after_a_failed_commit_is_swallowed() -> None:
    mock_begin()
    respx.post(f"{BASE_URL}/api/v1/commit/mydb").mock(return_value=httpx.Response(500, json={"error": "commit failed"}))
    respx.post(f"{BASE_URL}/api/v1/rollback/mydb").mock(
        return_value=httpx.Response(500, json={"error": "rollback failed too"})
    )

    with (
        ArcadeDBServer(base_url=BASE_URL) as srv,
        pytest.raises(ArcadeDBError) as caught,
        srv.db("mydb").transaction(),
    ):
        pass

    assert caught.value.error == "commit failed"


@respx.mock
def test_begin_raises_when_the_server_returns_no_session_id() -> None:
    respx.post(f"{BASE_URL}/api/v1/begin/mydb").mock(return_value=httpx.Response(204))

    with (
        ArcadeDBServer(base_url=BASE_URL) as srv,
        pytest.raises(ArcadeDBError) as caught,
        srv.db("mydb").transaction(),
    ):
        pass

    assert "session id" in str(caught.value)
