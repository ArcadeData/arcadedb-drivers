import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, AsyncArcadeDBServer

BASE_URL = "http://db.test"
SESSION = "AS-0000-2222"

pytestmark = pytest.mark.asyncio


@respx.mock
async def test_query_returns_the_whole_envelope() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(
            200, json={"result": [{"name": "Ada"}], "limit": 100, "returned": 1, "truncated": True}
        )
    )
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        env = await srv.db("mydb").query(language="sql", command="SELECT FROM Person")

    assert env.result == [{"name": "Ada"}]
    assert env.truncated is True


@respx.mock
@pytest.mark.parametrize("endpoint", ["query", "command"])
async def test_an_explain_answer_carries_the_plan_and_no_rows(endpoint: str) -> None:
    plan = {"type": "QueryExecutionPlan", "steps": [{"name": "FetchFromTypeExecutionStep"}]}
    respx.post(f"{BASE_URL}/api/v1/{endpoint}/mydb").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": [],
                "limit": 20000,
                "returned": 0,
                "truncated": False,
                "explain": "+ FETCH FROM TYPE Person",
                "explainPlan": plan,
            },
        )
    )
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        db = srv.db("mydb")
        call = db.query if endpoint == "query" else db.command
        env = await call(language="sql", command="EXPLAIN SELECT FROM Person")

    assert env.explain == "+ FETCH FROM TYPE Person"
    assert env.explain_plan == plan
    assert env.result == []
    assert env.returned == 0


@respx.mock
async def test_an_ordinary_answer_has_no_plan() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(200, json={"result": [], "limit": 100, "returned": 0, "truncated": False})
    )
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        env = await srv.db("mydb").query(language="sql", command="SELECT FROM Person")

    assert env.explain is None
    assert env.explain_plan is None


@respx.mock
async def test_a_non_2xx_raises_arcadedb_error() -> None:
    respx.post(f"{BASE_URL}/api/v1/command/mydb").mock(return_value=httpx.Response(400, json={"error": "Invalid"}))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            await srv.db("mydb").command(language="sql", command="NOPE")

    assert caught.value.status == 400


@respx.mock
async def test_list_databases_and_ready() -> None:
    respx.get(f"{BASE_URL}/api/v1/databases").mock(
        return_value=httpx.Response(200, json={"result": ["one"], "user": "root", "version": "26.10.1"})
    )
    respx.get(f"{BASE_URL}/api/v1/ready").mock(return_value=httpx.Response(503))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        assert await srv.list_databases() == ["one"]
        assert await srv.ready() is False


@respx.mock
async def test_commits_on_a_clean_exit() -> None:
    respx.post(f"{BASE_URL}/api/v1/begin/mydb").mock(
        return_value=httpx.Response(204, headers={"arcadedb-session-id": SESSION})
    )
    command = respx.post(f"{BASE_URL}/api/v1/command/mydb").mock(
        return_value=httpx.Response(200, json={"result": [], "limit": 20000, "returned": 0, "truncated": False})
    )
    commit = respx.post(f"{BASE_URL}/api/v1/commit/mydb").mock(return_value=httpx.Response(204))

    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv, srv.db("mydb").transaction() as tx:
        await tx.command(language="sql", command="INSERT INTO P SET n = 1")

    assert command.calls.last.request.headers["arcadedb-session-id"] == SESSION
    assert commit.called


@respx.mock
async def test_a_failed_rollback_is_attached_as_cause_not_substituted() -> None:
    respx.post(f"{BASE_URL}/api/v1/begin/mydb").mock(
        return_value=httpx.Response(204, headers={"arcadedb-session-id": SESSION})
    )
    respx.post(f"{BASE_URL}/api/v1/rollback/mydb").mock(
        return_value=httpx.Response(500, json={"error": "rollback failed"})
    )

    sentinel = RuntimeError("body failed")
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(RuntimeError) as caught:
            async with srv.db("mydb").transaction():
                raise sentinel

    assert caught.value is sentinel
    assert isinstance(caught.value.__cause__, ArcadeDBError)


@respx.mock
async def test_a_failed_commit_still_issues_a_rollback() -> None:
    respx.post(f"{BASE_URL}/api/v1/begin/mydb").mock(
        return_value=httpx.Response(204, headers={"arcadedb-session-id": SESSION})
    )
    respx.post(f"{BASE_URL}/api/v1/commit/mydb").mock(return_value=httpx.Response(500, json={"error": "commit failed"}))
    rollback = respx.post(f"{BASE_URL}/api/v1/rollback/mydb").mock(return_value=httpx.Response(204))

    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            async with srv.db("mydb").transaction():
                pass

    assert caught.value.error == "commit failed"
    assert rollback.called
