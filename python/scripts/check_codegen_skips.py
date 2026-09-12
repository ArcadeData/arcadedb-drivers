#!/usr/bin/env python3
"""Fails when the set of endpoints openapi-python-client silently skips changes.

The generator cannot model a non-JSON request body. When it meets one it prints a
warning to stderr, omits the endpoint, and EXITS 0. Nothing else in the build
notices: `git diff` over the generated tree is clean, because the endpoint was
never there to remove.

So the skip set is pinned. Adding an endpoint to EXPECTED_SKIPS is a deliberate
decision to leave it unwrapped or hand-written - never a way to quiet this check.

Run from `python/`:  uv run python scripts/check_codegen_skips.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Endpoints the generator cannot model, and what this repository does about each:
#   POST /api/v1/ts/{database}/write       text/plain      hand-written in facade/timeseries.py
#   POST /api/v1/batch/{database}          jsonl/ndjson/csv  hand-written in facade/batch.py
#                                                             (and @arcadedb/driver's facade/batch.ts)
#   POST /api/v1/ts/{database}/prom/read   x-protobuf      unwrapped, as in @arcadedb/driver
#   POST /api/v1/ts/{database}/prom/write  x-protobuf      unwrapped, as in @arcadedb/driver
EXPECTED_SKIPS = frozenset(
    {
        "POST /api/v1/batch/{database}",
        "POST /api/v1/ts/{database}/write",
        "POST /api/v1/ts/{database}/prom/read",
        "POST /api/v1/ts/{database}/prom/write",
    }
)

# Only the "Endpoint will not be generated" form counts. The ha/snapshot warning
# has the same "WARNING parsing" prefix but drops a single RESPONSE while still
# generating the operation, so a looser pattern would report a skip that is not one.
_SKIP = re.compile(
    r"^WARNING parsing (?P<op>[A-Z]+ /\S+) within \S+?\.\s+Endpoint will not be generated\.",
    re.MULTILINE,
)


def parse_skips(stderr: str) -> set[str]:
    """Extracts the operations the generator declined to generate."""
    return {match.group("op") for match in _SKIP.finditer(stderr)}


def main() -> int:
    python_dir = Path(__file__).resolve().parents[1]
    repo_root = python_dir.parent
    spec = subprocess.run(
        [str(repo_root / "scripts" / "resolve-openapi-contract.sh")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    result = subprocess.run(
        [
            "uv",
            "run",
            "openapi-python-client",
            "generate",
            "--path",
            spec,
            "--meta",
            "none",
            "--overwrite",
            "--output-path",
            str(python_dir / "packages/driver/src/arcadedb_driver/_generated"),
        ],
        cwd=python_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        return result.returncode

    # The generator writes warnings to stdout in some versions and stderr in others;
    # reading both is cheaper than depending on which. Joined with a newline, not
    # concatenated directly: `_SKIP` is `^`-anchored under `re.MULTILINE`, so if
    # stdout lacks a trailing newline, a bare `+` glues stderr's first line onto
    # stdout's last and it can no longer match `^WARNING parsing ...` - silently
    # dropping a skip this script exists to catch.
    found = parse_skips("\n".join((result.stdout, result.stderr)))
    if found == set(EXPECTED_SKIPS):
        print(f"OK: the generator skipped exactly the {len(found)} allowlisted operations.")
        return 0

    for op in sorted(found - set(EXPECTED_SKIPS)):
        sys.stderr.write(
            f"ERROR: {op} is NOT generated and is not on the allowlist. The contract added an\n"
            f"       endpoint this generator cannot model. Either hand-write it in the facade or\n"
            f"       add it to EXPECTED_SKIPS with a comment saying why it is unwrapped.\n"
        )
    for op in sorted(set(EXPECTED_SKIPS) - found):
        sys.stderr.write(
            f"ERROR: {op} is on the allowlist but IS now generated. The contract changed its media\n"
            f"       type; remove it from EXPECTED_SKIPS and use the generated operation.\n"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
