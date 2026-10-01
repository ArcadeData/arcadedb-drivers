#!/usr/bin/env bash
#
# The Go client's drift gate, four parts, each failing with a message that says what to
# commit. Mirrors ci-python.yml's HTTP gate. Exits non-zero on the first failure.
# Runnable from any cwd, but it inspects git state, so run it in a checkout.
set -euo pipefail

cd "$(dirname "$0")/.."
# Git pathspecs below are relative to the repository root, so the script works from any cwd.
ROOT="$(git rev-parse --show-toplevel)"
GEN="go/arcadedb/generated go/arcadedbgrpc/generated"
git() { command git -C "$ROOT" "$@"; }

# Part 1: catches a MODIFIED generated file (existing path, changed content). Both trees:
# the HTTP client's (generate.sh) and the gRPC client's (generate-grpc.sh).
# $GEN is deliberately unquoted below: it is a list of pathspecs.
./scripts/generate.sh
./scripts/generate-grpc.sh
# shellcheck disable=SC2086
if ! git diff --exit-code -- $GEN; then
  echo "Generated output drifted from the committed contract - run go/scripts/generate.sh and go/scripts/generate-grpc.sh and commit the result." >&2
  exit 1
fi

# Part 2: catches an ADDED or RENAMED generated file. `git diff` is blind to untracked
# paths, so a contract that introduces a new file would leave part 1 green.
# shellcheck disable=SC2086
if [[ -n "$(git status --porcelain -- $GEN)" ]]; then
  echo "Generated output changed (untracked and/or modified files below) - commit the regenerated output:" >&2
  # shellcheck disable=SC2086
  git status --porcelain -- $GEN >&2
  exit 1
fi

# Part 3: every contract operation (HTTP) and RPC (gRPC) is generated. oapi-codegen can
# drop an operation it cannot model and exit 0, which neither check above can see; the gRPC
# test guards the same for the .proto. Each test SKIPS when it cannot find contracts/, and a
# skip must not read as a pass, so require an explicit PASS.
check_generated_test() {
  local module="$1" test="$2" what="$3" out
  out="$(cd "$module" && go test -count=1 -run "^${test}\$" -v ./ 2>&1)" || {
    echo "$out" >&2
    echo "$test failed - the generator dropped or skipped a contract $what." >&2
    exit 1
  }
  if ! grep -q -- "--- PASS: $test" <<<"$out"; then
    echo "$out" >&2
    echo "$test did not pass (a skip counts as a failure) - the contract could not be checked." >&2
    exit 1
  fi
}
check_generated_test arcadedb TestEveryOperationIsGenerated operation
check_generated_test arcadedbgrpc TestEveryRPCIsGenerated RPC

# Part 4: go.mod / go.sum are tidy. `go mod tidy` ignores go.work, so run it per module:
# EVERY module go.work uses, read from go.work itself rather than listed here, so a new
# module (go/e2e was once left out) cannot join the workspace without joining this check.
modules="$(go list -m -f '{{.Dir}}')"
if [[ -z "$modules" ]]; then
  echo "go list -m found no workspace modules - is go/go.work present?" >&2
  exit 1
fi
while IFS= read -r dir; do
  [[ -f "$dir/go.mod" ]] || continue
  (cd "$dir" && go mod tidy)
done <<<"$modules"
if ! git diff --exit-code -- 'go/*go.mod' 'go/*go.sum'; then
  echo "go.mod/go.sum are not tidy - run go mod tidy in each module and commit the result." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=all -- 'go/*go.sum' | grep '^??' || true)" ]]; then
  echo "Untracked go.sum after go mod tidy - commit it:" >&2
  git status --porcelain --untracked-files=all -- 'go/*go.sum' >&2
  exit 1
fi

echo "drift gate: clean"
