"""The declared `grpcio` and `protobuf` floors must match what the generated stubs enforce.

`arcadedb_server_pb2_grpc.py` stamps `GRPC_GENERATED_VERSION` and raises `RuntimeError` on
import when the installed `grpcio` is older. `arcadedb_server_pb2.py` bakes the protoc
version into a `ValidateProtobufRuntimeVersion(...)` call that raises the same way for an
older `protobuf`. If `pyproject.toml` declares a lower floor than either stamp, a resolver is
allowed to pick a runtime the package cannot import with. These tests read each pair of
numbers and fail when they drift apart, for example after `generate-grpc.sh` runs against a
newer `grpcio-tools`.
"""

from __future__ import annotations

import re
from importlib.metadata import requires
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

_GENERATED = Path(__file__).parents[1] / "src" / "arcadedb_driver_grpc" / "_generated"


def _generated_grpcio_version() -> Version:
    # Read the source rather than importing it: the import is what raises when the
    # installed grpcio is too old, and this test must still report the mismatch then.
    source = (_GENERATED / "arcadedb_server_pb2_grpc.py").read_text()
    match = re.search(r"^GRPC_GENERATED_VERSION = '([^']+)'$", source, re.MULTILINE)
    assert match is not None, "GRPC_GENERATED_VERSION not found in the generated stubs"
    return Version(match.group(1))


def _generated_protobuf_version() -> Version:
    # Same reason to read the source: importing the module runs the validation call.
    source = (_GENERATED / "arcadedb_server_pb2.py").read_text()
    match = re.search(
        r"ValidateProtobufRuntimeVersion\(\s*_runtime_version\.Domain\.PUBLIC,\s*(\d+),\s*(\d+),\s*(\d+),",
        source,
    )
    assert match is not None, "ValidateProtobufRuntimeVersion(...) not found in the generated stubs"
    return Version(".".join(match.groups()))


def _declared_floor(package: str) -> Version:
    requirements = [Requirement(r) for r in requires("arcadedb-driver-grpc") or []]
    (requirement,) = (r for r in requirements if r.name == package)
    floors = [Version(s.version) for s in requirement.specifier if s.operator == ">="]
    assert len(floors) == 1, f"expected exactly one >= bound on {package}, got {requirement}"
    return floors[0]


def test_declared_grpcio_floor_is_what_the_generated_stubs_require() -> None:
    assert _declared_floor("grpcio") == _generated_grpcio_version()


def test_declared_protobuf_floor_is_what_the_generated_stubs_require() -> None:
    assert _declared_floor("protobuf") == _generated_protobuf_version()
