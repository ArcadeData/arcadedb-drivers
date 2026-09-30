# One release, every driver: orchestrating publishes from `release.yml`

**Date:** 2026-09-30.
**Related:** M9 (`2026-09-16-m9-java-http-driver-design.md`, section 9 — `publish-java.yml`);
#41 (adopt the released 26.10.1 and publish 0.2.0).

## 1. What this builds

A release today is four manual dispatches: `publish.yml` for `driver` and `driver-grpc`, and
`publish-python.yml` for the same two. Each dispatch checks its own package's version and nothing
else, so nothing guarantees that the four packages ship the same version, nothing tags the commit
they shipped from, and nothing writes release notes. Java (M9) adds a third registry and Go a
fourth; the dispatch count grows with every package.

This design adds one release, in two phases, that versions every driver in lockstep:

1. **Prepare** — a human dispatches `release.yml` with a version. It verifies every package agrees,
   dry-runs every package's publish gates, pushes the tag, and drafts a GitHub release with
   generated notes.
2. **Publish** — the human reviews and publishes the draft. That event fans out to each registry's
   existing publish workflow, waits for all of them, and records what shipped on the release.

Publishing the draft is the approval for the irreversible step. A problem found in the notes, or in
phase 1, costs nothing.

## 2. The premises, checked

- **"Four runs."** True: two workflows × two packages, each dispatch publishing exactly one
  (`publish.yml:15`, `publish-python.yml:15`).
- **"JReleaser implements the release."** Not here. JReleaser's deployers are Maven-only (Maven
  Central, Nexus 2/3, Artifactory, GitHub/GitLab/Gitea/Forgejo packages, Azure); it cannot publish
  to npm or PyPI. What remained for it — a changelog and a draft GitHub release — `gh release
  create` does natively, and this repository has no Java driver for its Maven Central support to
  serve. It is dropped (D5).
- **Trusted publishing is keyed on the top-level workflow.** PyPI documents that a reusable
  workflow cannot be the workflow in a trusted publisher, and npm keys on the workflow filename.
  An orchestrator that *called* the publish workflows as reusable workflows would move every OIDC
  claim onto its own filename, forcing all four trusted publishers to be reconfigured (the npm ones
  through an interactive 2FA login each). This design instead *dispatches* them, so each child run
  is a top-level `workflow_dispatch` run of the same file it is today and **no trusted publisher
  changes**.
- **Lockstep is free to adopt.** All four packages are at `0.1.0` today.

## 3. Decisions

| # | Decision | Chosen | Rejected |
|---|---|---|---|
| D1 | Where the human gate sits | Draft release; publishing it triggers the registries | One dispatch straight through; tag-push trigger |
| D2 | Who writes the version into manifests | `scripts/set-release-version.sh` in a reviewed PR; the workflow only verifies | Workflow commits to `main` (push rights on an unprotected branch); tag-derived versions (fights every build tool and the drift gates) |
| D3 | How publishes are orchestrated | `release.yml` dispatches the existing per-registry workflows | One `release.yml` with inline publish jobs (reconfigures every trusted publisher); JReleaser shelling out to `npm`/`twine` via hooks |
| D4 | SNAPSHOT contracts | Refused by phase 1 | Left to memory |
| D5 | Release notes and the draft release | `gh release create --draft --generate-notes`, categories in `.github/release.yml` | JReleaser (a downloaded JVM binary in a `contents: write` job, invisible to `check-licenses.py`, for two things `gh` already does) |

D4 makes enforceable what the 26.10.1 migration spec records as its own D3: nothing publishes until
a released contract exists.

## 4. The package table

One table drives both the version script and the workflow, so adding a package is one row.

`scripts/release-packages.py` (Python, stdlib only: it has to parse `package.json`, TOML and
`uv.lock` and compare versions, which shell does badly) holds `PACKAGES` — one row per published
package — and prints it as JSON for `release.yml` to build its matrices from:

| Field | `driver` (npm) example |
|---|---|
| `id` | `npm-driver` |
| `language` | `typescript` |
| `manifest` | `typescript/packages/driver/package.json` |
| `lockfile` | `typescript/package-lock.json` |
| `registry` | `npm` |
| `name` | `@arcadedb/driver` |
| `workflow` | `publish.yml` |
| `package_input` | `driver` |

Today's rows: `npm-driver`, `npm-driver-grpc`, `pypi-driver`, `pypi-driver-grpc`. Per-registry
behaviour — how to read and write a manifest's version, how to ask whether a version is already
published — is keyed on `registry`, not on the row, so a second package on a known registry is a
row and nothing else.

**`scripts/set-release-version.sh <version>`** rewrites every row's **own** package version and
then reads each back, failing unless every manifest yields the new version exactly once. It never
touches `arcadedb.serverVersion` or `[tool.arcadedb] server-version`; those belong to
`adopt-contract-version.sh`. The two scripts are deliberately separate: a contract move and a
release are different decisions made at different times.

Both are covered by new cases in `scripts/tests/test-contract-scripts.sh` (or a sibling
`test-release-scripts.sh` run from the same CI step): every row rewritten; no server version
touched; a manifest matching zero or two times fails; the JSON output parses and carries every
field.

## 5. Phase 1 — prepare

Trigger: `workflow_dispatch` on `main`, inputs `version` (string) and `dry-run` (boolean, default
`false`). Permissions default to `contents: read`.

1. **Verify agreement.**
   - `version` is semver without a leading `v`.
   - Every row's manifest version equals `version`.
   - Every package's server version equals the committed contracts (the OpenAPI `info.version`,
     and the `.proto` filename version) — the same checks the publish workflows run today.
   - No server version ends in `-SNAPSHOT` (D4).
   - Tag `v<version>` does not exist locally or on the remote.
2. **Dry-run every package.** A matrix job per row (`fail-fast: false`) runs that registry's
   verify script: tests, build, and the dist/wheel content assertions — stopping short of
   publishing. The gates currently inline in `publish.yml` and `publish-python.yml` move into
   `scripts/release/verify-npm.sh` and `scripts/release/verify-pypi.sh`, taking the package as an
   argument; the publish workflows call the same scripts. The dry run and the real run therefore
   cannot diverge in what they check. The existing step comments move with the code they explain.
3. **Tag** (skipped when `dry-run`). An annotated `v<version>` on the verified commit, pushed by a
   job holding `contents: write` — the only job in phase 1 that does.
4. **Draft notes** (skipped when `dry-run`). `gh release create` creates a **draft** GitHub
   release on the existing tag (section 7). Same job as the tag, so the write grant is not widened to a second job.

Phase 1 writes nothing to any registry, ever.

## 6. Phase 2 — publish

Trigger: `release: published`. The draft was created with `GITHUB_TOKEN`, whose events do not
start workflows, but the human publishes it, so this event fires.

1. **Re-check the tag.** It matches `v<semver>`, its commit is reachable from `main`, and every
   manifest at that commit reads the tag's version. Cheap, and it rejects a hand-made release on
   the wrong tag.
2. **Fan out.** A matrix job per row, `fail-fast: false`, holding `actions: write` (and only that
   beyond `contents: read`). Each:
   - **Checks whether the version is already published.** npm:
     `npm view <name>@<version> version`; PyPI: `GET https://pypi.org/pypi/<name>/<version>/json`
     returning 200. If present, the row is `skipped` and succeeds.
   - **Dispatches** `workflow` at `ref: v<version>` with inputs `package: <package_input>` and
     `version: <version>`, requesting the new run's ID back from the dispatch API
     (`return_run_details`). This API is confirmed.
   - **Waits** with `gh run watch <id> --exit-status` and adopts the child's result.
3. **Summarise** (`if: always()`). A table — package, registry, `published` / `skipped` /
   `failed`, link to the child run — goes to the job summary and is appended to the release body,
   so the release page states what actually shipped. This job needs `contents: write` to edit the
   release; it is the only phase 2 job that does.

### Failure

A registry publish cannot be undone, so there is no rollback. A partial release is completed by
fixing the cause and **re-running failed jobs**; the already-published check turns every row that
succeeded into a no-op. If the fix needs a code change, that is a new version: the tag never moves
and a version is never republished from a different commit.

## 7. Release notes

```bash
gh release create "v$VERSION" --draft --verify-tag --title "v$VERSION" \
  --generate-notes --notes-file "$HEADER"
```

- `--verify-tag` refuses to proceed unless the tag phase 1 just pushed exists, so `gh` never
  creates a tag of its own on some other commit.
- `--generate-notes` lists the merged PRs since the previous `v*` release. Its grouping comes from
  `.github/release.yml` (new), which categorises by **PR label**: Dependencies (`dependencies`,
  which Dependabot applies to its own PRs), Contract (`contract`), CI/Build (`build`, `release`),
  and everything else under Changes. PRs are not labelled consistently today, so most human PRs
  land in Changes; that is acceptable because a human reviews and edits the draft before
  publishing it, which is the point of D1.
- `$HEADER` is written by phase 1 from the package table: each package, its registry and the
  server version it was generated against. Rendering it from the table means it cannot disagree
  with what phase 2 publishes. `--notes-file` content precedes the generated notes.

No third-party tool is involved; `gh` is preinstalled on GitHub-hosted runners.

## 8. Changes to the existing publish workflows

`publish.yml` and `publish-python.yml` remain the **only** files that talk to their registries,
and remain `workflow_dispatch`-only. They change in three ways:

- a `run-name` carrying package and version (`Publish @arcadedb/<package> <version>`), so a
  dispatched run is identifiable in the UI and correlatable if needed;
- their verify steps become calls to `scripts/release/verify-*.sh` (section 5);
- their header comments are reframed: dispatched by `release.yml`; dispatching by hand is for
  recovery only, and bypasses the lockstep check.

Their filenames do not change — that is the point of D3 — so the trusted-publisher caveats already
recorded in them stay accurate as written.

## 9. Adding a language

A new registry needs: its rows in the table; its `read/write version` and `already published?`
cases keyed on the new `registry`; its `scripts/release/verify-<registry>.sh`; and its
`publish-<lang>.yml`. `release.yml` is not edited.

M9's `publish-java.yml` (M9 section 9) fits this unchanged. How it deploys and signs for Maven
Central — Sonatype's `central-publishing-maven-plugin` with `maven-gpg-plugin`, or JReleaser — is
M9's decision and lives **inside** `publish-java.yml`, never in `release.yml`. M9 section 9 should
gain a pointer to this design when it is next edited.

## 10. Documentation

- Root `CLAUDE.md`, Workflows: a `release.yml` entry (two phases, dispatch-not-reuse and why,
  re-run-to-complete), and the `publish.yml` / `publish-python.yml` entries reframed as dispatched
  children.
- Each package README's release paragraph points at `set-release-version.sh` + dispatching
  `release.yml`. The compatibility tables are untouched; adding a row stays a human decision.

## 11. Testing

- **Scripts:** the cases in section 4, running in CI with the existing script tests.
- **Phase 1:** `dry-run: true` exercises verify and every package's dry run without tagging or
  drafting, on any commit, today. Under `dry-run`, D4 is downgraded to a warning, so the rest of
  phase 1 can be exercised on today's SNAPSHOT contract; a real run always enforces it. The script
  tests include one run in each mode to prove the downgrade is confined to `dry-run`.
- **Phase 2** cannot be tested without publishing. Before the first real release (0.2.0, #41), it
  is exercised once on a fork, against TestPyPI and a throwaway npm scope, including one forced
  child failure followed by a re-run, to prove the already-published check makes the re-run
  complete only what was missing.

## 12. Out of scope

- Maven Central setup and signing secrets — M9's.
- Independent per-package versions. Lockstep is the design; a package that needs to ship alone is
  handled by dispatching its publish workflow directly, which section 8 keeps possible for
  recovery.
- Automatic triggering (on tag, on merge, on schedule). Releases stay human-initiated.
