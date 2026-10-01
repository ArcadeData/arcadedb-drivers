#!/usr/bin/env bash
#
# Regenerates go/arcadedbgrpc/generated/ from the single .proto contract.
#
# Staging: the contract is copied under the fixed name arcadedb_server.proto beside a minimal
# buf.yaml before generation. The generated filenames then carry no server version, so a
# contract bump leaves nothing to retire and no import to repoint (spec section 4).
#
# Tool resolution: `go tool` must run inside a module, so buf runs with its cwd in go/tools,
# where buf and both protoc plugins are pinned. buf resolves the plugins' ["go","tool",...]
# commands from that same cwd. All paths handed to buf are therefore absolute.
set -euo pipefail

cd "$(dirname "$0")/.."
GO_DIR="$PWD"

PROTO="$(../scripts/resolve-proto-contract.sh)"
PROTO="$(cd "$(dirname "$PROTO")" && pwd)/$(basename "$PROTO")"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cp "$PROTO" "$STAGE/arcadedb_server.proto"
printf 'version: v2\nmodules:\n  - path: .\n' >"$STAGE/buf.yaml"

(cd tools && go tool buf generate "$STAGE" \
  --template "$GO_DIR/arcadedbgrpc/generated/buf.gen.yaml" \
  -o "$GO_DIR/arcadedbgrpc/generated")

(cd arcadedbgrpc && go mod tidy)
