# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Language clients for ArcadeDB's HTTP and gRPC APIs. One contract per API in `contracts/`, many
language clients generated from it. `typescript/` and `python/` are the language directories
today; `go/` and others will appear as their siblings.

The organising rule: **generated code is never hand-edited.** The contract is the single source of
truth, and CI's *drift gate* regenerates from the committed contract and fails if the result
differs from what is checked in. If a generated file looks wrong, fix the contract or the
generator config — editing the output only makes CI red.

See `typescript/CLAUDE.md` for the TypeScript workspace and `python/CLAUDE.md` for the Python
workspace (commands, package layout, conventions). The Python workspace hosts two packages the
same way the TypeScript one does: `arcadedb-driver`, the HTTP client, and `arcadedb-driver-grpc`,
the gRPC client generated from the `.proto` contract.

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

scripts/check-licenses.py                            # fail if any dependency's license is off the allow-list
```

`fetch-contract.sh` writes the new contract **beside** the old one rather than in place, so a
version bump is a two-step operation: fetch both contracts, then run
`adopt-contract-version.sh <version>`, which deletes the retired contract and generated module,
rewrites the version-stamped imports, and updates each package's recorded server version
(`arcadedb.serverVersion` in a TypeScript `package.json`, `[tool.arcadedb] server-version` in a
Python `pyproject.toml`). It deliberately does not touch the compatibility tables in the READMEs —
those rows are a historical record tied to a package version, and adding one is a human decision.

`adopt-contract-version.sh` is language-aware: which files it rewrites is driven by an explicit
`LANGUAGES` table (file suffixes and directories to skip, per language) rather than by crawling
every top-level directory. Adding a language client to this repository is a deliberate one-line
addition to that table, not something the script infers by finding a new sibling of `contracts/`.

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
describes the contract itself and a future Python or Go client reads the same module.

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
- `contract-watch.yml` — daily, refreshes contracts from the SNAPSHOT server built off arcadedb's
  `main`. A changed contract gets an issue plus an adopt-and-regenerate PR; an unchanged contract
  with a red suite gets an issue only (it is a server regression no PR here can fix). Both are
  filed idempotently against one tracking issue and one branch. It now regenerates and verifies
  **both** clients, not just the TypeScript one.
- `publish.yml` — the only thing that talks to npm, and it is **manual workflow_dispatch only**.
  Nothing publishes on push, tag, or schedule. It re-verifies that the dispatch input, the
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
  **manual workflow_dispatch only**, with the same dispatch-input/version/contract re-verification.
  It publishes **one package per dispatch**, chosen by a `package` input (`driver` or
  `driver-grpc`), and is parameterised for the same reason `publish.yml` is: PyPI, like npm, keys a
  trusted publisher on the workflow **filename**, so both packages naming this one file means one
  thing to configure and cross-check instead of two. The version-check gate compares the chosen
  package's `[tool.arcadedb] server-version` against the committed OpenAPI contract's
  `info.version` — for **both** packages, including `driver-grpc`. That is not a proto-specific
  check masquerading as one; it works today only because `adopt-contract-version.sh` stamps every
  package's `server-version` from the same version argument, so the OpenAPI contract's version is a
  correct stand-in for the version the `.proto` contract carries too. Its bootstrap story inverts
  npm's: PyPI supports pending publishers, so a package's trusted publisher can be configured
  before the package exists on the index, and the first publish of either package needed no stored
  secret at all. Both are on PyPI at 0.1.0 today, `driver-grpc` included, each published that way.
  See the workflow file's comments for the caveat that does carry over from npm (check the
  workflow filename in PyPI's publisher settings against this file's actual name whenever either
  changes).
- `license-compliance.yml` — runs `scripts/check-licenses.py` over both dependency trees on a push
  or pull request that touches either lockfile, either package's manifests, the checker itself, its
  tests, or this file (a policy edit must re-run the gate it changes), plus weekly and on demand.
  The weekly run is not redundant with the path filters: a package can be relicensed on a version
  already pinned in a lockfile, which changes no manifest for the path filters to catch.

## Dependency licenses

Every dependency of this repository — in both ecosystems, runtime and development alike —
must carry a license on the allow-list below. This is ArcadeDB's policy, and the two
repositories are expected to agree; ArcadeDB's own copy lives in its `CLAUDE.md`.

- ✅ **ALLOWED:** Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, EPL-1.0/2.0, UPL-1.0,
  EDL-1.0, LGPL-2.1+ (i.e. 2.1 or 3.0, libraries only), MPL-2.0 (libraries only, unmodified),
  CDDL-1.0/1.1 (libraries only, unmodified), GPL-2.0 **WITH** the Classpath Exception
  specifically (never a bare GPL), CC0-1.0 / Public Domain, Unlicense, BlueOak-1.0.0,
  PSF-2.0 / Python-2.0
- ❌ **FORBIDDEN:** GPL, AGPL, SSPL, Commons Clause, BUSL-1.1, Elastic-2.0, and
  proprietary licenses without explicit permission

**This is an allow-list**: a license in neither row is not permitted by default. Anything
not allowed is denied whatever it is called, which is strictly stronger than enumerating
the bad ones — the FORBIDDEN row exists so a reader can tell a deliberate denial from an
accidental omission.

`scripts/check-licenses.py` enforces it over both dependency trees, and
`.github/workflows/license-compliance.yml` runs it on dependency changes, weekly, and on
demand. The weekly run is not redundant: a package can be **relicensed** on a version
already pinned in a lockfile, and no manifest changes when that happens.

Four entries above are this repository's own additions to ArcadeDB's list, each made on
evidence from this tree rather than in the abstract: `BlueOak-1.0.0` (5 npm dev packages —
`jackspeak`, `minimatch`, `minipass`, `package-json-from-dist`, `path-scurry`),
`PSF-2.0`/`Python-2.0` (`typing_extensions`, a runtime dependency of `arcadedb-driver`),
`Unlicense` (one npm dev package, `tweetnacl`; CLAUDE.md already allowed "CC0/Public
Domain" and this is that category under its SPDX name), and `MPL-2.0` — already allowed
upstream for libraries, recorded explicitly here because `certifi` makes it a **runtime**
dependency (pulled in through `httpx`) rather than the dev-scope case ArcadeDB originally
blessed.

**What the gate cannot check.** "Libraries only, unmodified" is a rule for humans. The
checker sees a license identifier attached to a package; it cannot know whether this
repository has vendored, patched or re-published that package's source. A green run does
not certify that nobody copied an MPL-2.0 file into the tree. Nothing is vendored today —
the generated code under `_generated/` and `src/gen/` comes from ArcadeDB's own Apache-2.0
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
directly, why `bulkInsert` cannot join a `transaction()`). When you change behaviour in one of
those areas, update the prose with it — those passages are load-bearing documentation, not
decoration.
