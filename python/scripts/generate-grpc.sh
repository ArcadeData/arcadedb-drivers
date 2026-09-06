#!/usr/bin/env bash
#
# Regenerates the gRPC client from the committed protobuf contract.
#
# Two things here are NOT arbitrary, and changing either produces output that is
# broken in a way the drift gate cannot see:
#
# 1. THE CONTRACT IS STAGED UNDER A NORMALISED FILENAME. protoc converts "-" to
#    "_" but treats "." as a DIRECTORY SEPARATOR. Handed
#    contracts/arcadedb-server-26.9.1.proto directly it writes
#    arcadedb_server_26/9/1_pb2.py and a service stub whose first import line is
#    `from arcadedb_server_26.9 import 1_pb2`, which is a SyntaxError - the output
#    cannot be imported at all. Staging it as `arcadedb_server.proto` sidesteps
#    that, and has the happy consequence that the generated module carries no
#    version stamp: nothing to retire on a contract bump, no imports to repoint.
#
# 2. THE STAGED PATH MIRRORS THE PYTHON PACKAGE PATH. protoc derives the generated
#    cross-file import from the proto's path relative to -I. Staged at the root,
#    the stub emits a bare `import arcadedb_server_pb2`, which resolves only if the
#    generated directory happens to be on sys.path. Staged at
#    arcadedb_driver_grpc/_generated/, it emits
#    `from arcadedb_driver_grpc._generated import arcadedb_server_pb2`, which is
#    correct for an installed wheel.
#
# --pyi_out is deliberately NOT passed: mypy-protobuf's --mypy_out writes the same
# arcadedb_server_pb2.pyi path with better stubs, and --mypy_grpc_out additionally
# types the service stub, which protoc does not do at all.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PYTHON_DIR/.." && pwd)"

PROTO="$("$REPO_ROOT/scripts/resolve-proto-contract.sh")"
PKG_DIR="$PYTHON_DIR/packages/driver-grpc/src"
REL_DIR="arcadedb_driver_grpc/_generated"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/$REL_DIR"
cp "$PROTO" "$STAGE/$REL_DIR/arcadedb_server.proto"

cd "$PYTHON_DIR"
uv run python -m grpc_tools.protoc \
  -I"$STAGE" \
  --python_out="$PKG_DIR" \
  --grpc_python_out="$PKG_DIR" \
  --mypy_out="$PKG_DIR" \
  --mypy_grpc_out="$PKG_DIR" \
  "$REL_DIR/arcadedb_server.proto"
