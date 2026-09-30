# M10: `arcadedb` for Go, the HTTP client

**Status:** design approved in conversation, spec under review, plan pending
**Date:** 2026-09-30
**Parent:** ArcadeData/arcadedb Epic #4894
**Predecessors:** M1/M1b (TypeScript), M3/M3b (Python), M5 (vector), M7 (ndjson streaming), M8
(control plane), and the unified release (`2026-09-30-unified-release-design.md`). M9 (Java,
`2026-09-16-m9-java-http-driver-design.md`) is proposed in parallel; nothing here depends on it.

## 1. Scope

M10 ships the Go module `github.com/ArcadeData/arcadedb-drivers/go/arcadedb`: an HTTP client
generated from the committed OpenAPI contract, with a hand-written facade at **feature parity with
the Python HTTP driver** as of the 26.10.1 contract — data plane, transactions, M5 vector, M7
ndjson streaming, batch load, time series / Grafana / PromQL, and the M8 control plane.

It also does the one-time work of teaching this repository that it hosts Go: a `go` row in
`adopt-contract-version.sh`'s `LANGUAGES`, a Go reader in `check-licenses.py`, `ci-go.yml`, a
`goproxy` registry in `release-packages.py`, `publish-go.yml`, Dependabot `gomod` coverage, and a
third client in `contract-watch.yml`.

The gRPC client is **M10b**, for the reason M1b and M3b were separate: a smaller first review. The
layout admits `go/arcadedbgrpc/` as a sibling module with no restructuring (section 5).

## 2. Decisions

| # | Decision | Choice | Rejected |
|---|---|---|---|
| D1 | Scope | HTTP now, gRPC as M10b | Both at once; generated layers first, facades later |
| D2 | Facade | Full parity with the Python HTTP driver | Core subset first; parity minus hand-written endpoints |
| D3 | Import path | `github.com/ArcadeData/arcadedb-drivers/go/arcadedb` | Vanity `arcadedb.com/go/...` (a `go-import` page to host forever); a separate repository (breaks the single contract and lockstep release) |
| D4 | Generator | `oapi-codegen` v2 (section 4) | `ogen`; `openapi-generator` `go` |
| D5 | Go floor | 1.26; e2e on 1.27 | — |
| D6 | Lint | `gofmt`, `go vet`, `staticcheck` | `golangci-lint` (GPL-3.0) |
| D7 | Tests | stdlib `testing` + `net/http/httptest`; `testcontainers-go` for e2e | `testify` (unneeded dependency) |
| D8 | Concurrency surface | One, `context.Context`-based | A sync/async split |
| D9 | Transactions | Callback (`db.Transaction(ctx, fn)`) | A `Begin()`/`Commit()`/`Rollback()` handle |
| D10 | Publishing | A path-prefixed git tag, then a proxy fetch | — (Go has no registry to upload to) |

Inherited and not revisited: generated code is committed and drift-gated, `raw` never errors on a
non-2xx status while the facade always does, every package carries a recorded contract version, the
README compatibility tables are a human decision, and a release is lockstep through `release.yml`.

### D5: why 1.26

The Go team supports only the two newest releases (1.26 and 1.27 today), and grpc-go and most of
the ecosystem follow the same policy. 1.26 is also past 1.23 (range-over-func iterators, section 7)
and 1.24 (the `tool` directive, section 5). Unit, lint and drift gate run on 1.26; e2e on 1.27. That
is the floor-and-current split `ci.yml` and `ci-python.yml` already use. The floor moves when Go
drops 1.26 from support, as a deliberate edit to `go.mod`'s `go` line and to `ci-go.yml`.

### D6: why not golangci-lint

`golangci-lint` is the de-facto Go meta-linter and is **GPL-3.0**, which the allow-list in the root
`CLAUDE.md` forbids for development dependencies as well as runtime ones. `staticcheck` (MIT) is the
analyser golangci-lint most often runs anyway; together with `go vet` and `gofmt` it covers what
this client needs. Record this in `go/CLAUDE.md` so nobody adds golangci-lint later as a helpful
improvement, whether as a `tool` directive or as a CI action.

## 3. Go facts this design rests on

For readers new to the ecosystem. Each is load-bearing somewhere below.

- **There is no registry.** A module version *is* a git tag. `proxy.golang.org` fetches the source
  from GitHub on first request and caches it; `pkg.go.dev` indexes from the proxy.
- **Versions are permanent.** The first fetch records the module's checksum in `sum.golang.org`, a
  public append-only log. A published version can be neither deleted nor replaced — only marked
  bad by a `retract` directive in a *later* version's `go.mod`. This matches the repository's
  existing rule that a fix is a new version and a tag never moves.
- **A module in a subdirectory needs a path-prefixed tag.** A module rooted at `go/arcadedb/` is
  versioned by tags named `go/arcadedb/v<version>`; the repository-wide `v<version>` tag means
  nothing to Go.
- **`go.mod` carries no version of its own.** The version lives only in the tag, so this repository
  has to record it somewhere its release tooling can read (section 5, `version.go`).
- **v2 and later change the import path.** A module at major version 2+ must end its path in `/v2`.
  Lockstep versioning means this module reaches v2 when every other package does, and that release
  must include the path change (section 10).
- **Consumers never run a generator.** They compile exactly what is committed in the tag, which
  this repository already guarantees.

## 4. The generator, chosen on evidence

A throwaway spike ran the three candidates against the committed 26.10.1 contract (72 operations,
two of them `HEAD`).

| | oapi-codegen v2.8.0 | ogen v1.24.0 | openapi-generator `go` 7.25.0 |
|---|---|---|---|
| Operations | 72/72 | Drops `promQLQuery`, `promQLQueryRange` (complex `anyOf`); exits 1 unless told to ignore unimplemented features | 72/72 |
| Builds | After `response-type-suffix` (7 name clashes); `go vet` then fails on `"/unreadableFiles"` (section 6) | Default mode yes; client-only mode does not compile | Yes |
| Non-JSON bodies | `...WithBody(ctx, …, contentType, io.Reader)` for every operation | `io.Reader` wrappers | Mangled: batch takes one JSON line, protobuf takes `*os.File` |
| Streaming responses | Plain `Client` returns `*http.Response` | **Rejects ndjson on query, command and batch** | No ndjson; SSE decoded as one object |
| Non-2xx | A response, `err == nil` | Typed variants for declared codes | **An error** |
| Runtime deps | 3 (`oapi-codegen/runtime`, `go-jsonmerge`, `google/uuid`), all permissive | 27 (otel, zap, …) | 1 |
| Deterministic | Yes | Yes | Yes, but stamps the contract version into every file |
| Output | 1 file, ~32k lines | 20 files, ~137k lines | 157 files, ~49k lines |

`ogen` silently loses operations and streaming responses this milestone must wrap: the silent-skip
failure mode `check_codegen_skips.py` exists to catch, now on features in scope.
`openapi-generator` breaks the batch bodies and the `raw` non-2xx semantics, and its version stamp
would rewrite every generated file on every contract bump. `oapi-codegen` is the only candidate
whose raw surface — `io.Reader` in, `*http.Response` out, no error on non-2xx — reaches all 72
operations unmodified, which is why the facade needs no hand-built HTTP (section 8).

## 5. Repository layout

```
go/
├── go.work                      # workspace: arcadedb, e2e, tools (dev only; consumers never read it)
├── CLAUDE.md
├── scripts/
│   ├── generate.sh              # resolve-openapi-contract.sh → oapi-codegen → arcadedb/generated/
│   └── check-codegen-coverage.sh
├── tools/
│   └── go.mod                   # `tool` directives, exact pins: oapi-codegen, staticcheck, go-licenses, gorelease
├── e2e/
│   └── go.mod                   # testcontainers-go; imports ../arcadedb through go.work
└── arcadedb/                    # module github.com/ArcadeData/arcadedb-drivers/go/arcadedb
    ├── go.mod                   # the three generator runtime deps, nothing else
    ├── README.md  LICENSE
    ├── version.go               # const Version, const ServerVersion
    ├── server.go  database.go  transaction.go  envelope.go  errors.go  auth.go
    ├── vector.go  timeseries.go  dashboards.go  promql.go  batch.go  stream.go  admin.go
    ├── internal/unwrap/  internal/batchrows/
    └── generated/               # NEVER hand-edited
        ├── oapi-codegen.yaml
        ├── overlay.yaml
        └── client.gen.go
```

**Three modules, deliberately.** A module's `go.mod` requirements are visible to every consumer's
module graph, so test and tool dependencies kept in `arcadedb/go.mod` would reach users who never
run the tests. `e2e/` and `tools/` are therefore their own modules, and `go.work` stitches the three
together for local work and CI — the role npm workspaces and `[tool.uv.workspace]` play in the
other two languages. `go/arcadedbgrpc/` joins as a fourth module in M10b.

**`tools/go.mod` pins every tool** through Go's `tool` directive and is run as
`go tool <name>`. It is the whole reproducibility story for generation: Go has no separate
lockfile, and `go.sum` pins the exact bytes. Dependabot bumps it like any other module.

**`generated/` is a public package** named `generated`, so `srv.Raw()` can return a typed client
whose types callers can name; Go's `internal/` would hide it. The name mirrors `_generated/` and
`src/generated/` in the other languages and keeps the drift-gate paths obvious.

**`version.go`** holds two constants, because `go.mod` has no version field:
`Version` (this module's release version, written by `release-packages.py set`, also sent in
`User-Agent`) and `ServerVersion` (the contract version, written by `adopt-contract-version.sh`).
Each writer asserts it matched exactly once, as the `pyproject.toml` rewrites do.

## 6. Generation and the drift gate

`go/scripts/generate.sh` resolves the contract with `../scripts/resolve-openapi-contract.sh` and runs
`go tool oapi-codegen -config arcadedb/generated/oapi-codegen.yaml <contract>`. The config fixes:

- `package: generated`, with types, client and `ClientWithResponses` in one output file;
- `response-type-suffix`, because seven contract schemas (`LoginResponse`,
  `VectorSearchResponse`, …) collide with the generator's response wrappers under the default;
- the overlay below.

### The `"/unreadableFiles"` overlay

The contract names one property `"/unreadableFiles"` with a leading slash (line 7871 of the 26.10.1
contract, in a checksum response). oapi-codegen derives an **unexported** Go field from it, so the
value is silently dropped on decode and `go vet` fails. This is an upstream contract defect, the
third after the two `python/CLAUDE.md` records, and Go is the first client where it breaks the
build.

`generated/overlay.yaml` is an [OpenAPI Overlay](https://spec.openapis.org/overlay/latest.html)
that oapi-codegen applies at generation time, setting `x-go-name: UnreadableFiles` on that property.
It is generator configuration, not a contract edit, so it stays inside the rule that generated
output is fixed through the contract or the generator config. It carries an expiry: a unit test
fails once the committed contract no longer contains `"/unreadableFiles"`, forcing the overlay's
deletion when upstream fixes the name. The upstream issue is filed as part of this milestone.

### The gate

`ci-go.yml` regenerates and fails on any of four checks:

1. `git diff --exit-code -- go/arcadedb/generated` — a modified generated file.
2. `git status --porcelain -- go/arcadedb/generated` — an added or renamed one.
3. `check-codegen-coverage.sh` — every `operationId` in the contract has a generated client
   method. oapi-codegen skips nothing today; this is the **positive** check M9 proposes, so a
   future generator version cannot start dropping operations silently the way
   `openapi-python-client` does.
4. `go mod tidy` in each module, then `git diff --exit-code` over every `go.mod` and `go.sum` — the
   Go equivalent of lockfile drift.

The spike found oapi-codegen's output byte-identical across two runs, stamped only with the
generator version (which moves only when `tools/go.mod` does). The plan's first step re-verifies
that across macOS and Linux before the gate is trusted.

## 7. The client API

```go
srv, err := arcadedb.NewServer("http://localhost:2480",
    arcadedb.WithBasicAuth("root", "pw"), // or WithBearerToken(token)
    arcadedb.WithHTTPClient(client))      // optional
if err != nil { ... }
defer srv.Close()

db := srv.DB("mydb")

env, err := db.Query(ctx, arcadedb.SQL,
    "SELECT FROM Person WHERE age > :min", map[string]any{"min": 18})
if env.Truncated { ... }
for _, row := range env.Result { ... } // []map[string]any

err = db.Transaction(ctx, func(tx *arcadedb.Database) error {
    _, err := tx.Command(ctx, arcadedb.SQL, "INSERT INTO Person SET name = 'Ada'", nil)
    return err
})

for row, err := range db.QueryStream(ctx, arcadedb.SQL, "SELECT FROM Person", nil) { ... }
```

### Context, not two facades

Every call takes `ctx context.Context` first. It carries cancellation and deadlines, and a caller
wanting concurrency uses goroutines over the same calls, so Go needs no async twin of each method
and has none of the sync/async duplication `python/CLAUDE.md` accepts.

**Timeouts.** A client built without `WithHTTPClient` uses an `http.Client` with no timeout, which
is Go's own default and matches the other drivers (`fetch` has none; the Python driver passes
`timeout=None`). Callers bound a call with a `ctx` deadline or pass their own client. The README
states it as plainly as `python/CLAUDE.md` does.

### Errors

Errors are returned, never panicked. `*ArcadeDBError` implements `error` and carries `Status`,
`Error`, `Exception`, `Detail`, `RequestID`, `Help` and `ExceptionArgs`, transliterating
`errors.ts` and `errors.py`; callers match it with `errors.As`. `RequestID` comes from the
`X-Request-Id` response header. **Parsing an error never itself fails**: an absent, unparsable or
incomplete body yields an `*ArcadeDBError` carrying only the status, which is `parseBody`'s contract
in TypeScript and load-bearing on a failure path. `internal/unwrap` holds the one helper that turns
a generated response into its parsed body or an `*ArcadeDBError`.

**`Help`, not `Help_`.** Python spells it `help_` to avoid shadowing a builtin and to match its
generated model. Go has no such builtin and an exported field must be capitalised anyway; note the
asymmetry in `errors.go` so nobody ports the underscore.

### The query envelope

`db.Query` and `db.Command` return a hand-written struct, not the generated `QueryResponse`:

```go
type QueryEnvelope struct {
    Result    []map[string]any
    Limit     int  // -1 when the server omits it: uncapped
    Returned  int  // 0 when omitted
    Truncated bool // false when omitted
}
```

The contract gives `QueryResponse` no `required` list, so the generated model makes every field a
pointer. The defaults are those of `facade/data.ts` and `facade/data.py`, and so is the warning the
doc comment must reproduce: they are the most reassuring possible reading of "the server did not
say", they assert a completeness the server never claimed, and today's server always sending all
four is a property of the implementation, not a guarantee the type enforces. Returning the generated
model would instead hand callers a `*bool` whose `nil` is one careless dereference from a panic or
one careless default from a silent partial result.

`params` is `map[string]any`; `language` and `command` pass through to the generated request so a
contract change to either fails the build here rather than on the wire. As in both other drivers,
`Command` does not expose `CommandRequest.Limit`.

### Transactions

`db.Transaction(ctx, fn)` begins a transaction, calls `fn` with a **second** `*Database` carrying
the session id, and commits or rolls back. Only calls through that second handle join the
transaction; calls through the outer `db` auto-commit individually. This is documented on
`Transaction` identically to the other drivers.

A callback rather than a handle (D9) because Go has no `with` or try-with-resources: a
`Begin()`-returning handle depends on every caller remembering `defer tx.Rollback()`, while a
callback makes leaking a session structurally impossible. This matches `pgx.BeginFunc` and the
TypeScript driver's `transaction()`.

`begin` answers 204 with the id in the `arcadedb-session-id` response header, which oapi-codegen
exposes as a typed field on the 204 response; every other data-plane operation takes the header as a
generated `ArcadedbSessionId` parameter, so no header plumbing is hand-written.

The contract, each clause with its own unit test:

1. **`fn` returns `nil` → commit.**
2. **`fn` returns an error or panics → roll back**, then return the error or re-panic with the
   original value. If the rollback also fails, the result is a `*TxError{Err, RollbackErr}` whose
   `Unwrap()` returns **only** `Err`: `errors.As` finds the error the caller's code produced, and
   the rollback failure stays inspectable on the struct. This is Go's analogue of Python's
   `__cause__` and Java's `addSuppressed`. `errors.Join` is deliberately not used — it unwraps to
   both, so `errors.As(err, &arcadeErr)` could match the rollback's `*ArcadeDBError` instead of the
   body's error. On a panic, a failed rollback is discarded and the original panic value wins.
3. **Commit fails → best-effort rollback** (its own error discarded) so the session is not left for
   `arcadedb.server.httpTxExpireTimeout` to reap, then return the commit error.

### Streaming

`db.QueryStream` and `db.CommandStream` (M7 ndjson) return `iter.Seq2[map[string]any, error]`, Go's
range-over-func iterator. The request is issued on the first iteration, rows are decoded one line
at a time, and leaving the loop early — `break`, `return`, or an error — closes the response body.
A mid-stream error is yielded once as the final `err` and ends the iteration.

### Namespaces and `Raw`

`db.Vector()`, `db.TS()`, `db.Grafana()`, `db.PromQL()` and `srv.Admin()` group the rest of the
surface. As in the Python driver they pass generated request and response models through unaltered;
`QueryEnvelope` remains the only normalised type, and `db.Vector()` returning whole generated
responses keeps `truncated`, `count` and `scoring` attached to their rows, for the reason
`facade/vector.py` gives.

`srv.Raw()` returns `*generated.ClientWithResponses` and never errors on a non-2xx status. One Go
caveat, documented on `Raw`: oapi-codegen represents a nullable field as a pointer, so through `Raw`
`null` and absent are indistinguishable.

### Auth

`WithBasicAuth` is `base64.StdEncoding.EncodeToString([]byte(user + ":" + password))`, and
`auth.go` says in one line that Go has neither of the `btoa` hazards `auth.ts` works around, as
`auth.py` does.

## 8. Hand-written paths and the known contract defects

Every item below issues its request through a generated call; none builds HTTP by hand.

**Non-JSON request bodies** use the generated `...WithBody(ctx, …, contentType, io.Reader)`
variants:

- `db.BatchLoad(ctx, rows)` and `db.BatchLoadStream(ctx, seq)` encode vertex and edge lines through
  `internal/batchrows`, a port of `_internal/batch_rows.py` with the same line format and tests.
  The streaming form writes through an `io.Pipe`, so a large load is never buffered.
- `db.TS().Write(ctx, lines)` sends the `text/plain` line-protocol body.
- The two PromQL remote read/write routes take and return caller-supplied protobuf bytes. The
  driver does not depend on a protobuf library for them, the same scoping the Python driver chose.

**Upstream defect 1: scalars typed as `"type": "object"`** (time-series rows and bucket values,
`latest`, Grafana frame values). oapi-codegen types them as `map[string]interface{}`, and
`json.Unmarshal` of a number into a map is a hard error. `TS().Query`, `TS().Latest` and
`Grafana().Query` therefore call the plain generated `Client`, which returns `*http.Response`, and
decode the body into `map[string]any`, as `facade/timeseries.py` and `facade/dashboards.py` do.
Their doc comments carry Python's warning: do not route them back through the typed parser until the
contract's element types are fixed.

**Upstream defect 2: `POST /api/v1/server` returns `{"result": "ok"}`** where the contract declares
an array. `srv.Admin().Command` decodes the raw response itself, and the e2e fixture creates its
database the same way.

**Upstream defect 3: `"/unreadableFiles"`**, handled by the overlay in section 6.

**Verify, don't assume.** A plan step checks each item against a live server before its workaround
is written. In particular, the time-series query response is a `oneOf` that oapi-codegen models as a
lazily parsed `json.RawMessage` union, so that one path may not need bypassing at all. The plan
records the outcome in `go/CLAUDE.md` either way; if a workaround turns out unnecessary it is not
written.

## 9. CI, tests, licenses, Dependabot

### `ci-go.yml` (new)

Paths: `go/**`, `contracts/**`, `scripts/**`, `.gitignore`, and itself. Deliberately not
`buf.yaml`; M10b adds it.

- **`build`** on Go 1.26: `gofmt -l` must print nothing, `go vet ./...`, `go tool staticcheck ./...`,
  regenerate plus the four-part drift gate, then `go test -race ./...` (unit tests only, offline).
- **`e2e`** on Go 1.27, `needs: build`, `timeout-minutes: 15`: the `e2e` module against the same
  ArcadeDB image the other e2e jobs use.

### Tests

Unit tests use `httptest.Server` fakes and cover: each transaction clause including a panicking
callback and `TxError` unwrapping; envelope defaults; error parsing on absent, garbage and partial
bodies; the batch line format; a stream closing its body on early exit and yielding a mid-stream
error once; the proxy path escaping in section 10's `is-published`; and the overlay's expiry. e2e
mirrors the Python suite feature for feature.

### Licenses

`check-licenses.py` gains a Go reader. `go.mod` carries no license metadata, so the reader runs
`go tool go-licenses report` (Apache-2.0; it classifies each module's LICENSE file) over
`arcadedb/`, `e2e/` and `tools/` — runtime, test and tool dependencies alike, as the policy
requires — and maps the results through the existing `NORMALISE` map and allow-list. The spike found
every expected dependency permissive: oapi-codegen's runtime (Apache-2.0), `go-jsonmerge` (MIT),
`google/uuid` (BSD-3-Clause), `testcontainers-go` (MIT), `staticcheck` (MIT), `go-licenses`
(Apache-2.0). No new allow-list entry is anticipated; the reader's first run is what proves it.
`license-compliance.yml` adds the Go `go.mod`/`go.sum` files to its paths.

### Dependabot

One `gomod` entry, `directories: [/go/arcadedb, /go/e2e, /go/tools]`, weekly, minor and patch
grouped, like the `npm` and `uv` entries. An oapi-codegen bump lands in `tools/go.mod`, changes
generated output, and turns the drift gate red; `dependabot-auto-merge.yml`'s generated-output guard
gains `go/arcadedb/generated/` so it refuses, and a human regenerates. That is the intended path.

### `contract-watch.yml`

Stays one job. It gains Go setup, a third regenerate step, `go` in its `git status --porcelain`
paths, and a `verify-go` sibling to `verify-ts` and `verify-py`. `report-contract-watch.sh` gains
`VERIFY_GO`, which **must** feed `finding_fingerprint`: without it, a change in which clients are red
yields an identical fingerprint and the tracking issue stays silent. As when Python was added, the
first run posts one "the finding changed" comment.

### `adopt-contract-version.sh`

Gains a `go` row in `LANGUAGES`: suffixes `.go`, `.md`; skip `generated`. The `ServerVersion` rewrite
in `version.go` asserts exactly one match, and `test-contract-scripts.sh` gains a case that fails if
`Version` is rewritten. No retirement step: the generated filename carries no version.

## 10. Release and publish

### The package table

`release-packages.py` gains a `goproxy` entry in `REGISTRIES` and one row:

| Field | Value |
|---|---|
| `id` | `go-arcadedb` |
| `language` | `go` |
| `manifest` | `go/arcadedb/version.go` (read and written through the `Version` constant, exactly once) |
| `lockfile` | none — `go.sum` records no version of its own; the table learns that a lockfile is optional |
| `registry` | `goproxy` |
| `name` | `github.com/ArcadeData/arcadedb-drivers/go/arcadedb` |
| `workflow` | `publish-go.yml` |
| `package_input` | `arcadedb` |

The server version is read from `ServerVersion` and checked against the OpenAPI `info.version`.
`is-published` requests `https://proxy.golang.org/<escaped module>/@v/v<version>.info`: 200 means
published, 404 or 410 means not, anything else is an error. The proxy escapes each capital letter
as `!` plus its lowercase, so `ArcadeData` becomes `!arcade!data`; that escaping is unit-tested.

### `scripts/release/verify-go.sh`

Shared by `release.yml`'s phase 1 dry run and by `publish-go.yml`, like `verify-npm.sh` and
`verify-pypi.sh`. It checks the dispatch version against `Version` and `ServerVersion` against the
contract, runs lint, unit tests, the drift gate and a clean `go mod tidy`, and runs
`go tool gorelease` (`golang.org/x/exp`, BSD-3-Clause) to validate the module zip. A file Go's
module-zip rules reject would make the tag unfetchable, and permanently so.

### `publish-go.yml` (new)

`workflow_dispatch` only, a child of `release.yml`, with inputs `package` and `version`. It refuses
any ref but `refs/tags/v<version>`, as its siblings do. It holds `contents: write` and **no registry
secret**, because Go has no registry credential to hold. It:

1. re-runs `verify-go.sh`;
2. creates and pushes the annotated tag `go/<package>/v<version>` on the tag's commit. If that tag
   already exists on the same commit it continues; on any other commit it fails;
3. requests `GOPROXY=https://proxy.golang.org go list -m <module>@v<version>` and polls the `.info`
   URL until it answers 200. That first fetch is the publish: it records the checksum in
   `sum.golang.org` and lets `pkg.go.dev` index the version.

Being dispatched rather than called keeps its OIDC identity and its own filename, for the same
reason as the npm and PyPI children, although no trusted publisher depends on it today.

### What Go makes permanent, recorded where it bites

- The README release paragraph and `go/CLAUDE.md` state that a fetched version cannot be deleted
  or replaced; the remedy for a bad one is a `retract` directive in the next version.
- The tag ruleset still outstanding before 0.2.0 must protect `go/**` tags from deletion and forced
  moves as well as `v*`.
- **v2.** When the lockstep version reaches 2.0.0, this module's path must become `.../go/arcadedb/v2`
  in the same release, and every import in the README and examples with it. `release-packages.py
  check` refuses a `>= 2.0.0` version while the module path lacks the matching `/vN` suffix, so the
  requirement cannot be forgotten.

### First version

The Go module joins the lockstep at the next release rather than shipping alone. `set` writes its
version with every other package's, and `check` refuses any disagreement.

## 11. Documentation

- `go/CLAUDE.md`: commands, the three-module layout, generation and the overlay, the deliberate
  asymmetries (`Help` vs `help_`, callback transactions, `TxError` vs `errors.Join`, no sync/async
  split, no golangci-lint), and the three contract defects.
- `go/arcadedb/README.md`: usage, the timeout warning, `Raw`'s null/absent caveat, the compatibility
  table, and the release paragraph with its permanence warning.
- Root `CLAUDE.md`: `go/` in the opening list, `ci-go.yml` and `publish-go.yml` in Workflows, the
  `goproxy` registry, and the third contract defect.
- Root `README.md`: the Go package in the package list.

## 12. Out of scope

- The gRPC client (M10b).
- An API-compatibility gate. `gorelease` could enforce one, but at v0 nothing is promised; enabling
  it is a decision for 1.0.
- A vanity import path (D3).
- Fixing the three contract defects upstream. This milestone files the `/unreadableFiles` issue and
  works around all three; fixing them belongs to arcadedb.
