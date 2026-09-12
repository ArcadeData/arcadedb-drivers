#!/usr/bin/env bash
#
# Makes the whole repository consistent with one contract version.
#
# A contract refresh is not a pure regeneration. fetch-contract.sh names each
# artifact after the version it carries, so a server version bump WRITES NEW
# FILES BESIDE THE OLD ONES rather than modifying anything in place, and the
# generated gRPC module inherits that name (arcadedb-server-<version>_pb.ts).
# Everything that imports it, and every recorded `serverVersion`, still points
# at the retired version. Left alone, that state is not merely untidy:
#
#   - two contracts/arcadedb-openapi-*.json make openapi-typescript generate
#     from whichever the glob yields FIRST, which is lexical order, so 26.9.1
#     beside 26.9.2 silently generates from the older one (this is what
#     scripts/resolve-openapi-contract.sh now refuses);
#   - two contracts/*.proto make `buf generate` fail on a duplicate symbol;
#   - the old _pb.ts lingers, so the build stays GREEN while every import still
#     resolves to the stale descriptor.
#
# This script retires the previous version and adopts the new one, so a refresh
# is a mergeable change rather than a half-applied one.
#
# It deliberately does NOT touch the "Contract compatibility" tables in the
# READMEs. Those rows are a historical record - 0.1.0 really was generated from
# 26.9.1-SNAPSHOT - and rewriting them would falsify history rather than update
# it. A new row is a human decision, tied to the package version, and the script
# says so when it finishes.
#
# Idempotent: adopting the version already in force changes nothing and exits 0.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTRACTS_DIR="$REPO_ROOT/contracts"
TS_DIR="$REPO_ROOT/typescript"
GEN_DIR="$TS_DIR/packages/driver-grpc/src/gen"

if [[ $# -ne 1 || -z "${1:-}" ]]; then
  echo "Usage: $0 <version>            e.g. $0 26.10.1-SNAPSHOT" >&2
  exit 2
fi
VERSION="$1"

OPENAPI="$CONTRACTS_DIR/arcadedb-openapi-${VERSION}.json"
PROTO="$CONTRACTS_DIR/arcadedb-server-${VERSION}.proto"
for required in "$OPENAPI" "$PROTO"; do
  if [[ ! -f "$required" ]]; then
    echo "ERROR: $required does not exist." >&2
    echo "Fetch both contracts for $VERSION first:" >&2
    echo "  scripts/fetch-contract.sh --image arcadedata/arcadedb:$VERSION" >&2
    echo "  scripts/fetch-contract.sh --proto-from <path-to-arcadedb-checkout>" >&2
    exit 1
  fi
done

# 1. Retire superseded contracts and generated modules.
retire() {
  local kept="$1"; shift
  local pattern="$1"; shift
  local dir="$1"; shift
  shopt -s nullglob
  # shellcheck disable=SC2206  # $pattern must glob here - expanding it is the point
  local found=("$dir"/$pattern)
  shopt -u nullglob
  for path in "${found[@]}"; do
    if [[ "$path" != "$kept" ]]; then
      echo "  retiring $(basename "$path")"
      rm -f "$path"
    fi
  done
}

# The version currently in force, read before anything is retired. package.json is
# the authoritative record of it, and knowing the exact outgoing string is what
# lets prose references be repointed by literal match rather than by a pattern
# broad enough to hit things it should not.
PREVIOUS_VERSION="$(python3 -c "
import json, sys
try:
    print(json.load(open(sys.argv[1]))['arcadedb']['serverVersion'])
except Exception:
    print('')
" "$TS_DIR/packages/driver-grpc/package.json")"

echo "Adopting contract version $VERSION (was: ${PREVIOUS_VERSION:-unknown})" >&2
retire "$OPENAPI" 'arcadedb-openapi-*.json' "$CONTRACTS_DIR"
retire "$PROTO"   'arcadedb-server-*.proto' "$CONTRACTS_DIR"
retire "$GEN_DIR/arcadedb-server-${VERSION}_pb.ts" 'arcadedb-server-*_pb.ts' "$GEN_DIR"

# 2. Repoint every reference. Found by search rather than hardcoded: a new source
#    file that imports the generated module must not be able to escape this by
#    not being on a list.
VERSION="$VERSION" PREVIOUS_VERSION="$PREVIOUS_VERSION" REPO_ROOT="$REPO_ROOT" python3 - <<'PY'
import os, pathlib, re, json, sys

version = os.environ["VERSION"]
previous = os.environ.get("PREVIOUS_VERSION", "")
root = pathlib.Path(os.environ["REPO_ROOT"])

# An explicit table, not filesystem discovery. The "found by search rather than
# hardcoded" rule above governs FILES WITHIN a language directory - a new source
# file must not escape repointing by not being on a list. Which top-level
# directories are language clients is a different question, and a script that
# silently began rewriting any new sibling of contracts/ would be worse, not
# better. Adding a language stays a deliberate one-line change here.
LANGUAGES = {
    "typescript": {
        "suffixes": (".ts", ".md"),
        "skip_dirs": {"node_modules", ".git", "dist", "gen", ".superpowers", "docs"},
    },
    "python": {
        "suffixes": (".py", ".md", ".toml"),
        "skip_dirs": {
            "_generated",
            "__pycache__",
            ".venv",
            ".git",
            "dist",
            "build",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "docs",
        },
    },
}


def candidates():
    for language, config in LANGUAGES.items():
        base = root / language
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in config["suffixes"]:
                continue
            if any(part in config["skip_dirs"] for part in path.relative_to(root).parts):
                continue
            yield path

# The generated module's filename, e.g. ./gen/arcadedb-server-26.9.1-SNAPSHOT_pb.js,
# and the contract filenames as they appear in prose.
#
# Each requires the version segment to START WITH A DIGIT and excludes <>, so a
# deliberately generic placeholder is left alone. The README tells a reader to
# generate "against contracts/arcadedb-server-<version>.proto"; a pattern loose
# enough to match that rewrites correct, general instructions into a claim about
# one specific version, which is a documentation regression disguised as an
# update. Caught exactly that way on a real run.
PB_REF = re.compile(r"arcadedb-server-\d[^\"'/\s<>]*_pb\.js")
SPEC_REF = re.compile(r"arcadedb-openapi-\d[^\s`\"'<>]*\.json")
PROTO_REF = re.compile(r"arcadedb-server-\d[^\s`\"'<>]*\.proto")
# A recorded serverVersion, in a README snippet or a comment.
SERVER_VERSION = re.compile(r'("serverVersion":\s*")[^"]+(")')

# The compatibility table rows are historical fact, not a current value: leave
# every `| <package version> | <server version> |` row exactly as it is.
TABLE_ROW = re.compile(r"^\s*\|\s*\d+\.\d+\.\d+\s*\|")

# issue #44: the literal replacement two lines below is correct - without it a
# bump leaves every passing mention of the old version stale - but it is also
# blind. It cannot tell a filename from a claim, and it cannot know a claim was
# TRUE before it ran. In the 26.9.1 -> 26.10.1-SNAPSHOT adoption it silently
# turned nine sites of the form "26.9.1 and every earlier server ignore it" into
# an assertion about a server version nobody had tested; two became
# self-contradictory, and the prose turned out to have been off by one release
# even before the rewrite ran. Nothing downstream catches this: the drift gate
# only compares generated output, and `git diff` shows that a substitution
# happened but not that it changed a claim's truth value.
#
# So every line the literal replacement touches is checked against these
# shapes. They are deliberately NOT anchored to the version string itself: a
# line only reaches this check once the literal substitution has actually
# changed it, so the version literal is already known to be present -
# re-anchoring to it would narrow nothing and would just make the patterns
# harder to read.
#
# This is a HEURISTIC over the shape of a claim, not an enumeration of the nine
# sites that were found - recall is the whole value of this guard: a version
# that quietly misses a common rephrasing converts "nobody checked" into
# "something checked and found nothing", which is worse than no guard at all.
# So each category below is a general pattern of assertion, not a literal
# transcription of one example:
#   - comparative   ("26.9.1 and every earlier", "26.10.1 or newer/older")
#   - boundary      ("until/before/since/from 26.9.1", "26.9.1 onwards")
#   - requirement   ("requires/needs 26.10.1")
#   - exclusivity   ("only 26.10.1 supports this")
#   - release status ("fixed in 26.9.1", "not yet in a release",
#                      "as of this writing", "once #NNNN lands")
# It will still miss phrasings nobody has thought of yet - it is a net, not a
# parser of English, and a clean run is evidence of nothing beyond "no line
# matched this list of shapes."
#
# It also matches PER LINE with no lookahead or joining of adjacent lines, so a
# claim split across a line break - "26.9.1 and\nevery earlier ignores it" -
# slips through entirely. That is a known gap, not an oversight: joining lines
# is a real design change (what counts as "one claim" across a wrap?) and is
# deliberately out of scope here.
#
# And it only ever LOOKS at a line the literal substitution rewrote, which
# means a line has to contain the outgoing version string to be examined at
# all - correctly so, since the guard's job is "this adoption rewrote these
# lines, re-verify them", not "audit all prose everywhere" (that would be a
# different, noisier tool). One consequence of that scoping is not obvious
# from the category list above: the three release-status patterns
# ("not yet in a release", "as of this writing", "once #NNNN lands") name no
# version of their own, so they can only ever fire when a rewritten version
# literal ALSO appears on that same line. A standalone sentence like "the fix
# merged but is not yet in a release as of this writing" - true or false,
# stale or current - is never rewritten and therefore never seen, no matter
# how it reads. They are kept anyway: the self-contradictory sentence that
# motivated this whole guard had exactly this shape, a release-status phrase
# and a version sharing one line, which is precisely the case they catch.
CLAIM_PATTERNS = (
    # Comparative: a version named as the boundary of a range, in either
    # direction - "26.9.1 and every earlier", "26.10.1 and later",
    # "26.10.1 or newer", "26.9.1 or older".
    re.compile(
        r"\d\S*\s+(?:and|or)\s+(?:every\s+)?(?:earlier|later|newer|older|above|below|higher|lower)\b",
        re.IGNORECASE,
    ),
    # Boundary: a version marks the edge of when something is true -
    # "until 26.10.1", "before 26.10.1", "since 26.9.1", "from 26.9.1", or the
    # version leads with "26.9.1 onwards".
    re.compile(r"\b(?:until|before|since|from)\s+\d", re.IGNORECASE),
    re.compile(r"\d\S*\s+onwards\b", re.IGNORECASE),
    # Requirement: the version is a prerequisite - "requires 26.10.1",
    # "needs 26.10.1 or newer".
    re.compile(r"\b(?:requires?|needs?)\s+\d", re.IGNORECASE),
    # Exclusivity: a property is claimed to hold for one version only -
    # "only 26.10.1 supports this".
    re.compile(r"\bonly\s+\d", re.IGNORECASE),
    # Release status: the claim is about whether something has shipped at all,
    # not about a version range.
    re.compile(r"\bfixed\s+in\s+\d", re.IGNORECASE),
    re.compile(r"\bnot yet in a release\b", re.IGNORECASE),
    re.compile(r"\bas of this writing\b", re.IGNORECASE),
    re.compile(r"\bonce\s+#\d+\s+lands\b", re.IGNORECASE),
)

changed = []
guard = []
for path in candidates():
    original = path.read_text()
    out_lines = []
    for lineno, line in enumerate(original.splitlines(keepends=True), start=1):
        if TABLE_ROW.match(line):
            out_lines.append(line)
            continue
        line = PB_REF.sub(f"arcadedb-server-{version}_pb.js", line)
        line = SPEC_REF.sub(f"arcadedb-openapi-{version}.json", line)
        line = PROTO_REF.sub(f"arcadedb-server-{version}.proto", line)
        line = SERVER_VERSION.sub(rf"\g<1>{version}\g<2>", line)
        # Prose that names the outgoing version in passing - a comment explaining
        # which contract the client was generated from, a sentence in a README.
        # Matched as a literal rather than by pattern: the patterns above cover
        # filenames only, so without this a bump leaves every such mention stale
        # and quietly wrong, which is the failure this whole script exists to stop.
        before_literal = line
        if previous and previous != version:
            line = line.replace(previous, version)
        # Flag only what THIS substitution changed - not the filename patterns
        # above, which are safe by construction - and only when the result also
        # reads like a claim about server behaviour, not an ordinary mention.
        if line != before_literal and any(p.search(line) for p in CLAIM_PATTERNS):
            guard.append((path.relative_to(root), lineno, line.strip()))
        out_lines.append(line)
    updated = "".join(out_lines)
    if updated != original:
        path.write_text(updated)
        changed.append(path.relative_to(root))

# package.json carries serverVersion as real data, so edit it as JSON and keep
# the file's existing indentation and trailing newline.
for pkg in sorted((root / "typescript").glob("packages/*/package.json")):
    data = json.loads(pkg.read_text())
    contract = data.get("arcadedb")
    if isinstance(contract, dict) and contract.get("serverVersion") not in (None, version):
        contract["serverVersion"] = version
        pkg.write_text(json.dumps(data, indent=2) + "\n")
        changed.append(pkg.relative_to(root))

# pyproject.toml carries server-version as real data. Python has tomllib for
# reading and no stdlib writer, so this is a targeted line substitution that
# asserts it matched exactly once - a malformed, duplicated, or missing key fails
# loudly rather than silently leaving a stale version behind. Note this means
# pyproject.toml is processed TWICE: once above by the generic prose pass (it
# matches the ".toml" suffix, so any bare version mention in a comment gets
# repointed there), and again here by this dedicated pass over the
# `server-version` key specifically. That is deliberate, not redundant - the
# duplicate-detection below counts how many times the KEY appears, not how many
# times the VALUE (a version string) appears in the file, which the generic pass
# cannot do. A future reader "simplifying" this by dropping the dedicated pass
# would lose that guard.
PYPROJECT_SERVER_VERSION = re.compile(r'^(server-version\s*=\s*")[^"]*(")', re.MULTILINE)

for pyproject in sorted((root / "python").glob("packages/*/pyproject.toml")):
    original = pyproject.read_text()
    updated, count = PYPROJECT_SERVER_VERSION.subn(rf"\g<1>{version}\g<2>", original)
    if count != 1:
        raise SystemExit(f"{pyproject} has {count} server-version keys; expected exactly one")
    if updated != original:
        pyproject.write_text(updated)
        changed.append(pyproject.relative_to(root))

if changed:
    print("  repointed:", file=sys.stderr)
    for path in changed:
        print(f"    {path}", file=sys.stderr)
else:
    print("  no references needed repointing", file=sys.stderr)

# Report, don't gate: this script writes files as it goes, so failing here would
# leave a half-applied bump; contract-watch.yml runs this unattended and opens a
# PR, so a non-zero exit would break that automation; and there is nothing to
# fix mechanically here anyway - the remedy is a human re-verifying a claim
# against the server, which is exactly what this block asks them to do. A guard
# that always speaks gets ignored, so it prints nothing when nothing qualifies.
if guard:
    print(f"  VERIFY: {len(guard)} rewritten line(s) assert something about a server version.", file=sys.stderr)
    print("  The substitution cannot tell a filename from a claim, and cannot know the", file=sys.stderr)
    print("  claim was true before it ran. Re-verify each against the server:", file=sys.stderr)
    for path, lineno, text in guard:
        print(f"    {path}:{lineno}", file=sys.stderr)
        print(f"      ... {text} ...", file=sys.stderr)
PY

echo "Adopted $VERSION." >&2
echo "NOTE: the 'Contract compatibility' tables in the package READMEs are a historical" >&2
echo "record and were left untouched. Add a row for $VERSION when the package version changes." >&2
