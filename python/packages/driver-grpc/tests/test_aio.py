from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Iterator

import grpc
import pytest
from arcadedb_driver_grpc import InsecureChannelError, InsertStreamRequest, TimeSeriesWriteStreamRequest, messages
from arcadedb_driver_grpc.aio import _envelope_chunks, _envelope_time_series_chunks, create_client
from arcadedb_driver_grpc.auth import bearer_auth, password_auth

from .conftest import RecordingServicer

pytestmark = pytest.mark.asyncio


def _records(*rids: str) -> list[messages.GrpcRecord]:
    return [messages.GrpcRecord(rid=rid) for rid in rids]


def _points(*types: str) -> list[messages.TimeSeriesPoint]:
    return [messages.TimeSeriesPoint(type=t, timestamp=1) for t in types]


async def test_raw_reaches_the_server_and_is_authenticated(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # Of the 14 data-plane RPCs the facade wraps five, so 9 are reachable only through
    # `raw` outside a transaction and 3 even inside one. The async facade attaching its
    # auth to the CHANNEL rather than to the wrapped calls is therefore the property worth
    # asserting: a call that bypasses the facade entirely still arrives authenticated.
    target, servicer = async_fake_server
    async with create_client(target, auth=bearer_auth("t0ken")) as client:
        await client.raw.ExecuteCommand(messages.ExecuteCommandRequest(database="db", command="SELECT 1"))
    assert servicer.calls == ["ExecuteCommand"]
    assert ("authorization", "Bearer t0ken") in servicer.metadata


async def test_auth_reaches_every_rpc_shape_not_only_unary_unary(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # Regression test for a real defect found against a real server during M3b's e2e
    # work: `grpc.aio.Channel.__init__` buckets each interceptor it is given with an
    # `isinstance(...)`/`elif` chain, so a SINGLE interceptor object implementing all
    # four client-interceptor protocols (this module's original combined
    # `_AsyncAuthInterceptor`) lands in only the FIRST matching bucket (unary-unary) and
    # is silently never invoked for the other three call shapes - `StreamQuery` came
    # back `UNAUTHENTICATED` even though `ExecuteCommand` on the same client, moments
    # earlier, succeeded. `async_interceptors` now returns four separate objects, one
    # per shape. This exercises unary-stream (`StreamQuery`) and stream-unary
    # (`InsertStream`) in addition to the unary-unary case
    # `test_raw_reaches_the_server_and_is_authenticated` above already covers - the two
    # additional call shapes this fake in-process server can answer without a
    # transaction.
    target, servicer = async_fake_server
    async with create_client(target, auth=bearer_auth("t0ken")) as client:
        async for _ in client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1")):
            pass
        assert ("authorization", "Bearer t0ken") in servicer.metadata

        await client.insert_stream(InsertStreamRequest(database="db", chunks=[_records("a")]))
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
    # `options.database` there too - ArcadeData/arcadedb#6597, where the server (26.8.1 and
    # earlier) builds its InsertContext from InsertOptions.database ALONE. Fixed in 26.9.1,
    # so the mirror is belt-and-braces on every supported server; it stays because removing
    # it is a behaviour change.
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


async def test_the_handles_crud_methods_forward_timeout_and_metadata_to_the_server(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # The async twin of the sync suite's equivalent test. `RecordingServicer` implements
    # only `ExecuteCommand`, so that is the one call this asserts through, but the
    # forwarding (`self._raw.<Method>(bound, timeout=, metadata=)`) is identical on all
    # six CRUD methods. Before this fix `execute_command` took only `request` and
    # calling it with `timeout=`/`metadata=` raised `TypeError`.
    target, servicer = async_fake_server
    async with create_client(target) as client, client.transaction("db") as tx:
        await tx.execute_command(
            messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1"),
            timeout=30.0,
            metadata=(("x-test-header", "hello"),),
        )
    # `grpc.aio`'s `ServicerContext.time_remaining()` answers `None` when no timeout was
    # set at all and the actual remaining seconds otherwise, so a non-`None`, bounded
    # value here is only reachable by the `timeout=30.0` above having actually reached
    # the server. Read from `command_time_remaining`/`command_metadata`, not the
    # last-call `time_remaining`/`metadata`: the `async with` block's own
    # `CommitTransaction` follows this call and would otherwise overwrite them first.
    assert servicer.command_time_remaining[0] is not None
    assert servicer.command_time_remaining[0] < 60.0
    assert ("x-test-header", "hello") in servicer.command_metadata[0]


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
    # ArcadeData/arcadedb#6607: on 26.8.1 and earlier the server ignored TransactionContext
    # for InsertStream and BulkInsert, so offering them here would have implied a guarantee
    # it did not honour - the same omission the sync handle makes. #6607 HAS since landed
    # (79d931070b, released in 26.9.1), so this pins a restriction no supported server
    # needs. Delete it when the methods are added; that is public surface, hence a release
    # decision rather than a contract-adoption change.
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


async def test_the_callers_request_object_is_left_unchanged(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # `_bind` binds onto a COPY. Binding in place would leave the caller's own request
    # carrying `database="db"` and a now-committed transaction's id after the block
    # ended, so reusing it - through `client.raw`, or in a later transaction before
    # `_bind` runs - would send a dead transaction id to the server: #5040's shape
    # reached by aliasing, in the module built to make it unrepeatable.
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    request = messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1", language="sql")
    async with create_client(target) as client, client.transaction("db") as tx:
        await tx.execute_command(request)

    # What arrived on the wire IS bound - the override is still the mechanism.
    sent = servicer.command_requests[0]
    assert sent.database == "db"
    assert sent.transaction.transaction_id == "tx-42"
    # The caller's object is byte-for-byte what they built.
    assert request == messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1", language="sql")
    assert request.database == ""
    assert request.transaction.transaction_id == ""


async def test_vector_search_through_the_handle_is_bound(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # The async twin of the sync suite's `test_vector_search_through_the_handle_is_bound`.
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    async with create_client(target) as client, client.transaction("db") as tx:
        await tx.vector_search(
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


async def test_the_callers_vector_request_object_is_left_unchanged(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    request = messages.VectorSearchRequest(index_name="v_idx", query_vector=[0.1])
    async with create_client(target) as client, client.transaction("db") as tx:
        await tx.vector_search(request)

    assert servicer.vector_requests[0].database == "db"
    assert request.database == ""
    assert request.transaction.transaction_id == ""


async def test_hybrid_and_fulltext_through_the_handle_are_bound(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    async with create_client(target) as client, client.transaction("db") as tx:
        await tx.hybrid_search(
            messages.HybridSearchRequest(database="elsewhere", vector_index_name="v_idx", query_vector=[0.1])
        )
        await tx.full_text_search(messages.FullTextSearchRequest(database="elsewhere", query_text="cat"))

    assert servicer.hybrid_requests[0].database == "db"
    assert servicer.hybrid_requests[0].transaction.transaction_id == "tx-42"
    assert servicer.fulltext_requests[0].database == "db"
    assert servicer.fulltext_requests[0].transaction.transaction_id == "tx-42"


async def test_cancelling_the_body_still_rolls_back(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # `__aexit__`'s guard is `if exc is not None`, NOT `isinstance(exc, Exception)`, so a
    # cancelled body takes the rollback branch like any other failure - and after a single
    # `task.cancel()` the CancelledError has already been delivered and `_must_cancel`
    # cleared, so the `await` inside `_rollback` does not immediately re-raise. This
    # module's docstring and the README both used to claim the opposite; this test is what
    # keeps that claim honest. (A SECOND cancellation arriving while the rollback is in
    # flight IS lost - that is the limitation `__aexit__` documents, and it is not
    # something this context manager can fix without a shielded await.)
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    entered = asyncio.Event()

    async def body() -> None:
        async with create_client(target) as client, client.transaction("db"):
            entered.set()
            await asyncio.sleep(3600)

    task = asyncio.create_task(body())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert servicer.calls == ["BeginTransaction", "RollbackTransaction"]
    assert servicer.rollback_requests[0].transaction.transaction_id == "tx-42"


async def test_an_aiter_style_class_is_finalised_when_the_stream_is_abandoned() -> None:
    # `InsertStreamRequest.chunks` is declared `AsyncIterable`, not `AsyncIterator`, and
    # deliberately so: an object with `__aiter__` but no `__anext__` of its own is a
    # legitimate caller value. For such an object `async for chunks` builds a FRESH async
    # generator every time, and `getattr(chunks, "aclose", None)` on the class instance is
    # `None` - so closing `chunks` rather than the iterator forwards the close to nothing
    # and leaves that generator suspended forever, its `finally` never running. Both
    # existing abandonment tests hand over a bare async generator, where `chunks` and its
    # iterator are the same object, so neither of them can see this.
    class _AiterChunks:
        def __init__(self) -> None:
            self.closed = False

        async def __aiter__(self) -> AsyncIterator[list[messages.GrpcRecord]]:
            try:
                yield _records("a")
                yield _records("b")
                yield _records("c")
            finally:
                self.closed = True

    source = _AiterChunks()
    request = InsertStreamRequest(database="db", chunks=source)  # keeps it alive
    envelope = _envelope_chunks(request, "session-1")
    await anext(envelope)
    await envelope.aclose()

    assert source.closed is True


class _SyncChunksWithADataCloseAttribute:
    """A sync iterator carrying an unrelated `close` attribute that is plain data, not a method."""

    def __init__(self) -> None:
        self.close = "not a cleanup hook"
        self._rows = iter([_records("a"), _records("b")])

    def __iter__(self) -> Iterator[list[messages.GrpcRecord]]:
        return self

    def __next__(self) -> list[messages.GrpcRecord]:
        return next(self._rows)


async def test_a_non_callable_close_attribute_on_the_sync_branch_does_not_raise() -> None:
    # `_aiter_chunks`'s sync branch: `getattr(iterator, "close", None)` alone is not
    # enough, because a caller's iterable can legitimately carry an attribute named
    # `close` that is plain data, unrelated to generator cleanup. Before this fix,
    # `if close is not None: close()` would try to CALL that data value here and raise
    # `TypeError: 'str' object is not callable`, instead of leaving it alone.
    request = InsertStreamRequest(database="db", chunks=_SyncChunksWithADataCloseAttribute())
    envelope = _envelope_chunks(request, "session-1")
    chunks = [chunk async for chunk in envelope]
    assert len(chunks) == 2


class _AsyncChunksWithADataAcloseAttribute:
    """An async ITERATOR (not an async-generator-function) whose `aclose` attribute is
    plain data, not a method. `__aiter__` returns `self` - unlike
    `_AiterChunks` above, whose `__aiter__` is itself an async-generator function and so
    returns a FRESH object (with a real `aclose`) on every call - so `aiter(chunks)`,
    which `_aiter_chunks` actually closes, is this very instance and its data `aclose`.
    """

    def __init__(self) -> None:
        self.aclose = "not a cleanup hook"
        self._rows = iter([_records("a"), _records("b")])

    def __aiter__(self) -> _AsyncChunksWithADataAcloseAttribute:
        return self

    async def __anext__(self) -> list[messages.GrpcRecord]:
        try:
            return next(self._rows)
        except StopIteration:
            raise StopAsyncIteration from None


async def test_a_non_callable_aclose_attribute_on_the_async_branch_does_not_raise() -> None:
    # `_aiter_chunks`'s async branch: same hazard as the sync one above, but for
    # `aclose`. Before this fix, `if aclose is not None: await aclose()` would try to
    # AWAIT-CALL that data value here and raise `TypeError`, instead of leaving it alone.
    request = InsertStreamRequest(database="db", chunks=_AsyncChunksWithADataAcloseAttribute())
    envelope = _envelope_chunks(request, "session-1")
    chunks = [chunk async for chunk in envelope]
    assert len(chunks) == 2


async def test_a_chunks_value_in_neither_half_of_the_union_is_rejected_before_the_rpc_opens(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # Both halves of the DECLARED union are accepted here, but a value in neither half
    # still has to be refused - and refused EAGERLY. `_envelope_chunks` is an async
    # generator, so a `raise` in its body would not fire until grpc pulled the first chunk
    # to open the RPC, where grpc catches it and re-raises an opaque `_InactiveRpcError`
    # ("Exception iterating requests!") instead: exactly the failure mode the sync facade's
    # eager-validation split closed. `insert_stream` being a plain `async def` is what
    # makes the guard raise in the caller's own frame instead.
    target, servicer = async_fake_server
    async with create_client(target) as client:
        with pytest.raises(TypeError, match="iterable or an async iterable"):
            await client.insert_stream(
                InsertStreamRequest(database="db", chunks=object())  # type: ignore[arg-type]  # off-contract on purpose
            )
    # No RPC was ever opened: the guard fired before grpc saw a single chunk.
    assert servicer.calls == []
    assert servicer.insert_chunks == []


async def test_write_stream_returns_the_summary_whole(async_fake_server: tuple[str, RecordingServicer]) -> None:
    # The async twin of the sync suite's `test_write_stream_returns_the_summary_whole`. A
    # successful RPC can still drop points - asserting only that it returned would pass
    # against a wrapper that discarded the reasons (D-M6-3).
    target, servicer = async_fake_server
    servicer.ts_summary = messages.TimeSeriesWriteSummary(
        received=5, written=3, dropped=2, unknown_types=["nosuchtype"], unavailable_types=["cold"]
    )
    async with create_client(target) as client:
        summary = await client.time_series_write_stream(
            TimeSeriesWriteStreamRequest(
                database="db", type="cpu", precision=messages.TS_PRECISION_SECONDS, chunks=iter([[]])
            )
        )

    assert summary.written == 3
    assert summary.dropped == 2
    assert list(summary.unknown_types) == ["nosuchtype"]
    assert list(summary.unavailable_types) == ["cold"]


async def test_write_stream_sets_the_envelope_on_every_chunk(async_fake_server: tuple[str, RecordingServicer]) -> None:
    # The async twin of the sync suite's `test_write_stream_sets_the_envelope_on_every_chunk`.
    target, servicer = async_fake_server
    credentials = messages.DatabaseCredentials(username="root", password="playwithdata")

    async def chunks() -> AsyncIterator[list[messages.TimeSeriesPoint]]:
        yield _points("cpu")
        yield _points("cpu")

    async with create_client(target) as client:
        await client.time_series_write_stream(
            TimeSeriesWriteStreamRequest(
                database="db",
                type="cpu",
                precision=messages.TS_PRECISION_SECONDS,
                chunks=chunks(),
                credentials=credentials,
            )
        )

    assert len(servicer.ts_chunks) == 2
    for chunk in servicer.ts_chunks:
        assert chunk.database == "db"
        assert chunk.type == "cpu"
        assert chunk.precision == messages.TS_PRECISION_SECONDS
        assert chunk.credentials.username == "root"


async def test_write_stream_a_sync_iterable_of_batches_is_accepted(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # The async facade takes either half of `TimeSeriesWriteStreamRequest.chunks`'s
    # declared union, the same as `insert_stream`'s.
    target, servicer = async_fake_server
    async with create_client(target) as client:
        await client.time_series_write_stream(
            TimeSeriesWriteStreamRequest(
                database="db",
                type="cpu",
                precision=messages.TS_PRECISION_SECONDS,
                chunks=[_points("cpu"), _points("cpu")],
            )
        )
    assert len(servicer.ts_chunks) == 2


async def test_write_stream_sends_zero_chunks_for_an_empty_stream(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # Mirrors Task 2's TypeScript twin and the sync suite's twin of this test: an empty
    # `chunks` sends ZERO wire chunks, unlike `insert_stream`'s single-empty-chunk special
    # case - there is no first-chunk-only field on `TimeSeriesWriteChunk` to force it.
    target, servicer = async_fake_server
    async with create_client(target) as client:
        await client.time_series_write_stream(
            TimeSeriesWriteStreamRequest(database="db", type="cpu", precision=messages.TS_PRECISION_SECONDS, chunks=[])
        )
    assert servicer.ts_chunks == []


async def test_write_stream_a_chunks_value_in_neither_half_of_the_union_is_rejected_before_the_rpc_opens(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # The async twin of `insert_stream`'s equivalent guard: refused eagerly, in the
    # caller's own frame, rather than inside `_envelope_time_series_chunks`'s generator
    # body where grpc would swallow the TypeError and re-raise its own opaque error.
    target, servicer = async_fake_server
    async with create_client(target) as client:
        with pytest.raises(TypeError, match="iterable or an async iterable"):
            await client.time_series_write_stream(
                TimeSeriesWriteStreamRequest(
                    database="db",
                    type="cpu",
                    precision=messages.TS_PRECISION_SECONDS,
                    chunks=object(),  # type: ignore[arg-type]  # off-contract on purpose
                )
            )
    assert servicer.calls == []
    assert servicer.ts_chunks == []


async def test_write_stream_the_callers_async_generator_is_finalised_when_the_stream_is_abandoned() -> None:
    # The async twin of the sync suite's finalisation test, and of
    # `test_the_callers_async_generator_is_finalised_when_the_stream_is_abandoned` for
    # `insert_stream`: `_aiter_chunks` (shared with `insert_stream`) forwards the close so
    # the caller's own generator does not stay suspended forever.
    closed = False

    async def chunks() -> AsyncIterator[list[messages.TimeSeriesPoint]]:
        nonlocal closed
        try:
            yield _points("a")
            yield _points("b")
            yield _points("c")
        finally:
            closed = True

    source = chunks()
    request = TimeSeriesWriteStreamRequest(
        database="db", type="cpu", precision=messages.TS_PRECISION_SECONDS, chunks=source
    )
    envelope = _envelope_time_series_chunks(request)
    await anext(envelope)
    await envelope.aclose()

    assert closed is True


async def test_time_series_query_flattens_nothing_but_yields_each_message(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.ts_query_results = [
        messages.TimeSeriesQueryResult(type="cpu", columns=["ts", "v"], last=False),
        messages.TimeSeriesQueryResult(type="cpu", columns=["ts", "v"], last=True, truncated=True),
    ]
    request = messages.TimeSeriesQueryRequest(database="db", type="cpu")
    async with create_client(target) as client:
        results = [r async for r in client.time_series_query(request)]

    assert [r.last for r in results] == [False, True]
    assert results[1].truncated is True


async def test_time_series_query_through_the_handle_is_bound_to_the_transaction(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    async with create_client(target) as client, client.transaction("db") as tx:
        results = [r async for r in tx.time_series_query(messages.TimeSeriesQueryRequest(type="cpu"))]
    assert results == []
    sent = servicer.ts_query_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.database == "db"


async def test_time_series_latest_through_the_handle_is_bound(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    # The async twin of the sync suite's `test_time_series_latest_through_the_handle_is_bound`.
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    async with create_client(target) as client, client.transaction("db") as tx:
        await tx.time_series_latest(
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


async def test_the_callers_time_series_latest_request_object_is_left_unchanged(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    request = messages.TimeSeriesLatestRequest(type="cpu")
    async with create_client(target) as client, client.transaction("db") as tx:
        await tx.time_series_latest(request)

    assert servicer.ts_latest_requests[0].database == "db"
    assert request.database == ""
    assert request.transaction.transaction_id == ""
