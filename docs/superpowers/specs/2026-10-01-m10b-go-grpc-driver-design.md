# M10b: `arcadedbgrpc` for Go, the gRPC client

**Status:** implemented (plan: `docs/superpowers/plans/2026-10-01-m10b-go-grpc-driver.md`); this spec is updated where the build
departed from it
**Date:** 2026-10-01
**Parent:** ArcadeData/arcadedb Epic #4894
**Predecessors:** M10 (`2026-09-30-m10-go-http-driver-design.md`, merged as #85), whose repository
machinery this milestone extends; M3b (`2026-09-04-m3b-python-grpc-driver-design.md`), whose facade
this one ports; M1b (TypeScript gRPC).

## 1. Scope

M10b ships the Go module `github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc`: a gRPC client
generated from the committed `.proto` contract, with a hand-written facade at **parity with the
Python gRPC driver** (`arcadedb-driver-grpc`). That facade is thin by design: client construction
with auth and two security guards, the four streaming RPCs that the generated stub handles badly
(`StreamQuery`, `InsertStream`, `TimeSeriesQuery`, `TimeSeriesWriteStream`), and a transaction whose
handle binds the transaction onto every request. Everything else, including all 44
`ArcadeDbAdminService` RPCs, is reached through the generated stubs.

It extends, rather than builds, the Go machinery M10 introduced: the drift gate, lint, e2e, the
license collector, the `goproxy` release row, `publish-go.yml`, Dependabot, the auto-merge guard and
contract watch each gain a row, a branch or a path.

## 2. Decisions

| # | Decision | Choice | Rejected |
|---|---|---|---|
| D1 | Facade scope | Parity with the Python gRPC driver | Wrapping the admin RPCs; a richer data-plane facade |
| D2 | gRPC library | `google.golang.org/grpc` (grpc-go) | connect-go (non-idiomatic for a grpc-java server; plaintext needs hand-built h2c transport) |
| D3 | Codegen | `protoc-gen-go` + `protoc-gen-go-grpc`, driven by `buf` run as a pinned `go tool` | A pinned `protoc` binary (unpinnable in `go.mod`, invisible to the license gate); an in-repo protocompile driver (code to own for a policy-only problem) |
| D4 | Module | Separate module `go/arcadedbgrpc`, no dependency on `go/arcadedb` | One module for both clients (HTTP users would download grpc-go) |
| D5 | Generated filenames | Unstamped: the contract is staged as `arcadedb_server.proto` | Version-stamped like TypeScript's `_pb.ts` (a retirement step and import repointing on every bump) |
| D6 | Errors | grpc-go status errors pass through unwrapped | A package error type (parity with Python's `grpc.RpcError` and TypeScript's `ConnectError`) |
| D7 | License | `MIT-0` added to the allow-list | Excluding tool dependencies from the gate |

### D3: what the probe established

A throwaway probe against the committed 26.10.1-SNAPSHOT contract found:

- `buf` v1.73.0, `protoc-gen-go` v1.36.12 and `protoc-gen-go-grpc` v1.6.2 generate
  `arcadedb_server.pb.go` and `arcadedb_server_grpc.pb.go` that build and vet clean.
- Output is byte-identical across two macOS runs and a Linux (`golang:1.26`) run. The only stamps
  are the two plugin versions, which move only when `go/tools/go.mod` does; buf's own version is
  not stamped.
- The runtime footprint of the compiled module is 7 modules: grpc, protobuf, `x/net`, `x/sys`,
  `x/text`, `genproto/googleapis/rpc` — all Apache-2.0 or BSD-3-Clause.
- buf requires `go 1.26.7` in the module that runs it. That is `go/tools` only; consumers of
  `go/arcadedbgrpc` see `go 1.26`.
- buf adds 86 modules to `go/tools`. One, `github.com/segmentio/asm`, is licensed **MIT-0** (MIT
  No Attribution), which go-licenses reports as Unknown and the allow-list does not name. D7.
- `go tool` must run with a working directory inside a module, so generation runs from `go/tools`
  (or the workspace) and passes the staged module and template by path.
- *(Found during the build.)* go-licenses pulls in the 2020 monolithic `google.golang.org/genproto`,
  which also contains the googleapis packages buf imports, making those imports ambiguous with the
  split `genproto/googleapis/*` modules. A `go get` pin or an `exclude` does not survive
  `go mod tidy`, so `go/tools/go.mod` carries a commented `replace google.golang.org/genproto => ...`.
  It is tools-only and is to be revisited whenever buf or go-licenses is bumped.
- *(Found during the build.)* `go work sync` must not be run: it pushes the workspace's resolved
  versions into every module and bumps `go/arcadedbgrpc`'s `go` line to `1.26.7`.

### D7: MIT-0

MIT-0 is the MIT license without its attribution clause, strictly more permissive than MIT, which is
allowed. It enters `ALLOWED_IDS` in `scripts/check-licenses.py` and the root `CLAUDE.md` license
section together, with the evidence recorded the way the existing additions are: one module,
`segmentio/asm`, reached only through the `buf` tool, never shipped. ArcadeDB's own `CLAUDE.md` is
expected to agree with this list; the matching line is drafted for a human to commit there.

go-licenses does not classify MIT-0 and reports `segmentio/asm` as `Unknown`, so a `NORMALISE`
spelling cannot fix it. `check-licenses.py` gains a narrow per-module override
(`github.com/segmentio/asm` → `MIT-0`) applied only when go-licenses says `Unknown` for exactly that
module; any other `Unknown`, or a different license reported for that module, stays a violation.

## 3. Repository layout

```
go/
├── go.work                      # gains ./arcadedbgrpc
├── scripts/
│   ├── generate-grpc.sh         # resolve-proto-contract.sh → stage → go tool buf generate
│   └── check-drift.sh           # both generated trees
├── tools/go.mod                 # go 1.26.7; + buf, protoc-gen-go, protoc-gen-go-grpc (exact pins)
├── e2e/                         # + grpc_*_test.go, second container
└── arcadedbgrpc/                # module github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc
    ├── go.mod                   # go 1.26; google.golang.org/grpc, google.golang.org/protobuf
    ├── README.md  LICENSE
    ├── version.go               # const Version, const ServerVersion (two top-level lines)
    ├── client.go  auth.go  errors.go
    ├── stream.go  insert.go  transaction.go
    └── generated/               # NEVER hand-edited
        ├── buf.gen.yaml
        ├── arcadedb_server.pb.go
        └── arcadedb_server_grpc.pb.go
```

The module neither imports `go/arcadedb` nor shares a dependency with it: an HTTP-only user never
downloads grpc-go, and the reverse holds. `version.go` follows the M10 convention exactly (two
separate top-level `const` lines), so `release-packages.py set` and `adopt-contract-version.sh`
rewrite it with the regexes they already have.

## 4. Generation and the drift gate

`go/scripts/generate-grpc.sh`:

1. resolves the single `.proto` with `scripts/resolve-proto-contract.sh`;
2. copies it to a staging directory as `arcadedb_server.proto`, beside a minimal buf v2 `buf.yaml`;
3. runs `go tool buf generate` with `generated/buf.gen.yaml`: managed mode overrides `go_package` to
   `github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated`; the two plugins are local
   commands resolved through the tools module (`["go", "tool", "protoc-gen-go"]`,
   `["go", "tool", "protoc-gen-go-grpc"]`); `paths=source_relative`;
4. runs `go mod tidy` in `go/arcadedbgrpc`.

Staging under a fixed name is the same choice the Python generator made, for the reason that
matters here: the generated filenames carry no version, so a contract bump modifies files in place
and needs no retirement step and no import repointing. The contract file in `contracts/` is never
edited; managed mode supplies the missing `go_package`.

`check-drift.sh` keeps its four parts and runs them over both generated trees:

1. `git diff --exit-code` over `go/arcadedbgrpc/generated`;
2. no untracked files there;
3. `TestEveryRPCIsGenerated` passes — it reads every `rpc` from the contract (with `//` and
   `/* */` comments stripped first, so a commented-out RPC or a stray brace cannot count) and
   asserts, by reflection over the generated `ArcadeDbServiceClient` and
   `ArcadeDbAdminServiceClient` interfaces, that each has a method. It also pins the counts (21
   and 44), so a contract that grows an RPC fails it until the count is updated deliberately. A
   skip fails the gate;
4. `go mod tidy` is clean in every workspace module (already the case since M10's final fix wave).

Part 3 deliberately departs from the Python gRPC gate, which has no third part because `protoc`
fails loudly rather than skipping. The check is kept here for symmetry with the HTTP module's
`TestEveryOperationIsGenerated` and because it is cheap; it guards against an RPC disappearing
through a generator or managed-mode change rather than against a silent skip.

`ServerVersion` is verified against the version in the `.proto` **filename** (as
`verify-pypi.sh`'s `driver-grpc` branch does), never the OpenAPI `info.version`: each package is
checked against the contract it is generated from.

## 5. The client API

```go
c, err := arcadedbgrpc.NewClient("localhost:50051",
    arcadedbgrpc.WithPasswordAuth("root", "pw", "mydb"), // or WithBearerToken(token)
    arcadedbgrpc.WithInsecure())                          // or WithTransportCredentials(creds)
if err != nil { ... }
defer c.Close()

res, err := c.Raw().ExecuteQuery(ctx, &generated.ExecuteQueryRequest{...})
admin, err := c.RawAdmin()

for rec, err := range c.StreamQuery(ctx, req) { ... }
for msg, err := range c.TimeSeriesQuery(ctx, req) { ... }
sum, err := c.InsertStream(ctx, arcadedbgrpc.InsertStreamRequest{Database: "mydb", Chunks: seq})
sum, err := c.TimeSeriesWriteStream(ctx, arcadedbgrpc.TimeSeriesWriteStreamRequest{...})

err = c.Transaction(ctx, "mydb", func(tx *arcadedbgrpc.TxHandle) error {
    _, err := tx.ExecuteCommand(ctx, &generated.ExecuteCommandRequest{...})
    return err
})
```

`NewClient(target string, opts ...Option) (*Client, error)` takes grpc-go's native `host:port`
target form, as Python does. Options: `WithPasswordAuth(user, password, database string)` (database
may be empty), `WithBearerToken(token)`, `WithTransportCredentials(credentials.TransportCredentials)`,
`WithInsecure()`, and `WithDialOptions(...grpc.DialOption)` for anything else. Without transport
credentials the connection uses `insecure.NewCredentials()`. `Close()` closes the connection and is
safe to call twice; the first call returns the real error, later ones nil. There is no default
timeout; callers bound calls with `ctx`, as with the HTTP client.

As built, three refinements:

- A target starting (case-insensitively, after trimming space) with `http://` or `https://` is
  refused: grpc-go would read the scheme as an unknown resolver. `host:port`, `[::1]:port`,
  `dns:///`, `passthrough:///` and `unix:` targets are accepted.
- An empty user in `WithPasswordAuth` or an empty token in `WithBearerToken` is an error from
  `NewClient`.
- **Credential order.** `grpc.WithTransportCredentials` is last-wins, so the implicit plaintext
  default is applied **before** the caller's `WithDialOptions` and an explicit
  `WithTransportCredentials` **after** them. TLS passed only inside `WithDialOptions` is therefore
  honoured, never downgraded; but the guards below cannot see it and fail closed (password auth
  and `RawAdmin` still need `WithTransportCredentials` or `WithInsecure`). The documented way to
  pass TLS is `WithTransportCredentials`. An earlier draft appended the default after the caller's
  options, which silently replaced their TLS with plaintext; that was fixed during review.

### Auth

A unary and a stream client interceptor are installed on the connection, so every call through
`Raw()` and `RawAdmin()` is authenticated too. Password auth sends `x-arcade-user`,
`x-arcade-password`, and `x-arcade-database` when non-empty; bearer auth sends
`authorization: Bearer <token>`. Both **append** to the outgoing metadata
(`metadata.AppendToOutgoingContext`) and never replace what the caller set. grpc-go splits
interceptors by call shape, which is exactly where Python's async client once left streaming RPCs
unauthenticated; one test covers all four shapes (unary, server-stream, client-stream, bidi).
`grpc.PerRPCCredentials` is not used, because grpc-go refuses to send it over an insecure connection
unless the credentials opt out — the same reason Python avoids `metadata_call_credentials`.

### The two guards

- **#5048.** `NewClient` returns `ErrInsecureChannel` when password auth would cross a connection
  without transport credentials and `WithInsecure()` was not given. Bearer tokens over plaintext are
  allowed.
- **Admin.** `RawAdmin() (generated.ArcadeDbAdminServiceClient, error)` returns `ErrInsecureChannel`
  unless the client has transport credentials or `WithInsecure()`. The guard is unconditional on
  auth, because 42 of the 44 admin RPCs carry `DatabaseCredentials` in the request body, where the
  #5048 check cannot see; it covers Health and Ready too, because carving out two RPCs would mean
  wrapping the other 42. Python raises when the property is read; Go returns an error, its idiom for
  a recoverable refusal.

`WithInsecure()` is the single explicit opt-in that satisfies both guards; supplying transport
credentials satisfies both as well.

### Errors

RPC failures are returned as grpc-go status errors, unwrapped: callers use `status.Code(err)` and
`status.FromError(err)`. There is no envelope to normalise, which is the reason Python passes
`grpc.RpcError` through and TypeScript passes `ConnectError` through. The facade's own errors are
`ErrInsecureChannel`, `ErrNoTransactionID`, `ErrNotCommitted` and `*TxError`.

### Streams

- `StreamQuery(ctx, *generated.StreamQueryRequest) iter.Seq2[*generated.GrpcRecord, error]` yields
  one record at a time across the `QueryResult` batches. `RetrievalMode` and `BatchSize` pass through
  untouched.
- `TimeSeriesQuery(ctx, *generated.TimeSeriesQueryRequest) iter.Seq2[*generated.TimeSeriesQueryResult, error]`
  yields whole messages, because `Truncated` is only meaningful on the message with `Last` set,
  where it is set when the request's `limit` cut the answer short, distinguishing "ended" from
  "cut off".

Both derive a cancellable context, so leaving the loop early (`break`, `return`, an error) cancels
the RPC and releases the stream. `io.EOF` ends iteration normally; any other error is yielded once
and ends it. Each range issues a new RPC: the iterators are single-use in practice, and the doc
comments say so.

### Client streams

grpc-go's client-stream `Send` runs on the caller's goroutine, so both methods iterate the caller's
`iter.Seq` directly — no `io.Pipe`, no background writer. The batch-load hazards M10 had to engineer
around (a panic on a library goroutine, a writer outliving the call) cannot arise.

- `InsertStream(ctx, InsertStreamRequest) (*generated.InsertSummary, error)` with
  `InsertStreamRequest{Database string; Chunks iter.Seq[[]*generated.GrpcRecord]; Options *generated.InsertOptions; Credentials *generated.DatabaseCredentials; Transaction *generated.TransactionContext}`
  ports Python's envelope: one random `session_id` per stream (16 `crypto/rand` bytes, hex);
  `chunk_seq` 1..n; chunk 1 carries `database` and a `proto.Clone` of the options with
  `options.database` forced, while later chunks carry the caller's options as given (Python
  parity); `credentials` and `transaction` on every chunk; `last=true` only on the final chunk,
  found by `iter.Pull` lookahead, so a `nil` or empty batch is a zero-row chunk, not the end; an
  empty input sends one empty chunk with `last=true` and `chunk_seq=1`. The generated chunk's row
  field is `Rows`. Returns the server's summary unchanged.
- `TimeSeriesWriteStream(ctx, TimeSeriesWriteStreamRequest) (*generated.TimeSeriesWriteSummary, error)`
  repeats `database`, `type`, `precision` and `credentials` on every chunk. `Precision` is required —
  an unset precision is an error before any RPC — because the proto's zero value (milliseconds)
  silently disagrees with HTTP line protocol's default (nanoseconds). It is a
  `*generated.TimeSeriesPrecision`, nil meaning unset: the enum has no `UNSPECIFIED` value, so a
  plain field could not tell "unset" from `TS_PRECISION_MILLISECONDS`. Empty input sends zero
  chunks. Writes are non-atomic; `Written < Received` is possible on success.

When `Send` fails with `io.EOF`, both return the result of `CloseAndRecv`: grpc-go reports a
failed `Send` as a bare `io.EOF` and puts the real status on the receive side. Returning the `Send`
error would hide every server-side failure behind `EOF`. Two consequences the docs state: a server
that ends the stream early with `SendAndClose` makes the call return its summary with a nil error,
so the summary, not the nil error, says how many rows landed; and because the caller's sequence
runs on the caller's goroutine, cancelling `ctx` cannot interrupt a sequence blocked producing its
next batch (a sequence that waits should watch `ctx` itself).

### Transactions

`(*Client).Transaction(ctx, database string, fn func(tx *TxHandle) error) error` begins with
`BeginTransaction` (a blank `transaction_id` is `ErrNoTransactionID`, before `fn` runs), then follows
the Go HTTP client's contract clause for clause:

1. `fn` returns `nil` → `CommitTransaction`.
2. `fn` returns an error or panics → `RollbackTransaction`, then the error is returned or the panic
   re-raised with its original value. A rollback failure on top of an error yields `*TxError{Err,
   RollbackErr}`, whose `Unwrap` returns only `Err`. A nil panic or `runtime.Goexit` rolls back and
   returns a sentinel error, never `nil`.
3. Commit fails → best-effort rollback, then the commit's error.

Rollbacks run on `context.WithoutCancel(ctx)`. Python's fourth clause is ported: a commit answering
`committed=false` — a transaction the server already reaped answers `success=true, committed=false`
— returns `ErrNotCommitted` carrying the server's message. The check reads `committed`, not
`success`.

`TxHandle` exposes `ExecuteQuery`, `ExecuteCommand`, `CreateRecord`, `UpdateRecord`, `DeleteRecord`,
`LookupByRid`, `VectorSearch`, `HybridSearch`, `FullTextSearch` and `TimeSeriesLatest` (unary, each
taking `(ctx, req, ...grpc.CallOption)`), plus bound `StreamQuery` and `TimeSeriesQuery`. Every call
`proto.Clone`s the request, overwrites `Database`, and **replaces** the whole `Transaction` field with
`TransactionContext{TransactionId, Database}` — a replace, never a merge, so caller-set inline
`begin`/`commit`/`rollback` flags are wiped. The caller's message is never mutated: binding in place
would let a later reuse of the same message carry a dead transaction id, recreating
ArcadeData/arcadedb#5040 by aliasing. The binding is plain typed assignment
(`r.Database, r.Transaction = h.binding()`), not protoreflect, so a regenerated contract that
renamed either field breaks the build instead of sending a call unbound. A request's own
`Credentials` field passes through unbound. A handle used after `Transaction` returns is refused by
the server with `FailedPrecondition` ("Unknown or expired transaction id"), verified live in e2e.

`InsertStream` and `TimeSeriesWriteStream` are absent from the handle, as in Python: the first
pending ArcadeData/arcadedb-drivers#46 (the server fix, ArcadeData/arcadedb#6607, shipped in
26.9.1), the second because `TimeSeriesWriteChunk` has no transaction field.

## 6. Testing

**Unit tests** use `google.golang.org/grpc/test/bufconn`, an in-memory listener shipped with
grpc-go, and small fake servers embedding the generated `Unimplemented…Server` types. No network, no
Docker, no new dependency. They cover:

- auth metadata on all four call shapes, appended not replaced;
- both guards, including `RawAdmin` with credentials and with `WithInsecure`;
- `TxHandle`: the caller's message unchanged, `Database` and `Transaction` forced, inline flags wiped;
- every transaction clause, `committed=false`, a blank transaction id, nil panic;
- the `InsertStream` envelope (constant `session_id`, `chunk_seq` 1..n, `last` only on the final
  chunk, empty stream, `nil` batch, options mirror) and `TimeSeriesWriteStream` (required precision,
  empty input);
- early `break` cancelling the server stream;
- a failed `Send` surfacing the server's status, not `io.EOF`;
- `TestEveryRPCIsGenerated` and `TestServerVersionMatchesProto`.

**e2e** tests live in the existing `go/e2e` module, against a second container: the same image with
`JAVA_OPTS="-Darcadedb.server.rootPassword=playwithdata -Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin"`
(the plugin is off by default; a root password under eight characters kills the server so 50051
merely looks closed), ports 2480 and 50051, ready on HTTP then on the log line
`gRPC server started on 0.0.0.0:50051`. Schema is created over HTTP. The tests mirror
`python/e2e/test_grpc.py` one for one: password and bearer auth (a token minted over HTTP login),
stream query, insert stream (and an empty one), commit, rollback, vector / hybrid / full-text search
raw and through `TxHandle`, and time-series write-stream, query and latest — asserting real values.
As built there are twelve, adding to that list a handle used after commit (refused with
`FailedPrecondition`), an empty time-series write stream, and `RawAdmin().Health` with
`WithInsecure`. The gRPC container is started by the same `TestMain` as the HTTP one, so either
failing to start fails the whole run.

## 7. CI, licenses, release, Dependabot

- **`ci-go.yml`:** paths gain root `buf.yaml` (M10 left it out until a Go module reads the proto).
  As built it is a precaution only: `generate-grpc.sh` stages its own minimal `buf.yaml` and never
  reads the root one.
  The build job runs `lint.sh`, `check-drift.sh` and `go test -race` in each module; the e2e job runs
  both containers' tests.
- **License gate:** `MIT-0` in `ALLOWED_IDS` and the root `CLAUDE.md` together (D7); `collect_go`
  gains the `arcadedbgrpc` module; `_MIN_PLAUSIBLE_GO_MODULES` moves to half the new measured count
  (64 of 129).
- **`release-packages.py`:** a second `goproxy` row — id `go-arcadedbgrpc`, manifest
  `go/arcadedbgrpc/version.go`, name `github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc`,
  workflow `publish-go.yml`, package input `arcadedbgrpc`, no lockfile. Its server version is checked
  against the `.proto` filename version, so rows learn per-row contract selection: an optional
  `contract` key (`"openapi"` on `go-arcadedb`, `"proto"` on `go-arcadedbgrpc`). The npm and PyPI
  rows carry no key and stay checked against both contracts. (An earlier draft said
  `pypi-driver-grpc` already had per-row selection in `release-packages.py`; it does not —
  that split lives in `verify-pypi.sh`.)
- **`verify-go.sh` and `publish-go.yml`:** the `package` choice and the script's `case` gain
  `arcadedbgrpc`; that branch compares `ServerVersion` to the proto filename; `checkzip` takes the
  module's required files as arguments instead of hard-coding `generated/client.gen.go`. The tag is
  `go/arcadedbgrpc/v<version>`. Go publishing stays one parameterised workflow, as npm's and PyPI's
  each are.
- **Dependabot:** the `gomod` entry's `directories` gains `/go/arcadedbgrpc`. A plugin bump in
  `go/tools` changes the generated headers, turns the drift gate red, and stops for a human —
  intended.
- **Auto-merge guard:** `GUARDED` gains `go/arcadedbgrpc/generated/`.
- **Contract watch:** `Regenerate` gains `go/scripts/generate-grpc.sh`; `verify_go` runs the new
  module's unit tests and its e2e tests. `REFRESH_PATHS` already includes `go`.
- **`adopt-contract-version.sh`:** no change — its `go/*/version.go` glob already rewrites the new
  `ServerVersion`. A test pins that both Go modules are rewritten. This is the same outcome the M3b
  note in the root `CLAUDE.md` records for the Python gRPC client, now true for Go as well.

## 8. Documentation

- `go/CLAUDE.md`: a gRPC section — fixed-name staging, buf as a tool and its `go 1.26.7` floor,
  MIT-0, the caller-goroutine streams and the `Send`/`RecvMsg` trap, the guards and why `RawAdmin`
  returns an error, `TxHandle` clone-and-replace (#5040), `committed=false`, and why part 3 of the
  drift gate exists here.
- `go/arcadedbgrpc/README.md`, in the shape of the Python gRPC README: usage, both auth modes,
  plaintext vs TLS, `RawAdmin` and body-carried admin credentials, `TxHandle`, streams, errors as
  status codes, a compatibility table with a `0.2.0 (unreleased)` row, and the release paragraph
  (permanence, `retract`, `/v2`).
- Root `CLAUDE.md`: `go/` hosting two modules; the `ci-go.yml`, `publish-go.yml`, `release.yml`,
  license and adopt-script entries. Root `README.md`: the package list.

## 9. First version and out of scope

The module joins the lockstep at the next release, as `go/arcadedb` does.

Out of scope:

- wrapping the 44 admin RPCs (reachable through `RawAdmin()`; Python does not wrap them either);
- `InsertStream` on `TxHandle` (#46);
- `BulkInsert`, `InsertBidirectional`, `GraphBatchLoad` (raw-only, as in Python and TypeScript);
- connect-go (D2).
