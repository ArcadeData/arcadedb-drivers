#!/usr/bin/env bash
# The PyPI pre-publish gates, in one place so a dry run and a real publish cannot diverge.
#
# Usage: scripts/release/verify-pypi.sh <driver|driver-grpc>
#
# Run from anywhere (it changes into python/ itself), after `uv sync --frozen` in python/. Runs, in
# order: the unit test suite, the recorded-server-version check against the package's own contract,
# and the wheel/sdist build with its content assertions. Exits non-zero on the first failure. It
# does not install anything and does not publish anything. It empties python/dist/ first and leaves
# the built wheel and sdist there for the publish step.
# publish-python.yml calls it before the PyPI upload; release.yml calls it as a dry run.
set -euo pipefail

PKG=${1:?usage: verify-pypi.sh <driver|driver-grpc>}
case "$PKG" in
  driver | driver-grpc) ;;
  *)
    echo "Unknown package \"$PKG\": expected driver or driver-grpc." >&2
    exit 1
    ;;
esac

# Every check below addresses the chosen package through these two, never through a literal
# workspace name - that is what keeps the two packages from drifting apart in what gets
# verified before a publish. The python programs read them from the environment.
PKG_DIR=packages/$PKG
export PKG PKG_DIR

cd "$(dirname "$0")/../../python"

echo "==> Run the full unit test suite"
uv run pytest

echo "==> Verify the package's recorded server version matches the committed contract"
case "$PKG" in
  driver)
    # The package records the ArcadeDB release it was generated against in
    # pyproject.toml's [tool.arcadedb] server-version. That must still match the
    # committed contract's info.version at publish time - otherwise the
    # compatibility table this package ships in its README would be lying the
    # moment it is published. The contract file's name carries the version, so
    # it is located by pattern rather than hardcoded, and the check fails loudly
    # if zero or more than one candidate is found.
    #
    # arcadedb-driver ONLY: this reads the OpenAPI contract, which is what
    # arcadedb-driver is generated from - driver-grpc is generated from the .proto
    # and never reads this JSON at all, so gating this on `driver` (rather than
    # running it unconditionally) is what keeps a proto-only contract bump from
    # blocking a driver-grpc publish on an OpenAPI contract it does not depend on.
    # The driver-grpc branch below is its own equivalent gate, on its own contract.
    uv run python - <<'PY'
import json, os, pathlib, sys, tomllib
contracts = pathlib.Path("../contracts")
candidates = sorted(contracts.glob("arcadedb-openapi-*.json"))
if len(candidates) != 1:
    sys.exit(f"Expected exactly one contracts/arcadedb-openapi-*.json, found {len(candidates)}")
pkg_dir = pathlib.Path(os.environ["PKG_DIR"])
pkg = tomllib.loads((pkg_dir / "pyproject.toml").read_text())
pkg_version = pkg.get("tool", {}).get("arcadedb", {}).get("server-version")
contract_version = json.loads(candidates[0].read_text()).get("info", {}).get("version")
if not pkg_version or not contract_version:
    sys.exit(f'Missing version field(s): server-version="{pkg_version}", info.version="{contract_version}"')
if pkg_version != contract_version:
    sys.exit(
        f'{pkg_dir}/pyproject.toml [tool.arcadedb] server-version ("{pkg_version}") does not match '
        f'{candidates[0].name}\'s info.version ("{contract_version}")'
    )
print(f"OK: server-version matches contract info.version ({pkg_version})")
PY
    ;;
  driver-grpc)
    # The driver branch above compares server-version against the OPENAPI contract's
    # info.version, gated to `driver` only - the right source for arcadedb-driver,
    # which is generated from it, but only indirect evidence for
    # arcadedb-driver-grpc, which is generated from the .proto and never reads that
    # JSON at all. The two agree today only because adopt-contract-version.sh
    # stamps every package from one argument; fetch-contract.sh's --image (OpenAPI)
    # and --proto-from (proto) modes are independent, so the two
    # contracts CAN be fetched apart and left disagreeing, and nothing else here
    # would notice. The publish workflow is the only irreversible one in the repository -
    # a wrong publish cannot be taken back - so the gRPC package gets its own gate
    # on its own contract here, gated to `driver-grpc`, rather than inheriting the
    # JSON one or blocking on a contract it does not depend on.
    #
    # resolve-proto-contract.sh already refuses zero or two matches, which is the
    # other half of the check: a version bump transiently leaves two contracts side
    # by side, and a glob resolves those in LEXICAL order - 26.9.1 before 26.9.2, the
    # stale one. All this step adds is comparing the surviving file's filename version
    # against what the package recorded.
    PROTO="$(../scripts/resolve-proto-contract.sh)"
    export PROTO
    uv run python - <<'PY'
import os, pathlib, sys, tomllib
proto = pathlib.Path(os.environ["PROTO"])
proto_version = proto.name.removeprefix("arcadedb-server-").removesuffix(".proto")
pkg_dir = pathlib.Path(os.environ["PKG_DIR"])
pkg = tomllib.loads((pkg_dir / "pyproject.toml").read_text())
pkg_version = pkg.get("tool", {}).get("arcadedb", {}).get("server-version")
if not proto_version or not pkg_version:
    sys.exit(f'Missing version(s): proto filename="{proto.name}", server-version="{pkg_version}"')
if proto_version != pkg_version:
    sys.exit(
        f'{pkg_dir}/pyproject.toml [tool.arcadedb] server-version ("{pkg_version}") does not match '
        f'the committed contract {proto.name} ("{proto_version}"). Run '
        f"scripts/adopt-contract-version.sh so both contracts and every package agree."
    )
print(f"OK: {proto.name} matches server-version ({pkg_version})")
PY
    ;;
esac

echo "==> Build the wheel and sdist, and verify their contents"
# Asserting the built artifacts actually contain the generated tree and the
# typing marker turns a silent no-op build into a hard CI failure instead of
# an empty published package - the same guard verify-npm.sh applies to dist/.
#
# The two packages need different required-entry lists, which is why this is
# a script and not one shared list - the same shape verify-npm.sh takes for the
# same reason. driver-grpc's generated modules are checked separately, in the
# section after this one, because their names are constant (see that section's
# comment) and so need no per-package branching here.
#
# dist/ is emptied first so a dry run and a publish both start from nothing, and so
# the publish step uploads exactly the one wheel and one sdist built here.
rm -rf dist
DIST_NAME="arcadedb_${PKG//-/_}"
uv build --package "arcadedb-$PKG" --out-dir dist
WHEEL="$(ls dist/"$DIST_NAME"-*.whl)"

if [[ "$PKG" == "driver-grpc" ]]; then
  REQUIRED=(
    "arcadedb_driver_grpc/__init__.py"
    "arcadedb_driver_grpc/py.typed"
  )
else
  REQUIRED=(
    "arcadedb_driver/__init__.py"
    "arcadedb_driver/py.typed"
    "arcadedb_driver/_generated/client.py"
    "arcadedb_driver/_generated/api/query/execute_query_post.py"
  )
fi

# The listing is captured once, not piped into `grep -q` per entry: `grep -q` exits at its first
# match, and under `pipefail` a still-writing `unzip` then dies of SIGPIPE (141) and fails a
# wheel that is in fact correct. Whether that happens depends on how the platform's unzip
# buffers its output, so it showed up on a laptop and not in CI.
LISTING="$(unzip -l "$WHEEL")"
for entry in "${REQUIRED[@]}"; do
  grep -q "$entry" <<<"$LISTING" \
    || { echo "$entry is missing from $WHEEL - the published package would be broken" >&2; exit 1; }
done
ls dist/"$DIST_NAME"-*.tar.gz >/dev/null

if [[ "$PKG" == "driver-grpc" ]]; then
  echo "==> Verify the gRPC generated modules are in the wheel"
  # Simpler than verify-npm.sh's dist assertion for driver-grpc, which derives the expected
  # filename from arcadedb.serverVersion because its generated module is version-stamped.
  # This one is not: generate-grpc.sh normalises the proto filename, so these names are
  # constant and a regenerate overwrites rather than accumulates. The stale-module hazard
  # npm's derived-name check exists to catch cannot occur here.
  #
  # Two things differ here from the exact command this step started from, both
  # found by actually building a wheel and running it rather than trusting it:
  #   - no trailing `$` on the pattern: `python -m zipfile -l` lists
  #     "name  mtime  size" per line, not a bare filename, so anchoring at
  #     end-of-line finds zero matches against a real wheel;
  #   - `dist/"$DIST_NAME"-*.whl`, not a bare `dist/*.whl`: `zipfile -l` accepts
  #     exactly one archive argument, so a bare glob breaks the moment more than
  #     one wheel sits in dist/ (harmless here, since the rm -rf above leaves only the
  #     one package just built, but the pinned glob costs nothing and removes the assumption).
  #
  # `|| true` is load-bearing: `grep -c` exits 1 when it matches nothing, and
  # under `set -e` (which this script runs with) that aborts the assignment - so the
  # zero-match case, the one the diagnostic below exists for, would kill the script
  # before it could print anything. With `|| true` the count is 0 and the `if`
  # below reports it properly.
  COUNT="$(uv run python -m zipfile -l dist/"$DIST_NAME"-*.whl | grep -cE 'arcadedb_server_pb2(_grpc)?\.(py|pyi)' || true)"
  if [[ "$COUNT" -ne 4 ]]; then
    echo "Expected 4 generated gRPC files (arcadedb_server_pb2.py/.pyi, arcadedb_server_pb2_grpc.py/.pyi) in the wheel, found $COUNT:" >&2
    uv run python -m zipfile -l dist/"$DIST_NAME"-*.whl | grep -E 'arcadedb_server_pb2(_grpc)?\.(py|pyi)' >&2
    exit 1
  fi
  echo "OK: found all 4 generated gRPC files in the wheel"
fi
