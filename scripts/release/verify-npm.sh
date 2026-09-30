#!/usr/bin/env bash
# The npm pre-publish gates, in one place so a dry run and a real publish cannot diverge.
#
# Usage: scripts/release/verify-npm.sh <driver|driver-grpc>
#
# Run from the repository root, after `npm ci` in typescript/. Runs, in order: the unit test suite,
# the recorded-server-version check, and the prepack build with its dist/ assertions. Exits
# non-zero on the first failure. It does not install anything and does not publish anything.
# publish.yml calls it before `npm publish`; release.yml calls it as a dry run.
set -euo pipefail

PKG=${1:?usage: verify-npm.sh <driver|driver-grpc>}
case "$PKG" in
  driver | driver-grpc) ;;
  *)
    echo "Unknown package \"$PKG\": expected driver or driver-grpc." >&2
    exit 1
    ;;
esac

# Every check below addresses the chosen package through these two, never through a literal
# workspace name - that is what keeps the two packages from drifting apart in what gets
# verified before a publish. The node programs read them from the environment.
PKG_DIR=packages/$PKG
export PKG PKG_DIR

cd "$(dirname "$0")/../../typescript"

echo "==> Run the full unit test suite"
npm test

echo "==> Verify the package's recorded server version matches the committed contract"
# The package records the ArcadeDB server release it was generated against in
# package.json's "arcadedb.serverVersion". That must still match the committed contract's
# "info.version" at publish time - otherwise the compatibility table this package ships in
# its README would be lying the moment it's published. The contract file's name carries the
# version, so it's located by pattern rather than hardcoded, and the check fails loudly if
# zero or more than one candidate is found.
# shellcheck disable=SC2016 # the JS template literals are meant to reach node unexpanded
node -e '
  const fs = require("fs");
  const path = require("path");
  const contractsDir = path.join("..", "contracts");
  const candidates = fs.readdirSync(contractsDir).filter((f) => f.startsWith("arcadedb-openapi-") && f.endsWith(".json"));
  if (candidates.length !== 1) {
    console.error(`Expected exactly one contracts/arcadedb-openapi-*.json file, found ${candidates.length}: ${candidates.join(", ")}`);
    process.exit(1);
  }
  const dir = process.env.PKG_DIR;
  const pkg = require(`./${dir}/package.json`);
  const contract = JSON.parse(fs.readFileSync(path.join(contractsDir, candidates[0]), "utf8"));
  const pkgVersion = pkg.arcadedb && pkg.arcadedb.serverVersion;
  const contractVersion = contract.info && contract.info.version;
  if (!pkgVersion || !contractVersion) {
    console.error(`Missing version field(s): ${dir}/package.json arcadedb.serverVersion="${pkgVersion}", contract info.version="${contractVersion}"`);
    process.exit(1);
  }
  if (pkgVersion !== contractVersion) {
    console.error(`${dir}/package.json arcadedb.serverVersion ("${pkgVersion}") does not match ${candidates[0]}'"'"'s info.version ("${contractVersion}")`);
    process.exit(1);
  }
  console.log(`OK: arcadedb.serverVersion matches contract info.version (${pkgVersion})`);
'

echo "==> Build the client package and verify dist/ was produced"
# npm runs "prepack" per-workspace on `npm publish`/`npm pack`, which is what actually puts
# dist/ in the tarball - see each package's "prepack" script. Running it explicitly here,
# ahead of the publish step, and asserting its output exists turns a silent no-op build
# (missing script, build that produces the wrong directory, etc.) into a hard CI failure
# instead of an empty published package.
#
# The two packages need DIFFERENT assertions, which is why this is a script and not one
# shared list. `driver` emits its generated schema at a fixed path. `driver-grpc` emits a
# module whose filename carries the contract version, so the expected name is derived from
# the package's own arcadedb.serverVersion - already proved equal to the committed
# contract by the check above - rather than hardcoded, where it would rot on every bump.
npm run prepack --workspace "$PKG_DIR"
# shellcheck disable=SC2016 # the JS template literals are meant to reach node unexpanded
node -e '
  const fs = require("fs");
  const path = require("path");
  const dir = process.env.PKG_DIR;
  const pkg = require(`./${dir}/package.json`);
  const required = ["dist/index.js", "dist/index.d.ts"];

  if (process.env.PKG === "driver-grpc") {
    const v = pkg.arcadedb.serverVersion;
    required.push(`dist/gen/arcadedb-server-${v}_pb.js`, `dist/gen/arcadedb-server-${v}_pb.d.ts`);
  } else {
    required.push("dist/generated/schema.js", "dist/generated/schema.d.ts");
  }

  const missing = required.filter((f) => !fs.existsSync(path.join(dir, f)));
  if (missing.length) {
    console.error(`Missing after the build, so the published package would have shipped empty or broken:`);
    for (const f of missing) console.error(`  ${dir}/${f}`);
    console.error(`dist/index.d.ts imports its generated module by name; that module must exist alongside it.`);
    process.exit(1);
  }

  // Only driver-grpc can accumulate here. `tsc --build` emits into dist/ and never
  // removes output whose source is gone, and "files": ["dist"] ships the whole
  // directory - so a tree that has been built across two contract versions carries a
  // retired *_pb.js that would go out in the tarball. A clean CI checkout cannot hit
  // that, which is exactly why publishing happens here and not from a laptop; this
  // assertion is what makes the guarantee explicit rather than incidental.
  if (process.env.PKG === "driver-grpc") {
    const genDir = path.join(dir, "dist/gen");
    const modules = fs.readdirSync(genDir).filter((f) => f.endsWith("_pb.js"));
    if (modules.length !== 1) {
      console.error(`Expected exactly one generated module in ${genDir}, found ${modules.length}: ${modules.join(", ")}`);
      console.error(`A stale module from a previous contract version would be published inside the tarball.`);
      process.exit(1);
    }
  }

  console.log(`OK: ${pkg.name}@${pkg.version} built with all expected dist/ output`);
'
