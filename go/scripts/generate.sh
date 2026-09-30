#!/usr/bin/env bash
#
# Regenerates go/arcadedb/generated/client.gen.go from the single OpenAPI contract.
#
# Tool resolution: `go tool oapi-codegen` works from go/arcadedb through the go.work
# workspace (the tool is pinned in go/tools/go.mod), so the tool runs from the generated
# directory with the config's relative paths and no absolute output path is needed.
set -euo pipefail

cd "$(dirname "$0")/.."

CONTRACT="$(../scripts/resolve-openapi-contract.sh)"

(cd arcadedb/generated && go tool oapi-codegen -config oapi-codegen.yaml "$CONTRACT")
(cd arcadedb && go mod tidy)
