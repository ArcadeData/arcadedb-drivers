import json as _json

import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer, basic_auth
from arcadedb_driver._generated.types import Unset

BASE_URL = "http://db.test"


def server() -> ArcadeDBServer:
    return ArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "playwithdata"))


def async_server() -> AsyncArcadeDBServer:
    return AsyncArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "playwithdata"))


@respx.mock
def test_search_posts_the_request_body() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/mydb/search").mock(
        return_value=httpx.Response(200, json={"results": [], "count": 0, "truncated": False})
    )
    with server() as srv:
        srv.db("mydb").vector.search(index_name="v_idx", query_vector=[0.1, 0.2], k=5)

    sent = route.calls.last.request
    assert sent.method == "POST"
    assert _json.loads(sent.content) == {"indexName": "v_idx", "queryVector": [0.1, 0.2], "k": 5}


@respx.mock
def test_search_returns_the_whole_response_not_just_results() -> None:
    # D-M5-2. A caller reading only `results` works off a partial answer when
    # `truncated` is true, without being told - the hazard QueryEnvelope documents.
    respx.post(f"{BASE_URL}/api/v1/vector/mydb/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [{"@rid": "#1:0", "score": 0.91}],
                "count": 1,
                "truncated": True,
                "scoring": "cosine",
                "indexName": "v_idx",
            },
        )
    )
    with server() as srv:
        result = srv.db("mydb").vector.search(index_name="v_idx", query_vector=[0.1])

    assert result.count == 1
    assert result.truncated is True
    assert result.scoring == "cosine"
    # `results` stays the generated per-element model, not stripped down to a plain
    # dict - matching "returns the parsed response model unaltered". `@rid` is not a
    # field the contract names on the item (only `rid`, `score`, `distance`,
    # `properties` are), so it round-trips through `additional_properties` rather
    # than a typed attribute; `.to_dict()` is what re-flattens it for comparison.
    results = result.results
    assert not isinstance(results, Unset)
    assert [item.to_dict() for item in results] == [{"@rid": "#1:0", "score": 0.91}]


@respx.mock
def test_search_percent_encodes_the_database_name() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/od%2Fdb/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    with server() as srv:
        srv.db("od/db").vector.search(index_name="v_idx", query_vector=[0.1])

    assert route.called


@respx.mock
def test_search_raises_arcadedb_error_with_a_request_id() -> None:
    respx.post(f"{BASE_URL}/api/v1/vector/mydb/search").mock(
        return_value=httpx.Response(400, json={"error": "no such index"}, headers={"X-Request-Id": "req-7"})
    )
    with server() as srv, pytest.raises(ArcadeDBError) as caught:
        srv.db("mydb").vector.search(index_name="nope", query_vector=[0.1])

    assert caught.value.status == 400
    assert caught.value.request_id == "req-7"


@respx.mock
def test_hybrid_posts_to_the_hybrid_endpoint() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/mydb/hybrid").mock(
        return_value=httpx.Response(200, json={"results": [], "count": 0, "fused": True})
    )
    with server() as srv:
        result = srv.db("mydb").vector.hybrid(vector_index_name="v_idx", query_vector=[0.1], fulltext_query="cat")

    assert route.called
    assert result.fused is True


@respx.mock
def test_fulltext_posts_to_the_fulltext_endpoint() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/mydb/fulltext").mock(
        return_value=httpx.Response(200, json={"results": [{"@rid": "#2:1"}], "count": 1, "similarity": "bm25"})
    )
    with server() as srv:
        result = srv.db("mydb").vector.fulltext(query_text="cat")

    assert route.called
    assert result.count == 1
    assert result.similarity == "bm25"


@respx.mock
@pytest.mark.asyncio
async def test_async_search_returns_the_whole_response() -> None:
    respx.post(f"{BASE_URL}/api/v1/vector/mydb/search").mock(
        return_value=httpx.Response(200, json={"results": [], "count": 0, "truncated": True})
    )
    async with async_server() as srv:
        result = await srv.db("mydb").vector.search(index_name="v_idx", query_vector=[0.1])

    assert result.truncated is True


@respx.mock
@pytest.mark.asyncio
async def test_async_hybrid_and_fulltext_reach_their_endpoints() -> None:
    hybrid = respx.post(f"{BASE_URL}/api/v1/vector/mydb/hybrid").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    fulltext = respx.post(f"{BASE_URL}/api/v1/vector/mydb/fulltext").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    async with async_server() as srv:
        await srv.db("mydb").vector.hybrid(vector_index_name="v_idx", query_vector=[0.1])
        await srv.db("mydb").vector.fulltext(query_text="cat")

    assert hybrid.called and fulltext.called
