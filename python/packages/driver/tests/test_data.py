import json
from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, basic_auth

BASE_URL = "http://db.test"


def server() -> ArcadeDBServer:
    return ArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "playwithdata"))


@respx.mock
def test_query_returns_the_whole_envelope() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(
            200,
            json={"result": [{"name": "Ada"}], "limit": 100, "returned": 1, "truncated": False},
        )
    )
    with server() as srv:
        env = srv.db("mydb").query(language="sql", command="SELECT FROM Person")

    assert env.result == [{"name": "Ada"}]
    assert env.limit == 100
    assert env.returned == 1
    assert env.truncated is False
    assert route.calls.last.request.headers["Authorization"].startswith("Basic ")


@respx.mock
def test_query_defaults_an_omitted_result_to_empty() -> None:
    # This test used to send `{}` and assert that all four envelope fields defaulted.
    # That premise died in 26.10.1-SNAPSHOT: QueryResponse gained a `required` list
    # naming limit/returned/truncated, so the generated model pops them with no
    # fallback and `{}` now raises KeyError before the envelope is ever built.
    #
    # The change is not a client regression. A real 26.10.1-SNAPSHOT server answers
    # every query with all three present - `{"result":[],"limit":20000,"returned":0,
    # "truncated":false}` - so the contract tightened onto behaviour the server
    # already had. `result` stayed optional, and that one default is still real.
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(200, json={"limit": 20000, "returned": 0, "truncated": False})
    )
    with server() as srv:
        env = srv.db("mydb").query(language="sql", command="SELECT 1")

    assert env.result == []
    assert env.limit == 20000
    assert env.returned == 0
    assert env.truncated is False


@respx.mock
def test_query_rejects_a_response_missing_a_now_required_field() -> None:
    # The other half of the same change, pinned so a future contract that drops
    # `required` again is noticed here rather than in a caller's traceback.
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(return_value=httpx.Response(200, json={}))
    with server() as srv, pytest.raises(KeyError):
        srv.db("mydb").query(language="sql", command="SELECT 1")


@respx.mock
def test_query_sends_params_and_limit_only_when_supplied() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(200, json={"result": [], "limit": 20000, "returned": 0, "truncated": False})
    )
    with server() as srv:
        srv.db("mydb").query(language="sql", command="SELECT FROM P WHERE age > :min", params={"min": 18}, limit=5)
        srv.db("mydb").query(language="sql", command="SELECT 1")

    with_opts: dict[str, Any] = json.loads(route.calls[0].request.read())
    without: dict[str, Any] = json.loads(route.calls[1].request.read())
    assert with_opts["params"] == {"min": 18}
    assert with_opts["limit"] == 5
    assert "params" not in without
    assert "limit" not in without


@respx.mock
def test_command_sends_language_as_a_required_field() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/command/mydb").mock(
        return_value=httpx.Response(200, json={"result": [], "limit": 20000, "returned": 0, "truncated": False})
    )
    with server() as srv:
        srv.db("mydb").command(language="sql", command="INSERT INTO Person SET name = 'Ada'")

    body = json.loads(route.calls.last.request.read())
    assert body["language"] == "sql"
    assert body["command"] == "INSERT INTO Person SET name = 'Ada'"


@respx.mock
def test_a_non_2xx_raises_arcadedb_error_with_the_servers_detail() -> None:
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(
            400,
            json={"error": "Invalid query", "detail": "line 1:8"},
            headers={"X-Request-Id": "req-77"},
        )
    )
    with server() as srv, pytest.raises(ArcadeDBError) as caught:
        srv.db("mydb").query(language="sql", command="SELCT 1")

    assert caught.value.status == 400
    assert caught.value.error == "Invalid query"
    assert caught.value.detail == "line 1:8"
    assert caught.value.request_id == "req-77"


@respx.mock
def test_raw_does_not_raise() -> None:
    # The deliberate asymmetry: the facade throws, `.raw` never does.
    from arcadedb_driver._generated.api.database import list_databases

    respx.get(f"{BASE_URL}/api/v1/databases").mock(return_value=httpx.Response(500, json={"error": "boom"}))
    with server() as srv:
        response = list_databases.sync_detailed(client=srv.raw)

    assert response.status_code == 500


@respx.mock
def test_query_rejects_a_graph_shaped_result_instead_of_mangling_it() -> None:
    # 26.10.1-SNAPSHOT widened QueryResponse.result from an array into a union: an
    # array under the default `record` serializer, and a {vertices, edges, records}
    # object under the two graph serializers. `QueryEnvelope.result` is a list of
    # rows and cannot represent the second shape.
    #
    # This client never sends `serializer`, so the server always picks `record` and
    # the graph arm is unreachable through `query()`/`command()`. The check exists
    # because "unreachable" is a property of today's request builder, not of the
    # contract - the day `serializer` becomes a parameter, this must fail loudly
    # rather than iterate an attrs object and raise something unreadable.
    respx.post(f"{BASE_URL}/api/v1/query/mydb").mock(
        return_value=httpx.Response(
            200,
            json={"result": {"vertices": [], "edges": []}, "limit": 100, "returned": 0, "truncated": False},
        )
    )
    # ArcadeDBError, not a builtin: "200 in a shape this client cannot represent" is an
    # ArcadeDBError everywhere else in this package, and the README tells callers that
    # `except ArcadeDBError` around query()/command() is enough. The TypeScript sibling
    # throws ArcadeDBError for the identical guard.
    with server() as srv, pytest.raises(ArcadeDBError) as caught:
        srv.db("mydb").query(language="sql", command="SELECT FROM Person")

    assert caught.value.status == 200
    assert "serializer" in str(caught.value.detail)
