#!/usr/bin/env python3
"""The release package table, and the lockstep check every release rests on.

Every published package is one row of PACKAGES. The table is explicit, and is not
discovered by crawling `typescript/packages/*` and `python/packages/*`, for the same
reason adopt-contract-version.sh has an explicit LANGUAGES table: a new directory
appearing next to the old ones is not a decision to publish it. Adding a package to a
registry already known here is one row. Adding a registry is one REGISTRIES entry (how
to read a manifest and lockfile for it) plus its rows - nothing else in this file
changes, and release.yml builds its matrices from `json` rather than repeating the list.

Subcommands:

  json                                   print the table as a JSON array
  check <version> [--allow-snapshot]     exit 1 listing every problem, else exit 0

`check` holds the invariant a lockstep release depends on: every manifest reads
<version>, every lockfile agrees with its manifest, and every package's recorded server
version matches the single OpenAPI contract and the single .proto contract. A
`-SNAPSHOT` server version is a problem unless --allow-snapshot is given, because a
release must not ship against a moving target while `main` legitimately does.

Stdlib only, so it runs anywhere Python 3.11+ does with no environment to build.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Callable, NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent

PACKAGES: list[dict[str, str]] = [
    {
        "id": "npm-driver",
        "language": "typescript",
        "manifest": "typescript/packages/driver/package.json",
        "lockfile": "typescript/package-lock.json",
        "registry": "npm",
        "name": "@arcadedb/driver",
        "workflow": "publish.yml",
        "package_input": "driver",
    },
    {
        "id": "npm-driver-grpc",
        "language": "typescript",
        "manifest": "typescript/packages/driver-grpc/package.json",
        "lockfile": "typescript/package-lock.json",
        "registry": "npm",
        "name": "@arcadedb/driver-grpc",
        "workflow": "publish.yml",
        "package_input": "driver-grpc",
    },
    {
        "id": "pypi-driver",
        "language": "python",
        "manifest": "python/packages/driver/pyproject.toml",
        "lockfile": "python/uv.lock",
        "registry": "pypi",
        "name": "arcadedb-driver",
        "workflow": "publish-python.yml",
        "package_input": "driver",
    },
    {
        "id": "pypi-driver-grpc",
        "language": "python",
        "manifest": "python/packages/driver-grpc/pyproject.toml",
        "lockfile": "python/uv.lock",
        "registry": "pypi",
        "name": "arcadedb-driver-grpc",
        "workflow": "publish-python.yml",
        "package_input": "driver-grpc",
    },
]

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class ReleaseError(Exception):
    """A release input is malformed."""


def validate_version(v: str) -> None:
    if not _SEMVER.fullmatch(v):
        raise ReleaseError(
            f"{v!r} is not a release version: expected MAJOR.MINOR.PATCH with no "
            "'v' prefix and no pre-release suffix"
        )


Row = dict[str, str]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _load_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _npm_read_version(root: Path, row: Row) -> str:
    return _load_json(root / row["manifest"])["version"]


def _npm_read_lock_version(root: Path, row: Row) -> str:
    lock = _load_json(root / row["lockfile"])
    return lock["packages"][f"packages/{row['package_input']}"]["version"]


def _npm_read_server_version(root: Path, row: Row) -> str:
    return _load_json(root / row["manifest"])["arcadedb"]["serverVersion"]


def _pypi_read_version(root: Path, row: Row) -> str:
    return _load_toml(root / row["manifest"])["project"]["version"]


def _pypi_read_lock_version(root: Path, row: Row) -> str:
    for block in _load_toml(root / row["lockfile"]).get("package", []):
        if block.get("name") == row["name"]:
            return block["version"]
    raise ReleaseError(f"{row['lockfile']} has no [[package]] named {row['name']}")


def _pypi_read_server_version(root: Path, row: Row) -> str:
    return _load_toml(root / row["manifest"])["tool"]["arcadedb"]["server-version"]


class Registry(NamedTuple):
    read_version: Callable[[Path, Row], str]
    read_lock_version: Callable[[Path, Row], str]
    read_server_version: Callable[[Path, Row], str]


REGISTRIES: dict[str, Registry] = {
    "npm": Registry(_npm_read_version, _npm_read_lock_version, _npm_read_server_version),
    "pypi": Registry(_pypi_read_version, _pypi_read_lock_version, _pypi_read_server_version),
}


def _contract_versions(root: Path) -> tuple[list[str], list[str]]:
    """Return problems and the contract versions found (OpenAPI, then proto)."""
    problems: list[str] = []
    versions: list[str] = []

    openapi = sorted((root / "contracts").glob("arcadedb-openapi-*.json"))
    if len(openapi) != 1:
        problems.append(
            f"contracts/ must hold exactly one arcadedb-openapi-*.json, found {len(openapi)}: "
            + ", ".join(p.name for p in openapi)
        )
    else:
        versions.append(_load_json(openapi[0])["info"]["version"])

    protos = sorted((root / "contracts").glob("arcadedb-server-*.proto"))
    if len(protos) != 1:
        problems.append(
            f"contracts/ must hold exactly one arcadedb-server-*.proto, found {len(protos)}: "
            + ", ".join(p.name for p in protos)
        )
    else:
        versions.append(protos[0].name.removeprefix("arcadedb-server-").removesuffix(".proto"))

    return problems, versions


def check(root: Path, version: str, allow_snapshot: bool) -> list[str]:
    try:
        validate_version(version)
    except ReleaseError as exc:
        return [str(exc)]

    problems, contract_versions = _contract_versions(root)

    for row in PACKAGES:
        reg = REGISTRIES[row["registry"]]
        manifest = row["manifest"]

        got = reg.read_version(root, row)
        if got != version:
            problems.append(f"{manifest}: version is {got}, expected {version}")

        try:
            locked = reg.read_lock_version(root, row)
        except (KeyError, ReleaseError) as exc:
            problems.append(f"{row['lockfile']}: no entry for {row['name']} ({exc})")
        else:
            if locked != got:
                problems.append(
                    f"{row['lockfile']}: {row['name']} is locked at {locked} "
                    f"but {manifest} says {got}; regenerate the lockfile"
                )

        server = reg.read_server_version(root, row)
        if server.endswith("-SNAPSHOT") and not allow_snapshot:
            problems.append(f"{manifest}: server version {server} is a SNAPSHOT; a release needs a fixed server version")
        for contract in contract_versions:
            if server != contract:
                problems.append(f"{manifest}: server version {server} does not match the contract version {contract}")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root (for tests)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("json", help="print the package table as JSON")
    chk = sub.add_parser("check", help="verify every package agrees on <version>")
    chk.add_argument("version")
    chk.add_argument("--allow-snapshot", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "json":
        print(json.dumps(PACKAGES, indent=2))
        return 0

    problems = check(args.root, args.version, args.allow_snapshot)
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    print(f"OK: {len(PACKAGES)} packages at {args.version}, lockfiles and contracts agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
