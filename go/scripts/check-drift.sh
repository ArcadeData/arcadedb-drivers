#!/usr/bin/env bash
#
# The Go client's drift gate, four parts, each failing with a message that says what to
# commit. Mirrors ci-python.yml's HTTP gate. Exits non-zero on the first failure.
# Runnable from any cwd, but it inspects git state, so run it in a checkout.
set -euo pipefail

cd "$(dirname "$0")/.."
# Git pathspecs below are relative to the repository root, so the script works from any cwd.
ROOT="$(git rev-parse --show-toplevel)"
GEN=go/arcadedb/generated
git() { command git -C "$ROOT" "$@"; }

# Part 1: catches a MODIFIED generated file (existing path, changed content).
./scripts/generate.sh
if ! git diff --exit-code -- "$GEN"; then
  echo "Generated output drifted from the committed contract - run go/scripts/generate.sh and commit the result." >&2
  exit 1
fi

# Part 2: catches an ADDED or RENAMED generated file. `git diff` is blind to untracked
# paths, so a contract that introduces a new file would leave part 1 green.
if [[ -n "$(git status --porcelain -- "$GEN")" ]]; then
  echo "Generated output changed (untracked and/or modified files below) - commit the regenerated output:" >&2
  git status --porcelain -- "$GEN" >&2
  exit 1
fi

# Part 3: every contract operation is generated. oapi-codegen can drop an operation it
# cannot model and exit 0, which neither check above can see. The test SKIPS when it
# cannot find contracts/, and a skip must not read as a pass, so require an explicit PASS.
out="$(cd arcadedb && go test -count=1 -run '^TestEveryOperationIsGenerated$' -v ./ 2>&1)" || {
  echo "$out" >&2
  echo "TestEveryOperationIsGenerated failed - the generator dropped or skipped a contract operation." >&2
  exit 1
}
if ! grep -q -- '--- PASS: TestEveryOperationIsGenerated' <<<"$out"; then
  echo "$out" >&2
  echo "TestEveryOperationIsGenerated did not pass (a skip counts as a failure) - the contract could not be checked." >&2
  exit 1
fi

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
