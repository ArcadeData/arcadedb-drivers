import json as _json
from typing import Any

import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer, basic_auth
from arcadedb_driver._generated.models.full_text_search_response_similarity import (
    FullTextSearchResponseSimilarity,
)
from arcadedb_driver._generated.models.hybrid_search_request_fusion_strategy import (
    HybridSearchRequestFusionStrategy,
)
from arcadedb_driver._generated.types import Unset

BASE_URL = "http://db.test"


def server() -> ArcadeDBServer:
    return ArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "playwithdata"))


def async_server() -> AsyncArcadeDBServer:
    return AsyncArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "playwithdata"))


# The three vector response schemas gained a `required` list in the 26.10.1-SNAPSHOT refresh -
# they had none before, so every field was optional and these fixtures carried only what the
# test asserted on. The generated models' `from_dict` now raises `KeyError` for a missing
# required field, which is what made seven tests here fail on the refresh.
#
# The contract is right and the fixtures were thin: `python/e2e/test_data_plane.py`'s vector cases
# (`test_vector_search_returns_a_non_empty_nearest_first_result` and its siblings) pass against a
# live 26.10.1-SNAPSHOT container, so the server really does send all of them. That check mattered
# - a field declared required and not always sent would have been a contract defect breaking every
# real call, the third of its kind in this package (see the module docstring in facade/vector.py).
#
# Each helper returns a complete body and takes overrides, so a test states only the fields it
# cares about and the next required field added upstream is one edit here rather than seven.
#
# `_hit` is the shape the server ACTUALLY sends, captured from a live container:
#
#     {"rid": "#1:2", "properties": {"@rid": ..., "@type": ..., <the record's own fields>},
#      "distance": 0.45227742}
#
# The fixtures here previously modelled a hit as `{"@rid": ..., "score": ...}` - an id spelled
# with an `@` and no `properties` wrapper - which the server has never sent. Nothing caught it
# because every field was optional until the refresh: `@rid` landed in `additional_properties`
# and the absent `rid`/`properties` cost nothing. The new `required` lists turned a test that
# asserted fiction into a test that fails, which is the good outcome.


def _hit(rid: str = "#1:0", **overrides: Any) -> dict[str, Any]:
    """One result row: `rid` (no `@`), a `properties` object carrying the record, and whichever
    of `distance`/`score` the search produced. `rid` and `properties` are both required."""
    return {"rid": rid, "properties": {"@rid": rid, "@type": "VectorItem", "name": "blue-car"}, **overrides}


def _vector_body(**overrides: Any) -> dict[str, Any]:
    """A complete `VectorSearchResponse`: candidateLimit, count, indexName, results, scoring,
    sparse, truncated."""
    return {
        "results": [],
        "count": 0,
        "indexName": "v_idx",
        "candidateLimit": 100,
        "scoring": "cosine",
        "sparse": False,
        "truncated": False,
        **overrides,
    }


def _hybrid_body(**overrides: Any) -> dict[str, Any]:
    """A complete `HybridSearchResponse`: count, fused, legs, results, scoring, sparse,
    truncated, vectorIndexName. `legs` is now a typed object (per-leg accounting) rather than the
    bare `object` it was before the refresh; an empty one is legal and says no leg reported."""
    return {
        "results": [],
        "count": 0,
        "fused": True,
        "legs": {"vector": {"count": 0}},
        "scoring": "cosine",
        "sparse": False,
        "truncated": False,
        "vectorIndexName": "v_idx",
        **overrides,
    }


def _fulltext_body(**overrides: Any) -> dict[str, Any]:
    """A complete `FullTextSearchResponse`: count, indexName, results, similarity.

    `similarity` is "BM25", not "bm25". This fixture said lowercase from the day it
    was written and nothing caught it, because the contract typed the field as a free
    string; 26.10.1-SNAPSHOT turned it into an enum of BM25/CLASSIC and the stale
    casing became a ValueError. The server has always emitted uppercase - see
    ArcadeData/arcadedb's `FullTextIndexMetadata.SIMILARITY_BM25` and the assertion in
    `MCPServerPluginTest` - so this is the fixture catching up with the server, not
    the contract changing what the server sends.
    """
    return {
        "results": [],
        "count": 0,
        "indexName": "ft_idx",
        "similarity": "BM25",
        **overrides,
    }


@respx.mock
def test_search_posts_the_request_body() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/mydb/search").mock(
        return_value=httpx.Response(200, json=_vector_body())
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
            json=_vector_body(
                results=[_hit(score=0.91)],
                count=1,
                truncated=True,
            ),
        )
    )
    with server() as srv:
        result = srv.db("mydb").vector.search(index_name="v_idx", query_vector=[0.1])

    assert result.count == 1
    assert result.truncated is True
    assert result.scoring == "cosine"
    # `results` stays the generated per-element model, not stripped down to a plain
    # dict - matching "returns the parsed response model unaltered". `.to_dict()` is
    # what flattens it back for comparison. Note the row's id is `rid`; the `@rid`
    # inside `properties` is the record's own, which is a different thing - the
    # record carries `@rid`/`@type`/`@cat` alongside its real fields.
    results = result.results
    assert not isinstance(results, Unset)
    assert [item.to_dict() for item in results] == [_hit(score=0.91)]


@respx.mock
def test_search_percent_encodes_the_database_name() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/od%2Fdb/search").mock(
        return_value=httpx.Response(200, json=_vector_body())
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
        return_value=httpx.Response(200, json=_hybrid_body())
    )
    with server() as srv:
        result = srv.db("mydb").vector.hybrid(vector_index_name="v_idx", query_vector=[0.1], fulltext_query="cat")

    assert route.called
    assert result.fused is True


@respx.mock
def test_fulltext_posts_to_the_fulltext_endpoint() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/mydb/fulltext").mock(
        return_value=httpx.Response(200, json=_fulltext_body(results=[_hit("#2:1")], count=1))
    )
    with server() as srv:
        result = srv.db("mydb").vector.fulltext(query_text="cat")

    assert route.called
    assert result.count == 1
    assert result.similarity is FullTextSearchResponseSimilarity.BM25


@respx.mock
@pytest.mark.asyncio
async def test_async_search_returns_the_whole_response() -> None:
    respx.post(f"{BASE_URL}/api/v1/vector/mydb/search").mock(
        return_value=httpx.Response(200, json=_vector_body(truncated=True))
    )
    async with async_server() as srv:
        result = await srv.db("mydb").vector.search(index_name="v_idx", query_vector=[0.1])

    assert result.truncated is True


@respx.mock
@pytest.mark.asyncio
async def test_async_hybrid_and_fulltext_reach_their_endpoints() -> None:
    hybrid = respx.post(f"{BASE_URL}/api/v1/vector/mydb/hybrid").mock(
        return_value=httpx.Response(200, json=_hybrid_body())
    )
    fulltext = respx.post(f"{BASE_URL}/api/v1/vector/mydb/fulltext").mock(
        return_value=httpx.Response(200, json=_fulltext_body())
    )
    async with async_server() as srv:
        await srv.db("mydb").vector.hybrid(vector_index_name="v_idx", query_vector=[0.1])
        await srv.db("mydb").vector.fulltext(query_text="cat")

    assert hybrid.called and fulltext.called


@respx.mock
def test_hybrid_sends_the_fusion_strategy_as_its_contract_value() -> None:
    # 26.10.1-SNAPSHOT narrowed `fusionStrategy` from a free string to an enum of
    # RRF/DBSF/LINEAR, and `openapi-python-client` turned that into a real Enum -
    # so `hybrid()` now takes HybridSearchRequestFusionStrategy, exactly as
    # `@arcadedb/driver` takes the "RRF" | "DBSF" | "LINEAR" union that
    # `openapi-typescript` emits from the same schema.
    #
    # The assertion is about the wire, not the annotation: a `str, Enum` member
    # must serialize as its bare value, never as "HybridSearchRequestFusionStrategy.RRF".
    route = respx.post(f"{BASE_URL}/api/v1/vector/mydb/hybrid").mock(
        return_value=httpx.Response(200, json=_hybrid_body())
    )
    with server() as srv:
        srv.db("mydb").vector.hybrid(
            vector_index_name="v_idx",
            query_vector=[0.1],
            fulltext_query="cat",
            fusion_strategy=HybridSearchRequestFusionStrategy.RRF,
        )

    body: dict[str, Any] = _json.loads(route.calls.last.request.read())
    assert body["fusionStrategy"] == "RRF"
