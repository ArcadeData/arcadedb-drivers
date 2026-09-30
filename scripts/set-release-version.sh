#!/usr/bin/env bash
#
# Sets every published package to <version>, every lockfile that exists included (the Go module
# has none), then proves it.
#
#   scripts/set-release-version.sh 0.2.0
#
# The rewrite is scripts/release-packages.py `set`; this wrapper follows it with the same
# script's `check`, so a bump that left a manifest or lockfile behind fails here rather
# than in CI. `--allow-snapshot` is deliberate: this script moves package versions and
# never a server version, so whether the server version is still a -SNAPSHOT is not its
# concern. The release workflow's own `check` (without the flag) is where that is refused.
#
# It does not commit, and it does not run npm or uv: both lockfiles are edited directly.
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "usage: $0 <version>   (MAJOR.MINOR.PATCH, no 'v' prefix)" >&2
  exit 2
fi

VERSION="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$SCRIPT_DIR/release-packages.py"

python3 "$TOOL" set "$VERSION"
python3 "$TOOL" check "$VERSION" --allow-snapshot
git -C "$SCRIPT_DIR/.." diff --stat
