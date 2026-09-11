import arcadedb_driver_grpc

EXPECTED_SURFACE = {
    "ArcadeDBGrpcClient",
    "AsyncArcadeDBGrpcClient",
    "AsyncTransaction",
    "AsyncTransactionHandle",
    "Auth",
    "InsecureChannelError",
    "InsertStreamRequest",
    "TimeSeriesWriteStreamRequest",
    "Transaction",
    "TransactionHandle",
    "__version__",
    "bearer_auth",
    "create_client",
    "messages",
    "password_auth",
}


def test_all_is_exactly_the_documented_surface() -> None:
    # Changing this set is a deliberate API decision, not a refactor. If this test
    # fails, update EXPECTED_SURFACE and the README's API section together.
    assert set(arcadedb_driver_grpc.__all__) == EXPECTED_SURFACE


def test_all_is_sorted_and_free_of_duplicates() -> None:
    assert arcadedb_driver_grpc.__all__ == sorted(set(arcadedb_driver_grpc.__all__))


def test_every_name_in_all_actually_resolves() -> None:
    for name in arcadedb_driver_grpc.__all__:
        assert hasattr(arcadedb_driver_grpc, name), f"__all__ names {name}, which does not exist"


def test_the_generated_package_is_not_part_of_the_public_surface() -> None:
    # `messages` is the PUBLIC alias for the generated message module, and it is stable
    # across contract bumps precisely because generate-grpc.sh normalises the proto
    # filename. `_generated` itself must never be re-exported: that path is private, and
    # exporting it would make its layout part of this package's API.
    assert "_generated" not in arcadedb_driver_grpc.__all__
    assert not any(name.startswith("_") and name != "__version__" for name in arcadedb_driver_grpc.__all__)


def test_messages_exposes_the_data_plane_types() -> None:
    for name in ("StreamQueryRequest", "InsertChunk", "InsertSummary", "GrpcRecord", "TransactionContext"):
        assert hasattr(arcadedb_driver_grpc.messages, name)
