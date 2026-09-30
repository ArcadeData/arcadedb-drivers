#!/usr/bin/env bash
#
# Lints every Go module listed in go/go.work that contains .go files: gofmt, go vet,
# staticcheck. Exits non-zero on the first failure. Runnable from any cwd.
#
# gofmt skips nothing: the generated client is gofmt-clean by construction, so a
# formatting diff there means the generator config changed and the output was not regenerated.
# staticcheck comes from go/tools/go.mod via `go tool` (never golangci-lint: GPL-3.0).
set -euo pipefail

cd "$(dirname "$0")/.."

# Module directories from the `use` block of go.work (one path per line, or `use ./dir`).
modules="$(awk '
  /^use[[:space:]]*\(/ { inblock = 1; next }
  inblock && /^\)/     { inblock = 0; next }
  inblock              { print $1; next }
  /^use[[:space:]]+[^(]/ { print $2 }
' go.work)"

for mod in $modules; do
  if [[ -z "$(find "$mod" -name '*.go' -print -quit)" ]]; then
    echo "lint: skipping $mod (no .go files)"
    continue
  fi
  echo "lint: $mod"
  (
    cd "$mod"
    unformatted="$(gofmt -l .)"
    if [[ -n "$unformatted" ]]; then
      echo "gofmt: these files in go/$mod are not formatted (run gofmt -w):" >&2
      echo "$unformatted" >&2
      exit 1
    fi
    go vet ./...
    go tool staticcheck ./...
  )
done
