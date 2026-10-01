#!/usr/bin/env bash
# The Go module's pre-publish gates, in one place so a dry run and a real publish cannot diverge.
#
# Usage: scripts/release/verify-go.sh <arcadedb>
#
# Run from anywhere (it changes into go/ itself), in a git checkout: the drift gate inspects git
# state. Runs, in order: lint, the unit tests under the race detector, the four-part drift gate
# (which includes a clean `go mod tidy`), the recorded-server-version check against the committed
# OpenAPI contract, and the module-zip check. Exits non-zero on the first failure. It tags nothing
# and fetches nothing through the proxy - that is publish-go.yml's job, after this passes.
# publish-go.yml calls it before tagging; release.yml calls it as a dry run.
set -euo pipefail

PKG=${1:?usage: verify-go.sh <arcadedb>}
case "$PKG" in
  arcadedb) ;;
  *)
    echo "Unknown package \"$PKG\": expected arcadedb." >&2
    exit 1
    ;;
esac

# The module lives in go/<package>; every check below addresses it through this, never through
# a literal directory name.
PKG_DIR=$PKG

cd "$(dirname "$0")/../../go"

echo "==> Lint (gofmt, go vet, staticcheck) every module in go.work"
./scripts/lint.sh

echo "==> Run the unit tests under the race detector"
(cd "$PKG_DIR" && go test -race ./...)

echo "==> Run the drift gate"
./scripts/check-drift.sh

echo "==> Verify the module's ServerVersion matches the committed contract"
# The module records the ArcadeDB release it was generated against in version.go's
# ServerVersion. That must still match the committed OpenAPI contract's info.version at publish
# time, or the compatibility table the README ships would be lying the moment the version is
# fetched - and a fetched Go version can never be replaced. resolve-openapi-contract.sh refuses
# zero or two contracts, so a version bump left half-done fails here rather than comparing
# against whichever file a glob yields first.
CONTRACT="$(../scripts/resolve-openapi-contract.sh)"
contract_version="$(jq -r '.info.version // empty' "$CONTRACT")"
# `const Version` and `const ServerVersion` are separate top-level lines in version.go - the
# same shape release-packages.py reads and writes.
read_const() {
  sed -nE "s/^const $1 = \"([^\"]*)\"\$/\1/p" "$PKG_DIR/version.go"
}
server_version="$(read_const ServerVersion)"
version="$(read_const Version)"
if [[ -z "$server_version" || -z "$version" || -z "$contract_version" ]]; then
  echo "Missing version(s): Version=\"$version\", ServerVersion=\"$server_version\", $(basename "$CONTRACT") info.version=\"$contract_version\"" >&2
  exit 1
fi
if [[ "$server_version" != "$contract_version" ]]; then
  echo "go/$PKG_DIR/version.go ServerVersion (\"$server_version\") does not match $(basename "$CONTRACT")'s info.version (\"$contract_version\"). Run scripts/adopt-contract-version.sh so the contract and every package agree." >&2
  exit 1
fi
echo "OK: ServerVersion matches contract info.version ($server_version)"

echo "==> Verify the module zip"
# A file the module-zip rules reject would make the tag unfetchable, and a fetched version is
# permanent, so this runs before any tag exists. checkzip also refuses a v2+ version on a module
# path without the matching /vN suffix.
# GOWORK=off: inside the go.work workspace `go list -m` names every module, not this one.
module_path="$(cd "$PKG_DIR" && GOWORK=off go list -m)"
(cd tools && go run ./cmd/checkzip "$module_path" "v$version" "../$PKG_DIR")
