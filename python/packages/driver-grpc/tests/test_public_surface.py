import arcadedb_driver_grpc
import grpc

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


def test_raw_is_an_instance_attribute_and_raw_admin_is_a_guarded_property() -> None:
    # `raw`/`raw_admin` are not module-level exports, so `EXPECTED_SURFACE` above never
    # lists them and never will - this is the guard that takes their place, pinned one
    # level down on the client object a caller actually holds. Despite living in this
    # file, this is NOT the public-surface check the other tests above are: it says
    # nothing about the many public methods the instance also exposes, and everything
    # about one implementation detail those tests can't see.
    #
    # `raw` is a plain instance attribute; `raw_admin` is a PROPERTY, not an instance
    # attribute - that is what lets its insecure-channel guard fire on ACCESS rather than
    # at construction (see `ArcadeDBGrpcClient.raw_admin`'s docstring). So this pins two
    # facts at once: the instance dict holds only `raw` (plus private bookkeeping,
    # filtered out here), and `raw_admin` is a property on the class, reachable once its
    # guard is satisfied.
    channel = grpc.insecure_channel("127.0.0.1:0")
    try:
        client = arcadedb_driver_grpc.ArcadeDBGrpcClient(channel, allow_admin=True)
        instance_public_attrs = {name for name in vars(client) if not name.startswith("_")}
        assert instance_public_attrs == {"raw"}
        assert isinstance(type(client).__dict__["raw_admin"], property)
        assert client.raw_admin is not None
    finally:
        channel.close()
