"""The declared `grpcio` floor must match what the generated stubs enforce.

`arcadedb_server_pb2_grpc.py` stamps `GRPC_GENERATED_VERSION` and raises `RuntimeError`
on import when the installed `grpcio` is older. If `pyproject.toml` declares a lower
floor, a resolver is allowed to pick a `grpcio` the package cannot import with. This
test reads both numbers and fails when they drift apart, for example after
`generate-grpc.sh` runs against a newer `grpcio-tools`.
"""

from __future__ import annotations

import re
from importlib.metadata import requires
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

_GRPC_STUB = Path(__file__).parents[1] / "src" / "arcadedb_driver_grpc" / "_generated" / "arcadedb_server_pb2_grpc.py"


def _generated_grpc_version() -> Version:
    # Read the source rather than importing it: the import is what raises when the
    # installed grpcio is too old, and this test must still report the mismatch then.
    match = re.search(r"^GRPC_GENERATED_VERSION = '([^']+)'$", _GRPC_STUB.read_text(), re.MULTILINE)
    assert match is not None, "GRPC_GENERATED_VERSION not found in the generated stubs"
    return Version(match.group(1))


def _declared_grpcio_floor() -> Version:
    requirements = [Requirement(r) for r in requires("arcadedb-driver-grpc") or []]
    (grpcio,) = (r for r in requirements if r.name == "grpcio")
    floors = [Version(s.version) for s in grpcio.specifier if s.operator == ">="]
    assert len(floors) == 1, f"expected exactly one >= bound on grpcio, got {grpcio}"
    return floors[0]


def test_declared_grpcio_floor_is_what_the_generated_stubs_require() -> None:
    assert _declared_grpcio_floor() == _generated_grpc_version()
