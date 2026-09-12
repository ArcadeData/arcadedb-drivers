"""End-to-end tests against a real ArcadeDB server. Requires Docker."""

from __future__ import annotations

from typing import Any

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


# BIG_PAYLOAD_SIZE is a second, different way to force a genuinely multi-chunk response: not many
# ordinarily-sized rows, but ONE record whose own ndjson line is large enough that a single write
# of it cannot be delivered to the client in one read. This matters because a large text field or
# a base64 blob big enough to land here is an ordinary shape, not an exotic one - a caller could
# plausibly store either - even though most rows are nowhere near this size and never take this
# path. The point of this test is not that the split is common; it is that the decoder must still
# reassemble it correctly on the rows where it does happen, which is the case where cross-chunk
# buffering is load-bearing against a real server rather than only against the fabricated
# boundaries in test_stream.py.
#
# The size was swept empirically against a live container (see task-4-report.md for the full
# table), not guessed. Up to ~40,000 bytes a single record's line reliably arrived in ONE read
# every time: ArcadeDB's response writer appears to issue one write() per output line, and TCP
# delivers a write that size as one segment on loopback as long as it stays under the client's own
# socket read buffer. Splitting only starts to appear past roughly 50,000-65,000 bytes, and even
# there it was inconsistent run to run (3 splits out of 5 at 40,000 bytes) - consistent with that
# boundary being where a single line starts to exceed the reader's read-buffer size (observed
# chunk sizes cluster at 65536 bytes for an even larger field in the initial probe). 70,000 through
# 95,000 bytes split on every one of 6 repeated runs against both this client's transport
# (`httpx`) and the TypeScript client's (Node's `fetch`). 80,000 bytes sits in the middle of that
# reliable range: comfortably past the ~64KB boundary with margin, not the 500,000 bytes used only
# to confirm the mechanism existed in the first place.
BIG_FIELD_TYPE = "BigFieldRow"
BIG_PAYLOAD_SIZE = 80_000
# A cycling digit pattern, not a repeated single character: a decoder that drops, duplicates, or
# reorders a byte at the chunk boundary changes this string's content, not just its length, so
# comparing the reassembled value against this exact string catches corruption a length-only or
# all-the-same-character check would miss.
BIG_PAYLOAD = "".join(str(i % 10) for i in range(BIG_PAYLOAD_SIZE))


@pytest.fixture(scope="module")
def big_field_row(base_url: str, database: str) -> str:
    """Creates `BigFieldRow` and inserts one row carrying `BIG_PAYLOAD`, once.

    A separate type from `StreamRow`, not one more row added to it: mixing this row into
    `StreamRow` would change the row count `stream_rows`'s own tests assert on.
    """
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        db.command(language="sql", command=f"CREATE DOCUMENT TYPE {BIG_FIELD_TYPE} IF NOT EXISTS")
        db.command(language="sql", command=f"CREATE PROPERTY {BIG_FIELD_TYPE}.payload STRING")
        db.command(language="sql", command=f"INSERT INTO {BIG_FIELD_TYPE} SET payload = '{BIG_PAYLOAD}'")
    return BIG_FIELD_TYPE


def _stats(event: NdJsonQueryEvent) -> NdJsonQueryEventStats:
    assert not isinstance(event.stats, Unset)
    return event.stats


def _record(event: NdJsonQueryEvent) -> dict[str, Any]:
    assert not isinstance(event.record, Unset)
    return event.record.to_dict()


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

    # Compare the FULL row shape (both "n" and "payload"), not just "n" - StreamRow carries both
    # fields, and the property under test is that streaming did not change what the buffered path
    # returns, not merely that the two sides agree on one column.
    streamed_rows = sorted((_record(e) for e in events if not isinstance(e.record, Unset)), key=lambda r: r["n"])
    buffered_rows = sorted(buffered.result, key=lambda r: r["n"])

    assert buffered.truncated is False
    assert streamed_rows == buffered_rows
    assert len(buffered_rows) == stream_rows


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


def test_stream_query_reassembles_a_single_record_whose_line_spans_multiple_real_reads(
    base_url: str, database: str, big_field_row: str
) -> None:
    # This is a DIFFERENT property from `stream_rows`'s tests above: those prove the response
    # arrives across many real reads; this one proves a single ndjson LINE really spans two of
    # them and still comes back whole. A test that only counted events here would pass against a
    # decoder that silently truncated `payload` at the chunk boundary - the value itself has to be
    # compared.
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        events = list(db.query_stream(language="sql", command=f"SELECT FROM {big_field_row}"))

    records = [e for e in events if not isinstance(e.record, Unset)]
    assert len(records) == 1
    payload = _record(records[0])["payload"]
    assert len(payload) == BIG_PAYLOAD_SIZE
    assert payload == BIG_PAYLOAD

    stats = _stats(events[-1])
    assert stats.returned == 1
    assert stats.truncated is False
