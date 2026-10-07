# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Scope: the Go workspace. See the repository root `CLAUDE.md` for the contract pipeline, the drift
gate, and the release workflows that govern this directory.

## Commands

The scripts run from any directory. The `go test` lines run from the module directory named in
the comment.

```bash
./scripts/generate.sh          # regenerate arcadedb/generated/client.gen.go from the OpenAPI contract
./scripts/generate-grpc.sh     # regenerate arcadedbgrpc/generated/*.pb.go from the .proto contract
./scripts/lint.sh              # gofmt -l, go vet, staticcheck over every module in go.work
./scripts/check-drift.sh       # the four-part drift gate over both generated trees (regenerates first; needs a git checkout)

go test -race ./...            # in arcadedb/: the HTTP client's unit tests, offline, no Docker
go test -race ./...            # in arcadedbgrpc/: the gRPC client's unit tests, in-memory (bufconn), no Docker
go test ./...                  # in e2e/: end-to-end tests for both clients against real ArcadeDB containers (Docker required)

go test -run '^TestStream' ./...                     # in arcadedb/: tests whose name matches a regexp
go test -count=1 -run '^TestOverlayStillNeeded$' .   # in arcadedb/: one test, bypassing the test cache
go test -run '^TestGrpc' ./...                       # in e2e/: the gRPC tests only (both containers still start)
ARCADEDB_DOCKER_IMAGE=arcadedata/arcadedb:<tag> go test ./...   # in e2e/: against another image
```

`-run` takes a regular expression matched against the test function name, unanchored: `-run
Stream` also matches `TestBatchStreamInBandError`. Anchor it with `^...$` to run one test. Go
caches passing test results and replays them when nothing it can see has changed; the contract
tests below read `contracts/` from disk through `os.ReadFile`, which the cache does track, but
`-count=1` is the habit that rules the question out, and `check-drift.sh` uses it.

The e2e suite starts two containers per `go test` run (`TestMain` in `e2e/main_test.go`), both
from `arcadedata/arcadedb:<the contract's version>`, a literal `adopt-contract-version.sh`
rewrites: one for the HTTP tests and one with the gRPC plugin enabled for the `TestGrpc...` tests
(`e2e/grpc_main_test.go`, below). It creates one uniquely named database per test.
`ARCADEDB_DOCKER_IMAGE` overrides the image of both; `contract-watch.yml` uses it to run the
suite against the SNAPSHOT it just fetched. Either container failing to start fails the whole
run, so a gRPC plugin that will not come up reddens the HTTP tests too; once both are up, the
two suites share nothing.

## Layout: four modules, deliberately

```
go/
├── go.work          # stitches the four modules together; consumers never read it
├── scripts/         # generate.sh, generate-grpc.sh, lint.sh, check-drift.sh
├── tools/           # module .../go/tools: `tool` directives, plus cmd/checkzip
├── e2e/             # module .../go/e2e: testcontainers-go, replace ../arcadedb and ../arcadedbgrpc
├── arcadedb/        # module github.com/ArcadeData/arcadedb-drivers/go/arcadedb, published (HTTP)
│   ├── *.go         # the hand-written facade
│   ├── internal/batchrows/  internal/ndjson/
│   └── generated/   # oapi-codegen.yaml, overlay.yaml, client.gen.go - NEVER hand-edited
└── arcadedbgrpc/    # module github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc, published (gRPC)
    ├── *.go         # the hand-written facade: client, auth, streams, transaction
    └── generated/   # buf.gen.yaml, arcadedb_server.pb.go, arcadedb_server_grpc.pb.go - NEVER hand-edited
```

A module's `go.mod` requirements reach every consumer's module graph, so a test or tool
dependency declared in `arcadedb/go.mod` would be downloaded and version-resolved by users who
never run the tests. `arcadedb/go.mod` therefore requires only the generator's three runtime
dependencies (`oapi-codegen/runtime`, `go-jsonmerge`, `google/uuid`); `testcontainers-go` lives in
`e2e/go.mod`, and oapi-codegen, buf, the two protoc plugins, staticcheck and go-licenses live in
`tools/go.mod`. The same rule holds for `arcadedbgrpc/go.mod`, which requires only
`google.golang.org/grpc` and `google.golang.org/protobuf` (plus what those two pull in). The two
published modules never import each other and share no dependency: an HTTP-only user never
downloads grpc-go, and a gRPC-only user never downloads the oapi-codegen runtime. `go.work` plays
the role npm workspaces and `[tool.uv.workspace]` play in the other two languages. It is a
development file only: a consumer's build never reads it, which is why `e2e/go.mod` also carries
its own `replace` lines pointing at `../arcadedb` and `../arcadedbgrpc`.

Every tool is pinned by a `tool` directive in `tools/go.mod` and run as `go tool <name>` from any
module in the workspace. There is no separate lockfile: `go.sum` pins the exact bytes. **Never add
golangci-lint** - see "Deliberate asymmetries" below.

The `go` line differs by module and that is not an oversight: `arcadedb/go.mod`,
`arcadedbgrpc/go.mod` and `e2e/go.mod` say `go 1.26`, the declared floor, while `tools/go.mod`
says `go 1.26.7`, because buf v1.73.0 requires that patch release in the module that runs it, and
`go.work` says the same because it must be at least every module's `go` line. A consumer of either
published module never sees the `1.26.7`. So the effective CI floor is **1.26.7** for anything run
inside the workspace, while consumers still need only 1.26. Every `setup-go` step that runs the
floor reads `go-version-file: go/go.work` rather than a literal `"1.26"`: a bare `"1.26"` without
`check-latest` lets `setup-go` pick an older 1.26.x the runner has cached, which fails outright under
`GOTOOLCHAIN=local` and silently downloads 1.26.7 otherwise. CI runs unit, lint and drift gate on
that floor and e2e on 1.27, the floor-and-current split `ci.yml` and `ci-python.yml` use.

**Never run `go work sync`.** It pushes the workspace's resolved versions down into every module's
`go.mod`, which bumps `arcadedbgrpc`'s `go` line to `1.26.7` (raising the floor every consumer sees)
and raises the published modules' dependency versions to whatever the tools module needs. Tidy each
module with `go mod tidy` instead, which is what the drift gate's part 4 runs.

`generated/` is a public package (named `generated`), not `internal/`, so `Server.Raw()` can return
a typed client whose types callers can name. `internal/batchrows` (the GraphBatch line encoder, a
port of the Python driver's `_internal/batch_rows.py`) and `internal/ndjson` (the `\n`-only line
splitter) are internal because nothing outside the module should build on either.

`version.go` holds two constants because `go.mod` has no version field: `Version`, this module's
release version, written by `scripts/release-packages.py set` and sent as `User-Agent:
arcadedb-go/<Version>`; and `ServerVersion`, the contract's version, written by
`scripts/adopt-contract-version.sh`. Each writer asserts it matched exactly one line. Edit neither
by hand. `arcadedbgrpc/version.go` has the same two constants on the same two separate top-level
lines (never a `const` block, which neither writer's pattern matches), so both writers needed no
change for it. Its `Version` is not sent on the wire: the gRPC client sets no user agent of its
own. Its `ServerVersion` is the version in the `.proto` contract's **filename**, which is the only
place the `.proto` records one; never the OpenAPI `info.version`.

## Generation

This section is the HTTP module's; the gRPC module's generation is under "The gRPC module" below,
and the drift gate described at the end of this section covers both.

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
run, in four parts, each over **both** generated trees (`arcadedb/generated` and
`arcadedbgrpc/generated`): (1) run both generators and `git diff --exit-code` the generated
directories; (2) `git status --porcelain` them, which catches an added or renamed file `git diff`
is blind to; (3) `TestEveryOperationIsGenerated` and `TestEveryRPCIsGenerated` (below), each with
a literal `--- PASS` required; (4) `go mod tidy` in every module `go.work` uses (`arcadedb/`,
`arcadedbgrpc/`, `e2e/`, `tools/`, read from `go list -m` rather than listed), then fail on any
`go.mod`/`go.sum` diff or untracked `go.sum`. There is no fifth "skipped endpoints" check, and
there should not be one: part 3 already covers what that check would.

A third contract test, `TestServerVersionMatchesContract`, holds `ServerVersion` to the contract's
`info.version`.

Everything above runs **inside** `go.work`, which resolves the highest version of each dependency
across all four modules, `tools/` included, so a published `go.mod` that pins something too low
passes there. A consumer's build never reads `go.work`. `ci-go.yml`'s build job and `verify-go.sh`
therefore also build, vet and test `arcadedb/` and `arcadedbgrpc/` with `GOWORK=off`, against each
module's own `go.mod` alone. The case it was added for: a `tools/` bump of protoc-gen-go-grpc whose
output needs a newer grpc than `arcadedbgrpc/go.mod` declares (v1.6 emits
`grpc.SupportPackageIsVersion9` and the generic stream types, so grpc < v1.64 fails to compile)
builds fine in the workspace, which resolves `tools/`' grpc v1.84, and fails only here. It is not a
complete generator-versus-runtime check: protobuf's `protoimpl.EnforceVersion` only rejects a
runtime older than v1.20, so a protoc-gen-go a few minors ahead of the declared protobuf runtime
still compiles unless the generated code calls an API that runtime lacks.

## Deliberate asymmetries

These are the HTTP module's, except the last, which binds the whole workspace. The gRPC module's
are under "The gRPC module" below.

- **The facade errors; `Raw()` does not, for a non-2xx status.** Every facade method returns an
  `*ArcadeDBError` for a non-2xx response, with one deliberate exception: `Ready` answers a 503 (up,
  but not ready) with `(false, nil)`, because "not ready" is the answer it exists to give.
  `Server.Raw()` returns the generated `*generated.ClientWithResponses`, whose methods return a
  response and a nil error for any status the server answered with; the caller inspects
  `HTTPResponse.StatusCode`. Do not blur it.
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
  back to the body's `requestId`. The one parser is the unexported `newError` in `errors.go`;
  `checkResponse` (buffered bodies) and `errorFromResponse` (streams and batch, which read the body
  themselves) both call it, so every non-2xx status is parsed the same way. The errors with no
  error body to parse - in-band stream and batch errors, a begin with no session id, an
  unrepresentable graph-serializer result - are built directly.
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
  `iter.Seq2[StreamEvent, error]`; each `StreamEvent` has exactly one of `Record` or `Stats` set. An
  event of an unknown kind, and `"record": null`, are **skipped**, where the Python driver yields an
  empty event. An in-band `{"error": ...}` event is yielded once as an `*ArcadeDBError` with status
  200 and the response's `X-Request-Id`, and ends the iteration. A stats trailer with no `limit`
  reads as `-1`. A non-EOF read error drops the partial line rather than decoding it, so a cancelled
  context surfaces as an error `errors.Is(err, context.Canceled)` matches, not as a bogus decode
  error. There is no line-length limit (`bufio.Scanner` would fail past 64 KiB).
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
   for `arcadedb.server.httpSessionExpireTimeout` to reap, then the commit's error is returned.

Both rollbacks run under `context.WithoutCancel(ctx)`: the commonest reason `fn` fails is that
`ctx` was cancelled or timed out, and a rollback bound to that `ctx` would never reach the server.
Preserve all of this exactly; it is repeated on `Transaction`'s doc comment for the same reason.

## Three contract quirks, and what each costs Go

Each item below was checked against a live 26.10.1 server before its workaround was
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

## The gRPC module: `arcadedbgrpc`

A port of the Python gRPC driver (`arcadedb-driver-grpc`), at parity with it: client construction
with auth and two security guards, the four streaming RPCs the generated stub handles badly
(`StreamQuery`, `TimeSeriesQuery`, `InsertStream`, `TimeSeriesWriteStream`), and `Transaction`
with a handle that binds the transaction onto every request. Everything else, all 44
`ArcadeDbAdminService` RPCs included, is reached through `Raw()` and `RawAdmin()`, the generated
clients. The design is `docs/superpowers/specs/2026-10-01-m10b-go-grpc-driver-design.md`.

### Generation: a fixed staging name, and buf as a tool

`scripts/generate-grpc.sh` resolves the contract with `../scripts/resolve-proto-contract.sh`,
copies it into a `mktemp` directory as `arcadedb_server.proto` beside a three-line buf v2
`buf.yaml`, runs `go tool buf generate` on that directory with `arcadedbgrpc/generated/buf.gen.yaml`
as the template, and then runs `go mod tidy` in `arcadedbgrpc/`. The template turns managed mode
on to supply `go_package` (`.../go/arcadedbgrpc/generated`), because the contract carries none and
`protoc-gen-go` refuses to generate without one; the contract itself is never edited. Both plugins
are local commands (`["go", "tool", "protoc-gen-go"]`, `["go", "tool", "protoc-gen-go-grpc"]`) with
`paths=source_relative`. The repository-root `buf.yaml` is **not** read: the staged directory has
its own.

The fixed name is the point. The contract's filename carries the server version, and generating
from it directly would stamp that version into `arcadedb_server.pb.go` and
`arcadedb_server_grpc.pb.go`, as TypeScript's `_pb.ts` is stamped. Unstamped, a contract bump
rewrites the two files in place: nothing to retire, no import to repoint, and
`adopt-contract-version.sh` needed no change beyond what its `go/*/version.go` glob already did.
The only stamps in the output are the two plugin versions in each file header, which move only
when `tools/go.mod` does; buf's own version is not stamped. So a Dependabot bump of either plugin
turns the drift gate red and stops for a human, which is intended.

`go tool` must run with its working directory inside a module, so buf runs from `tools/`, where it
and both plugins are pinned (buf `v1.73.0`, `protoc-gen-go` `v1.36.12`, `protoc-gen-go-grpc`
`v1.6.2`), and every path handed to it is absolute. A pinned protoc binary was rejected: `go.mod`
cannot pin it and the license gate cannot see it.

Two things buf brought into `tools/go.mod`, both tools-only and never reaching a consumer:

- **A `replace` for `google.golang.org/genproto`.** go-licenses pulls in the 2020 monolithic
  `genproto` module, which also contains the googleapis packages buf imports, so those imports
  become ambiguous with the split `genproto/googleapis/*` modules. A `go get` pin or an `exclude`
  does not survive `go mod tidy`; the `replace` does. Revisit it whenever buf or go-licenses is
  bumped: if the ambiguity is gone, drop it.
- **MIT-0.** buf's dependency `github.com/segmentio/asm` is MIT-0, which the root `CLAUDE.md`
  allow-list now names. go-licenses reports it as `Unknown`, so `scripts/check-licenses.py` carries
  `_GO_LICENSE_OVERRIDES = {"github.com/segmentio/asm": "MIT-0"}`, applied only to an exact
  `Unknown` for exactly that owning module; any other `Unknown`, or a different license for that
  module, stays a violation. The Go collector's plausibility floor, `_MIN_PLAUSIBLE_GO_MODULES`, is
  64, half the 129 modules measured once buf's 86 joined.

### Why part 3 of the drift gate exists here

The Python gRPC gate has no third part, because `protoc` fails loudly rather than skipping what it
cannot generate. Go keeps one anyway: `TestEveryRPCIsGenerated` (`arcadedbgrpc/contract_test.go`)
parses every `rpc` out of the contract, with `//` and `/* */` comments stripped first so a
commented-out RPC or a stray brace cannot count, and asserts by reflection that the generated
`ArcadeDbServiceClient` and `ArcadeDbAdminServiceClient` interfaces have a method for each. It is
cheap, it is symmetrical with the HTTP module's `TestEveryOperationIsGenerated`, and it guards
against something real even without a silent skip: an RPC vanishing through a plugin or
managed-mode change. It also pins the counts, 21 data-plane and 44 admin RPCs, so a contract that
grows an RPC fails it until someone updates the count on purpose and decides whether the new RPC
needs facade support. Like its HTTP sibling it skips when it cannot find `contracts/`, and
`check-drift.sh` reads a skip as a failure. `TestServerVersionMatchesProto` holds `ServerVersion`
to the `.proto` filename.

### Construction, auth, and the two guards

- **`NewClient` takes grpc-go's target form, not a URL.** `"host:port"`, `"[::1]:port"`,
  `dns:///`, `passthrough:///` and `unix:` targets are accepted; a target starting
  (case-insensitively, after trimming space) with `http://` or `https://` is refused, because
  grpc-go would read the scheme as an unknown resolver. Like `grpc.NewClient`, it performs no I/O.
  An empty user in `WithPasswordAuth` or an empty token in `WithBearerToken` is an error from
  `NewClient`.
- **Auth is a pair of interceptors, not `grpc.PerRPCCredentials`.** One unary and one stream
  interceptor, chained onto the connection, so every call through `Raw()` and `RawAdmin()` is
  authenticated as well as the facade's. grpc-go splits interceptors by call shape, and installing
  only one would leave whole shapes anonymous, which is the defect Python's async client once
  shipped; `TestAuthMetadataOnEveryCallShape` drives all four shapes. The metadata is
  **appended** (`metadata.AppendToOutgoingContext`), never replacing what the caller set.
  `PerRPCCredentials` is out because grpc-go refuses to send it over a connection without
  transport security, and password auth with `WithInsecure` is a supported configuration.
- **Credential order is a security property.** `grpc.WithTransportCredentials` is last-wins.
  `NewClient` puts the implicit plaintext default (`insecure.NewCredentials()`) **before** the
  caller's `WithDialOptions` and an explicit `WithTransportCredentials` **after** them, so TLS a
  caller passed inside `WithDialOptions` is honoured and never silently downgraded to plaintext
  (`TestDialOptionTLSIsNeverDowngraded`). The guards below cannot see credentials inside
  `WithDialOptions`, so they fail closed in that case: password auth and `RawAdmin` still demand
  `WithTransportCredentials` or `WithInsecure`. The README tells users to pass TLS through
  `WithTransportCredentials`; keep it that way.
- **Guard one, ArcadeData/arcadedb#5048.** `WithPasswordAuth` without `WithTransportCredentials`
  and without `WithInsecure` is `ErrInsecureChannel` from `NewClient`: the password would cross
  the wire as cleartext metadata. A bearer token over plaintext is allowed.
- **Guard two, `RawAdmin`.** `RawAdmin() (generated.ArcadeDbAdminServiceClient, error)` returns
  `ErrInsecureChannel` unless the client has `WithTransportCredentials` or `WithInsecure`, whatever
  auth is configured. 42 of the 44 admin RPCs authenticate from a `DatabaseCredentials` field in
  the request **body**, which guard one cannot see; the guard covers `Health` and `Ready` too,
  because carving out two RPCs would mean wrapping the other 42. It returns an error rather than
  panicking, or refusing in `NewClient`, because a refusal is recoverable and a plaintext client
  must keep working for the data plane. (Python raises when its `raw_admin` property is read.)
  `WithInsecure` is the single explicit opt-in that satisfies both guards.
- **Errors are grpc-go status errors, unwrapped.** Callers use `status.Code(err)`. There is no
  envelope to normalise, so there is no package error type, which is the same reason the Python
  client raises `grpc.RpcError` and the TypeScript one throws `ConnectError`. The facade's own
  refusals are `ErrInsecureChannel`, `ErrNoTransactionID`, `ErrNotCommitted` and `*TxError`, plus
  plain errors for a malformed option, a URL target and a missing `Precision`.
- **`Close` is safe twice.** The first call returns `grpc.ClientConn.Close`'s error; later calls
  return nil rather than grpc-go's "the client connection is closing".

### Streams

`StreamQuery` yields records, flattening the `QueryResult` batches; `TimeSeriesQuery` yields whole
messages, because `Truncated` is meaningful only on the message with `Last` set, where it says the
request's `limit` cut the answer short. Both are lazy: nothing is sent until the first iteration,
and each range issues a new RPC. Each derives a cancellable context that is cancelled on every exit
(exhaustion, error, `break`), so leaving the loop stops the server stream. `io.EOF` ends iteration;
any other error is yielded once, unwrapped, and ends it. The shared machinery is `recvAll` in
`stream.go`; `TxHandle` reuses the same two helpers.

### Client streams: the caller's goroutine, and the `Send` trap

`InsertStream` and `TimeSeriesWriteStream` iterate the caller's `iter.Seq` **on the caller's own
goroutine**, because grpc-go's client-stream `Send` runs there too. There is no `io.Pipe` and no
writer goroutine, so the hazards `BatchLoad` engineers around above (a panic on a library
goroutine, a writer outliving the call) cannot arise: a panic in the sequence surfaces from the
call itself (`TestInsertStreamSeqPanicStaysOnCaller`). The flip side is that cancelling `ctx`
cannot interrupt a sequence blocked producing its next batch; the wrapper regains control only
when the sequence yields, so a sequence that waits on I/O must watch `ctx` itself.

**The `Send`/`RecvMsg` trap.** When the server has already ended the stream, grpc-go's `Send`
returns a bare `io.EOF` and puts the real status on the receive side. Both wrappers therefore
answer a `Send` `io.EOF` with `CloseAndRecv`'s result (`failedSend` in `insert.go`); returning the
`Send` error would hide every server-side failure behind `EOF`. Two consequences: a failed `Send`
never surfaces as `io.EOF`, and a server that ends early with `SendAndClose` makes the call return
its summary with a **nil** error. The summary, not the nil error, says how many rows landed.

`InsertStream` ports Python's envelope exactly: one `session_id` per call (16 `crypto/rand` bytes,
hex), `chunk_seq` 1..n, `Database` on chunk 1 only as the `.proto` specifies, the caller's
`Options` on every chunk as given (`options.database` is never set: servers before 26.9.1, outside
the compatibility table, read the database only from it (ArcadeData/arcadedb#6597) and answer a
chunk-only database with rows received, `inserted=0` and no error, so the stream silently inserts
nothing against them; 0.2.0 mirrored `Database` into it, 0.3.0 retired the mirror and the
`proto.Clone`), `Credentials` and `Transaction` on every chunk, and
`last=true` only on the final chunk, found by `iter.Pull` lookahead so a `nil` or empty batch in
the middle is a zero-row chunk, not the end. An empty input sends one empty chunk with `last=true`.
The generated chunk's row field is `Rows`.

`TimeSeriesWriteStream` repeats `Database`, `Type`, `Precision` and `Credentials` on every chunk
(the message has no session, sequence or last field) and sends **zero** chunks for an empty input.
**`Precision` is a `*generated.TimeSeriesPrecision`**, and nil is an error before any RPC. A
pointer because the enum has no `UNSPECIFIED`: its zero value is `TS_PRECISION_MILLISECONDS`, a
real unit, so a plain field could not tell "unset" from "milliseconds", and HTTP line protocol's
omitted precision means nanoseconds, a factor of 10^6 away. Making the field required is Python's
choice; the pointer is how Go spells "required" for an enum without a sentinel value. The raw
unary `TimeSeriesWrite` has the same zero value and no such protection.

### Transactions and `TxHandle`

`Transaction(ctx, database, fn func(*TxHandle) error)` follows "The transaction contract" above
clause for clause (named result, `returned` flag, `WithoutCancel` rollbacks, `*TxError` unwrapping
only `Err`, the original panic value re-raised, nil panic and `Goexit` never read as a commit), plus
two clauses from Python: a blank `transaction_id` from `BeginTransaction` is `ErrNoTransactionID`
before `fn` runs, and a commit answering `committed=false` with no error status (how the server
answers for a transaction it already reaped: `success=true, committed=false`) is `ErrNotCommitted`
carrying the server's message, with no rollback since nothing is left to roll back. The check reads
`committed`, never `success`.

`TxHandle` has the ten unary data-plane methods (`ExecuteQuery`, `ExecuteCommand`, `CreateRecord`,
`UpdateRecord`, `DeleteRecord`, `LookupByRid`, `VectorSearch`, `HybridSearch`, `FullTextSearch`,
`TimeSeriesLatest`) plus bound `StreamQuery`, `TimeSeriesQuery` and `InsertStream`. Each
`proto.Clone`s the request (`InsertStream` copies its by-value `InsertStreamRequest` instead)
and assigns `r.Database, r.Transaction = h.binding()`: `Database` forced, and the whole
`Transaction` field **replaced** by a fresh `TransactionContext{TransactionId, Database}`, so
caller-set inline `begin`/`commit`/`rollback` flags are wiped, not merged. Three properties to
preserve:

- **Clone, never mutate.** Binding the caller's message in place would leave it carrying a dead
  transaction id after `Transaction` returns, and reusing it would send that id:
  ArcadeData/arcadedb#5040 recreated by aliasing (`TestTxHandleNeverMutatesCallerRequest`).
- **Typed assignment, not protoreflect.** If a regenerated contract renamed or dropped `Database`
  or `Transaction` on a bound type, the build fails instead of a call being sent unbound.
- **A request's own `Credentials` pass through unbound**; which principal may act is the server's
  business.

`TxHandle.InsertStream` reuses `Client.InsertStream`'s envelope (the shared `insertStream`) on a
by-value copy of the `InsertStreamRequest` with `Database, Transaction = h.binding()`, so every
chunk carries the handle's context and the caller's struct is untouched
(`TestTxHandleInsertStreamBindsEveryChunk`). Servers before 26.9.1, outside the compatibility table,
ignored the transaction on `InsertStream` (ArcadeData/arcadedb#6607), so rows would survive a
rollback there; `e2e`'s `TestGrpcTxInsertStreamCommitAndRollback` pins both outcomes live.
`TimeSeriesWriteStream` is absent from the handle: `TimeSeriesWriteChunk` has no transaction field
at all. `BulkInsert` and `GraphBatchLoad` stay raw-only. A handle used after
`Transaction` returns is refused by the server with `FailedPrecondition` ("Unknown or expired
transaction id"), measured live by `e2e`'s `TestGrpcHandleAfterCommitIsRefused`; the client does
not track handle liveness itself.

### Tests

Unit tests use `google.golang.org/grpc/test/bufconn` and small fake servers embedding the
generated `Unimplemented...Server` types (`fake_test.go`): no network, no Docker, no extra
dependency. The e2e tests (`e2e/grpc_test.go`, thirteen of them, mirroring `python/e2e/test_grpc.py`)
run against the second container `e2e/grpc_main_test.go` starts: the same image with
`JAVA_OPTS="-Darcadedb.server.rootPassword=playwithdata -Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin"`,
ports 2480 and 50051, ready on `/api/v1/ready` 204 and then on the log line
`gRPC server started on 0.0.0.0:50051`. Two facts there look like a broken plugin until you know
them: the plugin is off by default, so without the property nothing listens on 50051; and a root
password shorter than eight characters stops the whole server, so 50051 merely looks closed. Schema
and the bearer token are made over HTTP on the same container.

## Releasing

Both modules join the lockstep release through `release-packages.py`, as the `go-arcadedb` and
`go-arcadedbgrpc` rows (registry `goproxy`, workflow `publish-go.yml`, package input `arcadedb` or
`arcadedbgrpc`); see the root `CLAUDE.md`. Each Go row carries a `contract` key, `"openapi"` or
`"proto"`, so `check` holds its `ServerVersion` to the one contract it is generated from, where the
npm and PyPI rows are held to both. Go has no registry: a version is the git tag
`go/<package>/v<version>` (`go/arcadedb/v<version>`, `go/arcadedbgrpc/v<version>`), which
`publish-go.yml` pushes beside the repository-wide `v<version>`, and the first fetch through
`proxy.golang.org` is the publish. `verify-go.sh <package>` checks `ServerVersion` against that
same contract (the OpenAPI `info.version`, or the `.proto` filename), so a bump of one contract
never blocks the other module's publish.

**A fetched version is permanent.** `sum.golang.org` records its checksum in a public append-only
log, and the proxy never forgets it: a published version can be neither deleted nor replaced, and
moving or deleting the tag afterwards only breaks anyone who fetches around the proxy. The only
remedy for a bad version is a `retract` directive in `go.mod`, shipped in the **next** version. That
is why `verify-go.sh` checks the module zip (`tools/cmd/checkzip`, built on
`golang.org/x/mod/zip.CheckDir`) before any tag exists: a file the module-zip rules reject would
make the version unfetchable, forever. `checkzip` takes the files a module cannot work without as
arguments (`go.mod`, `LICENSE`, `version.go` and the generated code: `client.gen.go` for one,
the two `.pb.go` files for the other), so each module is checked for its own.

**v2 changes the import path.** When the lockstep version reaches 2.0.0, each module's path must
become `.../go/arcadedb/v2` and `.../go/arcadedbgrpc/v2` in the same release, with every import in
both READMEs (and `generated/buf.gen.yaml`'s `go_package` override, which names the import path).
`release-packages.py check` and `checkzip` both refuse a `>= 2.0.0` version on a path without the
matching `/vN`.

The repository's tag ruleset, still outstanding, must protect `go/**` tags from deletion and forced
moves as well as `v*`, and must let the Actions bot push them.

## Prose conventions

The root `CLAUDE.md`'s note on prose conventions applies here too: both package READMEs and the doc
comments document failure modes and deliberate asymmetries at length (why `Truncated` matters, why
`Exists` cannot prove absence, why `TxError` does not use `errors.Join`, why the time-series family
bypasses the typed parser, why `RawAdmin` refuses a plaintext connection, why `Precision` is a
pointer, why a failed `Send` returns `CloseAndRecv`'s status). When you change behaviour in one of
those areas, update the prose with it.
