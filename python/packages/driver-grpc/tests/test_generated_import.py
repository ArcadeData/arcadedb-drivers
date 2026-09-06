"""Smoke test for the generated gRPC modules.

This task's only deliverable is a package that imports and type-checks - there is
no facade yet. This test locks in that deliverable: it proves the four generated
files produced by `scripts/generate-grpc.sh` are importable and that the message
and service names later tasks depend on are actually present.
"""

from __future__ import annotations

from arcadedb_driver_grpc._generated import arcadedb_server_pb2 as pb2
from arcadedb_driver_grpc._generated import arcadedb_server_pb2_grpc as pb2_grpc


def test_generated_pb2_exposes_expected_messages() -> None:
    assert pb2.StreamQueryRequest is not None
    assert pb2.QueryResult is not None
    assert pb2.GrpcRecord is not None
    assert pb2.InsertChunk is not None
    assert pb2.InsertSummary is not None
    assert pb2.BeginTransactionRequest is not None
    assert pb2.TransactionContext is not None


def test_generated_pb2_grpc_exposes_expected_service_types() -> None:
    assert pb2_grpc.ArcadeDbServiceStub is not None
    assert pb2_grpc.ArcadeDbServiceServicer is not None
    assert pb2_grpc.add_ArcadeDbServiceServicer_to_server is not None
