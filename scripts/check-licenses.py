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

import json
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
    # Public-domain dedication, distinct from CC0-1.0 above. CLAUDE.md already allows
    # "CC0 / Public Domain"; this is that same category under its own SPDX id. Ships in
    # 1 npm package.
    "Unlicense",
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
        parts = [str(entry.get("type", "")) if isinstance(entry, dict) else str(entry) for entry in licenses]
        parts = [p for p in parts if p]
        if parts:
            return " OR ".join(parts), "package.json:licenses[]"

    return "", "package.json:absent"


def _npm_installed_index(node_modules: Path) -> dict[tuple[str, str], dict[str, object]]:
    """Indexes every installed package.json by (name, version).

    Walks node_modules rather than resolving each dependency's path by name, because
    hoisting means a package's directory is not reliably node_modules/<name> - it may
    sit in a nested node_modules under whichever dependent pulled it in. Reading each
    manifest's own declared `name` (rather than trusting the directory it lives in)
    also makes this correct for an npm alias such as
    `"string-width-cjs": "npm:string-width@^4.2.0"`, where the installed directory is
    named `string-width-cjs` but the package.json inside it declares itself as
    `string-width` - the identity that matters for licensing is the one the package
    declares for itself.
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


# A real `npm ci` here installs several hundred packages. This is a floor, not an exact
# count: an exact count would be brittle (it changes on every dependency bump) and a gate
# people have to re-baseline constantly is a gate they learn to edit rather than trust.
# 50 is low enough never to fire on a legitimate install and high enough to catch an
# empty or half-installed tree, which is the failure mode this guard exists to catch -
# a checker that silently checks nothing is worse than no checker.
_MIN_PLAUSIBLE_NPM_PACKAGES = 50


def collect_npm(typescript_dir: Path) -> list[Record]:
    """Collects every package installed under the npm workspace, dev included.

    node_modules itself is the authority here, not `npm ls`: the packages actually on
    disk are precisely the code this repository ships and depends on, which is what a
    license audit is about. Walking node_modules is alias-correct by construction (each
    package.json is read under its own declared name, never the directory it happens to
    live in) and platform-correct by construction (an optional native binary for another
    OS/CPU that never installed on this machine ships nothing to anyone here, so it is
    rightly absent rather than a bug to chase).
    """
    node_modules = typescript_dir / "node_modules"
    if not node_modules.is_dir():
        raise CollectorError(f"{node_modules} does not exist - run `npm ci` in {typescript_dir} first.")

    index = _npm_installed_index(node_modules)
    # Our own workspace packages are the thing being licensed, not a dependency of it.
    installed = {key: body for key, body in index.items() if not key[0].startswith("@arcadedb/")}

    if len(installed) < _MIN_PLAUSIBLE_NPM_PACKAGES:
        raise CollectorError(
            f"only {len(installed)} package(s) found under {node_modules}, fewer than the "
            f"{_MIN_PLAUSIBLE_NPM_PACKAGES} a real install has - run `npm ci` in {typescript_dir}."
        )

    return [Record("npm", name, version, *_npm_signal(body)) for (name, version), body in sorted(installed.items())]
