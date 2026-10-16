"""List and terminate running work, and `progress` (issue #124). Bodies are copied from a live
26.11.1-SNAPSHOT server."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import (
    ArcadeDBError,
    ArcadeDBServer,
    AsyncArcadeDBServer,
    OpenTransaction,
    RunningQuery,
    TerminateResult,
    is_query_terminated,
)

BASE_URL = "http://db.test"
SERVER = f"{BASE_URL}/api/v1/server"

QUERY_ROW = {
    "id": "q5-1f6d4564",
    "database": "p",
    "user": "root",
    "protocol": "http",
    "language": "sql",
    "text": "SLEEP 20000",
    "startedAt": 1792137065792,
    "elapsedMs": 1507,
    "terminating": False,
    "sessionId": "AS-1",
    "tag": "tagA",
    "clientAddress": "/192.168.65.1:18259",
    "server": "ArcadeDB_0",
}
TERMINATED_409 = {
    "error": "Query terminated",
    "requestId": "ee5d",
    "exception": "com.arcadedb.exception.QueryTerminatedException",
    "detail": "the commit has been terminated (query q5-1f6d4564, terminated by root)",
}


def sent(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


@respx.mock
@pytest.mark.parametrize(
    ("kwargs", "command"),
    [
        ({}, "list queries"),
        ({"database": "p"}, "list queries database p"),
        ({"tag": "a b"}, "list queries tag a b"),
        ({"database": "p", "tag": "nightly"}, "list queries database p tag nightly"),
        ({"database": "", "tag": ""}, "list queries"),
    ],
)
def test_list_queries_sends_filters_and_decodes(kwargs: dict[str, str], command: str) -> None:
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": [QUERY_ROW]}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        got = srv.list_queries(**kwargs)
    assert sent(route) == {"command": command, "language": "sql"}
    assert got == [
        RunningQuery(
            id="q5-1f6d4564",
            database="p",
            user="root",
            protocol="http",
            language="sql",
            text="SLEEP 20000",
            started_at=datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=1792137065792),
            elapsed=timedelta(milliseconds=1507),
            terminating=False,
            session_id="AS-1",
            tag="tagA",
            client_address="/192.168.65.1:18259",
            server="ArcadeDB_0",
        )
    ]


@respx.mock
def test_a_statement_outside_a_session_has_no_session_or_tag() -> None:
    row = {k: v for k, v in QUERY_ROW.items() if k not in ("sessionId", "tag")}
    respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": [row]}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        (got,) = srv.list_queries()
    assert got.session_id is None and got.tag is None


@respx.mock
@pytest.mark.parametrize("status", ["terminated", "completed", "terminating", "not found"])
def test_terminate_query_every_status(status: str) -> None:
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": {"id": "q6", "status": status}}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        got = srv.terminate_query("q6")
    assert sent(route) == {"command": "terminate query q6", "language": "sql"}
    assert got == TerminateResult(id="q6", status=status)  # type: ignore[arg-type]


@respx.mock
def test_terminate_query_inside_a_session() -> None:
    body = {"result": {"id": "q6", "status": "terminating", "sessionId": "AS-262f", "sessionOpen": True}}
    respx.post(SERVER).mock(return_value=httpx.Response(200, json=body))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        got = srv.terminate_query("q6")
    assert got == TerminateResult(id="q6", status="terminating", session_id="AS-262f", session_open=True)


@respx.mock
@pytest.mark.parametrize(
    ("wait", "expected"),
    [
        (None, None),
        (timedelta(0), None),
        (timedelta(seconds=-1), None),
        (timedelta(seconds=3), 3000),
        (timedelta(microseconds=1), 1),
        (timedelta(milliseconds=1.5), 2),
    ],
)
def test_terminate_sends_wait_in_milliseconds(wait: timedelta | None, expected: int | None) -> None:
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": []}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        assert srv.terminate_queries_by_tag("t", wait=wait) == []
    body = sent(route)
    assert body.get("wait") == expected and ("wait" in body) == (expected is not None)
    assert body["command"] == "terminate queries tag t"


@respx.mock
def test_terminate_queries_by_tag_decodes_each() -> None:
    body = {"result": [{"id": "q1", "status": "terminated"}, {"id": "q2", "status": "completed"}]}
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json=body))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        got = srv.terminate_queries_by_tag('it\'s "q"', wait=timedelta(seconds=1))
    assert sent(route) == {"command": 'terminate queries tag it\'s "q"', "language": "sql", "wait": 1000}
    assert [r.status for r in got] == ["terminated", "completed"]


@respx.mock
def test_list_and_terminate_transactions() -> None:
    row = {
        "id": "AS-4c9d",
        "user": "root",
        "database": "p",
        "idleMs": 1522,
        "busy": True,
        "runningQueries": ["q16"],
        "server": "ArcadeDB_0",
    }
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": [row]}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        txs = srv.list_transactions()
        assert sent(route)["command"] == "list transactions"
        assert txs == [
            OpenTransaction(
                id="AS-4c9d",
                user="root",
                database="p",
                idle=timedelta(milliseconds=1522),
                busy=True,
                running_queries=["q16"],
                server="ArcadeDB_0",
            )
        ]
        route.mock(return_value=httpx.Response(200, json={"result": {"id": "AS-4c9d", "status": "terminated"}}))
        assert srv.terminate_transaction("AS-4c9d") == TerminateResult(id="AS-4c9d", status="terminated")
        assert sent(route) == {"command": "terminate transaction AS-4c9d", "language": "sql"}


@respx.mock
@pytest.mark.parametrize(
    "call",
    [
        lambda srv: srv.terminate_query(""),
        lambda srv: srv.terminate_query("q1 q2"),
        lambda srv: srv.terminate_queries_by_tag(""),
        lambda srv: srv.terminate_queries_by_tag(" t"),
        lambda srv: srv.list_queries(tag="t\n"),
        lambda srv: srv.list_queries(database="a\tb"),
        lambda srv: srv.terminate_transaction(""),
        lambda srv: srv.terminate_transaction("AS-1 x"),
        lambda srv: srv.terminate_query("q1\x01"),
        lambda srv: srv.terminate_queries_by_tag("t\x00"),
        lambda srv: srv.list_queries(database="a\x1cb"),
    ],
)
def test_values_the_server_would_split_or_trim_are_refused_unsent(call: Any) -> None:
    route = respx.post(SERVER)
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ValueError):
        call(srv)
    assert not route.called


@respx.mock
def test_errors_and_bodies_without_a_result() -> None:
    route = respx.post(SERVER).mock(
        return_value=httpx.Response(400, json={"error": "Server command not valid", "detail": "Syntax"})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            srv.terminate_query("q1")
        assert caught.value.status == 400
        for response in (httpx.Response(200), httpx.Response(200, json={}), httpx.Response(200, json={"result": None})):
            route.mock(return_value=response)
            with pytest.raises(ValueError, match="no result"):
                srv.list_transactions()


@respx.mock
def test_is_query_terminated() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/command/p").mock(return_value=httpx.Response(409, json=TERMINATED_409))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(ArcadeDBError) as caught:
            srv.db("p").command(language="sql", command="SLEEP 20000")
        assert is_query_terminated(caught.value)

        in_flight = {"error": "Still in flight", "exception": "com.arcadedb.server.http.RequestStillInFlightException"}
        route.mock(return_value=httpx.Response(409, json=in_flight))
        with pytest.raises(ArcadeDBError) as caught:
            srv.db("p").command(language="sql", command="SELECT 1")
        assert not is_query_terminated(caught.value)
    assert not is_query_terminated(ValueError("Query terminated"))


PROGRESS = {
    "result": [
        {
            "database": "p",
            "done": 40,
            "elapsedMs": 1200,
            "id": 7,
            "operation": "CHECK DATABASE",
            "percentage": 40,
            "startedOn": 1792137065792,
            "stepIndex": 1,
            "stepName": "pages",
            "total": 100,
            "totalSteps": 3,
        }
    ]
}


@respx.mock
def test_progress() -> None:
    route = respx.get(f"{BASE_URL}/api/v1/progress/p").mock(return_value=httpx.Response(200, json=PROGRESS))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        got = srv.db("p").progress()
        assert got.result[0].operation == "CHECK DATABASE" and got.result[0].percentage == 40
        route.mock(return_value=httpx.Response(403, json={"error": "Security error"}))
        with pytest.raises(ArcadeDBError) as caught:
            srv.db("p").progress()
        assert caught.value.status == 403


@pytest.mark.asyncio
@respx.mock
async def test_async_twins() -> None:
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": [QUERY_ROW]}))
    respx.get(f"{BASE_URL}/api/v1/progress/p").mock(return_value=httpx.Response(200, json={"result": []}))
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        assert (await srv.list_queries(tag="tagA"))[0].id == "q5-1f6d4564"
        assert sent(route)["command"] == "list queries tag tagA"

        route.mock(return_value=httpx.Response(200, json={"result": {"id": "q5", "status": "completed"}}))
        assert (await srv.terminate_query("q5", wait=timedelta(seconds=2))).status == "completed"
        assert sent(route) == {"command": "terminate query q5", "language": "sql", "wait": 2000}

        route.mock(return_value=httpx.Response(200, json={"result": [{"id": "q5", "status": "terminated"}]}))
        assert (await srv.terminate_queries_by_tag("tagA"))[0].status == "terminated"

        route.mock(return_value=httpx.Response(200, json={"result": []}))
        assert await srv.list_transactions() == []

        route.mock(return_value=httpx.Response(200, json={"result": {"id": "AS-1", "status": "not found"}}))
        assert (await srv.terminate_transaction("AS-1")).status == "not found"

        with pytest.raises(ValueError):
            await srv.terminate_query("a b")

        assert (await srv.db("p").progress()).result == []


@respx.mock
def test_a_no_break_space_is_not_refused() -> None:
    # The rule is Java's trim: at or below U+0020. A no-break space is not white space to the server.
    route = respx.post(SERVER).mock(return_value=httpx.Response(200, json={"result": []}))
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.terminate_queries_by_tag("t\u00a0")
    assert sent(route)["command"] == "terminate queries tag t\u00a0"
