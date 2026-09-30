#!/usr/bin/env bash
#
# Files what the daily contract watch found: one tracking issue, and - when a
# refresh can fix it - one pull request that does. Closes the issue again when a
# later run comes back clean.
#
# Everything here is IDEMPOTENT against a single label and a single branch. The
# job runs every day; a script that created an issue per run would produce thirty
# a month, and a feed nobody reads is indistinguishable from no feed at all.
#
# Idempotency is compared on a FINGERPRINT of the finding, never on the rendered
# body. The body carries the run URL, which is unique per run, so a body-to-body
# comparison can never be equal and would post a "the finding changed" comment
# every single day while claiming to be quiet - the exact opposite of the design,
# and indistinguishable from it in the code until someone reads the run id.
#
# Consumes, from the environment: STATE, VERSION, IMAGE, VERIFY_TS, VERIFY_PY,
# VERIFY_GO, RUN_URL, TRACKING_LABEL, REFRESH_BRANCH, GH_TOKEN.
#
# Sourceable: the pure functions below can be tested without gh or a network.
set -euo pipefail

: "${TRACKING_LABEL:=contract-drift}" "${REFRESH_BRANCH:=chore/contract-refresh}"
REPO="${GITHUB_REPOSITORY:-ArcadeData/arcadedb-drivers}"

# Everything a refresh can rewrite: the contracts and every language directory.
# ONE list, read by main() for CHANGED_FILES, by open_refresh_pr() for what it
# commits, and by contract-watch.yml's detect step (which sources this script).
# Three hand-kept lists drifted once already: the commit staged `contracts
# typescript python` while detection and CHANGED_FILES named go/ too, so every
# refresh PR shipped a Go client generated from the retired contract. A new
# language directory is added here and nowhere else.
REFRESH_PATHS=(contracts typescript python go)

# Per-language, so the issue and PR bodies name WHICH client broke rather than
# just asserting that something did - "the suite fails" is not actionable, but
# "the Python client fails" tells a reader where to start.
verify_line() {
  local ts="${VERIFY_TS:-}" py="${VERIFY_PY:-}" go="${VERIFY_GO:-}"
  if [[ "$ts" == "success" && "$py" == "success" && "$go" == "success" ]]; then
    echo "All clients build and their full suites pass against \`${IMAGE:-}\`."
    return
  fi
  echo "**One or more clients FAIL against \`${IMAGE:-}\`.** See the run for which stage."
  echo
  [[ "$ts" == "success" ]] && echo "- \`@arcadedb/driver\` (TypeScript): passing" || echo "- \`@arcadedb/driver\` (TypeScript): **failing**"
  [[ "$py" == "success" ]] && echo "- \`arcadedb-driver\` (Python): passing" || echo "- \`arcadedb-driver\` (Python): **failing**"
  [[ "$go" == "success" ]] && echo "- \`github.com/ArcadeData/arcadedb-drivers/go/arcadedb\` (Go): passing" || echo "- \`github.com/ArcadeData/arcadedb-drivers/go/arcadedb\` (Go): **failing**"
}

# Everything that makes this finding what it is, and nothing that merely makes
# this RUN what it is. Two runs a day apart that found the same thing produce the
# same fingerprint; a run that found something different does not.
#
# EVERY verdict feeds the fingerprint. If only one did, TypeScript recovering
# while Python stayed red would produce an identical fingerprint to the run
# before it, and report_finding would silently decline to comment on a finding
# that genuinely changed - the exact failure the fingerprint exists to prevent,
# in a new disguise.
finding_fingerprint() {
  printf '%s\n%s\n%s\n%s\n%s\n%s\n' \
    "${STATE:-}" "${VERSION:-}" "${VERIFY_TS:-}" "${VERIFY_PY:-}" "${VERIFY_GO:-}" "${CHANGED_FILES:-}" \
    | shasum -a 256 | cut -c1-16
}

marker_of() {
  # The fingerprint as stored in an existing issue body, or empty if absent.
  sed -n 's/^<!-- contract-watch:[^:]*:\([0-9a-f]*\) -->$/\1/p' <<< "${1:-}" | head -1
}

build_body() {
  echo "<!-- contract-watch:${STATE}:$(finding_fingerprint) -->"
  echo
  case "$STATE" in
    contract-changed)
      cat <<MD
The contract served by \`$IMAGE\` no longer matches the one committed here.

$(verify_line)

Files affected by the refresh:

\`\`\`
${CHANGED_FILES:-(none)}
\`\`\`

A pull request from \`$REFRESH_BRANCH\` carries the refreshed contracts, the
regenerated output and the version adoption, so the change is reviewable as a
diff rather than as a description of one.

Reviewing it is the point of this issue: a contract change is a decision about
what the client promises, and the only moment that decision is cheap is now,
while it is one day old and attributable to a known set of commits.
MD
      ;;
    behaviour-regression)
      cat <<MD
The contract is **byte-identical** to the one committed here, and at least one
client's suite still fails against \`$IMAGE\`.

$(verify_line)

That combination is the interesting one. The server's behaviour moved under a
contract that did not, so nothing in this repository can fix it and there is no
refresh PR to open - the contract is already current. Either the server changed
behaviour without changing its contract, or the contract does not describe the
behaviour it should.
MD
      ;;
    *)
      echo "Unrecognised contract-watch state: \`$STATE\`."
      ;;
  esac
  echo
  echo "Snapshot version: \`$VERSION\` · [workflow run]($RUN_URL)"
  echo
  echo "_Maintained by \`.github/workflows/contract-watch.yml\`. Updated in place, and closed"
  echo "automatically by the first run that finds the contract current and both suites green._"
}

open_tracking_issue() {
  gh issue list --repo "$REPO" --label "$TRACKING_LABEL" --state open \
    --limit 1 --json number --jq '.[0].number // empty'
}

# A clean run has to be able to RETRACT a previous finding. Without this, a
# behaviour regression fixed upstream leaves its issue open forever, because no
# pull request exists to close it - and the issue footer would be promising a
# closure that nothing performs.
close_if_resolved() {
  local issue
  issue="$(open_tracking_issue)"
  [[ -z "$issue" ]] && return 0
  gh issue close "$issue" --repo "$REPO" --comment \
    "Resolved: [this run]($RUN_URL) found the contract current for \`$VERSION\` and both clients' suites green."
  echo "Closed issue #$issue" >&2
}

report_finding() {
  gh label create "$TRACKING_LABEL" \
    --repo "$REPO" \
    --color d93f0b \
    --description "Contract drift or behaviour regression found by the daily contract watch" \
    2>/dev/null || true

  local title body existing previous issue
  title="Contract watch: $STATE against $VERSION"
  body="$(build_body)"
  existing="$(open_tracking_issue)"

  if [[ -z "$existing" ]]; then
    local url
    url="$(gh issue create --repo "$REPO" --title "$title" --label "$TRACKING_LABEL" --body "$body")"
    issue="${url##*/}"
    echo "Opened issue #$issue" >&2
  else
    issue="$existing"
    previous="$(gh issue view "$issue" --repo "$REPO" --json body --jq .body)"
    # Always refresh the body, so the run link points at the latest evidence.
    gh issue edit "$issue" --repo "$REPO" --title "$title" --body "$body"
    if [[ "$(marker_of "$previous")" == "$(finding_fingerprint)" ]]; then
      echo "Issue #$issue already describes this exact finding; not commenting." >&2
    else
      gh issue comment "$issue" --repo "$REPO" --body \
        "The finding changed as of [this run]($RUN_URL). The description above has been updated."
      echo "Updated issue #$issue" >&2
    fi
  fi
  printf '%s' "$issue"
}

open_refresh_pr() {
  local issue="$1"
  git config user.name "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

  # -B, not -b: the branch may already exist locally, and a refresh that fails
  # only on its second run is worse than one that never worked.
  git checkout -B "$REFRESH_BRANCH"
  git add -- "${REFRESH_PATHS[@]}"
  git commit -m "chore: refresh the contract to $VERSION

Opened by the daily contract watch. Regenerated from $IMAGE, with the previous
version retired by scripts/adopt-contract-version.sh.

Refs #$issue"
  git push --force origin "$REFRESH_BRANCH"

  local open_pr pr_body
  open_pr="$(gh pr list --repo "$REPO" --head "$REFRESH_BRANCH" --state open \
    --limit 1 --json number --jq '.[0].number // empty')"
  pr_body="$(cat <<MD
Refreshes the committed contract to \`$VERSION\`, regenerates every client, and
retires the previous version's artifacts and references.

$(verify_line)

Closes #$issue

_Opened automatically by \`.github/workflows/contract-watch.yml\`, force-pushed
in place each day the contract moves._
MD
)"

  if [[ -z "$open_pr" ]]; then
    gh pr create --repo "$REPO" --base main --head "$REFRESH_BRANCH" \
      --title "chore: refresh the contract to $VERSION" --body "$pr_body"
  else
    gh pr edit "$open_pr" --repo "$REPO" \
      --title "chore: refresh the contract to $VERSION" --body "$pr_body"
    echo "Updated PR #$open_pr" >&2
  fi
}

main() {
  : "${STATE:?}" "${VERSION:?}" "${IMAGE:?}" "${VERIFY_TS:?}" "${VERIFY_PY:?}" "${VERIFY_GO:?}" "${RUN_URL:?}"
  CHANGED_FILES="$(git status --porcelain -- "${REFRESH_PATHS[@]}" || true)"
  export CHANGED_FILES

  if [[ "$STATE" == "quiet" ]]; then
    close_if_resolved
    return 0
  fi

  local issue
  issue="$(report_finding)"
  [[ "$STATE" == "contract-changed" ]] && open_refresh_pr "$issue"
  return 0
}

# Only run when executed, so the pure functions above can be sourced and tested.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
