# License Compliance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CI gate that fails when any dependency of this repository - npm or Python, runtime or dev - declares a license outside an allow-list.

**Architecture:** One entry point, `scripts/check-licenses.py`, with three internal sections: the policy (allowed SPDX ids, `WITH` pairs, and a normalisation map for messy spellings), two collectors that normalise each ecosystem into one record shape, and an engine that parses and evaluates SPDX expressions. Unknown spellings fail closed. A separate `license-compliance.yml` runs it on dependency changes, weekly, and on demand.

**Tech Stack:** Python 3.10+ (stdlib only - no new dependency in either ecosystem), `npm ls` for the npm tree, `importlib.metadata` via `uv run` for the Python tree, pytest for the tests.

**Spec:** `docs/superpowers/specs/2026-09-07-license-compliance-design.md`

## Global Constraints

- Python floor `>=3.10`. The checker is **stdlib only** - adding a dependency to the tool that audits dependencies has a bootstrapping smell, and it must run before either ecosystem's install step has necessarily succeeded.
- `mypy` runs in **strict** mode over the checker and its tests. **No `# type: ignore` without a comment saying why.**
- `ruff` line-length 120; lint selects `E, F, I, UP, B, SIM, RUF`. Unused imports (F401) and unnecessary `noqa` (RUF100) are both errors.
- **Fail closed.** A signal that is neither a known SPDX id nor in the normalisation map is a violation, never a guess.
- **`WITH` is atomic.** Never decompose a `WITH` pair; decomposing `GPL-2.0-only WITH Classpath-exception-2.0` would allow bare `GPL-2.0-only`, which the policy forbids.
- Exit codes: `0` clean, `1` policy violation, `2` usage or environment error.
- Pin any GitHub Action by full commit SHA with a version comment, matching the existing workflows.
- Do not push, do not open a PR, do not dispatch any workflow. Commit only.
- Commit after every task.

---

## File Structure

**New:**

| File | Responsibility |
|---|---|
| `scripts/check-licenses.py` | Policy, both collectors, the SPDX engine, the CLI. |
| `scripts/tests/test_check_licenses.py` | pytest suite for the policy and engine. |
| `.github/workflows/license-compliance.yml` | Runs the checker on dependency changes, weekly, and on demand. |

**Modified:**

| File | Change |
|---|---|
| `CLAUDE.md` | The ALLOWED / FORBIDDEN rows, and `check-licenses.py` in the scripts list. |
| `python/pyproject.toml` | Add the checker and its tests to mypy's scope. |

The checker is one file with three clearly separated sections, mirroring the 221-line upstream script it ports. If it passes ~300 lines the collectors split out; proposing that split now would be speculative.

---

### Task 1: The policy and the SPDX engine

The heart of the work, and the only part with subtle semantics. Pure functions, no I/O, fully testable in isolation.

**Files:**
- Create: `scripts/check-licenses.py`
- Create: `scripts/tests/test_check_licenses.py`
- Modify: `python/pyproject.toml`

**Interfaces:**
- Consumes: nothing.
- Produces, all imported by Tasks 2-4:
  - `ALLOWED_IDS: set[str]` - allowed SPDX identifiers
  - `ALLOWED_WITH: set[tuple[str, str]]` - allowed `(license, exception)` pairs
  - `NORMALISE: dict[str, str]` - lowercased messy spelling -> SPDX id
  - `evaluate(signal: str) -> tuple[bool, str]` - `(allowed, reason)`; `reason` is `""` when allowed

- [ ] **Step 1: Put the checker on mypy's path**

In `python/pyproject.toml`, extend `[tool.mypy]`:

```toml
files = [
    "packages/driver/src/arcadedb_driver",
    "packages/driver/tests",
    "packages/driver-grpc/src/arcadedb_driver_grpc",
    "packages/driver-grpc/tests",
    "e2e",
    "../scripts/check-licenses.py",
    "../scripts/tests/test_check_licenses.py",
]
```

`mypy_path` already lists `scripts` (for `python/scripts`); leave it alone. If mypy cannot resolve the module from that relative path, add `"../scripts"` to `mypy_path` and say so in your report - do not silence it with an ignore.

- [ ] **Step 2: Write the failing tests**

Create `scripts/tests/test_check_licenses.py`. Note the import dance: the checker has a hyphen in its name, so it is loaded by path rather than imported normally.

```python
"""Tests for scripts/check-licenses.py.

The semantics ARE the product here, so these tests pin them directly rather than
going through the collectors. Every case below corresponds to a decision recorded in
docs/superpowers/specs/2026-09-07-license-compliance-design.md section 7.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_CHECKER = Path(__file__).resolve().parent.parent / "check-licenses.py"


def _load() -> ModuleType:
    # The script's filename contains a hyphen, so it cannot be imported by name.
    spec = importlib.util.spec_from_file_location("check_licenses", _CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_licenses"] = module
    spec.loader.exec_module(module)
    return module


cl = _load()


def test_a_plain_allowed_id_passes() -> None:
    allowed, reason = cl.evaluate("MIT")
    assert allowed is True
    assert reason == ""


def test_a_forbidden_id_fails() -> None:
    allowed, reason = cl.evaluate("SSPL-1.0")
    assert allowed is False
    assert reason


def test_and_requires_every_operand_to_be_allowed() -> None:
    # THE regression test for this whole design. `license-checker --onlyAllow` uses
    # String.indexOf, so it passes this expression because "Apache-2.0" is a substring.
    # AND means the consumer must comply with BOTH; one forbidden operand poisons it.
    allowed, _ = cl.evaluate("(Apache-2.0 AND SSPL-1.0)")
    assert allowed is False


def test_and_passes_when_both_operands_are_allowed() -> None:
    allowed, _ = cl.evaluate("(Apache-2.0 AND BSD-3-Clause)")
    assert allowed is True


def test_or_passes_on_a_single_allowed_operand() -> None:
    assert cl.evaluate("(MIT OR CC0-1.0)")[0] is True


def test_or_without_parentheses_parses() -> None:
    # Real signal from `grpcio`'s metadata; the SPDX grammar does not require parens.
    assert cl.evaluate("Apache-2.0 OR BSD-2-Clause")[0] is True


def test_or_fails_when_no_operand_is_allowed() -> None:
    assert cl.evaluate("GPL-3.0-only OR AGPL-3.0-only")[0] is False


def test_with_is_atomic_and_allowed_as_a_pair() -> None:
    assert cl.evaluate("GPL-2.0-only WITH Classpath-exception-2.0")[0] is True


def test_bare_gpl_is_denied_even_though_the_with_pair_is_allowed() -> None:
    # The reason WITH must never be decomposed: splitting the pair above would make
    # this pass, which is exactly what the policy forbids.
    assert cl.evaluate("GPL-2.0-only")[0] is False


def test_with_an_unknown_exception_is_denied() -> None:
    assert cl.evaluate("GPL-2.0-only WITH Some-Other-Exception")[0] is False


def test_spdx_ids_compare_case_insensitively() -> None:
    assert cl.evaluate("mit")[0] is True
    assert cl.evaluate("APACHE-2.0")[0] is True


def test_a_trailing_plus_means_or_later() -> None:
    # The policy itself is written as "LGPL 2.1+", so a dependency spelling it that
    # way must not be blocked by the policy's own notation.
    assert cl.evaluate("LGPL-2.1+")[0] is True


def test_known_free_text_spellings_normalise() -> None:
    assert cl.evaluate("3-Clause BSD License")[0] is True   # protobuf
    assert cl.evaluate("Apache License 2.0")[0] is True     # legacy metadata
    assert cl.evaluate("ISC License")[0] is True
    assert cl.evaluate("Mozilla Public License 2.0 (MPL 2.0)")[0] is True  # Trove


def test_an_unrecognised_spelling_fails_closed() -> None:
    allowed, reason = cl.evaluate("Totally Made Up License v9")
    assert allowed is False
    assert "unrecognis" in reason.lower() or "unparse" in reason.lower()


def test_an_empty_signal_fails_closed() -> None:
    assert cl.evaluate("")[0] is False


def test_an_unbalanced_expression_fails_closed_rather_than_raising() -> None:
    allowed, reason = cl.evaluate("(MIT OR Apache-2.0")
    assert allowed is False
    assert reason


def test_the_four_policy_additions_are_present() -> None:
    # Section 5.3 of the spec. Each was added on evidence from this repo's own tree;
    # removing one should break a test, not silently start failing the real run.
    for spdx in ("BlueOak-1.0.0", "PSF-2.0", "Python-2.0", "Unlicense", "MPL-2.0"):
        assert cl.evaluate(spdx)[0] is True, spdx
```

- [ ] **Step 3: Run the tests and watch them fail**

Run: `cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -v`
Expected: FAIL - `FileNotFoundError` or `ModuleNotFoundError`, because `scripts/check-licenses.py` does not exist yet.

- [ ] **Step 4: Write the policy section**

Create `scripts/check-licenses.py` starting with the module docstring and policy:

```python
#!/usr/bin/env python3
"""Fails when any dependency of this repository declares a license outside the allow-list.

Covers BOTH ecosystems - the npm workspace under typescript/ and the uv workspace under
python/ - and both runtime and development dependencies, under one allow-list. See
docs/superpowers/specs/2026-09-07-license-compliance-design.md.

This is a port of ArcadeDB's .github/scripts/check-license-allowlist.py. What ports is its
PHILOSOPHY: a curated allow-list, matched exactly, failing closed on an unrecognised
spelling rather than guessing. What deliberately does NOT port is `license-checker
--onlyAllow`, which ArcadeDB uses on its npm graph, for two defects verified against the
installed tool:

  1. It matches SUBSTRINGS. license-checker/lib/index.js implements --onlyAllow as
     `licenses.indexOf(k) === -1`, so a declared "(Apache-2.0 AND SSPL-1.0)" PASSES a gate
     allowing Apache-2.0, because the allowed id is a substring of the expression. AND
     means the consumer must comply with EVERY operand; substring matching inverts that.
  2. It cannot see an npm workspace - run against typescript/ with node_modules present it
     exits "No packages found in this path.", because our packages live under packages/*.

Usage:
    scripts/check-licenses.py                # check both ecosystems
    scripts/check-licenses.py --ecosystem npm
    scripts/check-licenses.py --ecosystem python

Exit codes: 0 clean, 1 policy violation, 2 usage or environment error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Policy. Keep in sync with CLAUDE.md's ALLOWED / FORBIDDEN rows, and with
# ArcadeDB's own CLAUDE.md - the two repositories share this policy and are NOT
# synced automatically (see the spec, section 5.1).
# ---------------------------------------------------------------------------

# Allowed SPDX identifiers. One canonical id per license: the messy spellings live in
# NORMALISE below rather than being repeated here. Comparison is case-insensitive, per
# the SPDX specification.
ALLOWED_IDS = {
    # Permissive, uncontroversial, and the bulk of both trees.
    "Apache-2.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    # Eclipse.
    "EPL-1.0",
    "EPL-2.0",
    # UPL. EDL 1.0 has no SPDX id of its own - it IS BSD-3-Clause - so it is handled in
    # NORMALISE rather than listed here.
    "UPL-1.0",
    # LGPL 2.1+, for libraries only. "+" reaches LGPL-3.0, hence all four ids.
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    # MPL-2.0 and CDDL, for libraries only, unmodified: file-level weak copyleft that
    # imposes nothing on a project depending on the library as-is. NOTE that MPL-2.0 is
    # now a RUNTIME dependency here (certifi, via httpx), not the dev-scope case ArcadeDB
    # originally blessed - see the spec, section 5.3.
    "MPL-2.0",
    "CDDL-1.0",
    "CDDL-1.1",
    # Public domain and equivalents.
    "CC0-1.0",
    "Unlicense",
    # --- Additions made by this repository, each on evidence from its own tree. ---
    # OSI-approved, permissive, drafted as a plain-language MIT/BSD equivalent with an
    # explicit patent grant. Ships in 5 npm dev packages.
    "BlueOak-1.0.0",
    # The Python Software Foundation license: permissive, Apache-2.0 compatible, and
    # unavoidable in a Python project. `typing_extensions` is a RUNTIME dependency of
    # arcadedb-driver. Both spellings occur - PSF-2.0 in Python metadata, Python-2.0 in
    # npm metadata - and they name the same license.
    "PSF-2.0",
    "Python-2.0",
}

# Allowed (license, exception) pairs for SPDX `WITH`. This set is looked up ATOMICALLY and
# the pair is NEVER decomposed: GPL-2.0 is permitted only in combination with the Classpath
# Exception, which is the standard mechanism that makes a GPL-licensed jar safe to link
# against without the copyleft attaching. Splitting the pair would allow a bare GPL, which
# is exactly what CLAUDE.md's FORBIDDEN row prohibits.
ALLOWED_WITH = {
    ("GPL-2.0-only", "Classpath-exception-2.0"),
    ("GPL-2.0-or-later", "Classpath-exception-2.0"),
    ("GPL-2.0", "Classpath-exception-2.0"),  # deprecated id, still seen in the wild
}

# Messy spellings actually observed in this repository's dependency metadata, mapped to a
# canonical SPDX id. Keys are lowercased; lookup lowercases the whole trimmed signal.
#
# This map is the fail-closed boundary: a spelling that is neither a known SPDX id nor a key
# here is reported as a violation with the raw text, so a human decides whether it is a new
# way of writing something allowed or a genuinely new license. Guessing by substring is what
# this design exists to avoid.
NORMALISE = {
    # Python legacy `License:` free text.
    "3-clause bsd license": "BSD-3-Clause",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "isc license": "ISC",
    "mit license": "MIT",
    "python software foundation license": "PSF-2.0",
    "the unlicense": "Unlicense",
    "public domain": "CC0-1.0",
    # Trove classifiers, which are coarser than an SPDX id by design.
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "apache software license": "Apache-2.0",
    # The "BSD License" classifier CANNOT distinguish 2-Clause from 3-Clause. Mapping it to
    # BSD-3-Clause is safe ONLY because both are on the allow-list; if either is ever
    # removed, this entry must be revisited rather than silently keeping a dependency green.
    "bsd license": "BSD-3-Clause",
    # Eclipse Distribution License 1.0 is textually BSD-3-Clause and has no SPDX id.
    "edl-1.0": "BSD-3-Clause",
    "edl 1.0": "BSD-3-Clause",
    "eclipse distribution license - v 1.0": "BSD-3-Clause",
}

_ALLOWED_LOWER = {spdx.lower() for spdx in ALLOWED_IDS}
_ALLOWED_WITH_LOWER = {(lic.lower(), exc.lower()) for lic, exc in ALLOWED_WITH}
```

- [ ] **Step 5: Write the expression engine**

Append to `scripts/check-licenses.py`:

```python
# ---------------------------------------------------------------------------
# The SPDX expression engine.
# ---------------------------------------------------------------------------


class _ParseError(Exception):
    """Raised for a signal that is not a well-formed SPDX expression."""


def _canonical(raw: str) -> str:
    """Canonicalises one SPDX identifier.

    A trailing "+" is SPDX's older notation for "or later"; the policy itself is written
    as "LGPL 2.1+", so a dependency spelling it that way must not be blocked by the
    policy's own notation.
    """
    ident = raw.strip()
    if ident.endswith("+"):
        ident = ident[:-1] + "-or-later"
    return ident


def _tokenize(signal: str) -> list[str]:
    tokens: list[str] = []
    i, n = 0, len(signal)
    while i < n:
        char = signal[i]
        if char.isspace():
            i += 1
        elif char in "()":
            tokens.append(char)
            i += 1
        else:
            j = i
            while j < n and not signal[j].isspace() and signal[j] not in "()":
                j += 1
            tokens.append(signal[i:j])
            i = j
    return tokens


class _Parser:
    """Recursive-descent parser for the SPDX expression grammar.

        expr      := or_expr
        or_expr   := and_expr (OR and_expr)*
        and_expr  := with_expr (AND with_expr)*
        with_expr := atom (WITH atom)?
        atom      := IDENT | "(" expr ")"

    Hand-rolled rather than taking a dependency on `license-expression`, because the
    grammar is closed and tiny and because fail-closed makes any gap SAFE BY
    CONSTRUCTION: whatever this parser cannot handle becomes a violation a human reads,
    never a silent pass. If the grammar ever justifies it, `license-expression`
    (Apache-2.0, maintained by AboutCode) is the drop-in replacement.
    """

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _next(self) -> str:
        token = self._peek()
        if token is None:
            raise _ParseError("unexpected end of expression")
        self._pos += 1
        return token

    def parse(self) -> bool:
        value = self._or()
        if self._peek() is not None:
            raise _ParseError(f"trailing tokens from {self._peek()!r}")
        return value

    def _or(self) -> bool:
        value = self._and()
        while (token := self._peek()) is not None and token.upper() == "OR":
            self._next()
            # Evaluate BOTH sides: `value or self._and()` would short-circuit and leave
            # the right-hand operand unparsed, so a malformed tail would go unnoticed.
            right = self._and()
            value = value or right
        return value

    def _and(self) -> bool:
        value = self._with()
        while (token := self._peek()) is not None and token.upper() == "AND":
            self._next()
            right = self._with()
            # AND requires complying with EVERY operand. This is the case
            # license-checker's substring test inverts.
            value = value and right
        return value

    def _with(self) -> bool:
        token = self._next()
        if token == "(":
            value = self._or()
            closing = self._next()
            if closing != ")":
                raise _ParseError(f"expected ')', got {closing!r}")
        elif token == ")":
            raise _ParseError("unexpected ')'")
        elif token.upper() in {"AND", "OR", "WITH"}:
            raise _ParseError(f"unexpected operator {token!r}")
        else:
            if (nxt := self._peek()) is not None and nxt.upper() == "WITH":
                self._next()
                exception = self._next()
                # ATOMIC on purpose - see ALLOWED_WITH.
                pair = (_canonical(token).lower(), _canonical(exception).lower())
                return pair in _ALLOWED_WITH_LOWER
            value = _canonical(token).lower() in _ALLOWED_LOWER
        return value


def evaluate(signal: str) -> tuple[bool, str]:
    """Decides whether one license signal is permitted.

    Returns (allowed, reason); reason is "" when allowed.

    The whole trimmed signal is checked against NORMALISE FIRST, before any attempt to
    parse it as an expression. Free text such as "Mozilla Public License 2.0 (MPL 2.0)"
    contains parentheses and spaces and would otherwise be mangled by the parser.
    """
    text = signal.strip()
    if not text:
        return False, "no license declared"

    mapped = NORMALISE.get(text.lower())
    if mapped is not None:
        if mapped.lower() in _ALLOWED_LOWER:
            return True, ""
        return False, f"normalised to {mapped}, which is not on the allow-list"

    try:
        allowed = _Parser(_tokenize(text)).parse()
    except _ParseError as err:
        return False, f"unrecognised or unparseable license expression ({err})"

    return (True, "") if allowed else (False, "not on the allow-list")
```

- [ ] **Step 6: Run the tests and watch them pass**

Run: `cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -v`
Expected: 17 passed.

- [ ] **Step 7: Lint, type-check, commit**

```bash
cd python && uv run ruff check .. && uv run ruff format .. && uv run mypy
cd .. && git add scripts/check-licenses.py scripts/tests/test_check_licenses.py python/pyproject.toml
git commit -m "feat(licenses): the allow-list policy and SPDX expression engine"
```

If `ruff` complains about the parent directory, run it as `uv run ruff check ../scripts` and note the invocation in your report - Task 6 needs the command that actually works.

---

### Task 2: The npm collector

**Files:**
- Modify: `scripts/check-licenses.py`
- Modify: `scripts/tests/test_check_licenses.py`

**Interfaces:**
- Consumes: nothing from Task 1's policy; this task is pure data collection.
- Produces:
  - `class Record(NamedTuple)` with fields `ecosystem: str`, `name: str`, `version: str`, `signal: str`, `source: str` - **Task 3 and Task 4 both use this exact shape**
  - `class CollectorError(Exception)`
  - `collect_npm(typescript_dir: Path) -> list[Record]`

- [ ] **Step 1: Write the failing tests**

Append to `scripts/tests/test_check_licenses.py`:

```python
def test_npm_license_field_variants_normalise_to_one_signal() -> None:
    # npm packages declare a license three different ways across the registry's history.
    assert cl._npm_signal({"license": "MIT"}) == ("MIT", "package.json:license")
    assert cl._npm_signal({"license": {"type": "MIT"}}) == ("MIT", "package.json:license")
    # The legacy array form meant "the consumer may choose", i.e. OR.
    assert cl._npm_signal({"licenses": [{"type": "MIT"}, {"type": "Apache-2.0"}]}) == (
        "MIT OR Apache-2.0",
        "package.json:licenses[]",
    )


def test_npm_undeclared_license_yields_an_empty_signal() -> None:
    # Empty rather than a guess: evaluate() turns it into a violation with
    # "no license declared", which is what a human needs to see.
    assert cl._npm_signal({})[0] == ""
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -k npm -v`
Expected: FAIL - `AttributeError: module 'check_licenses' has no attribute '_npm_signal'`.

- [ ] **Step 3: Implement the record shape and the npm collector**

Append to `scripts/check-licenses.py`:

```python
# ---------------------------------------------------------------------------
# Collectors. Both normalise their ecosystem into one Record shape, which is what
# lets a single policy engine serve two package managers.
# ---------------------------------------------------------------------------


class Record(NamedTuple):
    ecosystem: str
    name: str
    version: str
    signal: str
    source: str


class CollectorError(Exception):
    """Raised when an ecosystem's dependency tree cannot be read at all."""


def _npm_signal(pkg: dict[str, object]) -> tuple[str, str]:
    """Extracts one license signal from a package.json body.

    npm has accumulated three spellings over its history. The legacy `licenses` ARRAY
    meant "the consumer may choose any of these", so it maps to an SPDX OR rather than
    an AND - picking AND here would reject dual-licensed packages that are entirely fine.
    """
    license_field = pkg.get("license")
    if isinstance(license_field, str):
        return license_field, "package.json:license"
    if isinstance(license_field, dict):
        return str(license_field.get("type", "")), "package.json:license"

    licenses = pkg.get("licenses")
    if isinstance(licenses, list):
        parts = [
            str(entry.get("type", "")) if isinstance(entry, dict) else str(entry)
            for entry in licenses
        ]
        parts = [p for p in parts if p]
        if parts:
            return " OR ".join(parts), "package.json:licenses[]"

    return "", "package.json:absent"


def _npm_installed_index(node_modules: Path) -> dict[tuple[str, str], dict[str, object]]:
    """Indexes every installed package.json by (name, version).

    Walks node_modules rather than resolving each dependency's path from `npm ls`,
    because hoisting means a package's directory is not reliably node_modules/<name> -
    it may sit in a nested node_modules under whichever dependent pulled it in.
    """
    index: dict[tuple[str, str], dict[str, object]] = {}
    for manifest in node_modules.rglob("package.json"):
        try:
            body = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # Fixtures, test scaffolding and broken files are not dependencies.
        name, version = body.get("name"), body.get("version")
        if isinstance(name, str) and isinstance(version, str):
            index.setdefault((name, version), body)
    return index


def collect_npm(typescript_dir: Path) -> list[Record]:
    """Collects every package in the npm dependency tree, dev included."""
    node_modules = typescript_dir / "node_modules"
    if not node_modules.is_dir():
        raise CollectorError(
            f"{node_modules} does not exist - run `npm ci` in {typescript_dir} first."
        )

    try:
        completed = subprocess.run(
            ["npm", "ls", "--all", "--json"],
            cwd=typescript_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        tree = json.loads(completed.stdout)
    except (OSError, json.JSONDecodeError) as err:
        raise CollectorError(f"could not read the npm dependency tree: {err}") from err

    wanted: set[tuple[str, str]] = set()

    def walk(node: dict[str, object]) -> None:
        deps = node.get("dependencies")
        if not isinstance(deps, dict):
            return
        for name, info in deps.items():
            if not isinstance(info, dict):
                continue
            version = info.get("version")
            # Our own workspace packages are the thing being licensed, not a dependency
            # of it. They resolve to a file: URL rather than the registry.
            if isinstance(version, str) and not str(info.get("resolved", "")).startswith("file:"):
                wanted.add((name, version))
            walk(info)

    walk(tree)

    index = _npm_installed_index(node_modules)
    records = []
    for name, version in sorted(wanted):
        body = index.get((name, version))
        if body is None:
            raise CollectorError(
                f"{name}@{version} is in the npm tree but not installed under {node_modules}; "
                "the tree and node_modules disagree - re-run `npm ci`."
            )
        signal, source = _npm_signal(body)
        records.append(Record("npm", name, version, signal, source))
    return records
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -k npm -v`
Expected: 2 passed.

- [ ] **Step 5: Verify the collector against the real tree**

```bash
cd /Users/frank/projects/arcade/arcadedb-drivers
python3 -c "
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location('cl', 'scripts/check-licenses.py')
cl = importlib.util.module_from_spec(spec); spec.loader.exec_module(cl)
recs = cl.collect_npm(pathlib.Path('typescript'))
print(len(recs), 'npm packages')
from collections import Counter
for sig, n in Counter(r.signal for r in recs).most_common(): print(f'  {n:4}  {sig}')
"
```

Expected: **367 packages** and **11 distinct signals**, matching the spec's section 4 - MIT (239), Apache-2.0 (41), ISC (27), BSD-3-Clause (14), BSD-2-Clause (6), BlueOak-1.0.0 (5), MPL-2.0 (2), `(Apache-2.0 AND BSD-3-Clause)`, `(MIT OR CC0-1.0)`, Python-2.0, Unlicense. A materially different count means the walk is wrong - report it rather than adjusting the expectation.

- [ ] **Step 6: Lint, type-check, commit**

```bash
cd python && uv run ruff check ../scripts && uv run ruff format ../scripts && uv run mypy
cd .. && git add scripts/ && git commit -m "feat(licenses): collect the npm dependency tree"
```

---

### Task 3: The Python collector

**Files:**
- Modify: `scripts/check-licenses.py`
- Modify: `scripts/tests/test_check_licenses.py`

**Interfaces:**
- Consumes: `Record`, `CollectorError` from Task 2.
- Produces: `collect_python(python_dir: Path) -> list[Record]`

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_check_licenses.py`:

```python
def test_python_source_precedence_prefers_the_spdx_expression() -> None:
    # httpcore carries BOTH a PEP 639 License-Expression and the vaguer "BSD License"
    # Trove classifier. The precise one must win: the classifier cannot distinguish
    # 2-Clause from 3-Clause.
    meta = {
        "name": "httpcore",
        "version": "1.0.0",
        "license_expression": "BSD-3-Clause",
        "license": "",
        "classifiers": ["License :: OSI Approved :: BSD License"],
    }
    assert cl._python_signal(meta) == ("BSD-3-Clause", "License-Expression")


def test_python_falls_back_to_the_legacy_license_field() -> None:
    meta = {
        "name": "protobuf",
        "version": "7.36.1",
        "license_expression": "",
        "license": "3-Clause BSD License",
        "classifiers": [],
    }
    assert cl._python_signal(meta) == ("3-Clause BSD License", "License")


def test_python_falls_back_to_a_trove_classifier_last() -> None:
    meta = {
        "name": "certifi",
        "version": "2026.1.1",
        "license_expression": "",
        "license": "",
        "classifiers": ["License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)"],
    }
    assert cl._python_signal(meta) == ("Mozilla Public License 2.0 (MPL 2.0)", "Classifier")


def test_python_multiline_legacy_license_text_is_not_used_as_a_signal() -> None:
    # Some packages paste their entire license TEXT into the License field. That is not a
    # signal, and treating its first line as one would be a guess.
    meta = {
        "name": "whatever",
        "version": "1.0",
        "license_expression": "",
        "license": "Copyright (c) 2026\n\nPermission is hereby granted, free of charge...",
        "classifiers": [],
    }
    assert cl._python_signal(meta)[0] == ""
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -k python_ -v`
Expected: FAIL - no attribute `_python_signal`.

- [ ] **Step 3: Implement**

Append to `scripts/check-licenses.py`:

```python
# The metadata dump runs INSIDE the uv-managed environment, because that is the only
# interpreter that can see the workspace's installed distributions. Keeping it as a
# string here rather than a separate file keeps the checker a single self-contained
# script, matching the upstream tool it ports.
_PYTHON_DUMP = """
import importlib.metadata as md, json
out = []
for dist in md.distributions():
    m = dist.metadata
    name = m["Name"]
    if not name:
        continue
    out.append({
        "name": name,
        "version": m["Version"] or "",
        "license_expression": m["License-Expression"] or "",
        "license": m["License"] or "",
        "classifiers": [c for c in (m.get_all("Classifier") or []) if c.startswith("License ::")],
    })
print(json.dumps(out))
"""

# Longest plausible one-line license NAME. Anything longer is license TEXT pasted into the
# metadata field, which is not a signal - see _python_signal.
_MAX_LICENSE_NAME = 80


def _python_signal(meta: dict[str, object]) -> tuple[str, str]:
    """Extracts one license signal from a distribution's metadata.

    Python exposes license information through three channels of DECREASING fidelity, and
    the precedence below is a real decision rather than a convenience:

      1. PEP 639 `License-Expression` - a validated SPDX expression. Authoritative.
      2. the legacy `License` free-text field - a name, usually, but see below.
      3. Trove classifiers - coarsest: "License :: OSI Approved :: BSD License" cannot
         distinguish 2-Clause from 3-Clause.

    A distribution may carry several of these and they may disagree; httpcore declares
    both `BSD-3-Clause` and the vaguer `BSD License` classifier. Taking the most precise
    available is what keeps the coarse fallback from erasing information we already have.
    """
    expression = str(meta.get("license_expression") or "").strip()
    if expression:
        return expression, "License-Expression"

    legacy = str(meta.get("license") or "").strip()
    # Some distributions paste the entire license TEXT into this field. Its first line is
    # not a license name, and using it as one would be exactly the guess this design
    # refuses to make - so fall through to the classifier instead.
    if legacy and "\n" not in legacy and len(legacy) <= _MAX_LICENSE_NAME:
        return legacy, "License"

    classifiers = meta.get("classifiers")
    if isinstance(classifiers, list):
        for classifier in classifiers:
            trailing = str(classifier).split("::")[-1].strip()
            if trailing and trailing != "OSI Approved":
                return trailing, "Classifier"

    return "", "absent"


def collect_python(python_dir: Path) -> list[Record]:
    """Collects every distribution installed in the uv workspace, dev included."""
    try:
        completed = subprocess.run(
            ["uv", "run", "--project", str(python_dir), "python", "-c", _PYTHON_DUMP],
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError as err:
        raise CollectorError(f"could not run uv: {err}") from err
    except subprocess.CalledProcessError as err:
        raise CollectorError(
            f"`uv run` failed in {python_dir} - run `uv sync` there first.\n{err.stderr}"
        ) from err

    try:
        dists = json.loads(completed.stdout)
    except json.JSONDecodeError as err:
        raise CollectorError(f"could not parse the Python metadata dump: {err}") from err

    records = []
    for meta in dists:
        name = str(meta.get("name", ""))
        # Our own packages are the thing being licensed, not a dependency of it.
        if name in {"arcadedb-driver", "arcadedb-driver-grpc"}:
            continue
        signal, source = _python_signal(meta)
        records.append(Record("python", name, str(meta.get("version", "")), signal, source))
    return sorted(records)
```

- [ ] **Step 4: Run and watch it pass**

Run: `cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -k python_ -v`
Expected: 4 passed.

- [ ] **Step 5: Verify against the real environment**

```bash
cd /Users/frank/projects/arcade/arcadedb-drivers
python3 -c "
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location('cl', 'scripts/check-licenses.py')
cl = importlib.util.module_from_spec(spec); spec.loader.exec_module(cl)
recs = cl.collect_python(pathlib.Path('python'))
print(len(recs), 'python distributions')
from collections import Counter
for k, n in Counter((r.source, r.signal) for r in recs).most_common(): print(f'  {n:3}  [{k[0]}] {k[1]}')
"
```

Expected: roughly **49 distributions** across **16 signals**, using all three sources - the spec's section 4 records the exact spread. Confirm `Apache-2.0 OR BSD-2-Clause` and `PSF-2.0` both appear; those are the two that exercise the engine hardest.

- [ ] **Step 6: Lint, type-check, commit**

```bash
cd python && uv run ruff check ../scripts && uv run ruff format ../scripts && uv run mypy
cd .. && git add scripts/ && git commit -m "feat(licenses): collect the Python dependency tree"
```

---

### Task 4: The CLI, the empty-tree guard, and the first real run

Where the pieces meet, and where the gate either goes green over the real repository or tells us the policy additions in Task 1 were insufficient.

**Files:**
- Modify: `scripts/check-licenses.py`
- Modify: `scripts/tests/test_check_licenses.py`

**Interfaces:**
- Consumes: `evaluate` (Task 1), `Record`/`CollectorError`/`collect_npm` (Task 2), `collect_python` (Task 3).
- Produces: `check(records: list[Record]) -> tuple[list[Record], Counter[str]]` returning `(violations, spread)`, and `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing tests**

First add `import pytest` to the test file's imports - the `capsys` annotations below need it,
and it was deliberately left out until now because ruff's F401 rejects an import nothing uses.

Then append to `scripts/tests/test_check_licenses.py`:

```python
def test_check_separates_violations_from_the_spread() -> None:
    records = [
        cl.Record("npm", "a", "1.0", "MIT", "package.json:license"),
        cl.Record("npm", "b", "2.0", "SSPL-1.0", "package.json:license"),
        cl.Record("python", "c", "3.0", "MIT", "License-Expression"),
    ]
    violations, spread = cl.check(records)
    assert [v.name for v in violations] == ["b"]
    assert spread["MIT"] == 2


def test_an_empty_inventory_is_an_error_not_a_pass(capsys: pytest.CaptureFixture[str]) -> None:
    # THE guard. ArcadeDB's checker once reported success while inspecting a near-empty
    # aggregator pom, and this repository shipped a testpaths setting that excluded every
    # gRPC test while CI stayed green. A checker that silently checks nothing is worse
    # than no checker: it converts an absence of evidence into a passing gate.
    assert cl.report([], cl.Counter()) == 2
    assert "no dependencies" in capsys.readouterr().err.lower()


def test_report_returns_1_and_names_the_offender(capsys: pytest.CaptureFixture[str]) -> None:
    bad = cl.Record("npm", "evil", "6.6.6", "SSPL-1.0", "package.json:license")
    assert cl.report([bad], cl.Counter({"SSPL-1.0": 1})) == 1
    err = capsys.readouterr().err
    # Everything a reviewer needs to act, without opening the tree.
    for expected in ("evil", "6.6.6", "SSPL-1.0", "package.json:license"):
        assert expected in err


def test_report_returns_0_on_a_clean_inventory(capsys: pytest.CaptureFixture[str]) -> None:
    assert cl.report([], cl.Counter({"MIT": 3})) == 0
    assert "3" in capsys.readouterr().out
```

- [ ] **Step 2: Run and watch them fail**

Run: `cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -k "check_ or report or empty_inventory" -v`
Expected: FAIL - no attribute `check`.

- [ ] **Step 3: Implement the engine's driver and the CLI**

Append to `scripts/check-licenses.py`:

```python
# ---------------------------------------------------------------------------
# Driver and CLI.
# ---------------------------------------------------------------------------


def check(records: list[Record]) -> tuple[list[Record], Counter[str]]:
    """Splits an inventory into violations and a license spread."""
    violations = []
    spread: Counter[str] = Counter()
    for record in records:
        spread[record.signal or "<undeclared>"] += 1
        allowed, _ = evaluate(record.signal)
        if not allowed:
            violations.append(record)
    return violations, spread


def report(violations: list[Record], spread: Counter[str]) -> int:
    """Prints the outcome and returns the process exit code."""
    total = sum(spread.values())

    # An inventory of zero is an ENVIRONMENT failure, never a pass. See the test for why
    # this guard is not optional.
    if total == 0:
        print("No dependencies found - nothing was checked.", file=sys.stderr)
        print("This usually means node_modules is absent or the uv workspace is not", file=sys.stderr)
        print("synced. Run `npm ci` in typescript/ and `uv sync` in python/.", file=sys.stderr)
        return 2

    if violations:
        print(f"Dependencies with licenses outside the allow-list (see CLAUDE.md):", file=sys.stderr)
        for record in violations:
            _, reason = evaluate(record.signal)
            print(
                f"  [{record.ecosystem}] {record.name}@{record.version}: "
                f"{record.signal or '<undeclared>'!r} - {reason} (from {record.source})",
                file=sys.stderr,
            )
        print(file=sys.stderr)
        print("If this license should be permitted: get maintainer sign-off, add its SPDX id", file=sys.stderr)
        print("to ALLOWED_IDS in this script, and update CLAUDE.md's ALLOWED row to match.", file=sys.stderr)
        print("If it is a new SPELLING of a license already allowed, add it to NORMALISE", file=sys.stderr)
        print("instead - do not widen the allow-list for a spelling.", file=sys.stderr)
        return 1

    print(f"OK: all {total} dependency license(s) are on the allow-list.")
    for signal, count in spread.most_common():
        print(f"  {count:5}  {signal}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--ecosystem",
        choices=("npm", "python", "all"),
        default="all",
        help="which dependency tree to check (default: all)",
    )
    args = parser.parse_args(argv)

    records: list[Record] = []
    try:
        if args.ecosystem in ("npm", "all"):
            records += collect_npm(REPO_ROOT / "typescript")
        if args.ecosystem in ("python", "all"):
            records += collect_python(REPO_ROOT / "python")
    except CollectorError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    violations, spread = check(records)
    return report(violations, spread)


if __name__ == "__main__":
    sys.exit(main())
```

Add `from collections import Counter` to the imports if it is not already there, and re-export it for the tests (they reference `cl.Counter`).

- [ ] **Step 4: Run the tests and watch them pass**

Run: `cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -v`
Expected: 25 passed.

- [ ] **Step 5: THE run that matters - the whole repository, for real**

```bash
chmod +x scripts/check-licenses.py
./scripts/check-licenses.py; echo "exit=$?"
```

Expected: `exit=0`, and a spread totalling roughly **416** licenses.

**If it exits 1**, do not widen `ALLOWED_IDS` to make it pass. Read the violations first and classify each one:
- a new **spelling** of an already-allowed license belongs in `NORMALISE`;
- a genuinely new **license** needs maintainer sign-off and goes in your report as a question, not into the allow-list;
- anything on CLAUDE.md's FORBIDDEN row is a real finding about a real dependency.

The spec's section 5.3 predicts exactly four additions are needed. If more are, that prediction was wrong and the controller needs to know.

**If it exits 2**, the environment is wrong, not the policy - run `npm ci` and `uv sync` and try again.

- [ ] **Step 6: Verify the guard fires**

Prove the empty-tree guard works rather than trusting it:

```bash
cd /Users/frank/projects/arcade/arcadedb-drivers
./scripts/check-licenses.py --ecosystem npm >/dev/null 2>&1; echo "npm alone: exit=$?"
# Temporarily hide node_modules to force the collector error path.
mv typescript/node_modules typescript/node_modules.bak
./scripts/check-licenses.py --ecosystem npm; echo "expect exit=2, got $?"
mv typescript/node_modules.bak typescript/node_modules
```

Expected: `exit=0` for the first, `exit=2` with a message naming `npm ci` for the second. **Restore `node_modules` before continuing** - the final `mv` is not optional.

- [ ] **Step 7: Lint, type-check, commit**

```bash
cd python && uv run ruff check ../scripts && uv run ruff format ../scripts && uv run mypy
cd .. && git add scripts/ && git commit -m "feat(licenses): the CLI, the empty-tree guard, and the license spread"
```

---

### Task 5: The policy in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** none - documentation only.

- [ ] **Step 1: Add the policy rows**

Add a `## Dependency licenses` section to the root `CLAUDE.md`, before `## Design docs`. Match this repository's register - dense and explanatory, not a bullet list of rules:

```markdown
## Dependency licenses

Every dependency of this repository - in both ecosystems, runtime and development alike -
must carry a license on the allow-list below. This is ArcadeDB's policy, and the two
repositories are expected to agree; ArcadeDB's own copy lives in its `CLAUDE.md`.

- ✅ **ALLOWED:** Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, EPL-1.0/2.0, UPL-1.0,
  EDL-1.0, LGPL-2.1+ (libraries only), MPL-2.0 (libraries only, unmodified),
  CDDL-1.0/1.1 (libraries only, unmodified), GPL-2.0 **WITH** the Classpath Exception
  specifically (never a bare GPL), CC0-1.0 / Public Domain, Unlicense, BlueOak-1.0.0,
  PSF-2.0 / Python-2.0
- ❌ **FORBIDDEN:** GPL, AGPL, SSPL, Commons Clause, BUSL-1.1, Elastic-2.0, and
  proprietary licenses without explicit permission

**This is an allow-list**: a license in neither row is not permitted by default. Anything
not allowed is denied whatever it is called, which is strictly stronger than enumerating
the bad ones - the FORBIDDEN row exists so a reader can tell a deliberate denial from an
accidental omission.

`scripts/check-licenses.py` enforces it over both dependency trees, and
`.github/workflows/license-compliance.yml` runs it on dependency changes, weekly, and on
demand. The weekly run is not redundant: a package can be **relicensed** on a version
already pinned in a lockfile, and no manifest changes when that happens.

Four entries above are this repository's own additions to ArcadeDB's list, each made on
evidence from this tree rather than in the abstract: `BlueOak-1.0.0` (5 npm dev packages),
`PSF-2.0`/`Python-2.0` (`typing_extensions`, a runtime dependency), `Unlicense` (one npm
package; CLAUDE.md already allowed "CC0/Public Domain" and this is that category under its
SPDX name), and `MPL-2.0` - already allowed upstream for libraries, recorded explicitly
here because `certifi` makes it a **runtime** dependency rather than the dev-scope case
ArcadeDB originally blessed.

**What the gate cannot check.** "Libraries only, unmodified" is a rule for humans. The
checker sees a license identifier attached to a package; it cannot know whether this
repository has vendored, patched or re-published that package's source. A green run does
not certify that nobody copied an MPL-2.0 file into the tree. Nothing is vendored today -
the generated code under `_generated/` and `src/gen/` comes from ArcadeDB's own Apache-2.0
contracts - and if that ever changes, both this rule and the absence of an
`ATTRIBUTIONS.md` need revisiting.

Adding a license to the ALLOWED row means editing `ALLOWED_IDS` in
`scripts/check-licenses.py` **and** this section, together. A new *spelling* of a license
already allowed goes in that script's `NORMALISE` map instead - do not widen the
allow-list for a spelling.
```

- [ ] **Step 2: Add the script to the contracts command list**

In `CLAUDE.md`'s existing script listing (the block containing `scripts/fetch-contract.sh` and friends), add:

```
scripts/check-licenses.py                            # fail if any dependency's license is off the allow-list
```

- [ ] **Step 3: Verify every claim you just wrote**

Documentation in this repository is held to the same standard as code. Check each against reality rather than against this plan:

```bash
cd /Users/frank/projects/arcade/arcadedb-drivers
./scripts/check-licenses.py | tail -20     # does the spread match what the section claims?
grep -n "BlueOak\|PSF-2.0\|Unlicense\|MPL-2.0" scripts/check-licenses.py | head
```

Confirm the four additions named in the prose are the four actually in `ALLOWED_IDS`, and that the counts you cite (5 npm dev packages, etc.) match the real spread. If any number is wrong, fix the prose - do not fix the count.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md && git commit -m "docs: record the dependency license policy"
```

---

### Task 6: The CI workflow

**Files:**
- Create: `.github/workflows/license-compliance.yml`

**Interfaces:** none.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/license-compliance.yml`. The action SHAs below are copied from this repository's existing workflows - do not re-pin them to different versions:

```yaml
name: License compliance

on:
  push:
    branches:
      - main
    paths: &license-paths
      - "typescript/package-lock.json"
      - "typescript/**/package.json"
      - "python/uv.lock"
      - "python/**/pyproject.toml"
      # The checker and the policy are themselves gated: an edit to either must re-run
      # the gate it changes, or a widened allow-list lands unverified.
      - "scripts/check-licenses.py"
      - "scripts/tests/test_check_licenses.py"
      - "CLAUDE.md"
      - ".github/workflows/license-compliance.yml"
  pull_request:
    paths: *license-paths
  schedule:
    # Weekly, Sunday 03:00 UTC. NOT redundant with the path filters above: a package can
    # be RELICENSED on a version already pinned in a lockfile, and no manifest changes
    # when that happens. This trigger is the only one that catches it.
    - cron: "0 3 * * 0"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  licenses:
    name: Check dependency licenses
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Set up Node
        uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: typescript/package-lock.json

      - name: Install uv
        uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          enable-cache: true
          cache-dependency-glob: python/uv.lock

      # Both trees must be fully installed, dev dependencies included: the allow-list
      # covers development dependencies too, and a partial install would leave the
      # checker reporting a clean bill of health over a tree it could not see.
      - name: Install npm dependencies
        working-directory: typescript
        run: npm ci

      - name: Install Python dependencies
        working-directory: python
        run: uv sync --frozen

      - name: Test the checker
        working-directory: python
        run: uv run python -m pytest ../scripts/tests/test_check_licenses.py -v

      - name: Check dependency licenses
        run: ./scripts/check-licenses.py

      - name: Write the license spread to the job summary
        if: always()
        run: |
          {
            echo "### Dependency licenses"
            echo
            echo '```'
            ./scripts/check-licenses.py 2>&1 || true
            echo '```'
          } >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 2: Verify the YAML parses, and that the anchor works**

The `&license-paths` / `*license-paths` anchor avoids duplicating nine path entries. YAML anchors are valid in GitHub Actions, but confirm rather than assume:

```bash
cd /Users/frank/projects/arcade/arcadedb-drivers
python3 -c "
import yaml, json
d = yaml.safe_load(open('.github/workflows/license-compliance.yml'))
on = d[True] if True in d else d['on']   # YAML parses bare 'on:' as the boolean True
print('triggers:', sorted(on))
print('push paths:', len(on['push']['paths']))
print('pr paths  :', len(on['pull_request']['paths']))
assert on['push']['paths'] == on['pull_request']['paths'], 'anchor did not expand'
print('anchor expanded correctly')
"
```

Expected: four triggers, 9 paths each, and the anchor confirmation. If `yaml` is unavailable, run it through `uv run --project python python` instead.

If the anchor turns out not to survive GitHub's own parser, write the two lists out longhand and note it in your report - correctness beats brevity here.

- [ ] **Step 3: Verify the workflow's own steps run locally**

Every command in the workflow should already work from Task 4:

```bash
cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -v
cd .. && ./scripts/check-licenses.py; echo "exit=$?"
```

Expected: all tests pass, `exit=0`.

- [ ] **Step 4: Confirm nothing else in CI is disturbed**

`ci.yml` and `ci-python.yml` both watch `.gitignore` and their own language trees. This workflow adds a new file and touches neither, but confirm the full local gate is still green:

```bash
cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
cd ../typescript && npm run lint && npm run typecheck && npm test
cd .. && git status --porcelain    # expect only .idea/
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/license-compliance.yml
git commit -m "ci: gate both dependency trees on the license allow-list"
```

**Do not dispatch the workflow.** It will run on the pull request.
