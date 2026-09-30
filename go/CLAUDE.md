# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Scope: the Go workspace. See the repository root `CLAUDE.md` for the contract pipeline, the drift
gate, and the release workflows that govern this directory.

## Commands

The scripts run from any directory. The `go test` lines run from the module directory named in
the comment.

```bash
./scripts/generate.sh          # regenerate arcadedb/generated/client.gen.go from contracts/
./scripts/lint.sh              # gofmt -l, go vet, staticcheck over every module in go.work
./scripts/check-drift.sh       # the four-part drift gate (regenerates first; needs a git checkout)

go test -race ./...            # in arcadedb/: unit tests only, offline, no Docker
go test ./...                  # in e2e/: end-to-end tests against a real ArcadeDB container (Docker required)

go test -run '^TestStream' ./...                     # in arcadedb/: tests whose name matches a regexp
go test -count=1 -run '^TestOverlayStillNeeded$' .   # in arcadedb/: one test, bypassing the test cache
ARCADEDB_DOCKER_IMAGE=arcadedata/arcadedb:<tag> go test ./...   # in e2e/: against another image
```

`-run` takes a regular expression matched against the test function name, unanchored: `-run
Stream` also matches `TestBatchStreamInBandError`. Anchor it with `^...$` to run one test. Go
caches passing test results and replays them when nothing it can see has changed; the contract
tests below read `contracts/` from disk through `os.ReadFile`, which the cache does track, but
`-count=1` is the habit that rules the question out, and `check-drift.sh` uses it.

The e2e suite starts one container per `go test` run (`TestMain` in `e2e/main_test.go`) from
`arcadedata/arcadedb:<the contract's version>`, a literal `adopt-contract-version.sh` rewrites,
and creates one uniquely named database per test. `ARCADEDB_DOCKER_IMAGE` overrides the image;
`contract-watch.yml` uses it to run the suite against the SNAPSHOT it just fetched.

## Layout: three modules, deliberately

```
go/
├── go.work          # stitches the three modules together; consumers never read it
├── scripts/         # generate.sh, lint.sh, check-drift.sh
├── tools/           # module .../go/tools: `tool` directives, plus cmd/checkzip
├── e2e/             # module .../go/e2e: testcontainers-go, replace ../arcadedb
└── arcadedb/        # module github.com/ArcadeData/arcadedb-drivers/go/arcadedb, the published one
    ├── *.go         # the hand-written facade
    ├── internal/batchrows/  internal/ndjson/
    └── generated/   # oapi-codegen.yaml, overlay.yaml, client.gen.go - NEVER hand-edited
```

A module's `go.mod` requirements reach every consumer's module graph, so a test or tool
dependency declared in `arcadedb/go.mod` would be downloaded and version-resolved by users who
never run the tests. `arcadedb/go.mod` therefore requires only the generator's three runtime
dependencies (`oapi-codegen/runtime`, `go-jsonmerge`, `google/uuid`); `testcontainers-go` lives in
`e2e/go.mod`, and oapi-codegen, staticcheck and go-licenses live in `tools/go.mod`. `go.work` plays
the role npm workspaces and `[tool.uv.workspace]` play in the other two languages. It is a
development file only: a consumer's build never reads it, which is why `e2e/go.mod` also carries
its own `replace` pointing at `../arcadedb`.

Every tool is pinned by a `tool` directive in `tools/go.mod` and run as `go tool <name>` from any
module in the workspace. There is no separate lockfile: `go.sum` pins the exact bytes. **Never add
golangci-lint** - see "Deliberate asymmetries" below.

The `go` line differs by module and that is not an oversight: `arcadedb/go.mod` and `e2e/go.mod`
say `go 1.26`, the declared floor, while `tools/go.mod` and `go.work` say `go 1.26.0`, because a
pinned tool dependency requires it and `go mod tidy` writes the patch-level form. CI runs unit,
lint and drift gate on Go 1.26 and e2e on 1.27, the floor-and-current split `ci.yml` and
`ci-python.yml` use.

`generated/` is a public package (named `generated`), not `internal/`, so `Server.Raw()` can return
a typed client whose types callers can name. `internal/batchrows` (the GraphBatch line encoder, a
port of the Python driver's `_internal/batch_rows.py`) and `internal/ndjson` (the `\n`-only line
splitter) are internal because nothing outside the module should build on either.

`version.go` holds two constants because `go.mod` has no version field: `Version`, this module's
release version, written by `scripts/release-packages.py set` and sent as `User-Agent:
arcadedb-go/<Version>`; and `ServerVersion`, the contract's version, written by
`scripts/adopt-contract-version.sh`. Each writer asserts it matched exactly one line. Edit neither
by hand.

## Generation

`scripts/generate.sh` resolves the contract with `../scripts/resolve-openapi-contract.sh` and runs
`go tool oapi-codegen -config oapi-codegen.yaml <contract>` from `arcadedb/generated/`, then `go mod
tidy` in `arcadedb/`. `oapi-codegen.yaml` asks for models and client in one file and sets
`response-type-suffix: Resp`, because seven contract schemas (`LoginResponse`,
`VectorSearchResponse`, ...) collide with the generator's own response wrappers under the default
naming. **`generated/` is never hand-edited**: fix the config or the overlay instead.

`generated/overlay.yaml` is an [OpenAPI Overlay](https://spec.openapis.org/overlay/latest.html)
oapi-codegen applies at generation time. It sets `x-go-name: UnreadableFiles` on the one contract
property named `"/unreadableFiles"` (third item under "Three contract quirks" below). It is
generator configuration, not a contract edit, so it stays inside the rule that generated output is
fixed through the contract or the generator config. It carries an expiry test:
`TestOverlayStillNeeded` fails the moment the committed contract no longer contains
`"/unreadableFiles"`, and the fix then is to delete `overlay.yaml` and the `overlay` key in
`oapi-codegen.yaml`, not to quiet the test.

oapi-codegen generates every operation, but a future version could drop one it cannot model and
still exit 0, the failure mode `python/scripts/check_codegen_skips.py` exists for. The Go check is
positive rather than an allowlist of skips: `TestEveryOperationIsGenerated` (`contract_test.go`)
reads every `operationId` from the contract and asserts by reflection that `*generated.Client` has
a method `<Name>` or `<Name>WithBody`. The four operations with no JSON request body (batch, time
series write, PromQL remote read and write) are generated as `<Name>WithBody` only, taking an
`io.Reader`. The test **skips** when it cannot find `contracts/`, so the drift gate runs it
explicitly and requires a literal `--- PASS`: a skip there is a failure.

`scripts/check-drift.sh` is the gate `ci-go.yml`, `scripts/release/verify-go.sh` and a developer all
run, in four parts: (1) regenerate and `git diff --exit-code` the generated directory; (2) `git
status --porcelain` it, which catches an added or renamed file `git diff` is blind to; (3)
`TestEveryOperationIsGenerated`, pass required; (4) `go mod tidy` in every module `go.work` uses
(`arcadedb/`, `e2e/`, `tools/`, read from `go list -m` rather than listed), then fail on any `go.mod`/`go.sum` diff or untracked `go.sum`. There is no fifth "skipped endpoints"
check, and there should not be one: part 3 already covers what that check would.

A third contract test, `TestServerVersionMatchesContract`, holds `ServerVersion` to the contract's
`info.version`.

## Deliberate asymmetries

- **The facade errors; `Raw()` does not, for a non-2xx status.** Every facade method returns an
  `*ArcadeDBError` for a non-2xx response. `Server.Raw()` returns the generated
  `*generated.ClientWithResponses`, whose methods return a response and a nil error for any status
  the server answered with; the caller inspects `HTTPResponse.StatusCode`. Do not blur it.
- **`ErrorMessage`, not `Error`.** Go forbids a field and a method with the same name, and
  `Error()` is what makes `*ArcadeDBError` an `error`, so the body's `error` string lands in
  `ErrorMessage`. `Error()` returns `ErrorMessage`, else `Detail`, else a generic message naming the
  status.
- **`Help`, not `help_`.** Python spells it `help_` to avoid shadowing a builtin and to match its
  generated model. Go has neither reason; do not port the underscore. `ExceptionArgs` is a plain
  `string` despite its plural name, because the contract types it that way; it is passed through,
  not parsed.
- **Parsing an error never fails.** An absent, non-JSON or partial body yields an `*ArcadeDBError`
  carrying `Status` and whatever parsed; `RequestID` comes from the `X-Request-Id` header and falls
  back to the body's `requestId`. The one helper that turns a response into this is the unexported
  `checkResponse` in `errors.go`.
- **A 2xx body is decoded even when the generated parser skipped it.** oapi-codegen fills `JSON200`
  only when the status is exactly 200 and the `Content-Type` contains `json`. Every facade method
  falls back to `decodeBody` (`errors.go`) when `JSON200` is nil, so a JSON body behind a proxy that
  rewrites the type, or a 203, is not lost. An empty or `null` body means `[]` for `ListDatabases`,
  `false` for `Exists`, and the one exported sentinel `ErrEmptyBody` for anything that returns a
  pointer or a map - never `(nil, nil)`, which would read as a successful empty answer. The shared
  helpers (`isSuccess`, `nonEmpty`, `readChecked`, `decodeMap`, `decodeBody`) all live in
  `errors.go`; do not grow a per-file sentinel again.
- **Transactions are a callback, not a handle.** `db.Transaction(ctx, fn)` begins, calls `fn` with
  a SECOND `*Database` carrying the session id, and commits or rolls back. Go has no `with` or
  try-with-resources, so a `Begin()`-returning handle depends on every caller remembering `defer
  tx.Rollback()`; a callback makes leaking a session structurally impossible. The three-clause
  contract is spelled out below.
- **`TxError`, not `errors.Join`.** When `fn` fails and the rollback also fails, the result is
  `*TxError{Err, RollbackErr}` whose `Unwrap` returns **only** `Err`. `errors.Join` would unwrap to
  both, so `errors.As(err, &arcadeErr)` could match the rollback's `*ArcadeDBError` instead of the
  one the caller's own code produced. This is Go's analogue of Python's `__cause__`.
- **A nested transaction is refused, not silently independent.** Beginning a transaction sends the
  receiver's session id, so `tx.Transaction(...)` called on the handle `fn` received carries its
  session and the server answers 409. The Python driver never sends it on begin.
- **One concurrency surface.** Every call takes `ctx context.Context` first; a caller who wants
  concurrency uses goroutines over the same calls. There is no async twin and none of the
  sync/async duplication `python/CLAUDE.md` accepts.
- **No timeout by default.** `NewServer` without `WithHTTPClient` uses a bare `&http.Client{}`,
  which has no timeout - Go's own default, and parity with `fetch` and the Python driver's
  `timeout=None`. Bound a call with a `ctx` deadline, or pass a client with a `Timeout`. Do not
  "fix" this with a facade default: `Raw()` shares the same client, and the two would then disagree.
- **`Raw()` cannot tell `null` from absent.** oapi-codegen represents an optional or nullable field
  as a pointer, so through `Raw()` a `null` and a missing key both decode to `nil`. A field the
  contract marks required is a plain value, and an omitted one reads as its zero value.
- **Streams skip what they do not understand.** `QueryStream`/`CommandStream` return
  `iter.Seq2[StreamEvent, error]`; each `StreamEvent` has exactly one of `Record` or `Stats` set.
  An event of an unknown kind, and `"record": null`, are **skipped**, where the Python driver yields
  an empty event. An in-band `{"error": ...}` event is yielded once as an `*ArcadeDBError` with
  status 200 and the response's `X-Request-Id`, and ends the iteration. A stats trailer with no `limit` reads as `-1`. A non-EOF read
  error drops the partial line rather than decoding it, so a cancelled context surfaces as an error
  `errors.Is(err, context.Canceled)` matches, not as a bogus decode error. There is no line-length
  limit (`bufio.Scanner` would fail past 64 KiB).
- **A property that shadows a batch control key is refused.** `BatchLoad`/`BatchLoadStream` reject
  a row whose `Properties` contain `@type`, `@class`, `@id`, `@from` or `@to` with an error wrapping
  `ErrPropertyShadowsControlKey`. The Python and TypeScript drivers let such a property silently
  override the control key, which can turn a vertex into an edge. Rows are validated as they are
  encoded, so the upload aborts at the bad row, which is never sent - but earlier rows may already
  be committed, because a load is not atomic.
- **Batch input is streamed from the caller's sequences.** The vertex and edge `iter.Seq`s are
  consumed on a writer goroutine feeding an `io.Pipe`; the call always stops and waits for that
  goroutine before returning, so no sequence is iterated after the call returns. A panic in a
  sequence is recovered on that goroutine (where it would otherwise kill the process), aborts the
  upload, and is re-raised with its original value on the caller's goroutine by `upload.stop`.
  `BatchLoadStream` returns an iterator that issues the request on every range, so ranging over it
  twice runs the load twice: treat it as single-use.
- **A batch load refuses a transaction handle.** The batch endpoint takes no session id, so
  `BatchLoad`/`BatchLoadStream` on the handle `Transaction` passes to `fn` would silently commit
  outside the transaction. Both refuse with the exported `ErrBatchInTransaction` before any request
  is sent (the stream yields it once).
- **Numbers in rows are `float64`.** Rows are `map[string]any` decoded with `encoding/json`, so an
  integer above 2^53 loses precision - the same as the TypeScript driver. `json.Number` is not used,
  because it would make every numeric field a string-backed type callers must convert.
- **Vector responses are returned whole.** `db.Vector()`'s methods return the generated response,
  never unwrapped to `Results`, to keep `Truncated`, `Count` and `Scoring` attached to their hits.
  `Truncated` is a plain `bool` in the generated model, so a response that omitted it would read
  `false`; `vector.go`'s doc comment says why that is only as good as the server's promise.
- **No golangci-lint.** It is the de-facto Go meta-linter and it is **GPL-3.0**, which the
  allow-list in the root `CLAUDE.md` forbids for development tools as well as runtime
  dependencies. `gofmt`, `go vet` and `staticcheck` (MIT, and the analyser golangci-lint most often
  runs anyway) cover what this client needs. Do not add it as a `tool` directive or as a CI action.

## The transaction contract

`Transaction` (`transaction.go`) has three clauses, each with its own test in
`transaction_test.go`:

1. **`fn` returns nil → commit.**
2. **`fn` returns an error or panics → roll back**, then return the error or re-panic with the
   original value. A failed rollback after an error yields `*TxError` (above); after a panic it is
   discarded and the original panic value wins. `runtime.Goexit` inside `fn` (`t.FailNow` in a
   test) rolls back and lets the goroutine keep exiting; it is never mistaken for a nil return.
   `panic(nil)` re-panics as `*runtime.PanicNilError`; under `GODEBUG=panicnil=1` it recovers as
   `nil`, indistinguishable from `Goexit`, so that branch sets the named result to a non-nil error
   - a nil return there would read as committed.
3. **The commit fails → best-effort rollback** (its own error discarded) so the session is not left
   for `arcadedb.server.httpTxExpireTimeout` to reap, then the commit's error is returned.

Both rollbacks run under `context.WithoutCancel(ctx)`: the commonest reason `fn` fails is that
`ctx` was cancelled or timed out, and a rollback bound to that `ctx` would never reach the server.
Preserve all of this exactly; it is repeated on `Transaction`'s doc comment for the same reason.

## Three contract quirks, and what each costs Go

Each item below was checked against a live 26.10.1-SNAPSHOT server before its workaround was
written, and each looks like a bug in this client until you know the cause is upstream.

1. **The time-series and Grafana responses.** `TS().Query`, `TS().Latest` and `Grafana().Query`
   call the plain generated `Client` and decode the body into `map[string]any` themselves; do not
   route them back through the `...WithResponse` methods. For `TS().Query` the bypass is forced:
   the raw/aggregated `oneOf` has no discriminator, the generated union's `AsTimeSeriesRawResponse`
   and `AsTimeSeriesAggregatedResponse` both "succeed" on either payload, and the typed raw model
   has no `limit` or `truncated`, so the typed parse discards the one flag that says the rows are a
   partial answer. The Python client's worse failure - scalars typed `"type": "object"` raising
   `TypeError` in the generated models - does **not** bite Go: the generator emits `interface{}`
   for those elements. `TS().Latest` and `Grafana().Query` would parse fine typed, and return
   `map[string]any` anyway so the whole family hands back one shape with nothing dropped or
   defaulted, as in the Python driver.
2. **`POST /api/v1/server` returns `{"result": "ok"}`**, a string, where the contract declares
   `QueryResponse` with an array `result`. The typed `ExecuteServerCommandWithResponse` does not
   crash on it, which is worse: it reports `Limit`, `Returned` and `Truncated` as zero values the
   wire never carried (the contract marks them required, so they are plain fields), beside a
   `Result` union holding a string that neither of its row shapes describes. No facade method
   wraps the endpoint. `e2e/main_test.go` creates its databases through the plain
   `ExecuteServerCommandWithBody` and checks the status itself, for exactly this reason.
3. **A property named `"/unreadableFiles"`** in the 200 body of `GET
   /api/v1/ha/snapshot/{database}/checksums`. This one is not an inaccuracy: the server really sends
   that key, and the slash is deliberate upstream (the body is a flat map keyed by file name, and a
   file name can never contain a path separator, so the key cannot collide with one). But
   oapi-codegen derives an **unexported** Go field from it, so the value is silently dropped on
   decode and `go vet` fails; Go is the first client where it breaks the build. The overlay above
   names it `UnreadableFiles`. A draft upstream issue asks whether the key can be spelled some other
   collision-proof way; until the contract changes, the overlay stays and `TestOverlayStillNeeded`
   passes.

One live finding that is not a defect but trips every newcomer: the PromQL metric for a time-series
type is the **type name itself** (`GoTsPoint`), not `<type>_value`.

## Releasing

The module joins the lockstep release through `release-packages.py`'s `go-arcadedb` row (registry
`goproxy`, workflow `publish-go.yml`); see the root `CLAUDE.md`. Go has no registry: a version is the
git tag `go/arcadedb/v<version>`, which `publish-go.yml` pushes beside the repository-wide
`v<version>`, and the first fetch through `proxy.golang.org` is the publish.

**A fetched version is permanent.** `sum.golang.org` records its checksum in a public append-only
log, and the proxy never forgets it: a published version can be neither deleted nor replaced, and
moving or deleting the tag afterwards only breaks anyone who fetches around the proxy. The only
remedy for a bad version is a `retract` directive in `go.mod`, shipped in the **next** version. That
is why `verify-go.sh` checks the module zip (`tools/cmd/checkzip`, built on
`golang.org/x/mod/zip.CheckDir`) before any tag exists: a file the module-zip rules reject would
make the version unfetchable, forever.

**v2 changes the import path.** When the lockstep version reaches 2.0.0, this module's path must
become `.../go/arcadedb/v2` in the same release, with every import in the README. `release-packages.py
check` and `checkzip` both refuse a `>= 2.0.0` version on a path without the matching `/vN`.

The repository's tag ruleset, still outstanding, must protect `go/**` tags from deletion and forced
moves as well as `v*`, and must let the Actions bot push them.

## Prose conventions

The root `CLAUDE.md`'s note on prose conventions applies here too: the package README and the doc
comments document failure modes and deliberate asymmetries at length (why `Truncated` matters, why
`Exists` cannot prove absence, why `TxError` does not use `errors.Join`, why the time-series family
bypasses the typed parser). When you change behaviour in one of those areas, update the prose with
it.
