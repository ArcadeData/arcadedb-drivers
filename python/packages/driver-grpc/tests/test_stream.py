from __future__ import annotations

from collections.abc import AsyncIterator, Generator, Iterator
from typing import cast

import pytest
from arcadedb_driver_grpc import InsertStreamRequest, create_client, messages

from .conftest import RecordingServicer


def test_flattens_batches_into_individual_records(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.stream_batches = [["#1:0", "#1:1"], ["#1:2"]]
    with create_client(target) as client:
        rids = [r.rid for r in client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1"))]
    assert rids == ["#1:0", "#1:1", "#1:2"]


def test_an_empty_stream_yields_nothing_rather_than_raising(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.stream_batches = []
    with create_client(target) as client:
        assert list(client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1"))) == []


def test_retrieval_mode_and_batch_size_pass_through_untouched(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # The wrapper must pick NO defaults: CURSOR, MATERIALIZE_ALL and PAGED have
    # materially different memory and consistency behaviour that only the caller can judge.
    target, servicer = fake_server
    with create_client(target) as client:
        list(
            client.stream_query(
                messages.StreamQueryRequest(
                    database="db",
                    query="SELECT 1",
                    batch_size=7,
                    retrieval_mode=messages.StreamQueryRequest.RetrievalMode.PAGED,
                )
            )
        )
    sent = servicer.stream_query_requests[0]
    assert sent.batch_size == 7
    assert sent.retrieval_mode == messages.StreamQueryRequest.RetrievalMode.PAGED


def test_a_request_with_no_batch_size_sends_no_batch_size(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        list(client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1")))
    assert servicer.stream_query_requests[0].batch_size == 0


def _records(*rids: str) -> list[messages.GrpcRecord]:
    return [messages.GrpcRecord(rid=rid) for rid in rids]


def test_envelope_bookkeeping_across_several_chunks(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        summary = client.insert_stream(
            InsertStreamRequest(database="db", chunks=[_records("a"), _records("b"), _records("c")])
        )

    chunks = servicer.insert_chunks
    assert len(chunks) == 3
    assert [c.chunk_seq for c in chunks] == [1, 2, 3]
    # One session id, stable for the whole stream, and non-empty.
    assert len({c.session_id for c in chunks}) == 1
    assert chunks[0].session_id != ""
    # `database` on the FIRST chunk only, per the .proto contract.
    assert chunks[0].database == "db"
    assert [c.database for c in chunks[1:]] == ["", ""]
    # `last` on the FINAL chunk only.
    assert [c.last for c in chunks] == [False, False, True]
    assert summary.received == 3


def test_the_first_chunk_mirrors_database_into_options(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # Compatibility with servers predating the fix for ArcadeData/arcadedb#6597. On 26.8.1
    # and earlier the server builds InsertContext from InsertOptions.database ALONE and
    # never reads InsertChunk.database, despite the .proto marking the latter REQUIRED on
    # the first chunk. Without this mirror a stream inserts nothing - inserted=0, or a
    # deferred-commit failure with "Invalid database name: name is required". Measured
    # against real servers: 0 of 2 rows land on 26.8.1, 2 of 2 on 26.9.1 and on
    # 26.10.1-SNAPSHOT, so the fix shipped in 26.9.1 and no supported server still needs
    # the mirror. It stays because removing it is a behaviour change.
    target, servicer = fake_server
    with create_client(target) as client:
        client.insert_stream(InsertStreamRequest(database="db", chunks=[_records("a")]))
    assert servicer.insert_chunks[0].options.database == "db"


def test_mirroring_preserves_the_callers_other_options(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        client.insert_stream(
            InsertStreamRequest(
                database="db",
                chunks=[_records("a")],
                options=messages.InsertOptions(target_class="Person", server_batch_size=32),
            )
        )
    sent = servicer.insert_chunks[0].options
    assert sent.database == "db"
    assert sent.target_class == "Person"
    assert sent.server_batch_size == 32


def test_later_chunks_carry_the_callers_options_without_the_database_mirror(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # `_build_chunk`'s `elif request.options is not None` branch. The `database` mirror is
    # a first-chunk-only workaround (#6597), so it must NOT leak onto chunk 2+ - while the
    # caller's own option fields must survive on every chunk, not just the first. Asserting
    # only the first chunk (as `test_mirroring_preserves_the_callers_other_options` does)
    # leaves this branch unexercised: an implementation that dropped `options` entirely
    # after chunk 1, or that mirrored `database` onto every chunk, passes that test.
    target, servicer = fake_server
    options = messages.InsertOptions(target_class="Person")
    with create_client(target) as client:
        client.insert_stream(InsertStreamRequest(database="db", chunks=[_records("a"), _records("b")], options=options))

    sent = servicer.insert_chunks
    assert len(sent) == 2
    assert sent[0].options.target_class == "Person"
    assert sent[0].options.database == "db"
    assert sent[1].options.target_class == "Person"
    assert sent[1].options.database == ""
    # The mirror is built on a copy: the caller's own InsertOptions is not touched.
    assert options == messages.InsertOptions(target_class="Person")


def test_an_empty_stream_sends_one_empty_final_chunk_rather_than_raising(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # A filter that matched nothing is a legitimate outcome, not an error - the same
    # principle both READMEs argue for `truncated`. M1b verified against a real server
    # that such a chunk is accepted cleanly and answers an all-zero InsertSummary.
    target, servicer = fake_server
    with create_client(target) as client:
        summary = client.insert_stream(InsertStreamRequest(database="db", chunks=[]))

    assert len(servicer.insert_chunks) == 1
    only = servicer.insert_chunks[0]
    assert list(only.rows) == []
    assert only.last is True
    assert only.chunk_seq == 1
    assert only.database == "db"
    assert only.options.database == "db"
    assert summary.received == 0


def test_a_none_row_batch_is_not_confused_with_end_of_stream(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # `next(iterator, None)` would conflate a `None` row batch - easy to produce from a
    # `dict.get()` in a batching helper, and not statically ruled out for an untyped
    # caller - with genuine end-of-stream, silently dropping every chunk after it: the
    # server would report a smaller `received` and nothing would raise anywhere. The
    # private `_EndOfStream` sentinel closes that hole.
    target, servicer = fake_server
    with create_client(target) as client:
        client.insert_stream(
            InsertStreamRequest(
                database="db",
                chunks=[_records("a"), None, _records("c")],  # type: ignore[list-item]  # deliberately off-contract
            )
        )
    chunks = servicer.insert_chunks
    assert len(chunks) == 3
    assert [c.chunk_seq for c in chunks] == [1, 2, 3]
    assert [c.last for c in chunks] == [False, False, True]
    assert [list(c.rows) for c in chunks] == [[messages.GrpcRecord(rid="a")], [], [messages.GrpcRecord(rid="c")]]


def test_the_callers_iterator_is_finalised_when_the_stream_ends() -> None:
    # The chunk iterator is pulled MANUALLY, because knowing which chunk is last needs
    # one-element lookahead. Manual pulling means finalisation is not automatic, so the
    # caller's own `finally` - closing a file handle, a cursor - must still run.
    #
    # Kept as documentation of intent only: this exhaustion-only case cannot actually
    # fail. Draining a generator to `StopIteration` already runs its own `finally`
    # regardless of what the consumer does - see
    # `test_the_callers_iterator_is_finalised_when_the_stream_is_abandoned` below for the
    # case that genuinely exercises `_envelope_chunks_inner`'s `try/finally`.
    closed = False

    def chunks() -> Iterator[list[messages.GrpcRecord]]:
        nonlocal closed
        try:
            yield _records("a")
            yield _records("b")
        finally:
            closed = True

    from arcadedb_driver_grpc.stream import _envelope_chunks

    list(_envelope_chunks(InsertStreamRequest(database="db", chunks=chunks()), "session-1"))
    assert closed is True


def test_the_callers_iterator_is_finalised_when_the_stream_is_abandoned() -> None:
    # The discriminating case: the RPC (or the caller) stops consuming mid-stream while a
    # reference to the caller's iterator survives - which is the real situation, because
    # `InsertStreamRequest.chunks` holds that reference and defeats ordinary
    # refcount-triggered cleanup. Without `_envelope_chunks_inner`'s `try/finally`, `chunks()`
    # below would stay suspended forever, its own `finally` (closing a file handle, a
    # database cursor) never running.
    closed = False

    def chunks() -> Iterator[list[messages.GrpcRecord]]:
        nonlocal closed
        try:
            yield _records("a")
            yield _records("b")
            yield _records("c")
        finally:
            closed = True

    from arcadedb_driver_grpc.stream import _envelope_chunks

    request = InsertStreamRequest(database="db", chunks=chunks())  # keeps the generator alive
    # `_envelope_chunks`'s declared return type is the narrower `Iterator`, which has no
    # `.close()` - but it is always, in fact, a generator, and that is exactly the
    # abandonment behaviour this test exercises.
    envelope = cast(Generator[messages.InsertChunk, None, None], _envelope_chunks(request, "session-1"))
    next(envelope)
    envelope.close()
    assert closed is True


class _ChunksWithADataCloseAttribute:
    """An iterator carrying an unrelated `close` attribute that is plain data, not a method."""

    def __init__(self) -> None:
        self.close = "not a cleanup hook"
        self._rows = iter([_records("a"), _records("b")])

    def __iter__(self) -> Iterator[list[messages.GrpcRecord]]:
        return self

    def __next__(self) -> list[messages.GrpcRecord]:
        return next(self._rows)


def test_a_non_callable_close_attribute_does_not_raise_during_finalisation() -> None:
    # `getattr(iterator, "close", None)` alone is not enough: a caller's iterable can
    # legitimately carry an attribute named `close` that is plain data, unrelated to
    # generator cleanup - `callable(...)` is what tells the two apart. Before this fix,
    # `_envelope_chunks_inner`'s `if close is not None: close()` would try to CALL that
    # data value here and raise `TypeError: 'str' object is not callable`, instead of
    # leaving it alone.
    from arcadedb_driver_grpc.stream import _envelope_chunks

    request = InsertStreamRequest(database="db", chunks=_ChunksWithADataCloseAttribute())
    assert len(list(_envelope_chunks(request, "session-1"))) == 2


def test_an_async_iterable_is_rejected_before_grpc_ever_sees_it(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # The isinstance guard used to live inside `_envelope_chunks`'s own generator body,
    # which does not run at all until the first `next()` pull - here, only once grpc
    # starts consuming the request iterator to open the RPC. That made the TypeError
    # below never reach the caller: grpc caught it inside its own request-consumption
    # loop and re-raised an opaque `_InactiveRpcError` instead. Driving this through
    # `client.insert_stream` (not the private `_envelope_chunks` directly) is what
    # actually exercises that failure mode - a test calling `_envelope_chunks` directly
    # would pass even with the guard back inside the generator, and hide the defect.
    class _AsyncChunks:
        async def __aiter__(self) -> AsyncIterator[list[messages.GrpcRecord]]:
            yield _records("a")

    target, servicer = fake_server
    with create_client(target) as client, pytest.raises(TypeError, match="async iterable"):
        client.insert_stream(InsertStreamRequest(database="db", chunks=_AsyncChunks()))
    # No RPC was ever opened: the guard fired before grpc saw a single chunk.
    assert servicer.insert_chunks == []
