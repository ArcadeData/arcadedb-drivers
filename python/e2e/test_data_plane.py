"""End-to-end tests against a real ArcadeDB server. Requires Docker."""

from __future__ import annotations

import pytest
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer, basic_auth
from arcadedb_driver._generated.models.nd_json_query_event import NdJsonQueryEvent
from arcadedb_driver._generated.models.nd_json_query_event_stats import NdJsonQueryEventStats
from arcadedb_driver._generated.types import Unset

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


# STREAM_ROW_COUNT and STREAM_PAYLOAD were worked out empirically against a live container before
# this fixture was written, not guessed - see task-4-report.md for the transcript of chunk counts
# measured at increasing row counts. A handful of rows arrives from a real server in a single
# ndjson chunk (one `iter_lines()`/`aiter_lines()` read), which would let a decoder with no
# cross-chunk buffering at all pass this suite for the wrong reason - the exact defect
# `test_stream.py`'s fabricated-boundary cases target. 2000 rows of ~150 bytes each reliably
# splits the response across dozens of real reads.
STREAM_TYPE = "StreamRow"
STREAM_ROW_COUNT = 2000
STREAM_PAYLOAD = "x" * 100


@pytest.fixture(scope="module")
def stream_rows(base_url: str, database: str) -> int:
    """Creates `StreamRow` and inserts `STREAM_ROW_COUNT` rows once for the streaming tests below.

    Module-scoped, like `test_data_plane.py`'s own `vector_index` fixture in `conftest.py`: the
    DDL and the bulk insert run once no matter how many tests in this module use them. Returns the
    row count so a test that wants it does not need to repeat the module constant.
    """
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        db.command(language="sql", command=f"CREATE DOCUMENT TYPE {STREAM_TYPE} IF NOT EXISTS")
        db.command(language="sql", command=f"CREATE PROPERTY {STREAM_TYPE}.n INTEGER")
        db.command(language="sql", command=f"CREATE PROPERTY {STREAM_TYPE}.payload STRING")
        values = ",".join(f"({i},'{STREAM_PAYLOAD}')" for i in range(STREAM_ROW_COUNT))
        db.command(language="sql", command=f"INSERT INTO {STREAM_TYPE} (n, payload) VALUES {values}")
    return STREAM_ROW_COUNT


def _stats(event: NdJsonQueryEvent) -> NdJsonQueryEventStats:
    assert not isinstance(event.stats, Unset)
    return event.stats


def test_stream_query_yields_records_and_a_stats_trailer_matching_what_arrived(
    base_url: str, database: str, stream_rows: int
) -> None:
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        events = list(db.query_stream(language="sql", command=f"SELECT FROM {STREAM_TYPE}", limit=-1))

    records = [e for e in events if not isinstance(e.record, Unset)]
    trailer = events[-1]  # the stats trailer is always the LAST event of a complete stream

    assert len(records) == stream_rows
    stats = _stats(trailer)
    assert stats.returned == len(records)
    assert stats.truncated is False


def test_stream_query_with_a_low_limit_reports_truncated_in_the_trailer(
    base_url: str, database: str, stream_rows: int
) -> None:
    cap = 500
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        events = list(db.query_stream(language="sql", command=f"SELECT FROM {STREAM_TYPE}", limit=cap))

    records = [e for e in events if not isinstance(e.record, Unset)]
    stats = _stats(events[-1])

    assert len(records) == cap
    assert stats.returned == cap
    assert stats.truncated is True


def test_buffered_query_returns_the_same_rows_streaming_did(base_url: str, database: str, stream_rows: int) -> None:
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        buffered = db.query(language="sql", command=f"SELECT FROM {STREAM_TYPE}", limit=-1)
        events = list(db.query_stream(language="sql", command=f"SELECT FROM {STREAM_TYPE}", limit=-1))

    streamed_ns = sorted(e.record["n"] for e in events if not isinstance(e.record, Unset))
    buffered_ns = sorted(row["n"] for row in buffered.result)

    assert buffered.truncated is False
    assert streamed_ns == buffered_ns
    assert len(buffered_ns) == stream_rows


@pytest.mark.asyncio
async def test_async_stream_query_yields_records_and_a_stats_trailer(
    base_url: str, database: str, stream_rows: int
) -> None:
    async with AsyncArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        events = [
            event async for event in db.query_stream(language="sql", command=f"SELECT FROM {STREAM_TYPE}", limit=-1)
        ]

    records = [e for e in events if not isinstance(e.record, Unset)]
    stats = _stats(events[-1])

    assert len(records) == stream_rows
    assert stats.returned == len(records)
    assert stats.truncated is False
