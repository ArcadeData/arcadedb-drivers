"""End-to-end tests for arcadedb-driver-grpc against a real ArcadeDB server."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import grpc
import pytest
from arcadedb_driver_grpc import (
    ArcadeDBGrpcClient,
    InsertStreamRequest,
    TimeSeriesWriteStreamRequest,
    create_client,
    messages,
)
from arcadedb_driver_grpc.auth import bearer_auth, password_auth, sync_interceptors

from .conftest import ROOT_PASSWORD


@pytest.fixture
def client(grpc_server: tuple[str, str], grpc_database: str) -> Iterator[ArcadeDBGrpcClient]:
    _, target = grpc_server
    with create_client(
        target,
        auth=password_auth("root", ROOT_PASSWORD, grpc_database),
        # The container speaks plaintext gRPC, so the guard has to be opted out of
        # explicitly. That it must be opted out of here IS the guard working.
        insecure=True,
    ) as grpc_client:
        yield grpc_client


def _person(name: str) -> messages.GrpcRecord:
    return messages.GrpcRecord(type="Person", properties={"name": messages.GrpcValue(string_value=name)})


# Same story as `auth._SyncAuthInterceptor`: grpc-stubs declares these four base
# classes `Generic[TRequest, TResponse]` for mypy's benefit, but the real runtime
# classes (grpc/__init__.py) only extend `abc.ABC` - they are not `typing.Generic`
# and cannot be subscripted at class definition time. Parameterizing them here would
# raise `TypeError: ... is not subscriptable` on import, so the per-line
# `# type: ignore[type-arg]` accepts mypy's "missing type arguments" note instead of
# a runtime crash.
class _CallRecorder(
    grpc.UnaryUnaryClientInterceptor,  # type: ignore[type-arg]
    grpc.UnaryStreamClientInterceptor,  # type: ignore[type-arg]
    grpc.StreamUnaryClientInterceptor,  # type: ignore[type-arg]
    grpc.StreamStreamClientInterceptor,  # type: ignore[type-arg]
):
    """Records each outgoing RPC's method name, then forwards the call unchanged.

    Used only by `test_transaction_rolls_back`, to assert the MECHANISM (that
    RollbackTransaction was actually issued and CommitTransaction was not) rather than
    only the row-absence outcome: an insert that silently failed - or a transaction that
    was simply abandoned, never committed and never rolled back - would also leave no
    rows, through ordinary isolation rather than cleanup. Row absence alone cannot tell
    those apart from a real rollback; this can.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _record(self, method: str) -> None:
        # client_call_details.method is the full "/package.Service/Method" path; only
        # the trailing segment is asserted on below.
        self.calls.append(method.rsplit("/", 1)[-1])

    def intercept_unary_unary(self, continuation: Any, client_call_details: Any, request: Any) -> Any:
        self._record(client_call_details.method)
        return continuation(client_call_details, request)

    def intercept_unary_stream(self, continuation: Any, client_call_details: Any, request: Any) -> Any:
        self._record(client_call_details.method)
        return continuation(client_call_details, request)

    def intercept_stream_unary(self, continuation: Any, client_call_details: Any, request_iterator: Any) -> Any:
        self._record(client_call_details.method)
        return continuation(client_call_details, request_iterator)

    def intercept_stream_stream(self, continuation: Any, client_call_details: Any, request_iterator: Any) -> Any:
        self._record(client_call_details.method)
        return continuation(client_call_details, request_iterator)


def _names(client: ArcadeDBGrpcClient, database: str, marker: str) -> list[str]:
    rows = client.stream_query(
        messages.StreamQueryRequest(
            database=database, language="sql", query=f"SELECT FROM Person WHERE name LIKE '{marker}%'"
        )
    )
    return sorted(r.properties["name"].string_value for r in rows)


def test_password_auth_reaches_the_server(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    response = client.raw.ExecuteQuery(
        messages.ExecuteQueryRequest(database=grpc_database, language="sql", query="SELECT FROM Person")
    )
    assert response is not None


def test_bearer_auth_reaches_the_server(grpc_server: tuple[str, str], grpc_database: str) -> None:
    # Both auth paths, exercised end to end. The token is minted over HTTP (there is no
    # data-plane RPC for it) and then presented as a gRPC bearer credential - proving the
    # same session token both drivers already share actually works against the real gRPC
    # service, not just against the fake server the unit suite uses.
    from arcadedb_driver import ArcadeDBServer, basic_auth
    from arcadedb_driver._generated.api.auth import login as http_login
    from arcadedb_driver._generated.models.login_response import LoginResponse

    http_url, target = grpc_server
    with ArcadeDBServer(base_url=http_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        login_response = http_login.sync_detailed(client=srv.raw)
        parsed = login_response.parsed
        assert isinstance(parsed, LoginResponse), parsed
        token = parsed.token
        assert isinstance(token, str)
        assert token.startswith("AU-")

    with create_client(target, auth=bearer_auth(token), insecure=True) as bearer_client:
        response = bearer_client.raw.ExecuteQuery(
            messages.ExecuteQueryRequest(database=grpc_database, language="sql", query="SELECT FROM Person")
        )
        assert response is not None


def test_stream_query_returns_rows(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"sq{uuid.uuid4().hex[:8]}"
    client.raw.ExecuteCommand(
        messages.ExecuteCommandRequest(
            database=grpc_database, language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'"
        )
    )
    assert _names(client, grpc_database, marker) == [f"{marker}-a"]


def test_insert_stream_inserts_rows(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    # THE test for the options.database mirroring. On a real 26.8.1 or earlier server, an
    # insert_stream that does not mirror `database` into `options` inserts nothing -
    # inserted=0, or a deferred-commit failure with "Invalid database name: name is
    # required". If this test ever fails that way, the mirroring in stream.py has been
    # removed - restore it, do not work around it.
    #
    # Note what this test CANNOT prove on the pinned image. ArcadeData/arcadedb#6597 was
    # fixed in 26.9.1, and the pin is 26.10.1-SNAPSHOT, so this passes with OR without the
    # mirror here. The boundary was established separately, by sending a chunk-only
    # `database` against 26.8.1, 26.9.1 and 26.10.1-SNAPSHOT directly: 0 of 2 rows land on
    # 26.8.1, 2 of 2 on both later versions. The mirror is kept anyway - removing it is a
    # behaviour change, not a documentation fix.
    marker = f"is{uuid.uuid4().hex[:8]}"
    summary = client.insert_stream(
        InsertStreamRequest(
            database=grpc_database,
            options=messages.InsertOptions(target_class="Person"),
            chunks=[[_person(f"{marker}-a"), _person(f"{marker}-b")], [_person(f"{marker}-c")]],
        )
    )
    assert summary.inserted == 3
    assert _names(client, grpc_database, marker) == [f"{marker}-a", f"{marker}-b", f"{marker}-c"]


def test_an_empty_insert_stream_is_accepted(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    summary = client.insert_stream(
        InsertStreamRequest(database=grpc_database, options=messages.InsertOptions(target_class="Person"), chunks=[])
    )
    assert summary.inserted == 0
    assert summary.failed == 0


def test_transaction_commits(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"tc{uuid.uuid4().hex[:8]}"
    with client.transaction(grpc_database) as tx:
        tx.execute_command(
            messages.ExecuteCommandRequest(language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'")
        )
    assert _names(client, grpc_database, marker) == [f"{marker}-a"]


def test_transaction_rolls_back(grpc_server: tuple[str, str], grpc_database: str, client: ArcadeDBGrpcClient) -> None:
    # Asserts the MECHANISM, not only the row absence: an insert that silently failed -
    # or a transaction simply left open and never resolved either way - would also leave
    # no rows, through ordinary isolation rather than cleanup. So a separate, recorded
    # channel proves RollbackTransaction was actually issued and CommitTransaction was
    # not, in addition to the row-absence check below.
    _, target = grpc_server
    marker = f"tr{uuid.uuid4().hex[:8]}"
    recorder = _CallRecorder()
    auth_interceptors = sync_interceptors(password_auth("root", ROOT_PASSWORD, grpc_database))
    channel = grpc.intercept_channel(grpc.insecure_channel(target), recorder, *auth_interceptors)
    spied_client = ArcadeDBGrpcClient(channel)
    try:
        sentinel = RuntimeError("boom")
        with pytest.raises(RuntimeError) as caught, spied_client.transaction(grpc_database) as tx:
            tx.execute_command(
                messages.ExecuteCommandRequest(language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'")
            )
            raise sentinel
        assert caught.value is sentinel
    finally:
        spied_client.close()

    assert "RollbackTransaction" in recorder.calls
    assert "CommitTransaction" not in recorder.calls

    # Belt and suspenders, and the brief's explicit requirement: the row must also be
    # ABSENT, not merely that the exception propagated and RollbackTransaction fired.
    assert _names(client, grpc_database, marker) == []


def test_vector_search_through_raw_outside_a_transaction_returns_a_non_empty_nearest_first_result(
    client: ArcadeDBGrpcClient, grpc_database: str, grpc_vector_index: tuple[str, str]
) -> None:
    vector_index_name, _ = grpc_vector_index
    response = client.raw.VectorSearch(
        messages.VectorSearchRequest(
            database=grpc_database, index_name=vector_index_name, query_vector=[1, 0, 0, 0], k=10
        )
    )

    assert len(response.results) > 0
    assert response.count == 3
    # k (10) exceeds the row count (3): the window was never filled, so this IS a complete
    # answer, not a partial one that happens to look complete.
    assert response.truncated is False
    # Nearest first: the query vector IS `red-apple`'s embedding, so its distance is exactly 0.
    assert response.results[0].distance == 0
    distances = [hit.distance for hit in response.results]
    assert distances == sorted(distances)


def test_hybrid_search_through_raw_outside_a_transaction_fuses_both_legs(
    client: ArcadeDBGrpcClient, grpc_database: str, grpc_vector_index: tuple[str, str]
) -> None:
    vector_index_name, fulltext_index_name = grpc_vector_index
    response = client.raw.HybridSearch(
        messages.HybridSearchRequest(
            database=grpc_database,
            vector_index_name=vector_index_name,
            query_vector=[1, 0, 0, 0],
            fulltext_index_name=fulltext_index_name,
            fulltext_query="apple",
            k=10,
        )
    )

    assert len(response.results) > 0
    assert response.count == 3
    assert response.fused is True


def test_fulltext_search_through_raw_outside_a_transaction_matches_a_known_term(
    client: ArcadeDBGrpcClient, grpc_database: str, grpc_vector_index: tuple[str, str]
) -> None:
    _, fulltext_index_name = grpc_vector_index
    response = client.raw.FullTextSearch(
        messages.FullTextSearchRequest(database=grpc_database, index_name=fulltext_index_name, query_text="apple")
    )

    assert len(response.results) > 0
    assert response.count == 2


def test_vector_hybrid_and_fulltext_search_through_the_transaction_handle_all_return_non_empty_results(
    client: ArcadeDBGrpcClient, grpc_database: str, grpc_vector_index: tuple[str, str]
) -> None:
    # D-M5-1 proven end to end against a real server: the same three RPCs reached two ways - raw
    # above (outside a transaction) and, here, bound to an open one through `TransactionHandle`.
    # There is no top-level `client.vector_search` alias; see the README for why.
    vector_index_name, fulltext_index_name = grpc_vector_index
    with client.transaction(grpc_database) as tx:
        search = tx.vector_search(
            messages.VectorSearchRequest(index_name=vector_index_name, query_vector=[1, 0, 0, 0], k=10)
        )
        hybrid = tx.hybrid_search(
            messages.HybridSearchRequest(
                vector_index_name=vector_index_name,
                query_vector=[1, 0, 0, 0],
                fulltext_index_name=fulltext_index_name,
                fulltext_query="apple",
                k=10,
            )
        )
        fulltext = tx.full_text_search(
            messages.FullTextSearchRequest(query_text="apple", index_name=fulltext_index_name)
        )

    assert len(search.results) > 0
    assert search.truncated is False
    assert len(hybrid.results) > 0
    assert hybrid.fused is True
    assert len(fulltext.results) > 0


def test_time_series_write_stream_multi_chunk_then_query_and_latest_through_a_transaction(
    client: ArcadeDBGrpcClient, grpc_database: str, grpc_timeseries_type: str
) -> None:
    """The three things D-M6-4's e2e coverage exists to prove, done together in one test so
    none of them depends on test execution order against the shared session-scoped database:

    1. A MULTI-CHUNK write stream (two chunks) - the only thing that can prove the per-chunk
       envelope (database/type/precision repeated on EVERY wire chunk, not just the first)
       actually works end to end; a unit test against a fake servicer cannot prove this,
       because the fake is not the server.
    2. `time_series_query` returns the points just written, non-empty.
    3. `time_series_latest`, bound to an open transaction handle (not the top-level client -
       there is no top-level alias for it; see the README), returns the most recent point.
    """
    summary = client.time_series_write_stream(
        TimeSeriesWriteStreamRequest(
            database=grpc_database,
            type=grpc_timeseries_type,
            precision=messages.TimeSeriesPrecision.TS_PRECISION_MILLISECONDS,
            chunks=[
                [
                    messages.TimeSeriesPoint(
                        timestamp=1000,
                        tags={"sensor": messages.GrpcValue(string_value="A")},
                        fields={"value": messages.GrpcValue(double_value=1.1)},
                    ),
                    messages.TimeSeriesPoint(
                        timestamp=2000,
                        tags={"sensor": messages.GrpcValue(string_value="A")},
                        fields={"value": messages.GrpcValue(double_value=1.2)},
                    ),
                ],
                [
                    messages.TimeSeriesPoint(
                        timestamp=3000,
                        tags={"sensor": messages.GrpcValue(string_value="B")},
                        fields={"value": messages.GrpcValue(double_value=2.1)},
                    ),
                ],
            ],
        )
    )
    assert summary.received == 3
    assert summary.written == 3
    assert summary.dropped == 0

    results = list(
        client.time_series_query(messages.TimeSeriesQueryRequest(database=grpc_database, type=grpc_timeseries_type))
    )
    rows = [row for result in results for row in result.rows]
    assert len(rows) > 0

    with client.transaction(grpc_database) as tx:
        latest = tx.time_series_latest(messages.TimeSeriesLatestRequest(type=grpc_timeseries_type))

    assert latest.found is True
    ts_index = list(latest.columns).index("ts")
    assert latest.latest.values[ts_index].int64_value == 3000


def test_an_empty_time_series_write_stream_is_accepted_with_an_all_zero_summary(
    client: ArcadeDBGrpcClient, grpc_database: str, grpc_timeseries_type: str
) -> None:
    """Established empirically against a real server: an empty `chunks` sends ZERO wire
    chunks (unlike `insert_stream`'s single-empty-chunk special case - see
    `TimeSeriesWriteStreamRequest`'s docstring), so the server is never told `database`,
    `type` or `precision` at all. That is accepted cleanly without raising: the call
    completes successfully and the server returns an all-zero `TimeSeriesWriteSummary`
    with `received`, `written`, and `dropped` all zero, and all three type lists empty.
    """
    summary = client.time_series_write_stream(
        TimeSeriesWriteStreamRequest(
            database=grpc_database,
            type=grpc_timeseries_type,
            precision=messages.TimeSeriesPrecision.TS_PRECISION_MILLISECONDS,
            chunks=[],
        )
    )
    assert summary.received == 0
    assert summary.written == 0
    assert summary.dropped == 0
    assert list(summary.unknown_types) == []
    assert list(summary.non_time_series_types) == []
    assert list(summary.unavailable_types) == []
