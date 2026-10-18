import arcadedb_driver

EXPECTED_SURFACE = {
    "APIToken",
    "ArcadeDBDatabase",
    "ArcadeDBError",
    "ArcadeDBServer",
    "AsyncArcadeDBDatabase",
    "AsyncArcadeDBServer",
    "AsyncInsertSession",
    "AsyncTransaction",
    "BatchOptions",
    "CreatedAPIToken",
    "EdgeRow",
    "InsertSession",
    "InsertSessionError",
    "IsolationLevel",
    "LoginResult",
    "NotSessionTokenError",
    "OpenTransaction",
    "QueryEnvelope",
    "QueryLanguage",
    "QueryStatus",
    "RunningQuery",
    "Session",
    "TerminateResult",
    "TimeSeriesWriteError",
    "Transaction",
    "VertexRow",
    "__version__",
    "basic_auth",
    "bearer_auth",
    "is_query_terminated",
}


def test_all_is_exactly_the_documented_surface() -> None:
    # Changing this set is a deliberate API decision, not a refactor. If this test
    # fails, update EXPECTED_SURFACE and the README's API section together.
    assert set(arcadedb_driver.__all__) == EXPECTED_SURFACE


def test_all_is_sorted_and_free_of_duplicates() -> None:
    assert arcadedb_driver.__all__ == sorted(set(arcadedb_driver.__all__))


def test_every_name_in_all_actually_resolves() -> None:
    for name in arcadedb_driver.__all__:
        assert hasattr(arcadedb_driver, name), f"__all__ names {name}, which does not exist"


def test_the_generated_package_is_not_part_of_the_public_surface() -> None:
    # `_generated` is reachable as `arcadedb_driver._generated` on purpose - `.raw`
    # returns its Client - but it must never be re-exported at the top level, or a
    # contract bump becomes a breaking change to this package's API.
    assert "_generated" not in arcadedb_driver.__all__
    assert not any(name.startswith("_") and name != "__version__" for name in arcadedb_driver.__all__)
