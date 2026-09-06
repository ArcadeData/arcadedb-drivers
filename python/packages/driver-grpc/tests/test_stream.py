from __future__ import annotations

from collections.abc import Iterator

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
    # Compatibility with servers predating the fix for ArcadeData/arcadedb#6597. On
    # 26.9.1 and earlier the server builds InsertContext from InsertOptions.database
    # ALONE and never reads InsertChunk.database, despite the .proto marking the latter
    # REQUIRED on the first chunk. Without this mirror every stream fails at the
    # deferred commit with "Invalid database name: name is required".
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


def test_the_callers_iterator_is_finalised_when_the_stream_ends() -> None:
    # The chunk iterator is pulled MANUALLY, because knowing which chunk is last needs
    # one-element lookahead. Manual pulling means finalisation is not automatic, so the
    # caller's own `finally` - closing a file handle, a cursor - must still run.
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
