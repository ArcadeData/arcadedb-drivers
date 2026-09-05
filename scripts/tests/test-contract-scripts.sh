#!/usr/bin/env bash
#
# Tests for scripts/resolve-openapi-contract.sh and scripts/adopt-contract-version.sh.
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
           "$root/python/packages/driver"
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
STATE=contract-changed VERSION=26.10.1-SNAPSHOT IMAGE=img VERIFY_TS=success VERIFY_PY=success RUN_URL=x \
  source "$SCRIPTS_DIR/report-contract-watch.sh"

# THE defect this replaced: the body embeds the run URL, which is unique per run,
# so comparing rendered bodies is never equal and posts a "the finding changed"
# comment every single day while the code claims to be quiet. The fingerprint
# must ignore the run and track only the finding.
STATE=contract-changed VERSION=26.10.1-SNAPSHOT VERIFY_TS=success VERIFY_PY=success CHANGED_FILES=" M a"
RUN_URL="https://example.invalid/runs/1"; a="$(finding_fingerprint)"
RUN_URL="https://example.invalid/runs/2"; b="$(finding_fingerprint)"
check "$a" "$b" "fingerprint ignores the run URL, so an unchanged finding stays unchanged"

CHANGED_FILES=" M a
 M b"; c="$(finding_fingerprint)"
if [[ "$c" != "$a" ]]; then ok "fingerprint moves when the affected files move"; else bad "fingerprint moves when the affected files move"; fi

# Both verdicts have to feed the fingerprint independently. If either one were
# dropped, that language recovering while the other stayed red would leave the
# fingerprint unchanged, and report_finding would silently decline to comment
# on a finding that genuinely changed - a silent production failure with no
# other check that would catch it.
CHANGED_FILES=" M a"; VERIFY_TS=failure; d="$(finding_fingerprint)"
if [[ "$d" != "$a" ]]; then ok "fingerprint moves when the TypeScript verdict flips alone"; else bad "fingerprint moves when the TypeScript verdict flips alone"; fi
VERIFY_TS=success

VERIFY_PY=failure; e="$(finding_fingerprint)"
if [[ "$e" != "$a" ]]; then ok "fingerprint moves when the Python verdict flips alone"; else bad "fingerprint moves when the Python verdict flips alone"; fi
VERIFY_PY=success

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

echo "resolve-proto-contract.sh"

FIX="$(make_fixture 26.9.1-SNAPSHOT)"
out="$("$FIX/scripts/resolve-proto-contract.sh" "$FIX/contracts" 2>/dev/null)"; rc=$?
check "$rc" "0" "exits 0 with exactly one proto"
check "$(basename "${out:-<none>}")" "arcadedb-server-26.9.1-SNAPSHOT.proto" "prints the single proto path"

# Two protos: refuses rather than picking one.
echo 'syntax = "proto3";' > "$FIX/contracts/arcadedb-server-26.9.2-SNAPSHOT.proto"
out="$("$FIX/scripts/resolve-proto-contract.sh" "$FIX/contracts" 2>&1)"; rc=$?
check "$rc" "1" "refuses two protos instead of silently picking the older one"
rm -f "$FIX/contracts/arcadedb-server-26.9.2-SNAPSHOT.proto"

# No proto at all: refuses.
rm -f "$FIX"/contracts/arcadedb-server-*.proto
"$FIX/scripts/resolve-proto-contract.sh" "$FIX/contracts" >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses when no proto is present"
rm -rf "$FIX"

echo
echo "passed: $PASS   failed: $FAIL"
[[ "$FAIL" -eq 0 ]]
