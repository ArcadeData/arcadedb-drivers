# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Language clients for ArcadeDB's HTTP and gRPC APIs. One contract per API in `contracts/`, many
language clients generated from it. `typescript/`, `python/` and `go/` are the language directories
today; others will appear as their siblings.

The organising rule: **generated code is never hand-edited.** The contract is the single source of
truth, and CI's *drift gate* regenerates from the committed contract and fails if the result
differs from what is checked in. If a generated file looks wrong, fix the contract or the
generator config — editing the output only makes CI red.

See `typescript/CLAUDE.md` for the TypeScript workspace and `python/CLAUDE.md` for the Python
workspace (commands, package layout, conventions). The Python workspace hosts two packages the
same way the TypeScript one does: `arcadedb-driver`, the HTTP client, and `arcadedb-driver-grpc`,
the gRPC client generated from the `.proto` contract. See `go/CLAUDE.md` for the Go workspace,
which hosts one module so far, `github.com/ArcadeData/arcadedb-drivers/go/arcadedb`, the HTTP
client; a Go gRPC client (M10b) will join it as a sibling module.

## The contracts

`contracts/` holds exactly one OpenAPI JSON and exactly one `.proto`, each named after the
ArcadeDB server version it came from (`arcadedb-openapi-<version>.json`,
`arcadedb-server-<version>.proto`). "Exactly one" is enforced, not conventional — two OpenAPI
files make `openapi-typescript` silently generate from whichever the glob yields first (lexical,
not version, order), and two `.proto` files make `buf generate` fail on a duplicate symbol.

```bash
scripts/fetch-contract.sh --release <tag>            # download + checksum-verify a GitHub release asset (OpenAPI)
scripts/fetch-contract.sh --image <image-reference>  # start the image, fetch /api/v1/openapi.json (OpenAPI)
scripts/fetch-contract.sh --proto-from <checkout> [<version>]  # copy arcadedb-server.proto from a local arcadedb checkout

scripts/adopt-contract-version.sh <version>          # retire the old version, adopt the new one, repo-wide
scripts/resolve-openapi-contract.sh                  # print the single OpenAPI contract path, or fail
scripts/resolve-proto-contract.sh                    # print the single .proto contract path, or fail
scripts/tests/test-contract-scripts.sh               # tests for the scripts above (runs in CI)

scripts/set-release-version.sh <version>             # write one release version into every package manifest and lockfile
scripts/release-packages.py check <version>          # verify every package, lockfile and server version agrees

scripts/check-licenses.py                            # fail if any dependency's license is off the allow-list
```

`fetch-contract.sh` writes the new contract **beside** the old one rather than in place, so a
version bump is a two-step operation: fetch both contracts, then run
`adopt-contract-version.sh <version>`, which deletes the retired contract and generated module,
rewrites the version-stamped imports, and updates each package's recorded server version
(`arcadedb.serverVersion` in a TypeScript `package.json`, `[tool.arcadedb] server-version` in a
Python `pyproject.toml`, `const ServerVersion` in a Go module's `version.go`). It deliberately does not touch the compatibility tables in the READMEs —
those rows are a historical record tied to a package version, and adding one is a human decision.

`adopt-contract-version.sh` is language-aware: which files it rewrites is driven by an explicit
`LANGUAGES` table (file suffixes and directories to skip, per language) rather than by crawling
every top-level directory. Adding a language client to this repository is a deliberate one-line
addition to that table, not something the script infers by finding a new sibling of `contracts/`.
Go was added exactly that way: a `go` row (`.go` and `.md`, skipping `generated/`), plus a
dedicated pass that rewrites `const ServerVersion` in every `go/*/version.go`, asserts exactly one
match per file, and never touches `const Version`, the module's own release version. Go needs no
retirement step either: the generated file, `client.gen.go`, carries no version in its name.

`arcadedb-driver-grpc` needed **no** change to that script, and this is the opposite of what the M3
design predicted for a second gRPC client: M3 assumed a Python client would inherit the TypeScript
gRPC client's `_pb.ts`-style version-stamped generated filename, and so would need its own
retirement step and import-repointing pattern. It does not, because the Python generator can't
tolerate a version-stamped proto filename at all — protoc treats `.` in a proto's filename as a
directory separator, so the contract is staged under a fixed, unstamped name before generation (see
`python/CLAUDE.md`). An unstamped generated module has nothing to retire and no import to repoint;
`adopt-contract-version.sh`'s existing glob over `python/packages/*/pyproject.toml` already picks up
`arcadedb-driver-grpc`'s `server-version` key for free.

In `--release` / `--image` mode the fetched OpenAPI spec is rejected unless it is structurally
post-M0 (the `/api/v1/begin/{database}` 204 response carrying the `arcadedb-session-id` header).
A version string alone is not accepted as proof of a spec's content.

`buf.yaml` lives at the repository root, not under `typescript/`, because the gRPC module
describes the contract itself and every gRPC client, a future Go one included, reads the same
module.

The OpenAPI contract has three known quirks that each look like a client bug until you know the
cause is upstream: time-series and Grafana scalars typed `"type": "object"`, `POST /api/v1/server`
answering `{"result": "ok"}` where an array is declared (both in `python/CLAUDE.md`), and a checksum
property named `"/unreadableFiles"` with a leading slash, which is deliberate upstream but which
oapi-codegen turns into an unexported field. The Go client names that field through a generator
overlay with an expiry test. Go also meets a fourth, of its own: the time-series query response is
a `oneOf` with no discriminator, so both generated `As...` accessors "succeed" on either payload and
`TS().Query` must bypass the typed parse. Each quirk's cost in Go is in `go/CLAUDE.md`.

## Workflows

- `ci.yml` — lint, typecheck, unit tests, the drift gate, and the "exactly one .proto" check on
  Node 20; then a separate e2e job on Node 24 (testcontainers@12 needs Node >= 22.22). Its `paths`
  filters include root `buf.yaml` and `.gitignore` on purpose: both can change generated output or
  silence the drift gate while leaving `typescript/` untouched.
- `ci-python.yml` — the same shape for the Python client: lint, typecheck, then **two** drift gates,
  one per package, then unit tests, all on the declared floor Python; a separate e2e job runs
  against a real container on a newer Python. The HTTP gate is three-part (regenerate and diff,
  catch untracked new generated files, and verify the generator skipped exactly the allowlisted
  endpoints via `scripts/check_codegen_skips.py`); the gRPC gate is only **two**-part (regenerate
  and diff, catch untracked new generated files) — deliberately with no third part, because `protoc`
  has no equivalent of `openapi-python-client`'s silent-skip failure mode. `openapi-python-client`
  meets an endpoint it can't model, prints a warning, drops it, and exits 0, so a skip leaves no
  trace `git diff` can catch; `protoc` fails loudly on anything it can't generate, so a third check
  mirroring `check_codegen_skips.py` would imply a risk that does not exist here.
- `ci-go.yml` — the same shape for the Go client: a `build` job on Go 1.26, the declared floor,
  running `go/scripts/lint.sh` (`gofmt`, `go vet`, `staticcheck` over every module in `go.work`),
  then `go/scripts/check-drift.sh`, then `go test -race ./...` in `go/arcadedb`; and an `e2e` job on
  Go 1.27 against a real container. Its drift gate is **four**-part: regenerate and diff, catch
  untracked new generated files, `TestEveryOperationIsGenerated`, and `go mod tidy` leaving no
  `go.mod`/`go.sum` diff. The third part is the positive form of `check_codegen_skips.py`: rather
  than pinning which operations the generator skipped, it asserts by reflection that every
  `operationId` in the contract has a generated method. The test skips when it cannot find
  `contracts/`, so the gate requires an explicit `--- PASS` and reads a skip as a failure. Its
  `paths` include `.gitignore` for the reason `ci.yml`'s do, and deliberately not `buf.yaml`: no Go
  code is generated from the `.proto` yet, and the Go gRPC client (M10b) adds it.
- `contract-watch.yml` — daily, refreshes contracts from the SNAPSHOT server built off arcadedb's
  `main`. A changed contract gets an issue plus an adopt-and-regenerate PR; an unchanged contract
  with a red suite gets an issue only (it is a server regression no PR here can fix). Both are
  filed idempotently against one tracking issue and one branch. It regenerates and verifies
  **all three** language clients (TypeScript, Python, Go), each verdict its own step, and every
  verdict feeds the finding's fingerprint: dropping one would let that language recover or break
  while the tracking issue stayed silent.
- `release.yml` — the one way a release happens: every package in `scripts/release-packages.py`'s
  table, at one version, in two phases with a human between them. **Phase 1** (`workflow_dispatch`
  from `main`) runs `release-packages.py check`, dry-runs every package's gates
  (`scripts/release/verify-*.sh`, the same scripts the publish workflows run), then pushes the tag
  `v<version>` and creates a **draft** release; it writes to no registry. If the tag-and-draft job
  fails partway (tag pushed, no draft), **re-run that failed job** rather than dispatching again:
  it keeps a tag that already names the run's verified commit and reuses a release that already
  exists, while a fresh dispatch still refuses any existing tag. **Phase 2**
  (`release: published`) re-checks the tag and fans out one job per package: each asks its registry
  whether the version is already there and, if not, dispatches that package's publish workflow at
  the tag and waits, and a summary job appends what shipped to the release body. **Publishing the
  draft is the approval**, because a registry publish cannot be undone; the draft is created with
  `GITHUB_TOKEN`, whose events start no workflows, so only a human's click fires phase 2. It
  **dispatches** the publish workflows rather than calling them as reusable workflows because
  trusted publishers key on the *top-level* workflow filename: a called workflow would present
  `release.yml` to npm and PyPI, forcing every publisher to be reconfigured, and PyPI rejects a
  reusable workflow as a trusted publisher outright. A partial release is completed by
  **re-running failed jobs** on the phase 2 run (packages already on their registry read as
  `skipped`) — after waiting a few minutes, because the npm registry can briefly 404 a version it
  has just published, and a premature re-run re-dispatches it and npm refuses the duplicate (red,
  but harmless); a fix that needs code is a **new version**, never a moved tag. Real runs refuse a
  `-SNAPSHOT` server version (D4) so a release cannot ship against a moving target; a dry run
  relaxes that to a warning and may run on any ref. A new package joins by adding one row to the
  package table; a package on a registry not already there also needs a `REGISTRIES` entry **and**
  that registry's setup and verify steps in phase 1's dry-run job. Those steps are each gated on the
  row's registry, so a registry with none would run only a checkout and pass, verified by nothing;
  the job's first step therefore refuses any registry it has no steps for (`npm`, `pypi` and
  `goproxy` today), and a new registry is added to that step's list along with its steps. A row's
  lockfile is optional: the Go module has none, its version living in `version.go` and the git
  tag. The notes categories live in `.github/release.yml`.
- `ci-release.yml` — tests the release scripts and runs `release-packages.py check` on the version
  `main` currently carries (with `--allow-snapshot`, since `main`'s contract is a SNAPSHOT), so
  `main` cannot hold packages at different versions. `paths`-filtered to the table, the release
  scripts and workflows, the manifests and lockfiles the table names (for the Go module,
  `go/arcadedb/version.go` and `go/arcadedb/go.mod`, whose `module` line `check` holds to the row's
  name, with a `/vN` suffix from v2 on), and `contracts/` (which `check` compares every server
  version against).
- `publish.yml` — the only thing that talks to npm, and it is **workflow_dispatch only**, a child
  of `release.yml`, which dispatches it once per package. Dispatching it by hand is for recovering a
  partial release and **bypasses the lockstep check**. It refuses to run anywhere but the version's
  own tag (`github.ref` must be `refs/tags/v<version>`), because the UI and `gh workflow run` both
  default to `main`; recover with exactly
  `gh workflow run publish.yml --ref v<version> -f package=<pkg> -f version=<version>`. Nothing
  publishes on push, tag, or schedule. It re-verifies that the dispatch input, the
  package version, and the contract's `info.version` all agree before publishing. It publishes
  **one package per dispatch**, chosen by a `package` input (`driver` or `driver-grpc`), and is
  parameterised rather than duplicated into a sibling workflow for a specific reason: npm keys a
  trusted publisher on the workflow **filename**, so both packages naming this one file means one
  thing to configure and cross-check instead of two. Each package still needs its *own* trusted
  publisher, and its own bootstrap token for its first publish — npm has no equivalent of PyPI's
  pending publishers, so a package must exist before it can be trusted. Verify a publisher by
  reading back what npm stored (`npm trust list <package>`), never by eye against the web UI; npm
  validates that configuration at neither save nor dispatch time. The dist assertions differ per
  package — `driver-grpc`'s generated module carries the contract version in its filename, so the
  expected name is derived from `arcadedb.serverVersion` rather than hardcoded, and the step also
  asserts that exactly one such module exists (`tsc --build` never removes output whose source is
  gone, and `files: ["dist"]` would ship a retired one from a tree built across two contract
  versions).
- `publish-python.yml` — the npm workflow's sibling, and the only thing that talks to PyPI; also
  **workflow_dispatch only** and a `release.yml` child, hand-dispatched for recovery only (it too
  bypasses the lockstep check), with the same refusal of any ref but `refs/tags/v<version>` —
  recover with exactly
  `gh workflow run publish-python.yml --ref v<version> -f package=<pkg> -f version=<version>` —
  and the same dispatch-input/version/contract re-verification.
  It publishes **one package per dispatch**, chosen by a `package` input (`driver` or
  `driver-grpc`), and is parameterised for the same reason `publish.yml` is: PyPI, like npm, keys a
  trusted publisher on the workflow **filename**, so both packages naming this one file means one
  thing to configure and cross-check instead of two. The server-version gate (in
  `scripts/release/verify-pypi.sh`) checks each package against **its own** contract:
  `driver`'s `[tool.arcadedb] server-version` against the committed OpenAPI contract's
  `info.version`, and `driver-grpc`'s against the version in the committed `.proto` contract's
  filename (resolved by `resolve-proto-contract.sh`). Neither package is gated on a contract it is
  not generated from, so bumping one contract never blocks the other package's publish — and
  since `fetch-contract.sh` can fetch the two contracts independently, a `driver-grpc` gate that
  borrowed the OpenAPI version could pass while the `.proto` disagreed. Its bootstrap story inverts
  npm's: PyPI supports pending publishers, so a package's trusted publisher can be configured
  before the package exists on the index, and the first publish of either package needed no stored
  secret at all. Both are on PyPI at 0.1.0 today, `driver-grpc` included, each published that way.
  See the workflow file's comments for the caveat that does carry over from npm (check the
  workflow filename in PyPI's publisher settings against this file's actual name whenever either
  changes).
- `publish-go.yml` — the third sibling, for the Go module: **workflow_dispatch only**, a
  `release.yml` child, hand-dispatched for recovery only (bypassing the lockstep check), refusing
  any ref but `refs/tags/v<version>` — recover with exactly
  `gh workflow run publish-go.yml --ref v<version> -f package=arcadedb -f version=<version>` — and
  one module per dispatch through a `package` input. Go has no registry and no credential: a
  version is the tag `go/<package>/v<version>`, and the first fetch through `proxy.golang.org` *is*
  the publish, recording the checksum in `sum.golang.org` and letting `pkg.go.dev` index it. It is
  **two jobs**, split so the write token never shares a runner with third-party code. `verify`
  holds `contents: read`, checks the dispatch input against `version.go`'s `Version` and the
  package table row against `go.mod`'s module path, and runs `scripts/release/verify-go.sh` (lint,
  unit tests under `-race`, the drift gate, `ServerVersion` against the OpenAPI contract, and the
  module-zip check, `go/tools/cmd/checkzip` on `golang.org/x/mod/zip.CheckDir`) — every step that
  executes code fetched through the module proxy. `publish` holds `contents: write` and runs only
  git, the go command's own `go list -m`, and `release-packages.py`: it refuses unless `HEAD` is the
  commit `verify` checked, pushes the annotated module tag with the token passed on that one push
  (the checkout persists no credentials), continues if the tag already names this commit (an
  earlier attempt) and fails if it names any other, then fetches through the proxy and polls
  `is-published` until it answers `true`. Neither job restores a Go cache, and a per-package,
  per-version `concurrency` group keeps two dispatches of one version from racing to the tag.
  **A fetched version is permanent** — the proxy never forgets it and the checksum database pins
  its content, so it can be neither deleted nor replaced, and moving the tag afterwards only breaks
  anyone fetching around the proxy. The remedy for a bad one is a `retract` directive in the next
  version, which is why the module-zip check runs before the tag exists. The repository's tag
  ruleset, still outstanding, must protect `go/**` tags as well as `v*`, and must let the Actions
  bot push them.
- `license-compliance.yml` — runs `scripts/check-licenses.py` over all three dependency trees on a
  push or pull request that touches a lockfile, a package manifest, `go/go.work` or any Go
  `go.mod`/`go.sum` (not `go.work.sum`, which only carries checksums), the checker itself, its
  tests, or this file (a policy edit must re-run the gate it changes), plus weekly and on demand.
  The weekly run is not redundant with the path filters: a package can be relicensed on a version
  already pinned in a lockfile, which changes no manifest for the path filters to catch.
- `dependabot-auto-merge.yml` — merges an approved Dependabot PR against `main`, ported from
  ArcadeData/arcadedb. It is **not** byte-identical to its copy there, and differs in exactly two
  places. arcadedb guards `native/pom.xml`, whose GraalVM pin has to move in lockstep with a
  builder JDK Dependabot cannot see; the equivalent invariant here is this file's own first rule,
  so the guard refuses instead to auto-merge anything touching `contracts/` or generated output —
  a bump that edits either is not a bump, it is drift or a contract move, and a human adopts those
  with `adopt-contract-version.sh`. And arcadedb merges on one approval with no CI condition at
  all, inherited from the Mergify rule it replaced; this one refuses on a failing or still-running
  check, because the drift gates are the only thing that catches a generator bump changing
  generated output and `main` has no branch protection behind them. An **empty** check rollup still
  merges, deliberately: `ci.yml`, `ci-python.yml` and `ci-go.yml` are `paths`-filtered, so a github-actions
  bump — which only ever edits files under `.github/workflows/` — legitimately runs nothing, and
  failing that case closed would deadlock every such PR, since nothing re-fires the workflow once
  the approval is in. The merge is pinned to the commit the guard inspected
  (`--match-head-commit`), so a Dependabot force-push mid-run fails the run rather than merging a
  commit no guard saw.
- `claude.yml` — answers an `@claude` mention on an issue, a PR review, or a review comment. Ported
  from ArcadeData/arcadedb and deliberately kept byte-identical to its copy there, so a fix to one
  can be copied to the other without a merge. Its tool allow-list is read-only `gh` plus
  `gh pr comment`: Claude can read the repository and reply, and can change nothing else.
- `claude-code-review.yml` — reviews every pull request on open and on push. This is the one ported
  file that does **not** match arcadedb's: its prompt adds the three rules a
  reviewer needs here and nowhere else (generated code is never hand-edited, `contracts/` holds
  exactly one file of each kind, and the load-bearing prose in the READMEs moves with the behaviour
  it documents), and the commented-out `paths` and author-filter scaffolding the action's
  template ships with is dropped. The job also skips when the actor is `dependabot[bot]`:
  Dependabot runs see no `CLAUDE_CODE_OAUTH_TOKEN`, and the action rejects bot actors since
  v1.0.233, so without the skip every Dependabot PR carries a red check that
  `dependabot-auto-merge.yml` refuses to merge past. The steps, pins and allow-list are
  arcadedb's unchanged.
- `classify-issue.yml` — byte-identical to arcadedb's, two jobs in one file. One labels an issue
  opened by an ArcadeData GitHub Sponsor `high_priority`, creating that label on first use. The
  other asks Claude which of the repository's **existing** labels fit a newly opened issue, and a
  separate `github-script` step applies the answer. That split is the containment, not a style
  choice: the issue body is untrusted input, so Claude gets a read-only tool allow-list pinned to
  this one issue number and no write tool at all, and the applying step intersects what it asked
  for against the live label list — a hallucinated or injected name never reaches the API. It also
  passes `github_token` rather than taking `id-token: write`, because the OIDC exchange rejects
  issues opened by anyone without write access, i.e. every external reporter.

  The classifier can only ever choose from labels that already exist, so the repository's label
  set *is* its vocabulary: eleven area labels (`typescript`, `python`, `go`, `http-driver`,
  `grpc-driver`, `contract`, `codegen`, `build`, `release`, `e2e`, `licensing`) alongside the
  triage labels shared with arcadedb. Deleting a label silently narrows what the classifier can
  say; adding one widens it with no workflow edit.

## Dependency licenses

Every dependency of this repository — in all three ecosystems, runtime and development alike —
must carry a license on the allow-list below. This is ArcadeDB's policy, and the two
repositories are expected to agree; ArcadeDB's own copy lives in its `CLAUDE.md`.

- ✅ **ALLOWED:** Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, EPL-1.0/2.0, UPL-1.0,
  EDL-1.0, LGPL-2.1+ (i.e. 2.1 or 3.0, libraries only), MPL-2.0 (libraries only, unmodified),
  CDDL-1.0/1.1 (libraries only, unmodified), GPL-2.0 **WITH** the Classpath Exception
  specifically (never a bare GPL), CC0-1.0 / Public Domain, Unlicense, BlueOak-1.0.0,
  PSF-2.0 / Python-2.0, MIT-0
- ❌ **FORBIDDEN:** GPL, AGPL, SSPL, Commons Clause, BUSL-1.1, Elastic-2.0, and
  proprietary licenses without explicit permission

**This is an allow-list**: a license in neither row is not permitted by default. Anything
not allowed is denied whatever it is called, which is strictly stronger than enumerating
the bad ones — the FORBIDDEN row exists so a reader can tell a deliberate denial from an
accidental omission.

`scripts/check-licenses.py` enforces it over all three dependency trees, and
`.github/workflows/license-compliance.yml` runs it on dependency changes, weekly, and on
demand. The weekly run is not redundant: a package can be **relicensed** on a version
already pinned in a lockfile, and no manifest changes when that happens.

Five entries above are this repository's own additions to ArcadeDB's list, each made on
evidence from this tree rather than in the abstract: `BlueOak-1.0.0` (5 npm dev packages —
`jackspeak`, `minimatch`, `minipass`, `package-json-from-dist`, `path-scurry`),
`PSF-2.0`/`Python-2.0` (`typing_extensions`, a runtime dependency of `arcadedb-driver`),
`Unlicense` (one npm dev package, `tweetnacl`; CLAUDE.md already allowed "CC0/Public
Domain" and this is that category under its SPDX name), and `MPL-2.0` — already allowed
upstream for libraries, recorded explicitly here because `certifi` makes it a **runtime**
dependency (pulled in through `httpx`) rather than the dev-scope case ArcadeDB originally
blessed. And `MIT-0` ("MIT No Attribution", MIT without its attribution clause, so strictly more
permissive than the allowed `MIT`), carried by one Go module, `github.com/segmentio/asm`, which is
reached only through the `buf` code generator in `go/tools` — a tool dependency, never shipped to a
consumer of either Go module. go-licenses cannot classify MIT-0 and reports that module as
`Unknown`, which no spelling in `NORMALISE` can fix, so `scripts/check-licenses.py` carries a
narrow per-module override (`_GO_LICENSE_OVERRIDES`) applied only when go-licenses says exactly
`Unknown` for exactly that module; any other `Unknown`, or a different license reported for that
module, stays a violation. No other Go module needed an addition. `go.mod` records no license, so the Go collector runs
`go-licenses report` (pinned in `go/tools/go.mod`) over `go/arcadedb`, `go/arcadedbgrpc` and `go/e2e` with their
test dependencies included, and over the tools `go/tools` declares, resolves each reported package to the module that owns it, and
fails closed on a malformed row, a package no module owns, or a report that saw implausibly few
modules.

**What the gate cannot check.** "Libraries only, unmodified" is a rule for humans. The
checker sees a license identifier attached to a package; it cannot know whether this
repository has vendored, patched or re-published that package's source. A green run does
not certify that nobody copied an MPL-2.0 file into the tree. Nothing is vendored today —
the generated code under `_generated/`, `src/gen/` and `go/arcadedb/generated/` comes from ArcadeDB's own Apache-2.0
contracts — and if that ever changes, both this rule and the absence of an
`ATTRIBUTIONS.md` need revisiting.

Adding a license to the ALLOWED row means editing `ALLOWED_IDS` in
`scripts/check-licenses.py` **and** this section, together. A new *spelling* of a license
already allowed goes in that script's `NORMALISE` map instead — do not widen the
allow-list for a spelling.

## Design docs

`docs/superpowers/specs/` holds the design for each milestone and `docs/superpowers/plans/` the
implementation plan. They record why a client is shaped the way it is; read the relevant one
before reworking a client's public surface.

## Prose conventions

Every package README and the code comments document failure modes and deliberate asymmetries at
length (why `truncated` matters, why `exists` cannot prove absence, why the TypeScript gRPC client
throws `ConnectError` and not `ArcadeDBError` while its Python sibling raises `grpc.RpcError`
directly, why `bulkInsert` cannot join a `transaction()`, why the Go client's `TxError` does not
use `errors.Join`). When you change behaviour in one of
those areas, update the prose with it — those passages are load-bearing documentation, not
decoration.
