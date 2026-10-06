#!/usr/bin/env bash
#
# Is a new .proto contract safe to adopt over the previous one?
#
#   scripts/check-proto-compat.sh <previous.proto> <new.proto>
#
# Two checks, both against the previous contract rather than in the abstract:
#
#   breaking  `buf breaking` with the FILE rules from the root buf.yaml. A failure means the
#             new contract changes the wire format or the generated code in a way a client
#             built from the previous one would notice: a removed or renumbered field, a
#             renamed message, an RPC whose type moved. That is not automatically wrong -
#             upstream may break on purpose - but it must never be adopted silently. The
#             drift gates cannot tell: they prove generated output is REPRODUCIBLE from the
#             committed contract, not that the change to it was SAFE.
#
#   lint      `buf lint` with the root buf.yaml's STANDARD rules, REPORTED, never failing. The
#             contract is ArcadeDB's and is never edited here, and it carries dozens of findings
#             (enum value prefixes, RPC request/response naming, the package name) that are
#             upstream style choices nobody here can fix, so a lint gate would be permanently
#             red. A ratchet - fail only on findings the previous contract lacked - was tried
#             and rejected on evidence: replayed over this repository's own history, every
#             refresh that added an RPC "introduced" findings, because upstream names new RPCs
#             in the same style as the old ones (26.9.1 -> 26.11.1-SNAPSHOT: 27 of them, every
#             one an added definition, none a regression). A gate that fires on every additive
#             change gets ignored. What changed is printed, so a reviewer sees it.
#             `buf breaking`, replayed over the same history, flagged nothing: every refresh
#             so far was additive.
#
# Both files are staged under one fixed name, arcadedb_server.proto, the way
# go/scripts/generate-grpc.sh stages them. The contracts' own filenames embed the version,
# and buf's FILE rules key on the path, so comparing them as named would report the whole
# previous file deleted and a new one added - every refresh "breaking" for a reason that is
# not a change at all. The fixed name also keeps FILE_LOWER_SNAKE_CASE from flagging the
# version-stamped name, which is a convention of this repository, not of the contract.
#
# Paths are explicit, never globbed: during a refresh contracts/ transiently holds two
# .proto files, and that is exactly when this check matters. The caller resolves the pair.
#
# buf: $BUF if set, else typescript/node_modules/.bin/buf (npm ci), else `go tool buf` from
# go/tools. Both pins are 1.73.0.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <previous.proto> <new.proto>" >&2
  exit 2
fi
PREVIOUS="$1"
NEW="$2"
for f in "$PREVIOUS" "$NEW"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: $f does not exist." >&2
    exit 2
  fi
done

buf() {
  if [[ -n "${BUF:-}" ]]; then
    "$BUF" "$@"
  elif [[ -x "$REPO_ROOT/typescript/node_modules/.bin/buf" ]]; then
    "$REPO_ROOT/typescript/node_modules/.bin/buf" "$@"
  else
    (cd "$REPO_ROOT/go/tools" && go tool buf "$@")
  fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# The rules come from the root buf.yaml, so there is one place that says what is checked. Only
# its top-level `lint:` and `breaking:` blocks are copied, each up to the next top-level key:
# anything else there (`modules: - path: contracts`, a future `deps:`) describes the repository
# layout and would not resolve against this flat staging directory. The staged module is the
# directory itself, stated explicitly as go/scripts/generate-grpc.sh does (buf v2 also defaults
# to it; verified: a FILE-only break is caught under FILE and passes under WIRE either way).
stage() {
  local dir="$WORK/$1" src="$2"
  mkdir -p "$dir"
  cp "$src" "$dir/arcadedb_server.proto"
  {
    printf 'version: v2\nmodules:\n  - path: .\n'
    awk '/^[^[:space:]#]/ { keep = ($0 ~ /^(lint|breaking):/) } keep' "$REPO_ROOT/buf.yaml"
  } > "$dir/buf.yaml"
}
stage previous "$PREVIOUS"
stage new "$NEW"

failed=0

echo "buf breaking: $(basename "$NEW") against $(basename "$PREVIOUS")"
if breaking="$(cd "$WORK/new" && buf breaking . --against "$WORK/previous" 2>&1)"; then
  echo "  OK: no breaking change"
else
  while IFS= read -r line; do echo "  $line"; done <<<"$breaking"
  echo "  FAIL: the new contract breaks clients generated from the previous one."
  failed=1
fi

# One finding per line, keyed on rule and message only: line numbers move whenever anything
# above them changes, so keying on them would report every finding below an insertion as new.
findings() {
  local out rc=0
  out="$(cd "$WORK/$1" && buf lint . --error-format=json 2>&1)" || rc=$?
  # buf exits 100 when it found lint failures and anything else non-zero when it could not
  # lint at all; the second must not read as "no findings".
  if [[ "$rc" -ne 0 && "$rc" -ne 100 ]]; then
    echo "ERROR: buf lint could not run on the $1 contract:" >&2
    echo "$out" >&2
    return 1
  fi
  [[ -z "$out" ]] && return 0
  # A contract that does not compile also exits 100, its parse errors reported as findings of
  # type COMPILE. Those are not upstream style to tolerate; they mean lint could not run at all.
  if jq -e -s 'any(.[]; .type == "COMPILE")' <<<"$out" >/dev/null; then
    echo "ERROR: the $1 contract does not compile:" >&2
    jq -r 'select(.type == "COMPILE") | "  \(.message)"' <<<"$out" >&2
    return 1
  fi
  jq -r '"\(.type): \(.message)"' <<<"$out" | sort -u
}

# Captured with `||` rather than left to `set -e`: a contract that does not compile has already
# failed `buf breaking` above, and the run should still end with this section's summary and
# `exit "$failed"` rather than stop mid-report.
lint_ok=1
previous_findings="$(findings previous)" || lint_ok=0
new_findings="$(findings new)" || lint_ok=0
introduced="$(comm -13 <(printf '%s\n' "$previous_findings") <(printf '%s\n' "$new_findings") | sed '/^$/d')"
count() { if [[ -z "$1" ]]; then echo 0; else wc -l <<<"$1" | tr -d '[:space:]'; fi; }

if [[ "$lint_ok" -eq 0 ]]; then
  echo "buf lint (report only): could not run on both contracts (see the error above)"
  failed=1
  exit "$failed"
fi
echo "buf lint (report only): $(count "$previous_findings") finding(s) before, $(count "$new_findings") after"
if [[ -z "$introduced" ]]; then
  echo "  no new finding"
else
  while IFS= read -r line; do echo "  new: $line"; done <<<"$introduced"
  echo "  (not a failure: upstream style, see this script's header)"
fi

exit "$failed"
