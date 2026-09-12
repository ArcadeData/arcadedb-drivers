from __future__ import annotations

import grpc
import pytest
from arcadedb_driver_grpc import create_client, messages

from .conftest import RecordingServicer


def test_commits_on_a_clean_exit(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    with create_client(target) as client, client.transaction("db") as tx:
        tx.execute_command(messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1"))
    assert servicer.calls == ["BeginTransaction", "ExecuteCommand", "CommitTransaction"]


def test_every_call_through_the_handle_carries_the_transaction(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        tx.execute_command(messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1"))
    sent = servicer.command_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.transaction.database == "db"
    assert sent.database == "db"


def test_the_handle_overrides_a_transaction_the_caller_supplied(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # The override IS the mechanism. A caller cannot forget, drop or mismatch the
    # transaction id the way the 2026-07 gRPC audit found three times (#5040-#5042).
    # Asserting only transaction_id/database here would also go green for a `_bind`
    # written with `MergeFrom` instead of `CopyFrom` - MergeFrom overwrites the id and
    # database but leaves the caller's inline rollback/read_only/commit/timeout_ms
    # flags in place, which is the same silent-data-loss shape this module exists to
    # make unrepeatable. Populating those fields and asserting they arrive cleared is
    # what actually distinguishes CopyFrom from MergeFrom.
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        tx.execute_command(
            messages.ExecuteCommandRequest(
                database="somewhere-else",
                command="INSERT INTO P SET n = 1",
                transaction=messages.TransactionContext(
                    transaction_id="tx-forged",
                    rollback=True,
                    read_only=True,
                    commit=True,
                    timeout_ms=5,
                ),
            )
        )
    sent = servicer.command_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.database == "db"
    assert sent.transaction.rollback is False
    assert sent.transaction.read_only is False
    assert sent.transaction.commit is False
    assert sent.transaction.timeout_ms == 0


def test_rolls_back_and_reraises_when_the_body_raises(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    sentinel = RuntimeError("boom")
    with pytest.raises(RuntimeError) as caught, create_client(target) as client, client.transaction("db"):
        raise sentinel
    assert caught.value is sentinel
    assert "RollbackTransaction" in servicer.calls
    assert "CommitTransaction" not in servicer.calls


def test_refuses_to_run_the_body_without_a_real_transaction_id(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # Running a caller's writes outside a real transaction while implying otherwise is
    # the worst outcome available here, so a blank id refuses BEFORE the body runs.
    target, servicer = fake_server
    servicer.transaction_id = "   "
    ran = False
    with (
        pytest.raises(RuntimeError, match="did not return a transaction id"),
        create_client(target) as client,
        client.transaction("db"),
    ):
        ran = True
    assert ran is False


def test_raises_when_the_server_reports_the_commit_did_not_take_effect(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # A server that reaped the transaction answers success=true, committed=false with no
    # error status. Reporting success there would silently lose the caller's writes.
    target, servicer = fake_server
    servicer.commit_committed = False
    servicer.commit_message = "transaction was reaped"
    with (
        pytest.raises(RuntimeError, match="did not take effect"),
        create_client(target) as client,
        client.transaction("db"),
    ):
        pass


def test_commit_failure_rolls_back_and_reraises_the_commit_error(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # A best-effort rollback is issued so the server does not hold the transaction open
    # until it is reaped, and the commit's own error - not the rollback's - is what the
    # caller sees.
    target, servicer = fake_server
    servicer.commit_raises = True
    with pytest.raises(grpc.RpcError), create_client(target) as client, client.transaction("db"):
        pass
    assert servicer.calls == ["BeginTransaction", "CommitTransaction", "RollbackTransaction"]


def test_rollback_failure_attaches_as_cause_but_the_bodys_exception_still_propagates(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # The body's own exception is what the caller asked about; a rollback failure on top
    # of it is attached as __cause__ rather than replacing it.
    target, servicer = fake_server
    servicer.rollback_raises = True
    sentinel = RuntimeError("boom")
    with pytest.raises(RuntimeError) as caught, create_client(target) as client, client.transaction("db"):
        raise sentinel
    assert caught.value is sentinel
    assert isinstance(caught.value.__cause__, grpc.RpcError)


def test_the_handles_crud_methods_forward_timeout_and_metadata_to_the_server(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # `execute_query`, `create_record`, `update_record`, `delete_record` and
    # `lookup_by_rid` all funnel through the same `self._raw.<Method>(bound, timeout=,
    # metadata=)` shape as `execute_command` below - `RecordingServicer` implements only
    # `ExecuteCommand`, so that is the one call this asserts through, but the forwarding
    # is identical on all six. Before this fix `execute_command` took only `request` and
    # calling it with `timeout=`/`metadata=` raised `TypeError`.
    target, servicer = fake_server
    with create_client(target) as client, client.transaction("db") as tx:
        tx.execute_command(
            messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1"),
            timeout=30.0,
            metadata=(("x-test-header", "hello"),),
        )
    # A real deadline reached the server: `grpc._server`'s sync `ServicerContext`
    # answers a huge sentinel float (~9.2e18) when no timeout was set at all, and the
    # actual remaining seconds otherwise - so a small bounded value here is only
    # reachable by the `timeout=30.0` above having actually been forwarded. Read from
    # `command_time_remaining`/`command_metadata`, not the last-call `time_remaining`/
    # `metadata`: the `with` block's own `CommitTransaction` follows this call and would
    # otherwise overwrite them first.
    assert servicer.command_time_remaining[0] is not None
    assert servicer.command_time_remaining[0] < 60.0
    assert ("x-test-header", "hello") in servicer.command_metadata[0]


def test_stream_query_through_the_handle_is_bound_to_the_transaction(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        list(tx.stream_query(messages.StreamQueryRequest(query="SELECT 1")))
    sent = servicer.stream_query_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.database == "db"


def test_insert_stream_is_not_offered_on_the_handle(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # ArcadeData/arcadedb#6607: on 26.8.1 and earlier the server ignored TransactionContext
    # for InsertStream and BulkInsert, so offering them here would have implied a guarantee
    # it did not honour. #6607 HAS since landed (79d931070b, released in 26.9.1) and was
    # re-measured against real 26.8.1 / 26.9.1 / 26.10.1-SNAPSHOT servers, so this test now
    # pins a restriction no supported server needs. Delete it when the methods are added -
    # that is public surface, so it is a release decision, not a contract-adoption change.
    target, _ = fake_server
    with create_client(target) as client, client.transaction("db") as tx:
        assert not hasattr(tx, "insert_stream")
        assert not hasattr(tx, "bulk_insert")


def test_the_callers_request_object_is_left_unchanged(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # `_bind` binds onto a COPY. Binding in place would leave the caller's own request
    # carrying `database="db"` and a now-committed transaction's id after the block
    # ended, so reusing it - through `client.raw`, or in a later transaction before
    # `_bind` runs - would send a dead transaction id to the server: #5040's shape
    # reached by aliasing, in the module built to make it unrepeatable.
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    request = messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1", language="sql")
    with create_client(target) as client, client.transaction("db") as tx:
        tx.execute_command(request)

    # What arrived on the wire IS bound - the override is still the mechanism.
    sent = servicer.command_requests[0]
    assert sent.database == "db"
    assert sent.transaction.transaction_id == "tx-42"
    # The caller's object is byte-for-byte what they built.
    assert request == messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1", language="sql")
    assert request.database == ""
    assert request.transaction.transaction_id == ""


def test_vector_search_through_the_handle_is_bound(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        tx.vector_search(
            messages.VectorSearchRequest(
                database="somewhere-else",
                index_name="v_idx",
                query_vector=[0.1, 0.2],
                transaction=messages.TransactionContext(
                    transaction_id="tx-forged",
                    rollback=True,
                    read_only=True,
                    commit=True,
                    timeout_ms=5,
                ),
            )
        )

    sent = servicer.vector_requests[0]
    assert sent.database == "db"
    assert sent.transaction.transaction_id == "tx-42"
    # CopyFrom, not MergeFrom: the caller's inline flags must NOT ride through.
    assert sent.transaction.rollback is False
    assert sent.transaction.read_only is False
    assert sent.transaction.commit is False
    assert sent.transaction.timeout_ms == 0
    # The payload the caller actually cares about is untouched.
    assert sent.index_name == "v_idx"
    assert list(sent.query_vector) == pytest.approx([0.1, 0.2])


def test_the_callers_vector_request_object_is_left_unchanged(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    request = messages.VectorSearchRequest(index_name="v_idx", query_vector=[0.1])
    with create_client(target) as client, client.transaction("db") as tx:
        tx.vector_search(request)

    assert servicer.vector_requests[0].database == "db"
    assert request.database == ""
    assert request.transaction.transaction_id == ""


def test_time_series_query_through_the_handle_is_bound_to_the_transaction(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # `TimeSeriesQueryRequest` carries a `transaction` field (issue #7370), the same shape
    # as `stream_query` above.
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        list(tx.time_series_query(messages.TimeSeriesQueryRequest(type="cpu")))
    sent = servicer.ts_query_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.database == "db"


def test_time_series_latest_through_the_handle_is_bound(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # `TimeSeriesLatest` is unary and carries a `transaction` field for the same #7370
    # reason as `time_series_query` above; it is bound directly rather than through a
    # stream-flattening wrapper. Populating the forged inline flags and asserting they are
    # cleared distinguishes CopyFrom from MergeFrom, as the vector_search test above does.
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        tx.time_series_latest(
            messages.TimeSeriesLatestRequest(
                database="somewhere-else",
                type="cpu",
                transaction=messages.TransactionContext(
                    transaction_id="tx-forged",
                    rollback=True,
                    read_only=True,
                    commit=True,
                    timeout_ms=5,
                ),
            )
        )

    sent = servicer.ts_latest_requests[0]
    assert sent.database == "db"
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.transaction.rollback is False
    assert sent.transaction.read_only is False
    assert sent.transaction.commit is False
    assert sent.transaction.timeout_ms == 0
    assert sent.type == "cpu"


def test_the_callers_time_series_latest_request_object_is_left_unchanged(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    request = messages.TimeSeriesLatestRequest(type="cpu")
    with create_client(target) as client, client.transaction("db") as tx:
        tx.time_series_latest(request)

    assert servicer.ts_latest_requests[0].database == "db"
    assert request.database == ""
    assert request.transaction.transaction_id == ""


def test_hybrid_and_fulltext_through_the_handle_are_bound(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        tx.hybrid_search(
            messages.HybridSearchRequest(database="elsewhere", vector_index_name="v_idx", query_vector=[0.1])
        )
        tx.full_text_search(messages.FullTextSearchRequest(database="elsewhere", query_text="cat"))

    assert servicer.hybrid_requests[0].database == "db"
    assert servicer.hybrid_requests[0].transaction.transaction_id == "tx-42"
    assert servicer.fulltext_requests[0].database == "db"
    assert servicer.fulltext_requests[0].transaction.transaction_id == "tx-42"


def test_a_failing_rollback_does_not_mask_the_commit_error(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # Both calls fail. `_safe_rollback` swallowing its own failure is what makes the
    # COMMIT's error the one that surfaces - without the suppression the rollback's error
    # would replace it, and the caller would be told the wrong thing about why their
    # writes did not land. `test_commit_failure_rolls_back_and_reraises_the_commit_error`
    # alone cannot see this: its rollback succeeds, so nothing is there to mask. The
    # async suite has carried this test since the start; the sync side had only its
    # sibling, leaving `contextlib.suppress(Exception)` here untested.
    target, servicer = fake_server
    servicer.commit_raises = True
    servicer.rollback_raises = True
    with pytest.raises(grpc.RpcError) as caught, create_client(target) as client, client.transaction("db"):
        pass
    assert "commit failed" in str(caught.value)
    assert "rollback failed" not in str(caught.value)
    assert servicer.calls == ["BeginTransaction", "CommitTransaction", "RollbackTransaction"]
