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
  set <version>                          write <version> into every manifest and lockfile

`check` holds the invariant a lockstep release depends on: every manifest reads
<version>, every lockfile agrees with its manifest, and every package's recorded server
version matches the single OpenAPI contract and the single .proto contract. A
`-SNAPSHOT` server version is a problem unless --allow-snapshot is given, because a
release must not ship against a moving target while `main` legitimately does.

`set` is the only writer. It edits manifests and lockfiles directly, with no network and no
package manager, and never touches a server version: that moves with the contract, through
adopt-contract-version.sh. Every new file content is computed in memory first and nothing is
written unless every edit succeeded, so a failure leaves the tree untouched.

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


def _dump_json(obj: dict) -> str:
    # The format npm itself writes: two-space indent and a trailing newline.
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def _npm_write_version(text: str, row: Row, version: str) -> str:
    data = json.loads(text)
    data["version"] = version
    return _dump_json(data)


def _npm_write_lock_version(text: str, row: Row, version: str) -> str:
    data = json.loads(text)
    key = f"packages/{row['package_input']}"
    try:
        data["packages"][key]["version"] = version
    except KeyError:
        raise ReleaseError(f"{row['lockfile']} has no packages[{key!r}] entry") from None
    return _dump_json(data)


def _sub_exactly_once(pattern: str, repl: str, text: str, where: str, what: str) -> str:
    new, count = re.subn(pattern, repl, text, flags=re.MULTILINE)
    if count != 1:
        raise ReleaseError(f"{where}: expected exactly one {what}, found {count}")
    return new


def _pypi_write_version(text: str, row: Row, version: str) -> str:
    # Confine the edit to the [project] table: [tool.*] tables may carry their own `version`.
    header = re.search(r"^\[project\][ \t]*$", text, flags=re.MULTILINE)
    if header is None:
        raise ReleaseError(f"{row['manifest']}: no [project] table")
    following = re.search(r"^\[", text[header.end() :], flags=re.MULTILINE)
    end = header.end() + following.start() if following else len(text)
    table = _sub_exactly_once(
        r'^(version\s*=\s*")[^"]*(")',
        rf"\g<1>{version}\g<2>",
        text[header.end() : end],
        row["manifest"],
        "`version =` line in [project]",
    )
    return text[: header.end()] + table + text[end:]


def _pypi_write_lock_version(text: str, row: Row, version: str) -> str:
    return _sub_exactly_once(
        rf'^(name = "{re.escape(row["name"])}"\nversion = ")[^"]*(")',
        rf"\g<1>{version}\g<2>",
        text,
        row["lockfile"],
        f"[[package]] block for {row['name']}",
    )


class Registry(NamedTuple):
    read_version: Callable[[Path, Row], str]
    read_lock_version: Callable[[Path, Row], str]
    read_server_version: Callable[[Path, Row], str]
    # Pure text -> text edits, so `set` can stage every change before writing any.
    write_version: Callable[[str, Row, str], str]
    write_lock_version: Callable[[str, Row, str], str]


REGISTRIES: dict[str, Registry] = {
    "npm": Registry(
        _npm_read_version,
        _npm_read_lock_version,
        _npm_read_server_version,
        _npm_write_version,
        _npm_write_lock_version,
    ),
    "pypi": Registry(
        _pypi_read_version,
        _pypi_read_lock_version,
        _pypi_read_server_version,
        _pypi_write_version,
        _pypi_write_lock_version,
    ),
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


def set_version(root: Path, version: str) -> None:
    """Write `version` into every manifest and lockfile, or into none of them."""
    validate_version(version)

    staged: dict[Path, str] = {}
    for row in PACKAGES:
        reg = REGISTRIES[row["registry"]]
        manifest = root / row["manifest"]
        staged[manifest] = reg.write_version(staged.get(manifest) or manifest.read_text(), row, version)
        lockfile = root / row["lockfile"]
        staged[lockfile] = reg.write_lock_version(staged.get(lockfile) or lockfile.read_text(), row, version)

    for path, text in staged.items():
        path.write_text(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root (for tests)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("json", help="print the package table as JSON")
    chk = sub.add_parser("check", help="verify every package agrees on <version>")
    chk.add_argument("version")
    chk.add_argument("--allow-snapshot", action="store_true")
    st = sub.add_parser("set", help="write <version> into every manifest and lockfile")
    st.add_argument("version")
    args = parser.parse_args(argv)

    if args.command == "json":
        print(json.dumps(PACKAGES, indent=2))
        return 0

    if args.command == "set":
        try:
            set_version(args.root, args.version)
        except ReleaseError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"Set {len(PACKAGES)} packages to {args.version}")
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
