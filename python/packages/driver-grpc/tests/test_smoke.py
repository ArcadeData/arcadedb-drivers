import importlib.metadata

import arcadedb_driver_grpc


def test_package_reports_its_version() -> None:
    # Against the installed distribution's metadata, not a literal: a literal here is what let a
    # hard-coded __version__ survive a release bump. uv builds that metadata from pyproject.toml's
    # [project] version, the one place a release writes. (tomllib would read pyproject.toml
    # directly, but it is 3.11+ and these tests run on the 3.10 floor.)
    assert arcadedb_driver_grpc.__version__ != ""
    assert arcadedb_driver_grpc.__version__ == importlib.metadata.version("arcadedb-driver-grpc")
