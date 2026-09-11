"""End-to-end tests against a real ArcadeDB server. Requires Docker."""

from __future__ import annotations

import pytest
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer, basic_auth

from .conftest import ROOT_PASSWORD


def test_sync_round_trip(base_url: str, database: str) -> None:
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        assert srv.ready() is True
        assert database in srv.list_databases()
        assert srv.exists(database) is True

        db = srv.db(database)
        db.command(language="sql", command="CREATE VERTEX TYPE PersonSync IF NOT EXISTS")
        db.command(language="sql", command="INSERT INTO PersonSync SET name = 'Ada', age = 36")

        env = db.query(
            language="sql",
            command="SELECT FROM PersonSync WHERE age > :min",
            params={"min": 18},
        )
        assert [row["name"] for row in env.result] == ["Ada"]
        assert env.truncated is False


def test_a_transaction_commits(base_url: str, database: str) -> None:
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        db.command(language="sql", command="CREATE VERTEX TYPE TxCommit IF NOT EXISTS")

        with db.transaction() as tx:
            tx.command(language="sql", command="INSERT INTO TxCommit SET n = 1")

        env = db.query(language="sql", command="SELECT count(*) AS c FROM TxCommit")
        assert env.result[0]["c"] == 1


def test_a_transaction_rolls_back_on_an_exception(base_url: str, database: str) -> None:
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        db.command(language="sql", command="CREATE VERTEX TYPE TxRollback IF NOT EXISTS")

        with pytest.raises(RuntimeError), db.transaction() as tx:
            tx.command(language="sql", command="INSERT INTO TxRollback SET n = 1")
            raise RuntimeError("abort")

        env = db.query(language="sql", command="SELECT count(*) AS c FROM TxRollback")
        assert env.result[0]["c"] == 0


def test_a_bad_query_raises_arcadedb_error_with_a_request_id(base_url: str, database: str) -> None:
    with (
        ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv,
        pytest.raises(ArcadeDBError) as caught,
    ):
        srv.db(database).query(language="sql", command="SELCT nonsense")

    assert caught.value.status >= 400
    assert caught.value.request_id is not None


@pytest.mark.asyncio
async def test_async_round_trip(base_url: str, database: str) -> None:
    async with AsyncArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        assert await srv.ready() is True

        db = srv.db(database)
        await db.command(language="sql", command="CREATE VERTEX TYPE PersonAsync IF NOT EXISTS")

        async with db.transaction() as tx:
            await tx.command(language="sql", command="INSERT INTO PersonAsync SET name = 'Grace'")

        env = await db.query(language="sql", command="SELECT FROM PersonAsync")
        assert [row["name"] for row in env.result] == ["Grace"]


def test_vector_search_returns_a_non_empty_nearest_first_result(
    base_url: str, database: str, vector_index: tuple[str, str]
) -> None:
    vector_index_name, _ = vector_index
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        result = srv.db(database).vector.search(index_name=vector_index_name, query_vector=[1, 0, 0, 0], k=10)

    results = result.results
    assert isinstance(results, list)  # narrows past `list[...] | Unset` for mypy and for `len()`
    assert len(results) > 0
    assert result.count == 3
    # k (10) exceeds the row count (3): the candidate window was never filled, so this is a
    # complete answer, not a partial one that happens to look complete.
    assert result.truncated is False
    # Nearest first: the query vector IS `red-apple`'s embedding, so its distance is exactly 0
    # and no later hit's distance is smaller.
    assert results[0].distance == 0
    distances = [d for r in results if isinstance(d := r.distance, float)]
    assert len(distances) == len(results)
    assert distances == sorted(distances)


def test_vector_search_with_a_smaller_k_fills_the_window_and_truncated_says_so(
    base_url: str, database: str, vector_index: tuple[str, str]
) -> None:
    # D-M5-2: truncated means the window was filled and more matches may exist. A caller
    # reading only `results` and ignoring this field would work off a partial answer silently.
    vector_index_name, _ = vector_index
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        result = srv.db(database).vector.search(index_name=vector_index_name, query_vector=[1, 0, 0, 0], k=2)

    assert result.count == 2
    assert result.truncated is True


def test_hybrid_search_fuses_both_legs_into_a_non_empty_result(
    base_url: str, database: str, vector_index: tuple[str, str]
) -> None:
    vector_index_name, fulltext_index_name = vector_index
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        result = srv.db(database).vector.hybrid(
            vector_index_name=vector_index_name,
            query_vector=[1, 0, 0, 0],
            fulltext_index_name=fulltext_index_name,
            fulltext_query="apple",
            k=10,
        )

    results = result.results
    assert isinstance(results, list)
    assert len(results) > 0
    assert result.count == 3
    assert result.truncated is False
    assert result.fused is True


def test_fulltext_search_matches_a_known_term_and_carries_no_truncated_field(
    base_url: str, database: str, vector_index: tuple[str, str]
) -> None:
    _, fulltext_index_name = vector_index
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        result = srv.db(database).vector.fulltext(query_text="apple", index_name=fulltext_index_name)

    results = result.results
    assert isinstance(results, list)
    assert len(results) > 0
    assert result.count == 2
    # Not False - ABSENT. FullTextSearchResponse carries no `truncated` field in the contract
    # at all, unlike VectorSearchResponse and HybridSearchResponse above (D-M5-2).
    assert not hasattr(result, "truncated")


@pytest.mark.asyncio
async def test_async_vector_hybrid_and_fulltext_search_all_return_non_empty_results(
    base_url: str, database: str, vector_index: tuple[str, str]
) -> None:
    vector_index_name, fulltext_index_name = vector_index
    async with AsyncArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        search = await db.vector.search(index_name=vector_index_name, query_vector=[1, 0, 0, 0], k=10)
        hybrid = await db.vector.hybrid(
            vector_index_name=vector_index_name,
            query_vector=[1, 0, 0, 0],
            fulltext_index_name=fulltext_index_name,
            fulltext_query="apple",
            k=10,
        )
        fulltext = await db.vector.fulltext(query_text="apple", index_name=fulltext_index_name)

    search_results = search.results
    hybrid_results = hybrid.results
    fulltext_results = fulltext.results
    assert isinstance(search_results, list) and len(search_results) > 0
    assert search.truncated is False
    assert isinstance(hybrid_results, list) and len(hybrid_results) > 0
    assert hybrid.fused is True
    assert isinstance(fulltext_results, list) and len(fulltext_results) > 0
    assert not hasattr(fulltext, "truncated")
