"""Tests for scripts/release-packages.py.

The script is the one place that knows which manifests make up a release, so these
tests pin both the table itself and the lockstep check that `main` is held to.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "release-packages.py"
_REPO = _SCRIPT.parent.parent

_ROW_KEYS = {"id", "language", "manifest", "lockfile", "registry", "name", "workflow", "package_input"}


def _load() -> ModuleType:
    # The script's filename contains a hyphen, so it cannot be imported by name.
    spec = importlib.util.spec_from_file_location("release_packages", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_packages"] = module
    spec.loader.exec_module(module)
    return module


rp = _load()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _npm_manifest(root: Path, pkg: str, version: str, server: str) -> None:
    _write(
        root / f"typescript/packages/{pkg}/package.json",
        json.dumps({"name": f"@arcadedb/{pkg}", "version": version, "arcadedb": {"serverVersion": server}}),
    )


def _pypi_manifest(root: Path, pkg: str, version: str, server: str) -> None:
    _write(
        root / f"python/packages/{pkg}/pyproject.toml",
        f'[project]\nname = "arcadedb-{pkg}"\nversion = "{version}"\n\n'
        f'[tool.arcadedb]\nserver-version = "{server}"\n',
    )


def _package_lock(root: Path, version: str) -> None:
    _write(
        root / "typescript/package-lock.json",
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "workspace"},
                    "packages/driver": {"name": "@arcadedb/driver", "version": version},
                    "packages/driver-grpc": {"name": "@arcadedb/driver-grpc", "version": version},
                },
            }
        ),
    )


def _uv_lock(root: Path, version: str) -> None:
    _write(
        root / "python/uv.lock",
        "version = 1\n\n"
        '[[package]]\nname = "annotated-doc"\nversion = "0.0.5"\n\n'
        f'[[package]]\nname = "arcadedb-driver"\nversion = "{version}"\n'
        'source = { editable = "packages/driver" }\n\n'
        f'[[package]]\nname = "arcadedb-driver-grpc"\nversion = "{version}"\n'
        'source = { editable = "packages/driver-grpc" }\n\n'
        '[[package]]\nname = "arcadedb-drivers-workspace"\nversion = "0.0.0"\n'
        'source = { virtual = "." }\n',
    )


_GO_NAME = "github.com/ArcadeData/arcadedb-drivers/go/arcadedb"


def _go_module(root: Path, version: str, server: str, module: str = _GO_NAME) -> None:
    _write(
        root / "go/arcadedb/version.go",
        "package arcadedb\n\n// Version is the release version.\n"
        f'const Version = "{version}"\n\n// ServerVersion is the server.\n'
        f'const ServerVersion = "{server}"\n',
    )
    _write(root / "go/arcadedb/go.mod", f"module {module}\n\ngo 1.26\n")


def fixture_repo(tmp_path: Path, version: str = "0.1.0", server: str = "26.10.1") -> Path:
    for pkg in ("driver", "driver-grpc"):
        _npm_manifest(tmp_path, pkg, version, server)
        _pypi_manifest(tmp_path, pkg, version, server)
    _package_lock(tmp_path, version)
    _uv_lock(tmp_path, version)
    _go_module(tmp_path, version, server)
    _write(tmp_path / f"contracts/arcadedb-openapi-{server}.json", json.dumps({"info": {"version": server}}))
    _write(tmp_path / f"contracts/arcadedb-server-{server}.proto", 'syntax = "proto3";\n')
    return tmp_path


def test_json_lists_every_package_with_every_field() -> None:
    proc = subprocess.run([sys.executable, str(_SCRIPT), "json"], capture_output=True, text=True, check=True)
    rows = json.loads(proc.stdout)
    assert [r["id"] for r in rows] == ["npm-driver", "npm-driver-grpc", "pypi-driver", "pypi-driver-grpc", "go-arcadedb"]
    for row in rows:
        assert set(row) == _ROW_KEYS


def test_table_paths_exist_in_this_repository() -> None:
    for row in rp.PACKAGES:
        assert (_REPO / row["manifest"]).is_file(), row["manifest"]
        if row["lockfile"]:
            assert (_REPO / row["lockfile"]).is_file(), row["lockfile"]


def test_check_passes_when_everything_agrees(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    assert rp.check(root, "0.1.0", False) == []


@pytest.mark.parametrize("bad", ["0.2.0-rc.1", "v0.2.0", "0.2"])
def test_check_rejects_prerelease_and_prefixed_versions(tmp_path: Path, bad: str) -> None:
    root = fixture_repo(tmp_path)
    problems = rp.check(root, bad, False)
    assert problems
    assert any(bad in p for p in problems)


def test_check_reports_each_manifest_that_disagrees(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    _pypi_manifest(root, "driver-grpc", "0.1.1", "26.10.1")
    problems = rp.check(root, "0.1.0", False)
    hit = [p for p in problems if "python/packages/driver-grpc/pyproject.toml" in p]
    assert hit
    assert "0.1.1" in hit[0] and "0.1.0" in hit[0]


def test_check_reports_stale_lockfile(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path / "a", version="0.2.0")
    _uv_lock(root, "0.1.0")
    problems = rp.check(root, "0.2.0", False)
    assert any("python/uv.lock" in p for p in problems)
    assert not any("typescript/package-lock.json" in p for p in problems)

    root2 = fixture_repo(tmp_path / "b", version="0.2.0")
    _package_lock(root2, "0.1.0")
    problems = rp.check(root2, "0.2.0", False)
    assert any("typescript/package-lock.json" in p for p in problems)


def test_check_reports_server_version_contract_mismatch(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    _npm_manifest(root, "driver", "0.1.0", "26.9.1")
    problems = rp.check(root, "0.1.0", False)
    assert any("typescript/packages/driver/package.json" in p and "26.9.1" in p for p in problems)


def test_check_refuses_snapshot_unless_allowed(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path, server="26.10.1-SNAPSHOT")
    assert any("SNAPSHOT" in p for p in rp.check(root, "0.1.0", False))
    assert rp.check(root, "0.1.0", True) == []


def test_check_requires_exactly_one_contract_of_each_kind(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path / "a")
    _write(root / "contracts/arcadedb-openapi-26.9.1.json", json.dumps({"info": {"version": "26.9.1"}}))
    assert any("openapi" in p for p in rp.check(root, "0.1.0", False))

    root2 = fixture_repo(tmp_path / "b")
    _write(root2 / "contracts/arcadedb-server-26.9.1.proto", "")
    assert any("proto" in p for p in rp.check(root2, "0.1.0", False))


def test_cli_check_exit_codes(tmp_path: Path) -> None:
    good = fixture_repo(tmp_path / "good")
    ok = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(good), "check", "0.1.0"], capture_output=True, text=True
    )
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.startswith("OK")

    bad = fixture_repo(tmp_path / "bad")
    _pypi_manifest(bad, "driver", "0.1.1", "26.10.1")
    res = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(bad), "check", "0.1.0"], capture_output=True, text=True
    )
    assert res.returncode == 1
    assert "python/packages/driver/pyproject.toml" in res.stderr


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_set_then_check_agrees(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    rp.set_version(root, "0.2.0")
    assert rp.check(root, "0.2.0", True) == []


def test_set_never_touches_server_versions(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    servers = {r["id"]: rp.REGISTRIES[r["registry"]].read_server_version(root, r) for r in rp.PACKAGES}
    before = _snapshot(root)
    rp.set_version(root, "0.2.0")
    after = _snapshot(root)
    for r in rp.PACKAGES:
        assert rp.REGISTRIES[r["registry"]].read_server_version(root, r) == servers[r["id"]]
    contracts = [name for name in before if name.startswith("contracts/")]
    assert contracts
    for name in contracts:
        assert after[name] == before[name]


def test_set_touches_only_table_files(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    before = _snapshot(root)
    rp.set_version(root, "0.2.0")
    after = _snapshot(root)
    assert set(after) == set(before)
    changed = {name for name in before if before[name] != after[name]}
    expected = {r["manifest"] for r in rp.PACKAGES} | {r["lockfile"] for r in rp.PACKAGES if r["lockfile"]}
    assert changed == expected


def test_set_preserves_formatting(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    manifest = root / "typescript/packages/driver/package.json"
    manifest.write_text(
        json.dumps({"name": "@arcadedb/driver", "version": "0.1.0", "arcadedb": {"serverVersion": "26.10.1"}}, indent=2)
        + "\n"
    )
    pyproject = root / "python/packages/driver/pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "arcadedb-driver"\n# keep me above\nversion = "0.1.0"  # keep me beside\n# keep me below\n\n'
        '[tool.arcadedb]\nserver-version = "26.10.1"\n'
    )
    rp.set_version(root, "0.2.0")
    text = manifest.read_text()
    assert text.endswith("}\n") and not text.endswith("\n\n")
    assert '\n  "version": "0.2.0",\n' in text
    assert pyproject.read_text() == (
        '[project]\nname = "arcadedb-driver"\n# keep me above\nversion = "0.2.0"  # keep me beside\n'
        "# keep me below\n\n"
        '[tool.arcadedb]\nserver-version = "26.10.1"\n'
    )


def test_set_fails_when_version_matches_twice(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    pyproject = root / "python/packages/driver-grpc/pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace('version = "0.1.0"\n', 'version = "0.1.0"\nversion = "9.9.9"\n')
    )
    before = _snapshot(root)
    with pytest.raises(rp.ReleaseError, match="python/packages/driver-grpc/pyproject.toml"):
        rp.set_version(root, "0.2.0")
    assert _snapshot(root) == before


def test_set_fails_when_lockfile_block_missing(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    lock = root / "python/uv.lock"
    lock.write_text(lock.read_text().replace('name = "arcadedb-driver-grpc"', 'name = "arcadedb-other"'))
    before = _snapshot(root)
    with pytest.raises(rp.ReleaseError, match="python/uv.lock"):
        rp.set_version(root, "0.2.0")
    assert _snapshot(root) == before


def test_set_rejects_invalid_version(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    before = _snapshot(root)
    with pytest.raises(rp.ReleaseError):
        rp.set_version(root, "v0.2.0")
    assert _snapshot(root) == before


def _row(row_id: str) -> dict[str, str]:
    return next(r for r in rp.PACKAGES if r["id"] == row_id)


def test_published_url_encodes_npm_scope() -> None:
    assert (
        rp.published_url(_row("npm-driver"), "0.2.0") == "https://registry.npmjs.org/@arcadedb%2Fdriver/0.2.0"
    )


def test_published_url_pypi() -> None:
    assert (
        rp.published_url(_row("pypi-driver-grpc"), "0.2.0")
        == "https://pypi.org/pypi/arcadedb-driver-grpc/0.2.0/json"
    )


def test_is_published_maps_200_and_404() -> None:
    row = _row("npm-driver")
    assert rp.is_published(row, "0.2.0", fetch=lambda url: 200) is True
    assert rp.is_published(row, "0.2.0", fetch=lambda url: 404) is False


def test_is_published_fails_closed_on_500_and_network_error() -> None:
    import urllib.error

    row = _row("pypi-driver")

    with pytest.raises(rp.ReleaseError, match="pypi.org"):
        rp.is_published(row, "0.2.0", fetch=lambda url: 503)

    def boom(url: str) -> int:
        raise urllib.error.URLError("down")

    with pytest.raises(rp.ReleaseError, match="pypi.org"):
        rp.is_published(row, "0.2.0", fetch=boom)


def test_header_lists_every_package_and_server_version(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path, "0.2.0", "26.10.1")
    header = rp.render_header(root, "0.2.0")
    for row in rp.PACKAGES:
        # Backticked, because "arcadedb-driver" is a substring of "arcadedb-driver-grpc".
        assert header.count("`" + row["name"] + "`") == 1
    assert "## Packages" in header
    assert "Generated against ArcadeDB server 26.10.1." in header
    assert not header.startswith("# ")


def test_cli_is_published_and_header(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path, "0.2.0")
    res = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(root), "header", "0.2.0"], capture_output=True, text=True
    )
    assert res.returncode == 0 and "## Packages" in res.stdout
    res = subprocess.run(
        [sys.executable, str(_SCRIPT), "is-published", "nope", "0.2.0"], capture_output=True, text=True
    )
    assert res.returncode == 1


def test_goproxy_escape() -> None:
    assert rp._goproxy_escape("github.com/ArcadeData/x") == "github.com/!arcade!data/x"


def test_published_url_goproxy() -> None:
    assert (
        rp.published_url(_row("go-arcadedb"), "0.2.0")
        == "https://proxy.golang.org/github.com/!arcade!data/arcadedb-drivers/go/arcadedb/@v/v0.2.0.info"
    )


def test_is_published_maps_410_to_false() -> None:
    row = _row("go-arcadedb")
    assert rp.is_published(row, "0.2.0", fetch=lambda url: 200) is True
    assert rp.is_published(row, "0.2.0", fetch=lambda url: 404) is False
    assert rp.is_published(row, "0.2.0", fetch=lambda url: 410) is False


def test_check_go_version_mismatch_reported(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    _go_module(root, "0.1.1", "26.10.1")
    problems = rp.check(root, "0.1.0", False)
    hit = [p for p in problems if "go/arcadedb/version.go" in p]
    assert hit and "0.1.1" in hit[0] and "0.1.0" in hit[0]


def test_check_go_server_version_compares_against_openapi_only(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    _go_module(root, "0.1.0", "26.9.1")
    problems = rp.check(root, "0.1.0", False)
    assert any("go/arcadedb/version.go" in p and "26.9.1" in p for p in problems)


def test_check_go_module_line_must_match_name(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    _go_module(root, "0.1.0", "26.10.1", module="github.com/example/other")
    problems = rp.check(root, "0.1.0", False)
    assert any("go/arcadedb/go.mod" in p and "github.com/example/other" in p for p in problems)


def test_check_refuses_v2_without_path_suffix(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path, version="2.0.0")
    problems = rp.check(root, "2.0.0", False)
    assert any("/v2" in p for p in problems)


def test_set_writes_go_version_and_not_server_version(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    rp.set_version(root, "0.2.0")
    text = (root / "go/arcadedb/version.go").read_text()
    assert 'const Version = "0.2.0"' in text
    assert 'const ServerVersion = "26.10.1"' in text


def test_set_refuses_version_go_with_two_version_consts(tmp_path: Path) -> None:
    root = fixture_repo(tmp_path)
    go = root / "go/arcadedb/version.go"
    go.write_text(go.read_text() + 'const Version = "9.9.9"\n')
    before = _snapshot(root)
    with pytest.raises(rp.ReleaseError, match="go/arcadedb/version.go"):
        rp.set_version(root, "0.2.0")
    assert _snapshot(root) == before
