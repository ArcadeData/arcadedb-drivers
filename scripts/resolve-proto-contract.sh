#!/usr/bin/env bash
#
# Prints the path of the single contracts/arcadedb-server-*.proto, or fails.
#
# The proto twin of resolve-openapi-contract.sh, and it exists for the same
# reason: fetch-contract.sh names each contract after its version and writes the
# new one BESIDE the old, so a version bump transiently leaves two. A glob
# resolves those in lexical order, not version order - with 26.9.1 and 26.9.2
# side by side it yields 26.9.1, the STALE one - and nothing downstream notices,
# because the committed output does match the contract it was generated from,
# just not the current one.
#
# ci.yml already counts contracts/*.proto for the TypeScript pipeline. This
# script is what lets python/scripts/generate-grpc.sh refuse locally, before CI,
# and it is deliberately usable by ci.yml later.
#
# Prints the path on stdout so a caller can substitute it; diagnostics go to stderr.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTRACTS_DIR="${1:-$(cd "$SCRIPT_DIR/.." && pwd)/contracts}"

shopt -s nullglob
PROTOS=("$CONTRACTS_DIR"/arcadedb-server-*.proto)
shopt -u nullglob

if [[ "${#PROTOS[@]}" -eq 0 ]]; then
  echo "ERROR: no $CONTRACTS_DIR/arcadedb-server-*.proto found." >&2
  echo "Run scripts/fetch-contract.sh --proto-from <arcadedb checkout> <version> first." >&2
  exit 1
fi

if [[ "${#PROTOS[@]}" -ne 1 ]]; then
  echo "ERROR: expected exactly one $CONTRACTS_DIR/arcadedb-server-*.proto, found ${#PROTOS[@]}:" >&2
  printf '  %s\n' "${PROTOS[@]}" >&2
  echo "Generating from a glob would silently pick one by lexical order - for 26.9.1 beside" >&2
  echo "26.9.2 that is the OLDER file. Retire the superseded contract first:" >&2
  echo "  scripts/adopt-contract-version.sh <version>" >&2
  exit 1
fi

printf '%s\n' "${PROTOS[0]}"
