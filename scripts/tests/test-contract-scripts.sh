#!/usr/bin/env bash
#
# Tests for scripts/resolve-openapi-contract.sh, scripts/resolve-proto-contract.sh
# and scripts/adopt-contract-version.sh.
#
# Both scripts exist because of failures that were INVISIBLE while they happened:
# generating a client from a stale contract, and a half-applied version bump that
# leaves the build green while every import points at a retired descriptor. So the
# tests assert the specific silent outcome, not merely that the scripts run.
#
# Each check is bounds-checked before it is asserted. An unguarded index or a
# missing file under `set -e` aborts the harness, which prints no FAIL line and
# silently skips every later check - a green-looking run that tested nothing.
# The report-contract-watch.sh section below SOURCES that script and drives its
# functions through the environment. shellcheck cannot follow a `source` into a
# runtime-resolved path, so every variable those functions read looks unused
# here. They are not: removing one turns the fingerprint assertions red. The
# directive has to sit before the first COMMAND to apply file-wide.
# shellcheck disable=SC2034
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_DIR/.." && pwd)"

PASS=0
FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS + 1)); }
bad()  { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }
check() { if [[ "$1" == "$2" ]]; then ok "$3"; else bad "$3 (expected '$2', got '$1')"; fi; }

# A throwaway repository laid out like the real one, so the scripts resolve their
# own REPO_ROOT naturally and no test-only hook is needed in production code.
make_fixture() {
  local version="$1"
  local root
  root="$(mktemp -d)"
  mkdir -p "$root/scripts" "$root/contracts" \
           "$root/typescript/packages/driver-grpc/src/gen" \
           "$root/typescript/packages/driver-grpc/test" \
           "$root/typescript/packages/driver" \
           "$root/python/packages/driver" \
           "$root/go/arcadedb/generated" \
           "$root/go/arcadedbgrpc"
  cp "$SCRIPTS_DIR/resolve-openapi-contract.sh" "$SCRIPTS_DIR/resolve-proto-contract.sh" \
     "$SCRIPTS_DIR/adopt-contract-version.sh" "$SCRIPTS_DIR/fetch-contract.sh" "$root/scripts/"
  mkdir -p "$root/fake-arcadedb/grpc/src/main/proto"
  echo 'syntax = "proto3";' > "$root/fake-arcadedb/grpc/src/main/proto/arcadedb-server.proto"
  echo '{}' > "$root/contracts/arcadedb-openapi-${version}.json"
  echo 'syntax = "proto3";' > "$root/contracts/arcadedb-server-${version}.proto"
  echo '// generated' > "$root/typescript/packages/driver-grpc/src/gen/arcadedb-server-${version}_pb.ts"
  cat > "$root/typescript/packages/driver-grpc/src/index.ts" <<TS
import { ArcadeDbService } from "./gen/arcadedb-server-${version}_pb.js";
export * from "./gen/arcadedb-server-${version}_pb.js";
TS
  cat > "$root/typescript/packages/driver-grpc/test/stream.test.ts" <<TS
import { GrpcRecordSchema } from "../src/gen/arcadedb-server-${version}_pb.js";
// The contract this client is generated from is ${version}, in prose.
TS
  cat > "$root/typescript/packages/driver-grpc/README.md" <<MD
This package was generated from \`contracts/arcadedb-server-${version}.proto\`.

Generate your own against \`contracts/arcadedb-server-<version>.proto\` if you prefer.

    "serverVersion": "${version}"

| Package | Server contract |
| --- | --- |
| 0.1.0 | ${version} |
MD
  printf '{\n  "name": "@arcadedb/driver-grpc",\n  "arcadedb": {\n    "serverVersion": "%s"\n  }\n}\n' "$version" \
    > "$root/typescript/packages/driver-grpc/package.json"
  printf '{\n  "name": "@arcadedb/driver",\n  "arcadedb": {\n    "serverVersion": "%s"\n  }\n}\n' "$version" \
    > "$root/typescript/packages/driver/package.json"
  cat > "$root/python/packages/driver/pyproject.toml" <<TOML
[project]
name = "arcadedb-driver"
version = "0.1.0"

[tool.arcadedb]
server-version = "${version}"
TOML
  cat > "$root/python/packages/driver/README.md" <<MD
This package was generated from \`contracts/arcadedb-openapi-${version}.json\`.

| Package | Server contract |
| --- | --- |
| 0.1.0 | ${version} |
MD
  cat > "$root/python/packages/driver/src_index.py" <<PY
# The contract this client is generated from is ${version}, in prose.
PY
  cat > "$root/go/arcadedb/version.go" <<GO
package arcadedb

const Version = "0.1.0"
const ServerVersion = "${version}"
GO
  cat > "$root/go/arcadedbgrpc/version.go" <<GO
package arcadedbgrpc

const Version = "0.1.0"
const ServerVersion = "${version}"
GO
  printf '// Code generated. Contract %s.\npackage generated\n' "$version" \
    > "$root/go/arcadedb/generated/client.gen.go"
  echo "$root"
}

echo "resolve-openapi-contract.sh"

FIX="$(make_fixture 26.9.1-SNAPSHOT)"
out="$("$FIX/scripts/resolve-openapi-contract.sh" "$FIX/contracts" 2>/dev/null)"; rc=$?
check "$rc" "0" "exits 0 with exactly one contract"
check "$(basename "${out:-<none>}")" "arcadedb-openapi-26.9.1-SNAPSHOT.json" "prints the single contract path"

# The defect this script exists for: openapi-typescript takes the FIRST glob
# match, and 26.9.1 sorts before 26.9.2, so a bump would silently generate from
# the OLD contract. Refusing is the whole point.
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.9.2-SNAPSHOT.json"
out="$("$FIX/scripts/resolve-openapi-contract.sh" "$FIX/contracts" 2>&1)"; rc=$?
check "$rc" "1" "refuses two contracts instead of silently picking the older one"
case "$out" in *"expected exactly one"*) ok "explains what it found" ;; *) bad "explains what it found (got: $out)" ;; esac
rm -f "$FIX/contracts/arcadedb-openapi-26.9.2-SNAPSHOT.json"

rm -f "$FIX/contracts/arcadedb-openapi-26.9.1-SNAPSHOT.json"
"$FIX/scripts/resolve-openapi-contract.sh" "$FIX/contracts" >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses when no contract is present"
rm -rf "$FIX"

echo "fetch-contract.sh --proto-from"

FIX="$(make_fixture 26.9.1-SNAPSHOT)"
# Mid-bump, --image has already written the new spec beside the old one. Deriving
# the version from "the single OpenAPI spec" is impossible at that moment, and
# without an explicit version the refresh DEADLOCKS in exactly the scenario the
# daily watch exists to handle: two specs present, --proto-from aborts, and
# adopt-contract-version.sh is never reached to resolve it.
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
"$FIX/scripts/fetch-contract.sh" --proto-from "$FIX/fake-arcadedb" >/dev/null 2>&1; rc=$?
check "$rc" "1" "still refuses to GUESS a version while two specs are present"

"$FIX/scripts/fetch-contract.sh" --proto-from "$FIX/fake-arcadedb" 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
check "$rc" "0" "accepts an explicit version while two specs are present"
if [[ -f "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto" ]]; then
  ok "writes the proto under the explicitly requested version"
else
  bad "writes the proto under the explicitly requested version"
fi

# The whole refresh sequence the workflow runs, in order, across a bump.
"$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
check "$rc" "0" "the full refresh sequence completes across a version bump"
check "$(find "$FIX/contracts" -maxdepth 1 -name '*.json' | wc -l | tr -d '[:space:]')" "1" "and leaves exactly one OpenAPI contract"

"$FIX/scripts/fetch-contract.sh" --image some:tag 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
check "$rc" "1" "rejects a version argument in a mode that has no use for one"
rm -rf "$FIX"

echo "fetch-contract.sh --release"

# gh is stubbed with a script on PATH that serves assets out of a local
# directory, so nothing leaves the machine. Like the real gh, it exits 0 when
# ANY pattern matches: a release missing one asset is otherwise silent, which is
# the case the script's per-asset check exists for.
make_release() {
  local fix="$1" version="$2" release="$1/fake-release"
  mkdir -p "$release" "$fix/bin"
  printf '%s\n' '{"paths":{"/api/v1/begin/{database}":{"post":{"responses":{"204":{"headers":{"arcadedb-session-id":{}}}}}}}}' \
    > "$release/arcadedb-openapi-${version}.json"
  printf 'syntax = "proto3";\n// released %s\n' "$version" > "$release/arcadedb-server-${version}.proto"
  (cd "$release" && for f in "arcadedb-openapi-${version}.json" "arcadedb-server-${version}.proto"; do
     shasum -a 256 "$f" > "$f.sha256"; done)
  cat > "$fix/bin/gh" <<'GH'
#!/usr/bin/env bash
dir=""; pats=()
shift 3
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pattern) pats+=("$2"); shift 2 ;;
    --dir) dir="$2"; shift 2 ;;
    *) shift ;;
  esac
done
mkdir -p "$dir"; n=0
for p in "${pats[@]}"; do
  if [[ -f "$FAKE_RELEASE/$p" ]]; then cp "$FAKE_RELEASE/$p" "$dir/"; n=$((n + 1)); fi
done
[[ "$n" -gt 0 ]] || { echo "no assets match the file pattern" >&2; exit 1; }
GH
  chmod +x "$fix/bin/gh"
}
fetch_release() { PATH="$FIX/bin:$PATH" FAKE_RELEASE="$FIX/fake-release" "$FIX/scripts/fetch-contract.sh" --release "$1"; }
count_new() { find "$FIX/contracts" -maxdepth 1 -name "*-$1.*" | wc -l | tr -d '[:space:]'; }

FIX="$(make_fixture 26.9.1)"
make_release "$FIX" 26.10.1
fetch_release 26.10.1 >/dev/null 2>&1; rc=$?
check "$rc" "0" "fetches a release carrying both contracts"
if [[ -f "$FIX/contracts/arcadedb-openapi-26.10.1.json" ]]; then ok "writes the OpenAPI contract"; else bad "writes the OpenAPI contract"; fi
if cmp -s "$FIX/fake-release/arcadedb-server-26.10.1.proto" "$FIX/contracts/arcadedb-server-26.10.1.proto"; then
  ok "writes the release's .proto byte-for-byte under the release version"
else
  bad "writes the release's .proto byte-for-byte under the release version"
fi
# The pair it writes is exactly what adopt-contract-version.sh requires.
"$FIX/scripts/adopt-contract-version.sh" 26.10.1 >/dev/null 2>&1; rc=$?
check "$rc" "0" "leaves a pair adopt-contract-version.sh accepts"
rm -rf "$FIX"

FIX="$(make_fixture 26.9.1)"
make_release "$FIX" 26.10.1
rm -f "$FIX/fake-release/arcadedb-server-26.10.1.proto" "$FIX/fake-release/arcadedb-server-26.10.1.proto.sha256"
out="$(fetch_release 26.10.1 2>&1)"; rc=$?
check "$rc" "1" "refuses a release with no .proto asset"
check "$(count_new 26.10.1)" "0" "and writes neither contract"
case "$out" in *"--proto-from"*) ok "and points at --proto-from" ;; *) bad "and points at --proto-from (got: $out)" ;; esac
rm -rf "$FIX"

FIX="$(make_fixture 26.9.1)"
make_release "$FIX" 26.10.1
rm -f "$FIX/fake-release/arcadedb-server-26.10.1.proto.sha256"
fetch_release 26.10.1 >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses a .proto with no published checksum"
check "$(count_new 26.10.1)" "0" "and writes neither contract"
rm -rf "$FIX"

FIX="$(make_fixture 26.9.1)"
make_release "$FIX" 26.10.1
echo '// tampered' >> "$FIX/fake-release/arcadedb-server-26.10.1.proto"
fetch_release 26.10.1 >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses a .proto that fails its checksum"
check "$(count_new 26.10.1)" "0" "and writes neither contract"
rm -rf "$FIX"

FIX="$(make_fixture 26.9.1)"
make_release "$FIX" 26.10.1
(cd "$FIX/fake-release" && echo '{"paths":{}}' > arcadedb-openapi-26.10.1.json \
  && shasum -a 256 arcadedb-openapi-26.10.1.json > arcadedb-openapi-26.10.1.json.sha256)
fetch_release 26.10.1 >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses a pre-M0 OpenAPI spec"
check "$(count_new 26.10.1)" "0" "and does not leave its .proto behind"
rm -rf "$FIX"

echo "adopt-contract-version.sh"

FIX="$(make_fixture 26.9.1-SNAPSHOT)"
# A bump: both new contracts land beside the old ones, as fetch-contract.sh leaves them.
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto"
"$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
check "$rc" "0" "adopts a new version"

check "$(find "$FIX/contracts" -maxdepth 1 -name 'arcadedb-openapi-*.json' | wc -l | tr -d '[:space:]')" "1" "retires the superseded OpenAPI contract"
check "$(find "$FIX/contracts" -maxdepth 1 -name 'arcadedb-server-*.proto' | wc -l | tr -d '[:space:]')" "1" "retires the superseded proto"
check "$(find "$FIX/typescript/packages/driver-grpc/src/gen" -maxdepth 1 -name '*_pb.ts' | wc -l | tr -d '[:space:]')" "0" "retires the orphaned generated module"

src="$FIX/typescript/packages/driver-grpc/src/index.ts"
if [[ -f "$src" ]] && ! grep -q "26.9.1-SNAPSHOT" "$src" && grep -q "arcadedb-server-26.10.1-SNAPSHOT_pb.js" "$src"; then
  ok "repoints src imports at the new generated module"
else
  bad "repoints src imports at the new generated module"
fi

tst="$FIX/typescript/packages/driver-grpc/test/stream.test.ts"
if [[ -f "$tst" ]] && grep -q "arcadedb-server-26.10.1-SNAPSHOT_pb.js" "$tst"; then
  ok "repoints test imports too (tests import the generated module as well)"
else
  bad "repoints test imports too"
fi

for pkg in driver driver-grpc; do
  f="$FIX/typescript/packages/$pkg/package.json"
  got="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['arcadedb']['serverVersion'])" "$f" 2>/dev/null)"
  check "${got:-<unreadable>}" "26.10.1-SNAPSHOT" "records the new serverVersion in $pkg/package.json"
done

readme="$FIX/typescript/packages/driver-grpc/README.md"
# shellcheck disable=SC2016  # the backticks are literal markdown, not a subshell
if [[ -f "$readme" ]] && grep -q 'generated from `contracts/arcadedb-server-26.10.1-SNAPSHOT.proto`' "$readme"; then
  ok "updates the README's 'generated from' line"
else
  bad "updates the README's 'generated from' line"
fi

# A bare mention of the outgoing version in a comment or a sentence must be
# repointed too. Filename patterns alone miss these, so before this was handled a
# bump left every such line stale - stating a contract version the client no
# longer used, in the one place a reader would trust.
if [[ -f "$tst" ]] && grep -q "generated from is 26.10.1-SNAPSHOT, in prose" "$tst"; then
  ok "repoints a bare version mentioned in prose"
else
  bad "repoints a bare version mentioned in prose"
fi

# A generic placeholder is instructions, not a value. Rewriting
# `arcadedb-server-<version>.proto` into a concrete version turns a general
# instruction into a claim about one release - a documentation regression that
# looks like an update. This happened on a real run before the patterns required
# the version segment to start with a digit.
if [[ -f "$readme" ]] && grep -q 'arcadedb-server-<version>.proto' "$readme"; then
  ok "leaves a generic <version> placeholder alone"
else
  bad "leaves a generic <version> placeholder alone"
fi

# The compatibility table is a historical record: 0.1.0 really was generated from
# 26.9.1-SNAPSHOT. Rewriting that row would replace a fact with a falsehood, and
# the literal repointing above is broad enough to do exactly that if unguarded.
if [[ -f "$readme" ]] && grep -qE '^\| 0\.1\.0 \| 26\.9\.1-SNAPSHOT \|' "$readme"; then
  ok "leaves the historical compatibility table row untouched"
else
  bad "leaves the historical compatibility table row untouched"
fi

# Idempotence: re-adopting the version already in force must be a clean no-op.
before="$(find "$FIX" -type f -exec shasum {} + | sort | shasum)"
"$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
after="$(find "$FIX" -type f -exec shasum {} + | sort | shasum)"
check "$rc" "0" "re-adopting the current version exits 0"
check "$after" "$before" "re-adopting the current version changes nothing"

"$FIX/scripts/adopt-contract-version.sh" 99.9.9-NOPE >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses a version whose contracts were never fetched"
rm -rf "$FIX"

echo "adopt-contract-version.sh - Python"

FIX="$(make_fixture 26.9.1-SNAPSHOT)"
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto"
"$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
check "$rc" "0" "adopts a new version with a Python package present"

PYPROJECT="$FIX/python/packages/driver/pyproject.toml"
if grep -q 'server-version = "26.10.1-SNAPSHOT"' "$PYPROJECT"; then
  ok "rewrites [tool.arcadedb] server-version in pyproject.toml"
else
  bad "rewrites [tool.arcadedb] server-version in pyproject.toml (got: $(grep server-version "$PYPROJECT"))"
fi

PYREADME="$FIX/python/packages/driver/README.md"
case "$(cat "$PYREADME")" in
  *arcadedb-openapi-26.10.1-SNAPSHOT.json*) ok "repoints the contract filename in a Python README" ;;
  *) bad "repoints the contract filename in a Python README" ;;
esac

case "$(cat "$FIX/python/packages/driver/src_index.py")" in
  *26.10.1-SNAPSHOT*) ok "repoints a prose version mention in a .py file" ;;
  *) bad "repoints a prose version mention in a .py file" ;;
esac

# The TABLE_ROW guard must cover Python files exactly as it covers TypeScript ones.
# A compatibility row records that 0.1.0 really WAS generated from 26.9.1-SNAPSHOT;
# rewriting it falsifies history rather than updating it.
if grep -q '^| 0.1.0 | 26.9.1-SNAPSHOT |$' "$PYREADME"; then
  ok "leaves the Python compatibility table row untouched"
else
  bad "leaves the Python compatibility table row untouched (the TABLE_ROW guard is not covering Python files)"
fi
rm -rf "$FIX"

# A malformed or merge-mangled pyproject must fail loudly rather than leave one of
# two keys silently stale.
FIX="$(make_fixture 26.9.1-SNAPSHOT)"
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto"
printf '[tool.arcadedb]\nserver-version = "26.9.1-SNAPSHOT"\nserver-version = "26.9.1-SNAPSHOT"\n' \
  > "$FIX/python/packages/driver/pyproject.toml"
"$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses a pyproject.toml carrying two server-version keys"
rm -rf "$FIX"

# The mirror-image case: a pyproject.toml missing the key entirely (e.g. a
# single-quoted TOML value, a mangled merge) must fail loudly too, not be
# silently accepted as "nothing to update".
FIX="$(make_fixture 26.9.1-SNAPSHOT)"
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto"
printf '[tool.arcadedb]\n' > "$FIX/python/packages/driver/pyproject.toml"
"$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses a pyproject.toml with no server-version key"
rm -rf "$FIX"

echo "adopt-contract-version.sh - Go"

FIX="$(make_fixture 26.9.1-SNAPSHOT)"
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto"
"$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
check "$rc" "0" "adopts a new version with a Go module present"

GOVER="$FIX/go/arcadedb/version.go"
if grep -qx 'const ServerVersion = "26.10.1-SNAPSHOT"' "$GOVER"; then
  ok "rewrites ServerVersion in go/arcadedb/version.go"
else
  bad "rewrites ServerVersion in go/arcadedb/version.go (got: $(grep ServerVersion "$GOVER"))"
fi
if grep -qx 'const Version = "0.1.0"' "$GOVER"; then
  ok "leaves Version in go/arcadedb/version.go untouched"
else
  bad "leaves Version in go/arcadedb/version.go untouched (got: $(grep '^const Version' "$GOVER"))"
fi
if grep -q '26.9.1-SNAPSHOT' "$FIX/go/arcadedb/generated/client.gen.go"; then
  ok "leaves go/arcadedb/generated untouched"
else
  bad "leaves go/arcadedb/generated untouched (the old version literal was rewritten)"
fi
rm -rf "$FIX"

FIX="$(make_fixture 26.9.1-SNAPSHOT)"
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto"
"$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT >/dev/null 2>&1
all_ok=1
for m in arcadedb arcadedbgrpc; do
  f="$FIX/go/$m/version.go"
  grep -qx 'const ServerVersion = "26.10.1-SNAPSHOT"' "$f" || all_ok=0
  grep -qx 'const Version = "0.1.0"' "$f" || all_ok=0
done
if [ "$all_ok" = 1 ]; then
  ok "rewrites ServerVersion in every Go module"
else
  bad "rewrites ServerVersion in every Go module (got: $(grep -h ServerVersion "$FIX"/go/*/version.go | tr '\n' ' '))"
fi
rm -rf "$FIX"

FIX="$(make_fixture 26.9.1-SNAPSHOT)"
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto"
printf 'package arcadedb\n\nconst ServerVersion = "26.9.1-SNAPSHOT"\nconst ServerVersion = "26.9.1-SNAPSHOT"\n' \
  > "$FIX/go/arcadedb/version.go"
"$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses a version.go carrying two ServerVersion consts"
rm -rf "$FIX"

FIX="$(make_fixture 26.9.1-SNAPSHOT)"
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto"
printf 'package arcadedb\n\nconst Version = "0.1.0"\n' > "$FIX/go/arcadedb/version.go"
"$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses a version.go with no ServerVersion const"
rm -rf "$FIX"

echo "adopt-contract-version.sh - version-rewrite guard (issue #44)"

# The literal substitution cannot tell a filename from a claim, and cannot know
# the claim was true before it ran. Issue #44: nine sites of the shape
# "26.9.1-SNAPSHOT and every earlier server ignore it" were silently rewritten
# into an untested claim about 26.10.1-SNAPSHOT. This fixture reproduces that
# shape, three plausible rephrasings of the same kind of claim the pattern set
# must generalize to (not just transcribe), and the things that must NOT trip
# the guard: a filename rewrite, a line a filename pattern rewrites that is
# ALSO claim-shaped (the literal replacement never touches it, so it must stay
# silent even though the words would match), a compatibility-table row (even
# one containing claim-shaped words), and an ordinary, non-claim mention of the
# outgoing version.
FIX="$(make_fixture 26.9.1-SNAPSHOT)"
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto"

STREAM="$FIX/typescript/packages/driver-grpc/src/stream.ts"
cat > "$STREAM" <<TS
// 26.9.1-SNAPSHOT and every earlier server ignore it entirely.
export const noop = 1;
TS

# Rephrasings of the same claim, in shapes issue #44's nine examples did not
# use literally: a requirement, a boundary, and an exclusivity.
REPHRASINGS="$FIX/typescript/packages/driver-grpc/src/rephrasings.ts"
cat > "$REPHRASINGS" <<TS
// requires 26.9.1-SNAPSHOT or newer
// broken until 26.9.1-SNAPSHOT
// only 26.9.1-SNAPSHOT supports this
TS

README="$FIX/typescript/packages/driver-grpc/README.md"
echo '| 9.9.9 | 26.9.1-SNAPSHOT and every earlier |' >> "$README"
# This line IS rewritten (PROTO_REF consumes the whole filename, version and
# all) and its remaining English IS claim-shaped ("and every earlier") - but
# the literal replacement finds nothing left to change once the filename
# pattern has already run, so the guard must not fire on it. A bug that
# flagged "any line a pattern touched" instead of "any line the LITERAL
# replacement touched" would bury the real signal under this kind of noise.
# shellcheck disable=SC2016  # the backticks are literal markdown, not a subshell
echo 'See `contracts/arcadedb-server-26.9.1-SNAPSHOT.proto` and every earlier contract for the schema.' >> "$README"

# A release-status claim with NO version literal on its line at all. The guard
# only ever looks at a line the literal substitution rewrote, and this one has
# nothing for that substitution to change - so it is never examined and never
# flagged, however stale or true it may be. That is correct, not a miss: three
# of the release-status patterns ("not yet in a release", "as of this
# writing", "once #NNNN lands") name no version of their own and so can only
# ever fire alongside a version rewritten on the SAME line - this fixture pins
# that a standalone instance is silently skipped rather than caught by luck.
RELEASE_STATUS="$FIX/typescript/packages/driver-grpc/src/release-status.ts"
cat > "$RELEASE_STATUS" <<TS
// The fix merged, but is not yet in a release as of this writing.
export const x = 1;
TS

out="$("$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT 2>&1 1>/dev/null)"; rc=$?
check "$rc" "0" "the guard firing does not change the script's exit code"

case "$out" in
  *"VERIFY: 4 rewritten line(s) assert something about a server version"*)
    ok "flags exactly the four claim-shaped rewritten lines" ;;
  *) bad "flags exactly the four claim-shaped rewritten lines (got: $out)" ;;
esac

case "$out" in
  *"typescript/packages/driver-grpc/src/stream.ts:1"*)
    ok "names the exact path and line number of the flagged claim" ;;
  *) bad "names the exact path and line number of the flagged claim (got: $out)" ;;
esac

case "$out" in
  *"26.10.1-SNAPSHOT and every earlier server ignore it entirely"*)
    ok "shows enough of the rewritten text to judge it" ;;
  *) bad "shows enough of the rewritten text to judge it (got: $out)" ;;
esac

case "$out" in
  *"requires 26.10.1-SNAPSHOT or newer"*) ok "generalizes to a requirement rephrasing (\"requires ... or newer\")" ;;
  *) bad "generalizes to a requirement rephrasing (got: $out)" ;;
esac

case "$out" in
  *"broken until 26.10.1-SNAPSHOT"*) ok "generalizes to a boundary rephrasing (\"until ...\")" ;;
  *) bad "generalizes to a boundary rephrasing (got: $out)" ;;
esac

case "$out" in
  *"only 26.10.1-SNAPSHOT supports this"*) ok "generalizes to an exclusivity rephrasing (\"only ...\")" ;;
  *) bad "generalizes to an exclusivity rephrasing (got: $out)" ;;
esac

case "$out" in
  *"9.9.9"*) bad "does not flag a compatibility-table row, even a claim-shaped one (got: $out)" ;;
  *) ok "does not flag a compatibility-table row, even a claim-shaped one" ;;
esac

# index.ts legitimately appears in the "repointed:" list above (it IS
# rewritten, by a filename pattern) - the guard block specifically is what must
# stay silent about it.
verify_block="${out#*VERIFY:}"
case "$verify_block" in
  *"index.ts"*) bad "does not flag a filename-only rewrite (got: $verify_block)" ;;
  *) ok "does not flag a filename-only rewrite" ;;
esac

case "$verify_block" in
  *"contract for the schema"*)
    bad "does not flag a claim-shaped line whose change came only from a filename pattern (got: $verify_block)" ;;
  *) ok "does not flag a claim-shaped line whose change came only from a filename pattern" ;;
esac

case "$out" in
  *"generated from is 26.10.1-SNAPSHOT, in prose"*)
    bad "does not flag an ordinary, non-claim version mention (got: $out)" ;;
  *) ok "does not flag an ordinary, non-claim version mention" ;;
esac

case "$verify_block" in
  *"release-status.ts"*)
    bad "does not flag a release-status claim carrying no version on its own line (got: $verify_block)" ;;
  *) ok "does not flag a release-status claim carrying no version on its own line" ;;
esac
rm -rf "$FIX"

# A guard that always speaks gets ignored: the default fixture's rewrites are
# filenames, a serverVersion key, and one ordinary prose mention - none of them
# claims about server behaviour - so nothing should print.
FIX="$(make_fixture 26.9.1-SNAPSHOT)"
echo '{}' > "$FIX/contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json"
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.10.1-SNAPSHOT.proto"
out="$("$FIX/scripts/adopt-contract-version.sh" 26.10.1-SNAPSHOT 2>&1 1>/dev/null)"; rc=$?
check "$rc" "0" "adopts cleanly when nothing qualifies for the guard"
case "$out" in
  *"VERIFY"*) bad "prints nothing when nothing qualifies for the guard (got: $out)" ;;
  *) ok "prints nothing when nothing qualifies for the guard" ;;
esac
rm -rf "$FIX"

echo "contract-watch.yml wiring"

# The script gaining a capability and the workflow USING it are two different
# facts, and the suite above only establishes the first. When --proto-from grew
# an explicit version argument, every one of those tests passed while the sole
# caller still omitted it - so the deadlock they were written to prevent was
# still live in production, and the tests could not see it.
#
# These assertions read the workflow itself. They are the only thing here that
# fails when the capability is wired up but not called.
WATCH="$REPO_ROOT/.github/workflows/contract-watch.yml"
if [[ -f "$WATCH" ]]; then
  proto_call="$(grep -E '^\s*\./scripts/fetch-contract\.sh --proto-from' "$WATCH" || true)"
  if [[ -n "$proto_call" ]] && [[ "$proto_call" =~ --proto-from[[:space:]]+[^[:space:]]+[[:space:]]+[^[:space:]]+ ]]; then
    ok "the workflow passes an explicit version to --proto-from"
  else
    bad "the workflow passes an explicit version to --proto-from (found: ${proto_call:-<no call>})"
  fi

  adopt_call="$(grep -E '^\s*\./scripts/adopt-contract-version\.sh' "$WATCH" || true)"
  if [[ -n "$adopt_call" ]] && [[ "$adopt_call" =~ adopt-contract-version\.sh[[:space:]]+[^[:space:]]+ ]]; then
    ok "the workflow passes a version to adopt-contract-version.sh"
  else
    bad "the workflow passes a version to adopt-contract-version.sh (found: ${adopt_call:-<no call>})"
  fi

  # The order is load-bearing: adopting a version asserts its proto already
  # exists, so a refresh that adopted before fetching could never complete.
  fetch_line="$(grep -n -- '--proto-from' "$WATCH" | head -1 | cut -d: -f1)"
  adopt_line="$(grep -n -- 'adopt-contract-version.sh' "$WATCH" | head -1 | cut -d: -f1)"
  if [[ -n "$fetch_line" && -n "$adopt_line" ]] && (( fetch_line < adopt_line )); then
    ok "the workflow fetches the proto before adopting the version"
  else
    bad "the workflow fetches the proto before adopting the version"
  fi
else
  bad "contract-watch.yml is readable from the test harness"
fi

echo "report-contract-watch.sh (pure functions, no gh)"

# Sourced, not executed: main() is guarded so these can be exercised offline.
# shellcheck source=/dev/null
STATE=contract-changed VERSION=26.10.1-SNAPSHOT IMAGE=img VERIFY_TS=success VERIFY_PY=success VERIFY_GO=success VERIFY_PROTO=success RUN_URL=x \
  source "$SCRIPTS_DIR/report-contract-watch.sh"

# THE defect this replaced: the body embeds the run URL, which is unique per run,
# so comparing rendered bodies is never equal and posts a "the finding changed"
# comment every single day while the code claims to be quiet. The fingerprint
# must ignore the run and track only the finding.
STATE=contract-changed VERSION=26.10.1-SNAPSHOT VERIFY_TS=success VERIFY_PY=success VERIFY_GO=success VERIFY_PROTO=success CHANGED_FILES=" M a"
RUN_URL="https://example.invalid/runs/1"; a="$(finding_fingerprint)"
RUN_URL="https://example.invalid/runs/2"; b="$(finding_fingerprint)"
check "$a" "$b" "fingerprint ignores the run URL, so an unchanged finding stays unchanged"

CHANGED_FILES=" M a
 M b"; c="$(finding_fingerprint)"
if [[ "$c" != "$a" ]]; then ok "fingerprint moves when the affected files move"; else bad "fingerprint moves when the affected files move"; fi

# Every verdict has to feed the fingerprint independently. If any one were
# dropped, that language recovering while another stayed red would leave the
# fingerprint unchanged, and report_finding would silently decline to comment
# on a finding that genuinely changed - a silent production failure with no
# other check that would catch it.
CHANGED_FILES=" M a"; VERIFY_TS=failure; d="$(finding_fingerprint)"
if [[ "$d" != "$a" ]]; then ok "fingerprint moves when the TypeScript verdict flips alone"; else bad "fingerprint moves when the TypeScript verdict flips alone"; fi
VERIFY_TS=success

VERIFY_PY=failure; e="$(finding_fingerprint)"
if [[ "$e" != "$a" ]]; then ok "fingerprint moves when the Python verdict flips alone"; else bad "fingerprint moves when the Python verdict flips alone"; fi
VERIFY_PY=success

VERIFY_GO=failure; g="$(finding_fingerprint)"
if [[ "$g" != "$a" ]]; then ok "fingerprint moves when the Go verdict flips alone"; else bad "fingerprint moves when the Go verdict flips alone"; fi
VERIFY_GO=success

VERIFY_PROTO=failure; h="$(finding_fingerprint)"
if [[ "$h" != "$a" ]]; then ok "fingerprint moves when the .proto compatibility verdict flips alone"; else bad "fingerprint moves when the .proto compatibility verdict flips alone"; fi
VERIFY_PROTO=success

# A breaking .proto with every suite green must not read as "all passing".
IMAGE=img; VERIFY_PROTO=failure; vl="$(verify_line)"; VERIFY_PROTO=success
case "$vl" in
  *'compatibility (`buf breaking` against the previous contract): **failing**'*) ok "verify_line names a breaking .proto even when every suite passes" ;;
  *) bad "verify_line names a breaking .proto even when every suite passes (got: $vl)" ;;
esac

# verify_line names the Go client when it is the only one failing.
IMAGE=img; VERIFY_GO=failure; vl="$(verify_line)"; VERIFY_GO=success
case "$vl" in
  *'`github.com/ArcadeData/arcadedb-drivers/go/arcadedb` (Go): **failing**'*) ok "verify_line names the Go client when it fails" ;;
  *) bad "verify_line names the Go client when it fails (got: $vl)" ;;
esac

# The round trip that decides whether a comment is posted.
IMAGE="arcadedata/arcadedb:26.10.1-SNAPSHOT"
REFRESH_BRANCH="chore/contract-refresh"
RUN_URL="https://example.invalid/runs/3"
body="$(build_body 2>/dev/null)"

# Assert the body is WHOLE, not merely that its first line is right. The marker
# is emitted before everything else, so a build_body that dies partway still
# satisfies a marker-only assertion - which is how these checks passed while
# stderr was reporting an unbound variable.
case "$body" in
  *"$RUN_URL"*) ok "build_body renders through to the end" ;;
  *) bad "build_body renders through to the end (truncated: ${#body} chars)" ;;
esac
check "$(marker_of "$body")" "$(finding_fingerprint)" "the marker written into the body is the one read back out"

RUN_URL="https://example.invalid/runs/4"
check "$(marker_of "$(build_body 2>/dev/null)")" "$(marker_of "$body")" "a later run with the same finding reads back the same marker"

check "$(marker_of "no marker here at all")" "" "an unmarked body yields no marker rather than a false match"

# report-contract-watch.sh sets its OWN `set -euo pipefail` (line 21), and since
# it was SOURCED above rather than run in a subshell, that -e leaked into this
# harness's shell and stayed there. Nothing between the source and here happens
# to trip it, so it went unnoticed - but the checks below deliberately capture a
# script's nonzero exit via `out="$(...)"; rc=$?`, and under -e the assignment
# itself aborts the whole harness before `rc=$?` ever runs, exactly the
# "silently skips every later check" failure mode this file's own header
# warns about. Restore the harness's own invariant (no -e, ever) before relying
# on it again.
set +e

# main() must require VERIFY_GO rather than treating an unset verdict as success.
out="$(env -i PATH="$PATH" STATE=quiet VERSION=v IMAGE=i VERIFY_TS=success VERIFY_PY=success RUN_URL=x \
  bash "$SCRIPTS_DIR/report-contract-watch.sh" 2>&1)"; rc=$?
if [[ "$rc" -ne 0 && "$out" == *VERIFY_GO* ]]; then ok "main refuses to run without VERIFY_GO"; else bad "main refuses to run without VERIFY_GO (rc=$rc out: $out)"; fi

# ...and VERIFY_PROTO, for the same reason: an unset compatibility verdict must not read as a pass.
out="$(env -i PATH="$PATH" STATE=quiet VERSION=v IMAGE=i VERIFY_TS=success VERIFY_PY=success VERIFY_GO=success RUN_URL=x \
  bash "$SCRIPTS_DIR/report-contract-watch.sh" 2>&1)"; rc=$?
if [[ "$rc" -ne 0 && "$out" == *VERIFY_PROTO* ]]; then ok "main refuses to run without VERIFY_PROTO"; else bad "main refuses to run without VERIFY_PROTO (rc=$rc out: $out)"; fi

# open_refresh_pr must COMMIT every language directory the regeneration touched.
# It once staged `contracts typescript python` and not `go`, so every automated
# refresh PR carried a Go client generated from the retired contract and turned
# the Go gates red - while CHANGED_FILES, computed from a separate list, did name
# go/. Driven against a throwaway repository with a local bare remote, and gh
# stubbed out, so nothing leaves the machine.
RPR="$(mktemp -d)"
git init -q --bare "$RPR/remote.git"
git init -q -b main "$RPR/work"
(
  cd "$RPR/work" || exit 1
  git config user.name t; git config user.email t@t
  mkdir -p contracts typescript python go
  for d in contracts typescript python go; do echo old > "$d/f"; done
  git add . && git commit -qm init
  git remote add origin "$RPR/remote.git"
  for d in contracts typescript python go; do echo new > "$d/f"; echo gen > "$d/untracked"; done
) >/dev/null 2>&1
(
  cd "$RPR/work" || exit 1
  # shellcheck disable=SC2329 # invoked by open_refresh_pr, not here
  gh() { :; }
  VERSION=v IMAGE=i VERIFY_TS=success VERIFY_PY=success VERIFY_GO=success VERIFY_PROTO=success REFRESH_BRANCH=chore/contract-refresh
  open_refresh_pr 1
) >/dev/null 2>&1
committed="$(git -C "$RPR/work" show --name-only --format= chore/contract-refresh 2>/dev/null | sort | tr '\n' ' ')"
for d in contracts typescript python go; do
  case " $committed" in
    *" $d/f $d/untracked "*) ok "open_refresh_pr commits the refreshed $d/ (modified and new files)" ;;
    *) bad "open_refresh_pr commits the refreshed $d/ (committed: $committed)" ;;
  esac
done
leftover="$(git -C "$RPR/work" status --porcelain 2>/dev/null)"
check "$leftover" "" "open_refresh_pr leaves nothing the watch detected uncommitted"
rm -rf "$RPR"

# The watch's detect step and the script share ONE list of refreshed paths, so a
# new language directory cannot be detected but not committed (or the reverse).
WATCH_YML="$REPO_ROOT/.github/workflows/contract-watch.yml"
# shellcheck disable=SC2016 # the literal text of the workflow line, unexpanded
if grep -q 'git status --porcelain -- "${REFRESH_PATHS\[@\]}"' "$WATCH_YML" \
   && grep -q 'source scripts/report-contract-watch.sh' "$WATCH_YML"; then
  ok "contract-watch.yml detects changes over the script's REFRESH_PATHS"
else
  bad "contract-watch.yml detects changes over the script's REFRESH_PATHS"
fi
check "${REFRESH_PATHS[*]:-}" "contracts typescript python go" "REFRESH_PATHS names the contracts and every language directory"

echo "resolve-proto-contract.sh"

FIX="$(make_fixture 26.9.1-SNAPSHOT)"
out="$("$FIX/scripts/resolve-proto-contract.sh" "$FIX/contracts" 2>/dev/null)"; rc=$?
check "$rc" "0" "exits 0 with exactly one proto"
check "$(basename "${out:-<none>}")" "arcadedb-server-26.9.1-SNAPSHOT.proto" "prints the single proto path"

# Two protos: refuses rather than picking one.
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.9.2-SNAPSHOT.proto"
out="$("$FIX/scripts/resolve-proto-contract.sh" "$FIX/contracts" 2>&1)"; rc=$?
check "$rc" "1" "refuses two protos instead of silently picking the older one"
# `out` already captures stderr, so assert what it SAID and not only that it failed -
# the same thing the resolve-openapi-contract.sh section above asserts. A rc-only
# check goes green for any nonzero exit, including one from a script that broke
# before it ever got to the count.
case "$out" in *"expected exactly one"*) ok "explains what it found" ;; *) bad "explains what it found (got: $out)" ;; esac
rm -f "$FIX/contracts/arcadedb-server-26.9.2-SNAPSHOT.proto"

# No proto at all: refuses.
rm -f "$FIX"/contracts/arcadedb-server-*.proto
"$FIX/scripts/resolve-proto-contract.sh" "$FIX/contracts" >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses when no proto is present"
rm -rf "$FIX"

echo "check-proto-compat.sh"

# Driven against the REAL script, not a fixture copy: it reads the rules from the root buf.yaml
# and finds buf relative to itself, and both are what is under test. Needs buf, which every job
# that runs this suite has (npm ci installs it); a missing buf is a failure, never a skip.
COMPAT="$SCRIPTS_DIR/check-proto-compat.sh"
PDIR="$(mktemp -d)"
proto() { # proto <file> <body of message Row> [extra definitions]
  printf 'syntax = "proto3";\npackage com.arcadedb.grpc;\nmessage Row {\n%s\n}\n%s\n' "$2" "${3:-}" > "$PDIR/$1"
}
proto base.proto '  string name = 1;
  int64 count = 2;'

proto additive.proto '  string name = 1;
  int64 count = 2;
  bool flag = 3;' 'message Extra { string note = 1; }'
"$COMPAT" "$PDIR/base.proto" "$PDIR/additive.proto" >/dev/null 2>&1; rc=$?
check "$rc" "0" "passes an additive change (new field, new message)"

proto removed.proto '  string name = 1;'
out="$("$COMPAT" "$PDIR/base.proto" "$PDIR/removed.proto" 2>&1)"; rc=$?
check "$rc" "1" "fails a removed field"
case "$out" in *FAIL*breaks*) ok "and says it breaks clients" ;; *) bad "and says it breaks clients (got: $out)" ;; esac

proto renumbered.proto '  string name = 1;
  int64 count = 3;'
"$COMPAT" "$PDIR/base.proto" "$PDIR/renumbered.proto" >/dev/null 2>&1; rc=$?
check "$rc" "1" "fails a renumbered field (a wire break)"

proto retyped.proto '  string name = 1;
  string count = 2;'
"$COMPAT" "$PDIR/base.proto" "$PDIR/retyped.proto" >/dev/null 2>&1; rc=$?
check "$rc" "1" "fails a field whose type changed"

# The reason the files are staged under one fixed name: compared under their own names, two
# identical contracts with different version stamps read as one file deleted and one added.
cp "$PDIR/base.proto" "$PDIR/arcadedb-server-1.0.0.proto"
cp "$PDIR/base.proto" "$PDIR/arcadedb-server-1.1.0-SNAPSHOT.proto"
"$COMPAT" "$PDIR/arcadedb-server-1.0.0.proto" "$PDIR/arcadedb-server-1.1.0-SNAPSHOT.proto" >/dev/null 2>&1; rc=$?
check "$rc" "0" "passes identical contracts under different version-stamped names"

# Lint is reported, never a failure: upstream names new definitions in its own style.
proto lintonly.proto '  string name = 1;
  int64 count = 2;' 'enum Colour { RED = 0; GREEN = 1; }'
out="$("$COMPAT" "$PDIR/base.proto" "$PDIR/lintonly.proto" 2>&1)"; rc=$?
check "$rc" "0" "does not fail on a new lint finding"
case "$out" in *"new: ENUM_"*) ok "but reports it" ;; *) bad "but reports it (got: $out)" ;; esac

printf 'syntax = "proto3";\nmessage {\n' > "$PDIR/broken.proto"
"$COMPAT" "$PDIR/base.proto" "$PDIR/broken.proto" >/dev/null 2>&1; rc=$?
if [[ "$rc" -ne 0 ]]; then ok "fails a contract that does not compile"; else bad "fails a contract that does not compile"; fi

"$COMPAT" "$PDIR/base.proto" "$PDIR/missing.proto" >/dev/null 2>&1; rc=$?
check "$rc" "2" "refuses a missing file"
rm -rf "$PDIR"

echo
echo "passed: $PASS   failed: $FAIL"
[[ "$FAIL" -eq 0 ]]
