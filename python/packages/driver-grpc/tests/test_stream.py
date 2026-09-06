from __future__ import annotations

from arcadedb_driver_grpc import create_client, messages

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
