from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Iterator

import grpc
import pytest
from arcadedb_driver_grpc import InsecureChannelError, InsertStreamRequest, messages
from arcadedb_driver_grpc.aio import _envelope_chunks, create_client
from arcadedb_driver_grpc.auth import bearer_auth, password_auth

from .conftest import RecordingServicer

pytestmark = pytest.mark.asyncio


def _records(*rids: str) -> list[messages.GrpcRecord]:
    return [messages.GrpcRecord(rid=rid) for rid in rids]


async def test_raw_reaches_the_server_and_is_authenticated(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # `raw` is where 11 of the 14 data-plane RPCs live, so the async facade attaching its
    # auth to the CHANNEL rather than to the three wrapped calls is the property worth
    # asserting: a call that bypasses the facade entirely still arrives authenticated.
    target, servicer = async_fake_server
    async with create_client(target, auth=bearer_auth("t0ken")) as client:
        await client.raw.ExecuteCommand(messages.ExecuteCommandRequest(database="db", command="SELECT 1"))
    assert servicer.calls == ["ExecuteCommand"]
    assert ("authorization", "Bearer t0ken") in servicer.metadata


async def test_password_auth_over_an_insecure_channel_is_refused() -> None:
    # The async facade carries the same #5048 guard as the sync one; a facade that
    # quietly dropped it would be the easier of the two to reach by accident.
    with pytest.raises(InsecureChannelError):
        create_client("127.0.0.1:50051", auth=password_auth("root", "playwithdata"))


async def test_stream_query_flattens_batches(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.stream_batches = [["#1:0", "#1:1"], ["#1:2"]]
    async with create_client(target) as client:
        rids = [r.rid async for r in client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1"))]
    assert rids == ["#1:0", "#1:1", "#1:2"]


async def test_insert_stream_envelope_bookkeeping(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server

    async def chunks() -> AsyncIterator[list[messages.GrpcRecord]]:
        yield _records("a")
        yield _records("b")

    async with create_client(target) as client:
        summary = await client.insert_stream(InsertStreamRequest(database="db", chunks=chunks()))

    sent = servicer.insert_chunks
    assert [c.chunk_seq for c in sent] == [1, 2]
    assert [c.last for c in sent] == [False, True]
    # One session id, stable for the whole stream, and non-empty.
    assert len({c.session_id for c in sent}) == 1
    assert sent[0].session_id != ""
    # `database` on the FIRST chunk only, per the .proto contract, and mirrored into
    # `options.database` there too - ArcadeData/arcadedb#6597, where the server builds
    # its InsertContext from InsertOptions.database ALONE.
    assert sent[0].database == "db"
    assert sent[0].options.database == "db"
    assert sent[1].database == ""
    assert summary.received == 2


async def test_a_sync_iterable_of_batches_is_accepted(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # The async facade takes either half of `InsertStreamRequest.chunks`'s declared
    # union. A caller who already has a list should not have to wrap it in an async
    # generator just to reach this facade - unlike the sync facade, which genuinely
    # cannot consume the async half and says so.
    target, servicer = async_fake_server
    async with create_client(target) as client:
        await client.insert_stream(InsertStreamRequest(database="db", chunks=[_records("a"), _records("b")]))
    assert [c.chunk_seq for c in servicer.insert_chunks] == [1, 2]
    assert [c.last for c in servicer.insert_chunks] == [False, True]


async def test_a_none_row_batch_is_not_confused_with_end_of_stream(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # `anext(source, None)` would conflate a `None` row batch - easy to produce from a
    # `dict.get()` in a batching helper - with genuine end-of-stream, silently dropping
    # every chunk after it: the server reports a smaller `received` and nothing raises
    # anywhere. `stream._EndOfStream` closes that hole for both facades.
    target, servicer = async_fake_server

    async def chunks() -> AsyncIterator[list[messages.GrpcRecord]]:
        yield _records("a")
        yield None  # type: ignore[misc]  # deliberately off-contract
        yield _records("c")

    async with create_client(target) as client:
        await client.insert_stream(InsertStreamRequest(database="db", chunks=chunks()))

    sent = servicer.insert_chunks
    assert [c.chunk_seq for c in sent] == [1, 2, 3]
    assert [c.last for c in sent] == [False, False, True]
    assert [list(c.rows) for c in sent] == [_records("a"), [], _records("c")]


async def test_an_empty_async_stream_sends_one_empty_final_chunk(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # A filter that matched nothing is a legitimate outcome, not an error. M1b verified
    # against a real server that a single empty final chunk is accepted cleanly and
    # answers an all-zero InsertSummary.
    target, servicer = async_fake_server

    async def chunks() -> AsyncIterator[list[messages.GrpcRecord]]:
        nothing: list[list[messages.GrpcRecord]] = []
        for batch in nothing:
            yield batch

    source = chunks()
    # The point of the test is an async generator that yields nothing, not a coroutine or
    # an empty list dressed up as one. Bound to a name first because asserting the
    # `TypeGuard` directly would narrow `source` to `AsyncGenerator[object, Never]` and
    # make the `InsertStreamRequest(...)` below stop type-checking.
    is_async_generator = inspect.isasyncgen(source)
    assert is_async_generator

    async with create_client(target) as client:
        summary = await client.insert_stream(InsertStreamRequest(database="db", chunks=source))

    assert len(servicer.insert_chunks) == 1
    only = servicer.insert_chunks[0]
    assert list(only.rows) == []
    assert only.last is True
    assert only.chunk_seq == 1
    assert only.database == "db"
    assert only.options.database == "db"
    assert summary.received == 0


async def test_transaction_commits_and_binds(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # The override IS the mechanism (#5040-#5042). Asserting only transaction_id and
    # database would also go green for a `_bind` written with `MergeFrom` instead of
    # `CopyFrom`: MergeFrom corrects the id and database while letting a caller-supplied
    # inline rollback/commit/read_only flag ride straight through. Populating those and
    # asserting they arrive CLEARED is what distinguishes the two.
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    async with create_client(target) as client, client.transaction("db") as tx:
        await tx.execute_command(
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
    assert servicer.calls == ["BeginTransaction", "ExecuteCommand", "CommitTransaction"]
    sent = servicer.command_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.transaction.database == "db"
    assert sent.database == "db"
    assert sent.transaction.rollback is False
    assert sent.transaction.read_only is False
    assert sent.transaction.commit is False
    assert sent.transaction.timeout_ms == 0


async def test_transaction_rolls_back_and_reraises(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    sentinel = RuntimeError("boom")
    with pytest.raises(RuntimeError) as caught:
        async with create_client(target) as client, client.transaction("db"):
            raise sentinel
    assert caught.value is sentinel
    # The mechanism, not just the propagation: a rollback was actually issued for THIS
    # transaction, and no commit was attempted alongside it.
    assert servicer.calls == ["BeginTransaction", "RollbackTransaction"]
    assert "CommitTransaction" not in servicer.calls
    assert servicer.rollback_requests[0].transaction.transaction_id == "tx-42"


async def test_transaction_raises_when_the_commit_did_not_take_effect(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # A server that reaped the transaction answers success=TRUE, committed=false with no
    # error status - so an implementation checking `success` alone passes every
    # happy-path test and silently loses the caller's writes here.
    target, servicer = async_fake_server
    servicer.commit_committed = False
    servicer.commit_message = "transaction was reaped"
    with pytest.raises(RuntimeError, match="did not take effect"):
        async with create_client(target) as client, client.transaction("db"):
            pass


async def test_refuses_to_run_the_body_without_a_real_transaction_id(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # Running a caller's writes outside a real transaction while implying otherwise is
    # the worst outcome available here, so a blank id refuses BEFORE the body runs.
    target, servicer = async_fake_server
    servicer.transaction_id = "   "
    ran = False
    with pytest.raises(RuntimeError, match="did not return a transaction id"):
        async with create_client(target) as client, client.transaction("db"):
            ran = True
    assert ran is False


async def test_stream_query_through_the_handle_is_bound_to_the_transaction(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # `tx.stream_query` is a plain `def` returning an async generator, not an `async def`
    # returning a coroutine, so it is iterated directly - and `_bind` runs eagerly at the
    # call, not lazily on the first pull.
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    async with create_client(target) as client, client.transaction("db") as tx:
        rids = [r.rid async for r in tx.stream_query(messages.StreamQueryRequest(query="SELECT 1"))]
    assert rids == ["a", "b", "c"]
    sent = servicer.stream_query_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.database == "db"


async def test_insert_stream_is_not_offered_on_the_handle(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # ArcadeData/arcadedb#6607: the server ignores TransactionContext for InsertStream and
    # BulkInsert. Offering them here would imply a guarantee it does not honour - the same
    # omission the sync handle makes. Delete this test when #6607 lands.
    target, _ = async_fake_server
    async with create_client(target) as client, client.transaction("db") as tx:
        assert not hasattr(tx, "insert_stream")
        assert not hasattr(tx, "bulk_insert")


async def test_the_callers_async_generator_is_finalised_when_the_stream_is_abandoned() -> None:
    # The discriminating case, and the async twin of the sync suite's: the RPC (or the
    # caller) stops consuming mid-stream while a reference to the caller's generator
    # survives - which is the real situation, because `InsertStreamRequest.chunks` holds
    # that reference and defeats ordinary refcount-triggered cleanup.
    #
    # `_envelope_chunks` closing its own `source` is NOT enough here. `aclose()` throws
    # GeneratorExit at `_aiter_chunks`'s `yield`, which unwinds out of its `async for` -
    # and `async for` never closes the iterator it was given. Without `_aiter_chunks`
    # forwarding the close, `chunks()` below stays suspended forever and its `finally`
    # (closing a file handle, a database cursor) never runs.
    closed = False

    async def chunks() -> AsyncIterator[list[messages.GrpcRecord]]:
        nonlocal closed
        try:
            yield _records("a")
            yield _records("b")
            yield _records("c")
        finally:
            closed = True

    source = chunks()
    request = InsertStreamRequest(database="db", chunks=source)  # keeps the generator alive
    envelope = _envelope_chunks(request, "session-1")
    await anext(envelope)
    await envelope.aclose()

    # `inspect.getasyncgenstate` would pin this harder, but it is 3.12+ and the floor
    # here is 3.10. The flag is discriminating on its own: without the fix it stays False.
    assert closed is True


async def test_a_callers_sync_generator_is_finalised_when_the_stream_is_abandoned() -> None:
    # The same hazard on `_aiter_chunks`'s OTHER branch: a plain `for` does not close its
    # iterator either, so handing the async facade a sync generator must forward the close
    # just as the sync facade does.
    closed = False

    def chunks() -> Iterator[list[messages.GrpcRecord]]:
        nonlocal closed
        try:
            yield _records("a")
            yield _records("b")
            yield _records("c")
        finally:
            closed = True

    source = chunks()
    request = InsertStreamRequest(database="db", chunks=source)
    envelope = _envelope_chunks(request, "session-1")
    await anext(envelope)
    await envelope.aclose()

    # `inspect.getasyncgenstate` would pin this harder, but it is 3.12+ and the floor
    # here is 3.10. The flag is discriminating on its own: without the fix it stays False.
    assert closed is True


async def test_commit_failure_rolls_back_and_reraises_the_commit_error(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # A best-effort rollback is issued so the server does not hold the transaction open
    # until it is reaped, and the commit's own error - not the rollback's - is what the
    # caller sees. `_safe_rollback` exists for exactly this path.
    target, servicer = async_fake_server
    servicer.commit_raises = True
    with pytest.raises(grpc.RpcError):
        async with create_client(target) as client, client.transaction("db"):
            pass
    assert servicer.calls == ["BeginTransaction", "CommitTransaction", "RollbackTransaction"]


async def test_rollback_failure_attaches_as_cause_but_the_bodys_exception_still_propagates(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # The body's own exception is what the caller asked about; a rollback failure on top
    # of it is attached as __cause__ rather than replacing it.
    target, servicer = async_fake_server
    servicer.rollback_raises = True
    sentinel = RuntimeError("boom")
    with pytest.raises(RuntimeError) as caught:
        async with create_client(target) as client, client.transaction("db"):
            raise sentinel
    assert caught.value is sentinel
    assert isinstance(caught.value.__cause__, grpc.RpcError)


async def test_a_failing_rollback_does_not_mask_the_commit_error(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # Both calls fail. `_safe_rollback` swallowing its own failure is what makes the
    # COMMIT's error the one that surfaces - without the suppression the rollback's error
    # would replace it, and the caller would be told the wrong thing about why their
    # writes did not land. `test_commit_failure_rolls_back_and_reraises_the_commit_error`
    # alone cannot see this: its rollback succeeds, so nothing is there to mask.
    target, servicer = async_fake_server
    servicer.commit_raises = True
    servicer.rollback_raises = True
    with pytest.raises(grpc.RpcError) as caught:
        async with create_client(target) as client, client.transaction("db"):
            pass
    assert "commit failed" in str(caught.value)
    assert "rollback failed" not in str(caught.value)
    assert servicer.calls == ["BeginTransaction", "CommitTransaction", "RollbackTransaction"]
