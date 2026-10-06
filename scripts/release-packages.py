#!/usr/bin/env python3
"""The release package table, and the lockstep check every release rests on.

Every published package is one row of PACKAGES. The table is explicit, and is not
discovered by crawling `typescript/packages/*` and `python/packages/*`, for the same
reason adopt-contract-version.sh has an explicit LANGUAGES table: a new directory
appearing next to the old ones is not a decision to publish it. Adding a package to a
registry already known here is one row. Adding a registry is one REGISTRIES entry (how
to read a manifest and lockfile for it, or none) plus its rows - nothing else in this file
changes, and release.yml builds its matrices from `json` rather than repeating the list.

Subcommands:

  json                                   print the table as a JSON array
  check <version> [--allow-snapshot]     exit 1 listing every problem, else exit 0
  set <version>                          write <version> into every manifest and lockfile
  is-published <id> <version>            print true/false: is it on its registry? errors if unsure
  header <version>                       print the release-notes header (Markdown)

`check` holds the invariant a lockstep release depends on: every manifest reads
<version>, every lockfile agrees with its manifest (the Go module has none: its version is a
constant in version.go and the git tag), and every package's recorded server version matches the
single OpenAPI contract and the single .proto contract. A Go row is the exception: it carries an
optional `contract` key ("openapi" or "proto") naming the one contract it is generated from, and is
held to that contract alone (go/arcadedb to the OpenAPI version, go/arcadedbgrpc to the version in
the .proto filename). The key is optional so the npm and PyPI rows keep the both-contracts rule. Each
Go module's go.mod must also name the row's module path, with a /vN suffix from v2 on. A
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
import subprocess
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
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
    {
        "id": "go-arcadedb",
        "language": "go",
        "manifest": "go/arcadedb/version.go",
        "lockfile": "",
        "registry": "goproxy",
        "name": "github.com/ArcadeData/arcadedb-drivers/go/arcadedb",
        "workflow": "publish-go.yml",
        "package_input": "arcadedb",
        "contract": "openapi",
    },
    {
        "id": "go-arcadedbgrpc",
        "language": "go",
        "manifest": "go/arcadedbgrpc/version.go",
        "lockfile": "",
        "registry": "goproxy",
        "name": "github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc",
        "workflow": "publish-go.yml",
        "package_input": "arcadedbgrpc",
        "contract": "proto",
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


def _go_const_pattern(name: str) -> str:
    # `const Version` and `const ServerVersion` are two separate top-level lines, never a const
    # block, so a line-anchored match cannot confuse one for the other.
    return rf'^(const {name} = ")([^"\n]*)(")'


def _go_read_const(root: Path, row: Row, name: str) -> str:
    text = (root / row["manifest"]).read_text()
    matches = re.findall(_go_const_pattern(name), text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise ReleaseError(f"{row['manifest']}: expected exactly one `const {name} =` line, found {len(matches)}")
    return matches[0][1]


def _go_read_version(root: Path, row: Row) -> str:
    return _go_read_const(root, row, "Version")


def _go_read_server_version(root: Path, row: Row) -> str:
    return _go_read_const(root, row, "ServerVersion")


def _go_read_module(root: Path, row: Row) -> str | None:
    go_mod = (root / row["manifest"]).parent / "go.mod"
    match = re.search(r"^module\s+(\S+)", go_mod.read_text(), flags=re.MULTILINE)
    return match.group(1) if match else None


def _go_write_version(text: str, row: Row, version: str) -> str:
    return _sub_exactly_once(
        _go_const_pattern("Version"),
        rf"\g<1>{version}\g<3>",
        text,
        row["manifest"],
        "`const Version =` line",
    )


def _goproxy_no_lock(*_args: object) -> str:
    raise ReleaseError("goproxy has no lockfile")


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
    # A Go module has no lockfile of its own: go.mod records dependencies, not this module's
    # version, which is the git tag. The lock callables exist only to refuse being called.
    "goproxy": Registry(
        _go_read_version,
        _goproxy_no_lock,
        _go_read_server_version,
        _go_write_version,
        _goproxy_no_lock,
    ),
}


def _contract_versions(root: Path) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return problems, the contract versions found (OpenAPI, then proto), then the OpenAPI and proto ones alone."""
    problems: list[str] = []
    versions: list[str] = []
    openapi_only: list[str] = []
    proto_only: list[str] = []

    openapi = sorted((root / "contracts").glob("arcadedb-openapi-*.json"))
    if len(openapi) != 1:
        problems.append(
            f"contracts/ must hold exactly one arcadedb-openapi-*.json, found {len(openapi)}: "
            + ", ".join(p.name for p in openapi)
        )
    else:
        versions.append(_load_json(openapi[0])["info"]["version"])
        openapi_only.append(versions[0])

    protos = sorted((root / "contracts").glob("arcadedb-server-*.proto"))
    if len(protos) != 1:
        problems.append(
            f"contracts/ must hold exactly one arcadedb-server-*.proto, found {len(protos)}: "
            + ", ".join(p.name for p in protos)
        )
    else:
        proto_only.append(protos[0].name.removeprefix("arcadedb-server-").removesuffix(".proto"))
        versions.append(proto_only[0])

    return problems, versions, openapi_only, proto_only


def check(root: Path, version: str, allow_snapshot: bool) -> list[str]:
    try:
        validate_version(version)
    except ReleaseError as exc:
        return [str(exc)]

    problems, contract_versions, openapi_versions, proto_versions = _contract_versions(root)
    by_contract = {"openapi": openapi_versions, "proto": proto_versions}

    for row in PACKAGES:
        reg = REGISTRIES[row["registry"]]
        manifest = row["manifest"]

        got = reg.read_version(root, row)
        if got != version:
            problems.append(f"{manifest}: version is {got}, expected {version}")

        if row["lockfile"]:
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

        if row["registry"] == "goproxy":
            module = _go_read_module(root, row)
            if module != row["name"]:
                problems.append(
                    f"{Path(manifest).parent}/go.mod: module is {module}, expected {row['name']}"
                )
            major = int(version.split(".")[0])
            if major >= 2 and not row["name"].endswith(f"/v{major}"):
                problems.append(
                    f"{row['name']}: a Go module at v{major} must carry the /v{major} suffix in its "
                    "module path (and go.mod); the table name and go.mod need the suffix before this release"
                )

        server = reg.read_server_version(root, row)
        if server.endswith("-SNAPSHOT") and not allow_snapshot:
            problems.append(f"{manifest}: server version {server} is a SNAPSHOT; a release needs a fixed server version")
        # A row naming its `contract` is generated from that one contract alone (the Go modules);
        # every other row is held to both.
        for contract in by_contract[row["contract"]] if "contract" in row else contract_versions:
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
        if row["lockfile"]:
            lockfile = root / row["lockfile"]
            staged[lockfile] = reg.write_lock_version(staged.get(lockfile) or lockfile.read_text(), row, version)

    for path, text in staged.items():
        path.write_text(text)


def _goproxy_escape(path: str) -> str:
    """The module proxy's case encoding: every uppercase letter becomes `!` and its lowercase."""
    return re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), path)


_REGISTRY_URLS: dict[str, Callable[[str, str], str]] = {
    "npm": lambda name, version: f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}/{version}",
    "pypi": lambda name, version: f"https://pypi.org/pypi/{name}/{version}/json",
    "goproxy": lambda name, version: f"https://proxy.golang.org/{_goproxy_escape(name)}/@v/v{version}.info",
}


def published_url(row: Row, version: str) -> str:
    """The registry URL that answers 200 when `row` is published at `version`."""
    try:
        return _REGISTRY_URLS[row["registry"]](row["name"], version)
    except KeyError:
        raise ReleaseError(f"no registry URL scheme for {row['registry']!r}") from None


def _http_status(url: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=20) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


_GO_REPO = "github.com/ArcadeData/arcadedb-drivers"


def go_module_tag(row: Row, version: str) -> str:
    """The git tag that IS a Go module version: the module's directory in the repo, then v<version>."""
    prefix = _GO_REPO + "/"
    if not row["name"].startswith(prefix):
        raise ReleaseError(f"{row['name']} is not a module in {_GO_REPO}")
    return f"{row['name'][len(prefix):]}/v{version}"


def _remote_tag_exists(tag: str) -> bool:
    """Ask the PUBLIC repository, unauthenticated, as proxy.golang.org will: does `tag` exist?"""
    res = subprocess.run(
        ["git", "ls-remote", "--tags", f"https://{_GO_REPO}", f"refs/tags/{tag}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if res.returncode != 0:
        raise ReleaseError(f"git ls-remote for {tag} failed: {res.stderr.strip()}")
    return bool(res.stdout.strip())


def is_published(
    row: Row,
    version: str,
    fetch: Callable[[str], int] = _http_status,
    tag_exists: Callable[[str], bool] = _remote_tag_exists,
) -> bool:
    """Fail closed: only 200 means published and only 404 (410 on the Go proxy) means not; else an error.

    Guessing "not published" on a 5xx or a network failure would let a retry re-publish a
    version that already exists, so the caller is told it does not know.

    A Go module is never looked up on the proxy before its tag exists. proxy.golang.org caches a
    "not found" for a version it could not resolve, for up to about half an hour, and keeps serving
    it after the tag appears: in the 0.2.0 release, release.yml asked here three minutes before
    publish-go.yml pushed the tag, and both module fetches then failed for ~25 minutes. A version
    with no tag cannot be on the proxy, so "no tag" answers False without asking it.

    The version is validated first: a malformed one (say "v0.2.0") would otherwise build a tag or
    URL that cannot exist and read as a confident "not published" rather than as an error.
    """
    validate_version(version)
    if row["registry"] == "goproxy":
        tag = go_module_tag(row, version)
        try:
            has_tag = tag_exists(tag)
        except ReleaseError:
            raise
        except Exception as exc:
            raise ReleaseError(f"could not check whether tag {tag} exists: {exc}") from exc
        if not has_tag:
            return False
    url = published_url(row, version)
    try:
        status = fetch(url)
    except Exception as exc:
        raise ReleaseError(f"could not query {url}: {exc}") from exc
    if status == 200:
        return True
    if status in (404, 410):
        return False
    raise ReleaseError(f"unexpected HTTP {status} from {url}")


def render_header(root: Path, version: str) -> str:
    """Markdown that precedes GitHub's generated notes: what shipped, and against which server."""
    lines = ["## Packages", "", "| Package | Registry | Version |", "| --- | --- | --- |"]
    lines += [f"| `{row['name']}` | {row['registry']} | {version} |" for row in PACKAGES]
    first = PACKAGES[0]
    server = REGISTRIES[first["registry"]].read_server_version(root, first)
    lines += ["", f"Generated against ArcadeDB server {server}.", ""]
    return "\n".join(lines)


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
    pub = sub.add_parser("is-published", help="is <id> published at <version>?")
    pub.add_argument("id")
    pub.add_argument("version")
    hdr = sub.add_parser("header", help="print the release-notes header")
    hdr.add_argument("version")
    args = parser.parse_args(argv)

    if args.command == "json":
        print(json.dumps(PACKAGES, indent=2))
        return 0

    if args.command == "is-published":
        try:
            row = next((r for r in PACKAGES if r["id"] == args.id), None)
            if row is None:
                raise ReleaseError(f"no package with id {args.id!r}; known: " + ", ".join(r["id"] for r in PACKAGES))
            print("true" if is_published(row, args.version) else "false")
        except ReleaseError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.command == "header":
        try:
            validate_version(args.version)
            print(render_header(args.root, args.version), end="")
        except ReleaseError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
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
