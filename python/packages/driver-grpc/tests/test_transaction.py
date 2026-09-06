from __future__ import annotations

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
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        tx.execute_command(
            messages.ExecuteCommandRequest(
                database="somewhere-else",
                command="INSERT INTO P SET n = 1",
                transaction=messages.TransactionContext(transaction_id="tx-forged"),
            )
        )
    sent = servicer.command_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.database == "db"


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
    # ArcadeData/arcadedb#6607: the server ignores TransactionContext for InsertStream
    # and BulkInsert. Offering them here would imply a guarantee it does not honour.
    # Delete this test when #6607 lands and the methods are added.
    target, _ = fake_server
    with create_client(target) as client, client.transaction("db") as tx:
        assert not hasattr(tx, "insert_stream")
        assert not hasattr(tx, "bulk_insert")
