# Unified Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace four manual publish dispatches with one two-phase `release.yml` that versions every driver in lockstep, tags, drafts notes, and — once a human publishes the draft — dispatches each registry's existing publish workflow.

**Architecture:** A package table in `scripts/release-packages.py` is the single source for which packages exist, how their versions are read and written, and how to ask a registry whether a version is out. `release.yml` builds its matrices from it. Each registry's pre-publish gates move into `scripts/release/verify-<registry>.sh`, called by both the phase 1 dry run and the existing publish workflows, which keep their filenames so no trusted publisher changes.

**Tech Stack:** GitHub Actions, `gh` CLI (2.101+), Python ≥ 3.11 stdlib (`tomllib`, `urllib`), bash, pytest, actionlint, shellcheck.

**Spec:** `docs/superpowers/specs/2026-09-30-unified-release-design.md`

## Global Constraints

- Releases stay human-initiated: `release.yml` triggers are exactly `workflow_dispatch` and `release: published`. Nothing on push, tag or schedule.
- `publish.yml` and `publish-python.yml` keep their filenames and stay the only files that talk to npm / PyPI. `release.yml` never runs `npm publish` or a PyPI upload.
- Versions are plain `MAJOR.MINOR.PATCH` — no leading `v`, no prerelease or build suffix. Tags are `v<version>`.
- A real (non-dry-run) phase 1 refuses any server version ending in `-SNAPSHOT` (spec D4).
- `set` never touches `arcadedb.serverVersion` / `[tool.arcadedb] server-version`; that is `adopt-contract-version.sh`'s job.
- Least privilege per job: `contents: read` by default; `contents: write` only on the tag+draft job and the summary job; `actions: write` only on the fan-out job.
- Every third-party action pinned by full commit SHA with a version comment, reusing the SHAs already in `ci.yml` / `publish*.yml`.
- Comments explaining a gate move with the gate. Load-bearing prose in the publish workflows is relocated, not deleted.
- Branch: `feat/unified-release`, off `main` (the spec branch `docs/unified-release-design` merges first or is rebased in).

## Decisions made at plan time

- **The package table is Python, not shell** (`scripts/release-packages.py`, hyphenated like `check-licenses.py`). It reads TOML and JSON and does HTTP; bash would shell out to Python for all three. `scripts/set-release-version.sh` stays as the spec's human-facing entry point, a thin wrapper. The spec is amended in Task 1 to say so.
- **Lockfiles move with manifests.** `typescript/package-lock.json` records each workspace's version (`packages["packages/<pkg>"].version`) and `python/uv.lock` each editable package's (`[[package]] name = "arcadedb-driver"` / `version = …`). A release bump that left them stale would leave the tree internally inconsistent, so `set` rewrites them and `check` verifies them. Edits are direct (JSON / exactly-once regex), not `npm install` / `uv lock`, so they need no network and touch nothing else.
- **Run ID from the dispatch API.** `POST …/actions/workflows/{file}/dispatches` accepts `return_run_details: true` and answers `200` with `workflow_run_id` (checked against GitHub's published OpenAPI description on 2026-09-30). The spec's run-name fallback is not built; `run-name` is still added because it makes the UI legible.
- **"Already published?" fails closed.** `200` → published, `404` → not, anything else → error. Treating a registry outage as "not published" would only cause a failed dispatch, but treating it as "published" would silently skip a package — so neither guess is made.

## Review Focus

1. **A prerelease-looking version** (`0.2.0-rc.1`, `v0.2.0`) — PyPI normalises `-rc.1` to `rc1`, so the manifest, tag and registry query would disagree. Expected: rejected up front by `check` and `set`. Tested in Task 1.
2. **Lockfile left stale by a bump** — expected: `set` rewrites both lockfiles; `check` fails when a lockfile disagrees with its manifest. Tested in Tasks 1–2.
3. **Registry returns 500 / times out during the already-published check** — expected: the row fails loudly, never skipped. Tested in Task 3.
4. **Re-running phase 2 after one package failed** — expected: published rows are `skipped`, only the missing one is dispatched. Tested by the fork rehearsal in Task 8.
5. **A GitHub release published by hand on a tag that is not a lockstep release** (wrong format, commit off `main`, manifests at another version) — expected: phase 2 fails at the re-check and dispatches nothing. Tested in Task 7 via `check` and in Task 8's rehearsal.

---

### Task 1: The package table, `json` and `check`

**Files:**
- Create: `scripts/release-packages.py`
- Create: `scripts/tests/test_release_packages.py`
- Create: `.github/workflows/ci-release.yml`
- Modify: `docs/superpowers/specs/2026-09-30-unified-release-design.md` §4 (script name/language), §6 (run ID: API confirmed, fallback dropped)

**Interfaces:**
- Produces:
  - `PACKAGES: list[dict]`, four rows with keys `id, language, manifest, lockfile, registry, name, workflow, package_input`:
    | id | manifest | lockfile | registry | name | workflow | package_input |
    |---|---|---|---|---|---|---|
    | `npm-driver` | `typescript/packages/driver/package.json` | `typescript/package-lock.json` | `npm` | `@arcadedb/driver` | `publish.yml` | `driver` |
    | `npm-driver-grpc` | `typescript/packages/driver-grpc/package.json` | `typescript/package-lock.json` | `npm` | `@arcadedb/driver-grpc` | `publish.yml` | `driver-grpc` |
    | `pypi-driver` | `python/packages/driver/pyproject.toml` | `python/uv.lock` | `pypi` | `arcadedb-driver` | `publish-python.yml` | `driver` |
    | `pypi-driver-grpc` | `python/packages/driver-grpc/pyproject.toml` | `python/uv.lock` | `pypi` | `arcadedb-driver-grpc` | `publish-python.yml` | `driver-grpc` |
  - `REGISTRIES: dict[str, Registry]` keyed `npm` / `pypi`, each with `read_version(root, row) -> str`, `read_lock_version(root, row) -> str`, `read_server_version(root, row) -> str`, `write_version(root, row, version) -> None` (Task 2), `published_url(row, version) -> str` (Task 3).
  - `validate_version(v: str) -> None` — raises `ReleaseError` unless `^\d+\.\d+\.\d+$`.
  - `check(root: Path, version: str, allow_snapshot: bool) -> list[str]` — returns problems (empty = OK).
  - CLI: `release-packages.py json` → the table as a JSON array on stdout; `release-packages.py check <version> [--allow-snapshot]` → exit 1 listing every problem, exit 0 with `OK: …` otherwise. `--root` (default: repo root from `__file__`) for tests.

- [ ] **Step 1: Write the failing tests** in `scripts/tests/test_release_packages.py`, loading the module with `importlib.util.spec_from_file_location` as `test_check_licenses.py` does. A `fixture_repo(tmp_path, version="0.1.0", server="26.10.1")` helper writes the four manifests, both lockfiles (minimal: `package-lock.json` with `packages["packages/driver"]` / `["packages/driver-grpc"]`; `uv.lock` with the two `[[package]]` blocks as in the real file), `contracts/arcadedb-openapi-<server>.json` with `{"info":{"version":server}}`, and `contracts/arcadedb-server-<server>.proto`.
  - `test_json_lists_every_package_with_every_field` — four rows, ids as in the table, each row has all eight keys.
  - `test_table_paths_exist_in_this_repository` — every `manifest` and `lockfile` exists under the real repo root (catches a moved package).
  - `test_check_passes_when_everything_agrees` — `check(root, "0.1.0", False) == []`.
  - `test_check_rejects_prerelease_and_prefixed_versions` — `"0.2.0-rc.1"`, `"v0.2.0"`, `"0.2"` each yield a problem naming the version.
  - `test_check_reports_each_manifest_that_disagrees` — bump one pyproject to `0.1.1`; problems mention that manifest's path and both versions.
  - `test_check_reports_stale_lockfile` — manifest `0.2.0`, `uv.lock` still `0.1.0`; problem names `python/uv.lock`. Same for `package-lock.json`.
  - `test_check_reports_server_version_contract_mismatch` — one package's server version `26.9.1` vs contracts `26.10.1`.
  - `test_check_refuses_snapshot_unless_allowed` — server `26.10.1-SNAPSHOT`: problem with `allow_snapshot=False`, none with `True`.
  - `test_check_requires_exactly_one_contract_of_each_kind` — a second `arcadedb-openapi-*.json` is a problem, not a silent pick.
  - `test_cli_check_exit_codes` — subprocess: exit 0 on the agreeing fixture, 1 on a mismatched one with the problem on stderr.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --no-project --python 3.12 --with pytest python -m pytest scripts/tests/test_release_packages.py -v`
Expected: FAIL — module file not found.

- [ ] **Step 3: Implement `scripts/release-packages.py`** (executable, `#!/usr/bin/env python3`, stdlib only). npm reads `version` / `arcadedb.serverVersion` via `json`, lock version from `packages["packages/<package_input>"].version`; pypi reads `project.version` / `tool.arcadedb.server-version` via `tomllib`, lock version from the `[[package]]` block whose `name` equals the row's `name` (parse `uv.lock` with `tomllib`). Contract versions: the single OpenAPI file's `info.version`, and the single `.proto` filename between `arcadedb-server-` and `.proto` — both must equal every package's server version. A header comment states why the table is explicit (same argument as `adopt-contract-version.sh`'s `LANGUAGES`) and that a new registry is a `REGISTRIES` entry plus rows.

- [ ] **Step 4: Run the tests** — same command. Expected: all PASS. Then `./scripts/release-packages.py check 0.1.0 --allow-snapshot` on the real tree → `OK`, and without `--allow-snapshot` → exit 1 naming `26.10.1-SNAPSHOT`.

- [ ] **Step 5: Add `.github/workflows/ci-release.yml`** — `on: push`/`pull_request` to `main` with paths `scripts/release-packages.py`, `scripts/set-release-version.sh`, `scripts/release/**`, `scripts/tests/test_release_packages.py`, `.github/workflows/release.yml`, `.github/workflows/publish.yml`, `.github/workflows/publish-python.yml`, `.github/workflows/ci-release.yml`, `.github/release.yml`, and every manifest/lockfile in the table. One job: checkout, `astral-sh/setup-uv` (SHA from `publish-python.yml`), run the pytest command above, then `./scripts/release-packages.py check "$(jq -r .version typescript/packages/driver/package.json)" --allow-snapshot` so `main` can never hold packages at different versions. Run `actionlint .github/workflows/ci-release.yml` → no output.

- [ ] **Step 6: Amend the spec** §4: `scripts/release-packages.py` (Python, reasons above) replaces `release-packages.sh`; the table gains `lockfile`. §6: the dispatch API's `return_run_details` is confirmed; delete the run-name fallback sentence.

- [ ] **Step 7: Commit** — `feat(release): add the release package table and lockstep check`.

### Task 2: `set` and `scripts/set-release-version.sh`

**Files:**
- Modify: `scripts/release-packages.py`
- Create: `scripts/set-release-version.sh`
- Modify: `scripts/tests/test_release_packages.py`

**Interfaces:**
- Consumes: `PACKAGES`, `REGISTRIES`, `validate_version`, `check` (Task 1).
- Produces: `set_version(root: Path, version: str) -> None`; CLI `release-packages.py set <version>`; `scripts/set-release-version.sh <version>` (`exec`s `set`, then runs `check <version> --allow-snapshot` and prints `git diff --stat`).

- [ ] **Step 1: Write the failing tests**
  - `test_set_then_check_agrees` — `set_version(root, "0.2.0")`, then `check(root, "0.2.0", True) == []`.
  - `test_set_never_touches_server_versions` — every package's server version and both contract files byte-identical before/after.
  - `test_set_touches_only_table_files` — hash every file in the fixture; only manifests and lockfiles changed.
  - `test_set_preserves_formatting` — `package.json` keeps 2-space indent and trailing newline; `pyproject.toml` comments on the lines around `version` survive.
  - `test_set_fails_when_version_matches_zero_or_two_times` — a pyproject with two `version =` lines under `[project]`, and a `uv.lock` missing the package block: each raises `ReleaseError` naming the file, and **no** file in the fixture is modified (compute all edits first, write only if all succeed).
  - `test_set_rejects_invalid_version` — `"v0.2.0"` raises before any write.

- [ ] **Step 2: Run to verify they fail.** Expected: `AttributeError: set_version`.

- [ ] **Step 3: Implement.** npm: load JSON, set `version` (manifest) and `packages["packages/<pkg>"].version` (lock), dump with `indent=2` + trailing newline — the format `npm` itself writes. pypi: exactly-once regex on `^version\s*=\s*"[^"]*"` within the `[project]` table of the manifest, and on the `version = "…"` line immediately following `name = "<name>"` in `uv.lock`; count ≠ 1 → `ReleaseError`. Stage every new file content in memory, write all at the end.

- [ ] **Step 4: Run the tests.** Expected: PASS. On a scratch copy of the repo (`git worktree add`), `scripts/set-release-version.sh 0.1.1` → `git diff --stat` lists exactly the 4 manifests + 2 lockfiles; then `npm ci` in `typescript/` and `uv sync --frozen` in `python/` both succeed. Remove the worktree.

- [ ] **Step 5: `shellcheck scripts/set-release-version.sh`** → clean. **Commit** — `feat(release): add set-release-version.sh`.

### Task 3: `is-published` and `header`

**Files:**
- Modify: `scripts/release-packages.py`, `scripts/tests/test_release_packages.py`

**Interfaces:**
- Produces:
  - `published_url(row, version) -> str` — npm: `https://registry.npmjs.org/<name with "/" as "%2F">/<version>`; pypi: `https://pypi.org/pypi/<name>/<version>/json`.
  - `is_published(row, version, fetch=_http_status) -> bool` — `fetch(url) -> int` status; 200 → True, 404 → False, anything else or an exception → `ReleaseError`.
  - `render_header(root, version) -> str` — Markdown: a `## Packages` table (package name, registry, version), then `Generated against ArcadeDB server <server version>.`
  - CLI: `is-published <id> <version>` → prints `true`/`false`, exit 0; exit 1 on `ReleaseError`. `header <version>` → Markdown on stdout.

- [ ] **Step 1: Write the failing tests**
  - `test_published_url_encodes_npm_scope` — `@arcadedb/driver`, `0.2.0` → `https://registry.npmjs.org/@arcadedb%2Fdriver/0.2.0`.
  - `test_published_url_pypi` — `arcadedb-driver-grpc` → `https://pypi.org/pypi/arcadedb-driver-grpc/0.2.0/json`.
  - `test_is_published_maps_200_and_404` — stub fetch.
  - `test_is_published_fails_closed_on_500_and_network_error` — stub returning 503, and stub raising `URLError`: both raise `ReleaseError`.
  - `test_header_lists_every_package_and_server_version` — every `name` appears once; server version appears.

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement.** `_http_status` issues a `GET` via `urllib.request` with a 20 s timeout and returns the status, catching `HTTPError` to return its code; other exceptions propagate to `is_published`, which wraps them in `ReleaseError`.

- [ ] **Step 4: Run tests** → PASS. Live smoke: `./scripts/release-packages.py is-published npm-driver 0.1.0` → `true`; `… pypi-driver-grpc 9.9.9` → `false`.

- [ ] **Step 5: Commit** — `feat(release): add registry and release-notes helpers`.

### Task 4: `scripts/release/verify-npm.sh`, called by `publish.yml`

**Files:**
- Create: `scripts/release/verify-npm.sh`
- Modify: `.github/workflows/publish.yml`

**Interfaces:**
- Produces: `scripts/release/verify-npm.sh <package>` (`driver` | `driver-grpc`), run from the repo root after `npm ci` in `typescript/`. Runs, in order, exactly the gates now at `publish.yml:78-170`: `npm test`, server-version vs contract, `npm run prepack` + dist assertions (including driver-grpc's exactly-one-`_pb.js` check). Exit non-zero on the first failure. Does not install and does not publish.

- [ ] **Step 1: Move the three gate steps' logic into the script verbatim** (the inline `node -e` programs stay `node -e` programs), with each step's YAML comment moved above its block. `set -euo pipefail`; `PKG=$1`, `PKG_DIR=packages/$PKG`, `cd typescript`. Reject any `PKG` other than the two known values.

- [ ] **Step 2: Replace those steps in `publish.yml`** with one step `run: ./scripts/release/verify-npm.sh "$PKG"`. Keep the dispatch-input check, checkout, setup and the publish step with its caveats untouched. Add `run-name: Publish @arcadedb/${{ inputs.package }} ${{ inputs.version }}`. Reframe the header comment: dispatched by `release.yml` per package; dispatching by hand is for recovering a partial release and bypasses the lockstep check.

- [ ] **Step 3: Verify.** `shellcheck scripts/release/verify-npm.sh` clean; `actionlint .github/workflows/publish.yml` clean. Locally, `(cd typescript && npm ci) && ./scripts/release/verify-npm.sh driver` and `… driver-grpc` → both end with `OK: … built with all expected dist/ output`. Negative: temporarily edit `typescript/packages/driver/package.json` `serverVersion` → script exits non-zero with the mismatch message; revert.

- [ ] **Step 4: Commit** — `refactor(publish): move npm pre-publish gates into verify-npm.sh`.

### Task 5: `scripts/release/verify-pypi.sh`, called by `publish-python.yml`

Same shape as Task 4.

**Files:**
- Create: `scripts/release/verify-pypi.sh`
- Modify: `.github/workflows/publish-python.yml`

**Interfaces:**
- Produces: `scripts/release/verify-pypi.sh <package>`, run from the repo root after `uv sync --frozen` in `python/`. Runs the gates now at `publish-python.yml:95-237`: `uv run pytest`, the per-package server-version gate (OpenAPI for `driver`, `.proto` for `driver-grpc` — the `if:` conditions become a `case`), `uv build` + wheel/sdist content checks, and driver-grpc's four-generated-files check. Leaves the built artifacts in `python/dist/` for the publish step.

- [ ] **Step 1: Move the gates verbatim with their comments**, including the `|| true` explanation and the `zipfile -l` notes. Start with `rm -rf dist` so a dry run and a publish both start from an empty `dist/`.

- [ ] **Step 2: Replace the steps in `publish-python.yml`** with `run: ./scripts/release/verify-pypi.sh "$PKG"`; the `pypa/gh-action-pypi-publish` step still reads `python/dist`. Add `run-name: Publish arcadedb-${{ inputs.package }} ${{ inputs.version }}` and the same header reframing as Task 4.

- [ ] **Step 3: Verify.** shellcheck + actionlint clean. Locally for both packages → exit 0 and `python/dist/` holds exactly one wheel and one sdist for that package. Negative: bump one pyproject's `server-version` → non-zero with the mismatch; revert.

- [ ] **Step 4: Commit** — `refactor(publish): move PyPI pre-publish gates into verify-pypi.sh`.

### Task 6: `release.yml` phase 1 and `.github/release.yml`

**Files:**
- Create: `.github/workflows/release.yml`
- Create: `.github/release.yml`

**Interfaces:**
- Consumes: `release-packages.py json|check|header` (Tasks 1, 3); `verify-npm.sh` / `verify-pypi.sh` (Tasks 4, 5).
- Produces: workflow `release.yml` with `on.workflow_dispatch.inputs` `version` (string, required) and `dry-run` (boolean, default `false`); jobs `prepare-verify`, `prepare-dry-run`, `prepare-tag-and-draft`, all `if: github.event_name == 'workflow_dispatch'`. Task 7 adds the `release` trigger and its jobs to the same file.

- [ ] **Step 1: `.github/release.yml`** — `changelog.categories`: `Dependencies` (labels `dependencies`, `github_actions`), `Contract` (`contract`, `contract-drift`), `CI and build` (`build`, `release`), `Changes` (`*`). `exclude.labels: [invalid, duplicate, wontfix]`. All labels exist today (`gh label list`).

- [ ] **Step 2: `prepare-verify`** — refuse unless `github.ref == 'refs/heads/main'`; run `./scripts/release-packages.py check "$VERSION"` plus `--allow-snapshot` only when `dry-run` is true (emit a `::warning::` saying D4 was relaxed); fail if `git ls-remote --exit-code --tags origin "refs/tags/v$VERSION"` finds the tag. Outputs `matrix` = `release-packages.py json`. Inputs reach scripts only through `env:`, never interpolated into `run:` text.

- [ ] **Step 3: `prepare-dry-run`** — `needs: prepare-verify`, `strategy.matrix.package: ${{ fromJSON(needs.prepare-verify.outputs.matrix) }}`, `fail-fast: false`, name `Dry run ${{ matrix.package.name }}`. Steps conditional on `matrix.package.registry`: npm → setup-node 20 + `npm ci` + `verify-npm.sh "${{ matrix.package.package_input }}"` via env; pypi → setup-uv + `uv sync --frozen` + `verify-pypi.sh`. Same action SHAs as the publish workflows.

- [ ] **Step 4: `prepare-tag-and-draft`** — `needs: prepare-dry-run`, `if: ${{ !inputs.dry-run }}`, `permissions: contents: write`. Configure `github-actions[bot]` identity; `git tag -a "v$VERSION" -m "Release v$VERSION" "$GITHUB_SHA"`; `git push origin "v$VERSION"`; `release-packages.py header "$VERSION" > header.md`; `gh release create "v$VERSION" --draft --verify-tag --title "v$VERSION" --generate-notes --notes-file header.md`. Write the draft's URL to the job summary with the next step spelled out: review, edit, publish.

- [ ] **Step 5: Verify.** `actionlint .github/workflows/release.yml` clean. After merge (a dispatch needs the file on the default branch): `gh workflow run release.yml -f version=0.1.0 -f dry-run=true` → verify passes with the SNAPSHOT warning, all four dry runs green, tag job skipped, no `v0.1.0` tag and no draft created. Then `gh workflow run release.yml -f version=0.1.0` (not dry run) → fails in `prepare-verify` on `-SNAPSHOT`, which is D4 working.

- [ ] **Step 6: Commit** — `feat(release): add release.yml phase 1 and release-note categories`.

### Task 7: `release.yml` phase 2

**Files:**
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: `release-packages.py json|check|is-published` (Tasks 1, 3); the publish workflows' `package` / `version` inputs.
- Produces: trigger `release: types: [published]`; jobs `publish-verify`, `publish-fan-out`, `publish-summary`, all `if: github.event_name == 'release'`.

- [ ] **Step 1: `publish-verify`** — derive `VERSION` from `github.event.release.tag_name` (must match `^v\d+\.\d+\.\d+$`, strip `v`); checkout the tag with full history; `git merge-base --is-ancestor HEAD origin/main`; `release-packages.py check "$VERSION"` (no `--allow-snapshot`). Outputs `version`, `matrix`.

- [ ] **Step 2: `publish-fan-out`** — matrix over the table, `fail-fast: false`, `permissions: actions: write, contents: read`. Per row:
  1. `release-packages.py is-published "$ID" "$VERSION"` → `true` ⇒ write `skipped` to a result file and stop successfully.
  2. `RUN_ID=$(gh api -X POST "repos/$GITHUB_REPOSITORY/actions/workflows/$WORKFLOW/dispatches" -f ref="v$VERSION" -f "inputs[package]=$PACKAGE_INPUT" -f "inputs[version]=$VERSION" -F return_run_details=true --jq .workflow_run_id)`.
  3. `gh run watch "$RUN_ID" --exit-status --interval 30`; record `published` or `failed` plus the run URL.
  4. Upload the one-line result as artifact `result-<id>` (`actions/upload-artifact`, pinned) with `if: always()`.

- [ ] **Step 3: `publish-summary`** — `needs: [publish-verify, publish-fan-out]`, `if: always() && needs.publish-verify.result == 'success'`, `permissions: contents: write`. Download all `result-*`; render a Markdown table (package, registry, status, run link) to `$GITHUB_STEP_SUMMARY`; append it to the release body with `gh release view --json body` + `gh release edit --notes-file`. A missing result for a row is reported as `unknown`, never dropped.

- [ ] **Step 4: Verify.** `actionlint` clean. Confirm by reading the file that no job in `release.yml` has both `actions: write` and `contents: write`, and that no `run:` interpolates `${{ github.event.release.* }}` directly (env only — the release body and tag name are user-controlled). Live verification is Task 8.

- [ ] **Step 5: Commit** — `feat(release): add release.yml phase 2 fan-out and summary`.

### Task 8: Docs, then a fork rehearsal of phase 2

**Files:**
- Modify: `CLAUDE.md` (Workflows: new `release.yml` and `ci-release.yml` entries; `publish.yml` / `publish-python.yml` entries reframed as dispatched children, recovery-only by hand; the "bootstrap" and trusted-publisher text unchanged)
- Modify: `typescript/README.md` or the package READMEs, `python/README.md` or the package READMEs — wherever a release paragraph exists today (`grep -rn "publish.yml\|publish-python.yml" --include=README.md`) — to: run `scripts/set-release-version.sh <version>`, merge the PR, dispatch `release.yml`, review and publish the draft.

- [ ] **Step 1: Write the docs.** The `release.yml` entry must state: the two phases and that publishing the draft is the approval; why it dispatches rather than calls (trusted publishers key on the top-level filename; PyPI rejects reusable workflows); that a partial release is completed by re-running failed jobs and a code fix is a new version; that D4 refuses SNAPSHOT server versions. Commit — `docs: document the unified release`.

- [ ] **Step 2: Fork rehearsal (manual, before 0.2.0).** On a personal fork with the branch merged into its `main`:
  - point `publish.yml` at a throwaway npm scope and `publish-python.yml` at TestPyPI (`repository-url: https://test.pypi.org/legacy/`) with trusted publishers configured for the fork — **fork-only edits, never merged**;
  - use a scratch contract version without `-SNAPSHOT`;
  - dispatch phase 1 → tag and draft appear, notes carry the header and categories;
  - make one package's publish fail on purpose (e.g. its trusted publisher not yet configured), publish the draft → three `published`, one `failed`, summary appended to the release;
  - fix the cause, re-run failed jobs → three `skipped`, one `published`;
  - publish a hand-made release on a tag at the wrong version → `publish-verify` fails, nothing dispatched.

  Record the outcome (run URLs) in the PR description. If any step behaves differently from the spec, stop and revise the spec before merging.

- [ ] **Step 3: Open the PR** against `main`, linking the spec and the rehearsal runs.
