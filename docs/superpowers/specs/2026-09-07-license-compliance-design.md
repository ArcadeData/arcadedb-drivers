# License compliance for `arcadedb-drivers`

**Status:** design approved, plan pending
**Date:** 2026-09-07
**Ports:** ArcadeDB's `.github/scripts/check-license-allowlist.py` and `license-compliance.yml`

> **This is a dated design record, not a synced policy source.** The live policy is `ALLOWED_IDS`
> in `scripts/check-licenses.py` plus the "Dependency licenses" section of the root `CLAUDE.md`,
> which reference each other and are changed together. Read this document for *why* the gate is
> shaped the way it is; read those two for *what is allowed today*. The measured figures below were
> re-derived against the tree as of the implementation's final review and will drift with the next
> dependency bump - that is expected, and is not something to chase.

## 1. Scope

A CI gate that fails when any dependency of this repository declares a license outside an
allow-list, across **both** package ecosystems: the npm workspace under `typescript/` and the uv
workspace under `python/`.

One entry point, `scripts/check-licenses.py`, runnable by hand and from CI. One policy. Both
ecosystems.

**Runtime and development dependencies are both gated**, under one allow-list, matching what
ArcadeDB's Maven checker does for its whole reactor. The measured cost of that choice is small:
362 packages produce only 19 distinct license signals.

## 2. Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Policy engine | One script in this repo; not `license-checker`, not `dependency-review-action` |
| 2 | Scope | Runtime AND development dependencies, one allow-list |
| 3 | Policy home | Prose in root `CLAUDE.md`; machine-readable set inline in the script |
| 4 | Sync with ArcadeDB | By hand, cross-referenced in both `CLAUDE.md`s; no automated drift check |
| 5 | Matching | Normalise to SPDX ids, then evaluate as an SPDX expression |
| 6 | Unknown spellings | Fail closed - a violation a human reads, never a silent pass |
| 7 | Expression parser | Hand-rolled (~40 lines); `license-expression` named as the fallback |
| 8 | Attribution files | Out of scope - we vendor nothing (section 8) |

## 3. What the upstream tooling does, and why only part of it ports

ArcadeDB enforces its policy three ways. Only one of them is worth porting.

**`check-license-allowlist.py` (Maven) - port the philosophy.** A curated allow-list of exact
license clause strings, matched exactly so an unrecognised spelling fails closed rather than
silently passing or silently blocking. Its module docstring is explicit that a naive substring
grep for "GPL" mis-fires on `GNU General Public License (GPL), version 2, with the Classpath
exception`, which is exactly what makes those jars safe to link. That reasoning is the valuable
part, and it transfers unchanged.

**`license-checker --onlyAllow` (npm) - do not port.** Two independent defects, both verified
against the installed tool rather than inferred:

1. **It matches substrings, not licenses.** `lib/index.js` implements `--onlyAllow` as
   `restricted[item].licenses.indexOf(k) === -1`, i.e. `String.indexOf`. So a declared
   `(Apache-2.0 AND SSPL-1.0)` **passes** a gate configured to allow `Apache-2.0`, because the
   allowed id is a substring of the expression. `AND` means the consumer must comply with *every*
   operand; substring matching inverts that. SSPL is on ArcadeDB's FORBIDDEN row.
2. **It cannot see an npm workspace.** Run against `typescript/`, with `node_modules` present, it
   exits with `Error: No packages found in this path.` - our packages live under `packages/*`.

Upstream additionally invokes it as `... || echo "⚠️ Non-standard licenses detected"`, so it cannot
fail a build even when it is right. And its allow-list
(`MIT;Apache-2.0;BSD-2-Clause;BSD-3-Clause;ISC;0BSD`) is narrower than ArcadeDB's own stated
policy - it omits EPL, LGPL-2.1+, MPL-2.0 and CC0, all of which CLAUDE.md ALLOWS. A dependency
under a license the project permits would be flagged; a dependency under SSPL would not.

**`dependency-review-config.yml` - cannot express this policy.** Its own comments say so:
`allow-licenses` and `deny-licenses` are mutually exclusive, so it cannot be an allow-list *and*
carry the specific denials; "Commons Clause" and proprietary terms have no SPDX id and cannot be
expressed at all. It is also PR-only, so it can never audit `main` or run on a schedule - which
matters, because a package can be relicensed on a version already in the lockfile.

## 4. What we actually depend on

Measured, not estimated, at the time of writing.

| Ecosystem | Packages | Distinct license signals |
|---|---|---|
| npm (`typescript/`, all deps) | 313 | 11 |
| Python (`python/`, all deps) | 49 | 13 |
| **Both** | **362** | **19** |

The two ecosystems share five signals (MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, MPL-2.0), which
is why 11 + 13 is 19 and not 24.

npm's spread is entirely SPDX ids: MIT (216), Apache-2.0 (40), ISC (26), BSD-3-Clause (14),
BSD-2-Clause (6), BlueOak-1.0.0 (5), MPL-2.0 (2), `(Apache-2.0 AND BSD-3-Clause)` (1),
`(MIT OR CC0-1.0)` (1), Python-2.0 (1), Unlicense (1). Zero undeclared.

The npm count is what a run on *this* machine installs, not what the lockfile enumerates - see
section 6.2 for why those differ and what it costs.

Python's spread arrives through **three** metadata channels with different fidelity: PEP 639
`License-Expression` (SPDX), the legacy free-text `License` field (`3-Clause BSD License`,
`Apache License 2.0`, `ISC License`), and Trove classifiers (`BSD License`,
`Mozilla Public License 2.0 (MPL 2.0)`). It also contains one unparenthesised compound,
`Apache-2.0 OR BSD-2-Clause`.

Python's 13 signals break down as MIT (24), Apache-2.0 (7), BSD-3-Clause (6), BSD-2-Clause (2),
`MIT License` (2), and one each of `MPL-2.0`, `BSD License`, `Apache License 2.0`,
`Apache-2.0 OR BSD-2-Clause`, `Mozilla Public License 2.0 (MPL 2.0)`, `3-Clause BSD License`,
`ISC License` and `PSF-2.0`. Six of those thirteen are free text or Trove classifiers rather than
SPDX ids - the whole reason `NORMALISE` exists.

The **runtime** graph - what a user inherits by installing our packages - is 5 npm and 11 Python
distributions, the eleventh being `exceptiongroup`, which `anyio` pulls in only below Python 3.11.

## 5. Policy

### 5.1 Where it lives

The human-readable rows go in this repository's root `CLAUDE.md`, in the same shape ArcadeDB uses
(ALLOWED / FORBIDDEN / "this is an allow-list"). The machine-readable set lives inline in
`scripts/check-licenses.py`, each entry carrying its justification as a comment, with a "keep in
sync with CLAUDE.md" note in both directions - the same arrangement upstream has, for the same
reason: the reasoning belongs beside the entry.

**Not automatically synced with ArcadeDB.** Two repositories, prose canon, and genuinely different
license spellings per ecosystem. A job diffing two `CLAUDE.md` files would fail for reasons that
are not policy drift. Each repository's `CLAUDE.md` instead names the other as its sibling, so a
reviewer knows a real policy change propagates by hand. If drift turns out to bite, that is a
follow-up with evidence behind it.

### 5.2 One canonical set plus a normalisation map

ArcadeDB's checker matches raw clause strings because Maven metadata is almost entirely free text -
SPDX ids are the exception there. Our data inverts that: most signals are already valid SPDX ids.

So the engine keeps **one set of allowed SPDX identifiers** and a **curated map** from the messy
spellings actually observed to those ids (`3-Clause BSD License` -> `BSD-3-Clause`,
`Apache License 2.0` -> `Apache-2.0`, `Mozilla Public License 2.0 (MPL 2.0)` -> `MPL-2.0`, ...).
Same fail-closed principle, less duplication: `Apache-2.0` is written once rather than ten times.

### 5.3 Allowed

Ported from ArcadeDB's ALLOWED row: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, EPL-1.0,
EPL-2.0, UPL-1.0, EDL-1.0, LGPL-2.1+ (libraries only), MPL-2.0 (libraries only, unmodified),
CDDL-1.0/1.1 (libraries only, unmodified), GPL-2.0 **WITH** the Classpath Exception specifically,
CC0-1.0 / Public Domain.

**Four additions**, each proposed on evidence from our own tree:

| License | Rationale | Where it appears |
|---|---|---|
| `BlueOak-1.0.0` | OSI-approved, permissive, drafted as a plain-language MIT/BSD equivalent with a patent grant | 5 npm dev packages |
| `PSF-2.0` / `Python-2.0` | The Python Software Foundation license: permissive, Apache-2.0 compatible, unavoidable in a Python project | `typing_extensions` (**runtime**), 1 npm package |
| `Unlicense` | Public-domain dedication; CLAUDE.md already allows "CC0/Public Domain" - this is that category under its SPDX name | 1 npm package |
| `MPL-2.0` | Already ALLOWED upstream for libraries; recorded explicitly here because it is now a **runtime** dependency | `certifi` (**runtime**), 2 npm |

**`certifi` is a decision, not a list entry.** Upstream blessed MPL-2.0 "for libraries only,
unmodified" when it applied to jars that ship inside a fat artifact. Here it reaches every user who
installs `arcadedb-driver`. MPL-2.0's copyleft is file-level and attaches to modifications of the
covered files, so a consumer depending on it unmodified takes on no obligation - which is why this
design allows it. But it is a change in what we ship, and it is recorded here as such so a
maintainer can disagree with it deliberately rather than discover it in a list.

### 5.4 What "libraries only, unmodified" means, and what the gate cannot check

Three entries carry a qualifier: LGPL-2.1+, MPL-2.0 and CDDL are allowed "for libraries only",
MPL-2.0 and CDDL additionally "unmodified". **The checker does not and cannot enforce those
qualifiers.** It sees a license identifier attached to a package; it has no way to know whether
this repository has vendored, patched or re-published that package's source.

So the split is explicit: the gate enforces *which licenses may appear*, and a human enforces *how
those dependencies may be used*. Depending on the published artifact as-is is what the qualifier
permits. Copying a weak-copyleft file into this repository, or patching one and shipping the
result, is outside what the gate can see and requires revisiting the license implications
directly.

This is worth stating because the failure mode is a false sense of coverage: a green
license-compliance run does not certify that nobody vendored an MPL-2.0 file. Today nothing is
vendored - the generated code under `_generated/` and `src/gen/` is produced from ArcadeDB's own
Apache-2.0 contracts, not from a third-party source tree - and section 8's non-goal on attribution
files expires under exactly the same condition.

### 5.5 Forbidden

Ported verbatim: GPL, AGPL, SSPL, Commons Clause, BUSL-1.1, Elastic-2.0, and proprietary licenses
without explicit permission. GPL-2.0 is permitted **only** in the `WITH Classpath-exception-2.0`
form, never bare.

This row is documentation, not mechanism. The gate is an allow-list: anything not allowed is denied
whatever it is called, which is strictly stronger than enumerating the bad ones. The row exists so
a reader knows which denials are deliberate rather than accidental omissions.

## 6. Architecture

```
scripts/
├── check-licenses.py          # policy + collectors + engine
└── tests/
    └── test_check_licenses.py # pytest
.github/workflows/
└── license-compliance.yml
```

One file with three sections, mirroring upstream's 221-line single-file shape. If it passes ~300
lines the collectors split out; proposing that split now would be speculative.

### 6.1 The record shape

Both collectors normalise to one record, which is what lets one engine serve two ecosystems:

```python
{
  "ecosystem": "npm",
  "name": "@bufbuild/protobuf",
  "version": "2.14.0",
  "signal": "(Apache-2.0 AND BSD-3-Clause)",
  "source": "package.json:license",
}
```

`source` is carried into every error message. A reviewer needs to know whether a signal came from a
machine-readable SPDX expression or a guessed Trove classifier, because those warrant different
responses.

### 6.2 npm collector

**`node_modules` itself is the authority, not `npm ls`.** The collector walks
`typescript/node_modules` with `rglob("package.json")`, reads each manifest, and indexes it by the
`(name, version)` the manifest declares *for itself* - never by the directory it happens to sit in.
Its `license` field is then the signal, including the legacy `licenses: [...]` array form. No new
dependency, and it works on a workspace, which `license-checker` does not.

This design started as `npm ls --all --json` and changed during implementation, for two reasons
both verified against this tree rather than reasoned about:

1. **npm aliases.** `node_modules/string-width-cjs/package.json` declares `"name": "string-width"`.
   `npm ls` reports the alias name (`string-width-cjs`), so an index keyed on the package's own
   declared name cannot be looked up by it, and one keyed on the alias name mislabels the package.
   Three such aliases are installed here (`string-width-cjs`, `strip-ansi-cjs`, `wrap-ansi-cjs`).
   Reading the manifest's own `name` sidesteps the question entirely: the identity that matters for
   licensing is the one the package declares for itself.
2. **Platform-specific optional dependencies.** `npm ls` lists native binaries for OS/CPU targets
   that never install on the running machine, so every entry would have to be probed for existence
   before its manifest could be read - and a missing one is indistinguishable from a broken install.
   Walking the directory makes "installed" the definition rather than something to reconstruct.

**The trade-off this carries, stated plainly.** `package-lock.json` holds 390 dependency entries
(excluding the two workspace symlinks and the two workspace path entries). **60 of those are
`os`/`cpu`-gated optional packages**, and no single run ever audits all of them: on the ubuntu CI
runner only the `linux-x64` subset installs, and on an arm64 macOS checkout only 5 of the 60 do.
They are the `@esbuild/*`, `@rolldown/binding-*`, `lightningcss-*`, `@bufbuild/buf-*` and `fsevents`
families - all 60 are `dev: true`, and all 60 declare a license in `{MIT, Apache-2.0, MPL-2.0}`,
every one of which is on the allow-list.

That is acceptable **today, on that condition** - dev-scope build tooling under already-allowed
licenses, small enough to read from the lockfile by hand. **The condition matters more than the
conclusion.** It would *not* be acceptable for a platform-specific **runtime** dependency: such a
package reaches users of that platform, is never installed on the ubuntu runner, and would
therefore never be audited by this gate at all. The lockfile's `license` field is the fallback for
that case - readable without installing anything - and a runtime `os`/`cpu`-gated dependency
appearing in this tree is the trigger to add it.

### 6.3 Python collector

`uv run --project python python -c ...` emitting `importlib.metadata` records as JSON. Source
precedence is explicit and recorded per package:

1. PEP 639 `License-Expression` (SPDX, authoritative)
2. the legacy `License` field (free text)
3. Trove classifiers (coarsest)

The precedence is a real decision: `httpcore` carries both `BSD-3-Clause` and the vaguer
`BSD License` classifier, and the precise one must win. Note that the `BSD License` classifier
cannot distinguish 2-clause from 3-clause; both are allowed, so it is harmless here, but the
fallback is coarse by nature and `source` records when it was used.

### 6.4 The empty-tree guard

Each collector asserts it found a plausible number of packages and exits 2 with the fix when it did
not - `node_modules` absent, or the uv venv unsynced.

This is ported deliberately. Upstream's checker once reported success while inspecting a near-empty
aggregator pom, which is why it now prints "No dependency lines found ... this usually means the
report was generated with the non-aggregate goal". This repository hit the same class of bug during
M3b, when `[tool.pytest.ini_options] testpaths` excluded every gRPC test and CI stayed green over
zero tests. **A checker that silently checks nothing is worse than no checker**, because it
converts an absence of evidence into a passing gate.

### 6.5 Exit codes

Matching upstream: `0` clean, `1` policy violation (offending packages printed with name, version,
raw signal and source), `2` usage or environment error.

## 7. Evaluating a signal

Normalise first, then evaluate as an SPDX expression. A signal that is neither a known SPDX id nor
in the normalisation map is a **violation** - never a guess.

**Operator semantics:**

- **`AND` - every operand must be allowed.** The consumer must comply with all of them. This is the
  case upstream's substring test inverts, and it gets a dedicated regression test.
- **`OR` - one allowed operand suffices.** The consumer chooses.
- **`WITH` - atomic.** The pair is looked up as a unit and never decomposed. Decomposing
  `GPL-2.0-only WITH Classpath-exception-2.0` would allow bare `GPL-2.0-only`, which is exactly
  what section 5.5 forbids. This is the most dangerous place in the engine to be clever.
- **npm's legacy `licenses: [...]` array** is treated as `OR`, which is what that form meant.
- **Undeclared** is a violation. There are currently zero; the point is to find out if that changes.

**Parser.** Hand-rolled, roughly 40 lines, over adding `license-expression`. The grammar is closed
and tiny (identifiers, `AND`, `OR`, `WITH`, parentheses), and fail-closed makes parser gaps safe by
construction: anything unparseable becomes a violation a human reads, never a silent pass. Adding a
dependency to the tool that audits dependencies also has a bootstrapping smell.
`license-expression` (Apache-2.0, AboutCode) is named in a comment as the drop-in if the grammar
ever justifies it.

**Two spec details:** SPDX identifiers compare case-insensitively, per the specification, so `MIT`
and `mit` do not produce a spurious failure. A trailing `+` (`LGPL-2.1+`) normalises to the
`-or-later` id - absent from our tree today, but the policy itself is written as "LGPL 2.1+", and a
legitimate dependency should not be blocked by the policy's own spelling.

## 8. Non-goals

- **`ATTRIBUTIONS.md` / `NOTICE` aggregation.** Upstream needs it because it ships a fat jar
  containing third-party code. We publish four thin libraries that *declare* dependencies;
  consumers resolve those from npm and PyPI with their licenses attached, and we vendor nothing.
  **The condition matters more than the conclusion**: if this repository ever bundles or vendors a
  dependency, this non-goal expires and attribution obligations become real.
- **A PR comment.** Upstream posts one on every PR. This repository has no such habit and a bot
  comment on every dependency bump is noise. The failing step is the signal.
- **An uploaded report artifact.** Upstream uploads one because a Maven run is not reproducible from
  the repository alone. Ours is: `package-lock.json` and `uv.lock` are both committed, so any past
  inventory regenerates exactly. The artifact would duplicate what the lockfiles already pin.
- **Automated policy sync with ArcadeDB** - see section 5.1.
- **Vulnerability scanning.** Out of scope; a separate concern with separate tooling.

## 9. CI

`.github/workflows/license-compliance.yml`, separate from `ci.yml` and `ci-python.yml`. Those are
per-language with path filters; this is one cross-cutting check over both ecosystems with its own
schedule - the same argument that puts `buf.yaml` at the repository root.

**Triggers:**

- `pull_request` on `typescript/package-lock.json`, `typescript/**/package.json`, `python/uv.lock`,
  `python/**/pyproject.toml`, `scripts/check-licenses.py`, `scripts/tests/test_check_licenses.py`,
  and `CLAUDE.md`. The last three matter: **a policy edit must re-run the gate that enforces it.**
- `schedule`, weekly. A package can be **relicensed** on a version already pinned in a lockfile, and
  no manifest changes when that happens. This is the only trigger that catches it.
- `workflow_dispatch`.

**Steps:** checkout, `npm ci` in `typescript/`, `uv sync` in `python/`, run the checker, run its
tests, write the license spread to the job summary.

The job summary lists the spread (`240 MIT, 47 Apache-2.0, ...`) so a passing run still shows what
we depend on rather than only asserting that it is fine.

## 10. Testing

`scripts/tests/test_check_licenses.py`, run with `uv run --project python python -m pytest`, and the
checker added to `python/pyproject.toml`'s mypy scope - this repository already type-checks its own
tooling (`check_codegen_skips.py` is on the mypy path).

The semantics are the product, so they are what the tests pin:

1. **`(Apache-2.0 AND SSPL-1.0)` fails.** The direct regression test against the upstream substring
   hole, and the reason this design does not reuse that tool.
2. `(MIT OR CC0-1.0)` and `Apache-2.0 OR BSD-2-Clause` pass.
3. `GPL-2.0-only WITH Classpath-exception-2.0` passes; bare `GPL-2.0-only` fails.
4. An unrecognised spelling fails closed, naming the package and the raw text.
5. **An empty inventory exits 2, not 0** - the silent-pass guard of section 6.4.
6. SPDX ids compare case-insensitively.
7. npm's legacy `licenses: [...]` array evaluates as `OR`.
8. Python source precedence: a PEP 639 expression beats a Trove classifier.
9. An end-to-end run over the real repository exits 0 - which is also what proves the four
   additions in section 5.3 are sufficient and that the gate is not green over an empty tree.

## 11. Prose conventions

The root `CLAUDE.md` gains the ALLOWED / FORBIDDEN rows and a pointer to the checker. `scripts/`'s
entry in `CLAUDE.md` gains `check-licenses.py` alongside the contract scripts.

Per this repository's conventions, the checker's comments carry the reasoning, at length: why
substring matching is wrong for `AND`, why `WITH` is atomic, why unknown spellings fail closed, and
why the empty-tree guard exists. Those passages are the load-bearing part - a future reader who
"simplifies" the `WITH` handling or relaxes the fail-closed rule would reintroduce exactly the
defects this design exists to avoid.
