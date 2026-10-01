# M10b Go gRPC Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Go module `github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc`, a grpc-go client generated from the committed `.proto` with a thin facade at parity with the Python gRPC driver, wired into the Go machinery M10 built.

**Architecture:** `buf` (a pinned `go tool`) drives `protoc-gen-go` and `protoc-gen-go-grpc` over the contract staged as `arcadedb_server.proto`, writing two committed files under `go/arcadedbgrpc/generated/`. A hand-written facade in package `arcadedbgrpc` adds auth interceptors, two security guards, four streaming wrappers and a binding transaction handle. The repository machinery (drift gate, licenses, release row, publish, Dependabot, contract watch) gains a row or branch each.

**Tech Stack:** Go 1.26 (module floor) / 1.26.7 (tools module, buf-forced) / 1.27 (e2e); grpc-go v1.84.0; protobuf v1.36.12; buf v1.73.0; protoc-gen-go-grpc v1.6.2; testcontainers-go; bash + Python 3 for repo scripts.

**Spec:** `docs/superpowers/specs/2026-10-01-m10b-go-grpc-driver-design.md` — read it first; this plan argues from it. M10's spec (`2026-09-30-m10-go-http-driver-design.md`) and `go/CLAUDE.md` describe the machinery being extended.

## Global Constraints

- Generated code under `go/arcadedbgrpc/generated/` is never hand-edited; fix `generated/buf.gen.yaml` or the staging script instead. `contracts/` is never edited.
- Module path `github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc`; package `arcadedbgrpc`; generated package `generated`.
- `go/arcadedbgrpc/go.mod`: `go 1.26`; requires only `google.golang.org/grpc` and `google.golang.org/protobuf` (plus what they pull). It never imports `go/arcadedb`.
- `go/tools/go.mod` and `go/go.work`: `go 1.26.7` (buf requires it; go.work must be ≥ every module's go line). Tool pins exact: buf `v1.73.0`, protoc-gen-go `v1.36.12` (`google.golang.org/protobuf/cmd/protoc-gen-go`), protoc-gen-go-grpc `v1.6.2`.
- `version.go`: two separate top-level lines `const Version = "0.1.0"` and `const ServerVersion = "26.10.1-SNAPSHOT"` — never a const block.
- `ServerVersion` is checked against the version in the `.proto` FILENAME (`scripts/resolve-proto-contract.sh`), never the OpenAPI `info.version`.
- Every call takes `ctx context.Context` first. No default timeout.
- RPC errors pass through as grpc-go status errors, unwrapped. Facade errors: `ErrInsecureChannel`, `ErrNoTransactionID`, `ErrNotCommitted`, `*TxError`.
- Auth metadata keys: `x-arcade-user`, `x-arcade-password`, `x-arcade-database` (only when non-empty), `authorization: Bearer <token>`. Always appended, never replacing caller metadata.
- Release row id `go-arcadedbgrpc`, package input `arcadedbgrpc`, tag `go/arcadedbgrpc/v<version>`.
- e2e gRPC container: image `arcadedata/arcadedb:26.10.1-SNAPSHOT` (env override `ARCADEDB_DOCKER_IMAGE`), `JAVA_OPTS=-Darcadedb.server.rootPassword=playwithdata -Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin`, ports 2480 and 50051, ready on `/api/v1/ready` 204 then log `gRPC server started on 0.0.0.0:50051`.
- Stdlib `testing` only; unit tests use `google.golang.org/grpc/test/bufconn`. Lint: `gofmt`, `go vet`, `staticcheck`; never golangci-lint.
- Actions pinned by full SHA: checkout `3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`, setup-go `b7ad1dad31e06c5925ef5d2fc7ad053ef454303e # v7.0.0`.
- `go/go.work.sum`: commit changes caused by this task's dependency changes (Task 1's new modules); never commit lines that only a local Go 1.27 toolchain run added — if unsure, regenerate it inside `docker run golang:1.26` and commit that.
- Load-bearing prose moves with behaviour (root `CLAUDE.md`, "Prose conventions").

## Review Focus

1. **Caller ctx already carries outgoing metadata** (their own `x-request-id` or even `x-arcade-database`): auth must still be present and the caller's keys kept. → Task 4 `TestAuthAppendsToCallerMetadata`.
2. **A request message reused after a transaction** (caller passes the same `*ExecuteQueryRequest` to `tx.ExecuteQuery` and later to `c.Raw().ExecuteQuery`): the later call must carry no transaction. → Task 7 `TestTxHandleNeverMutatesCallerRequest`.
3. **An empty batch in the middle of `InsertStream` chunks** (`[]`): sent as a zero-record chunk with the next `chunk_seq`, never treated as the end. → Task 6 `TestInsertStreamEmptyMiddleBatchIsAChunk`.
4. **Server aborts `StreamQuery` mid-stream** after some records: delivered records stay delivered, then exactly one error whose `status.Code` is the server's. → Task 5 `TestStreamQueryMidStreamErrorKeepsStatus`.
5. **Target given as a URL** (`"http://localhost:50051"`): grpc-go would treat `http` as an unknown resolver scheme and fail confusingly at the first RPC. Expect `NewClient` to return a clear error naming the `host:port` form. → Task 4 `TestNewClientRejectsURLTarget`.

---

## File Structure

```
go/go.work                                       + ./arcadedbgrpc; go 1.26.7
go/tools/go.mod                                  + buf, protoc-gen-go, protoc-gen-go-grpc; go 1.26.7
go/scripts/generate-grpc.sh                      new
go/scripts/check-drift.sh                        both generated trees
go/arcadedbgrpc/go.mod  README.md  LICENSE  version.go
go/arcadedbgrpc/generated/{buf.gen.yaml,arcadedb_server.pb.go,arcadedb_server_grpc.pb.go}
go/arcadedbgrpc/contract_test.go                 TestEveryRPCIsGenerated, TestServerVersionMatchesProto
go/arcadedbgrpc/client.go  auth.go  errors.go    NewClient, options, guards, interceptors
go/arcadedbgrpc/stream.go  insert.go  transaction.go
go/arcadedbgrpc/fake_test.go                     bufconn fake server helpers
go/e2e/grpc_main_test.go  grpc_test.go           second container + tests
```

Modified: `scripts/check-licenses.py` (+ tests), `CLAUDE.md`, `scripts/release-packages.py` (+ tests), `scripts/release/verify-go.sh`, `go/tools/cmd/checkzip/main.go`, `.github/workflows/{ci-go,publish-go,contract-watch,license-compliance,dependabot-auto-merge,ci-release}.yml`, `.github/dependabot.yml`, `scripts/tests/test-contract-scripts.sh`, `go/CLAUDE.md`, `README.md`.

---

### Task 1: Tools, module scaffold and deterministic generation

**Files:**
- Modify: `go/tools/go.mod`, `go/tools/go.sum`, `go/go.work`
- Create: `go/arcadedbgrpc/{go.mod,go.sum,LICENSE,version.go}`, `go/arcadedbgrpc/generated/{buf.gen.yaml,arcadedb_server.pb.go,arcadedb_server_grpc.pb.go}`, `go/scripts/generate-grpc.sh`
- Test: `go/arcadedbgrpc/contract_test.go`

**Interfaces:**
- Produces: package `generated` with `ArcadeDbServiceClient`, `ArcadeDbAdminServiceClient`, `NewArcadeDbServiceClient`, `NewArcadeDbAdminServiceClient`, the server interfaces and `Unimplemented…Server` types, and every message type; `const Version`, `const ServerVersion`; `findProto(t) string` helper in `contract_test.go` (walks up to the directory holding `contracts/`, resolves the single `arcadedb-server-*.proto`, `t.Skip` if none).

- [ ] **Step 1: Pin the tools.** From `go/tools`: `go get -tool github.com/bufbuild/buf/cmd/buf@v1.73.0`, `go get -tool google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.12`, `go get -tool google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.6.2`. Expect the `go` line to become `1.26.7`; set `go/go.work`'s `go` line to `1.26.7` and add `./arcadedbgrpc` to `use`.
- [ ] **Step 2: Create the module.** `go/arcadedbgrpc`: `go mod init github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc`, `go 1.26`; `LICENSE` copied from the root; `version.go` per Global Constraints, each const with a doc comment naming its writer.
- [ ] **Step 3: Write `generated/buf.gen.yaml`** (buf v2): `managed: {enabled: true, override: [{file_option: go_package, value: github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated}]}`; plugins `local: ["go", "tool", "protoc-gen-go"]` and `local: ["go", "tool", "protoc-gen-go-grpc"]`, each `out: <generated dir>`, `opt: paths=source_relative`. Header comment: why managed mode (no `go_package` in the contract) and why fixed-name staging.
- [ ] **Step 4: Write `go/scripts/generate-grpc.sh`.** `set -euo pipefail`; cwd-independent; resolve the proto with `../scripts/resolve-proto-contract.sh`; `mktemp -d` stage; copy as `arcadedb_server.proto` beside a minimal `buf.yaml` (`version: v2`, `modules: [{path: .}]`); `(cd go/tools && go tool buf generate <stage> --template <abs buf.gen.yaml> -o <abs generated dir>)` adjusted so outputs land as `generated/arcadedb_server.pb.go` and `generated/arcadedb_server_grpc.pb.go`; remove the stage on exit (trap); then `(cd go/arcadedbgrpc && go mod tidy)`. Comment block: why staging (unstamped filenames, nothing to retire — spec §4) and why `go tool` runs from `go/tools` (must run inside a module).
- [ ] **Step 5: Generate, build, vet.** Run `go/scripts/generate-grpc.sh && (cd go/arcadedbgrpc && go build ./... && go vet ./...)` → success; `head -8` of both files shows only plugin-version stamps.
- [ ] **Step 6: Determinism.** Two local runs plus `docker run --rm -v "$PWD":/w -w /w golang:1.26 go/scripts/generate-grpc.sh` → identical hashes, `git status --porcelain go/arcadedbgrpc/generated` unchanged after the Linux run.
- [ ] **Step 7: Write the contract tests.**

```go
func TestEveryRPCIsGenerated(t *testing.T)        // every `rpc Name (` in the proto's ArcadeDbService / ArcadeDbAdminService blocks → method Name on reflect.TypeOf((*generated.ArcadeDbServiceClient)(nil)).Elem() / Admin; lists all missing; fails on zero RPCs found
func TestServerVersionMatchesProto(t *testing.T)  // ServerVersion == filename minus "arcadedb-server-" and ".proto"
```
Parse service blocks with a small regexp over the file text (service name, then `rpc (\w+)\s*\(` until the closing `}`); expect 21 and 44 today.
- [ ] **Step 8: Run** `cd go/arcadedbgrpc && go test -run 'TestEveryRPCIsGenerated|TestServerVersionMatchesProto' -v ./` → both PASS; prove `TestServerVersionMatchesProto` fails by temporarily editing `ServerVersion`; prove the RPC parser by a sub-test that feeds it a fabricated proto string naming an RPC no interface has and asserts it is reported missing. Revert.
- [ ] **Step 9: Commit** `feat(go): gRPC module scaffold, pinned buf and generated stubs`.

### Task 2: Drift gate, lint and CI cover the gRPC module

**Files:**
- Modify: `go/scripts/check-drift.sh`, `.github/workflows/ci-go.yml`
- (lint.sh discovers modules from go.work — confirm, no edit expected)

**Interfaces:**
- Consumes: `generate-grpc.sh`, `TestEveryRPCIsGenerated` (Task 1).

- [ ] **Step 1: Extend `check-drift.sh`.** Parts 1–3 run for both generated trees: regenerate with both scripts; part 1 `git diff --exit-code` over `go/arcadedb/generated go/arcadedbgrpc/generated`; part 2 porcelain over both; part 3 requires `--- PASS: TestEveryOperationIsGenerated` (in `arcadedb`) AND `--- PASS: TestEveryRPCIsGenerated` (in `arcadedbgrpc`), each captured into a variable before grepping (no `| grep -q` under pipefail), `-count=1`. Part 4 unchanged (already all workspace modules).
- [ ] **Step 2: Prove the new paths fail.** Stage a one-line edit to `arcadedb_server.pb.go` → exit 1; `touch go/arcadedbgrpc/generated/extra.go` → exit 1; restore by deleting the extra file and re-running `generate-grpc.sh`. Clean run → exit 0.
- [ ] **Step 3: Edit `ci-go.yml`.** Paths (push and pull_request) gain `buf.yaml`; update the header comment that said M10b adds it. Build job's unit-test step runs `go test -race ./...` in both `go/arcadedb` and `go/arcadedbgrpc` (a loop or two steps).
- [ ] **Step 4: Verify** `go/scripts/lint.sh && go/scripts/check-drift.sh` → 0; `actionlint .github/workflows/ci-go.yml` → 0.
- [ ] **Step 5: Commit** `ci(go): drift gate and CI cover the gRPC module`.

### Task 3: License gate — MIT-0 and the new module

**Files:**
- Modify: `scripts/check-licenses.py` (`ALLOWED_IDS`, additions block, `_GO_MODULES`, `_MIN_PLAUSIBLE_GO_MODULES`), `scripts/tests/test_check_licenses.py`, `CLAUDE.md` ("Dependency licenses"), `.github/workflows/license-compliance.yml` (paths)

**Interfaces:**
- Produces: `"MIT-0"` in `ALLOWED_IDS`; `NORMALISE` maps the spelling go-licenses emits for segmentio/asm (measure it — may be `"Unknown"`, in which case see Step 1).

- [ ] **Step 1: Measure.** `./scripts/check-licenses.py --ecosystem go` after Task 1 → expect violations for `github.com/segmentio/asm` reported as Unknown. go-licenses classifies MIT-0 as Unknown, so a `NORMALISE` entry cannot fix it; add a narrowly scoped `_GO_LICENSE_OVERRIDES = {"github.com/segmentio/asm": "MIT-0"}` consulted only when go-licenses says `Unknown` for exactly that module, with a comment citing its LICENSE file's first line ("MIT No Attribution"). Record the observed module count.
- [ ] **Step 2: Write failing tests.**

```python
def test_mit_0_is_allowed(): ...                       # evaluate("MIT-0") allowed
def test_go_override_applies_only_to_unknown_for_that_module(): ...  # segmentio/asm Unknown → MIT-0; other Unknown stays a violation; segmentio/asm reported as "GPL-3.0" stays a violation
def test_go_collector_includes_the_grpc_module(): ...  # "arcadedbgrpc" in cl._GO_MODULES
def test_the_policy_additions_are_present(): ...       # update the existing additions test to include MIT-0
```
- [ ] **Step 3: Run** `cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -v` → new tests FAIL.
- [ ] **Step 4: Implement.** Add `"MIT-0"` to the additions block of `ALLOWED_IDS` with an evidence comment; add `"arcadedbgrpc"` to `_GO_MODULES` (it is a normal module: `--include_tests ./...`); set `_MIN_PLAUSIBLE_GO_MODULES` to half the new measured count with the count in the comment. Edit root `CLAUDE.md`: add `MIT-0` to the ALLOWED row and a sentence to "Four entries above are this repository's own additions" (now five) with the segmentio/asm evidence and "tool-only, never shipped".
- [ ] **Step 5: Verify** tests PASS; `./scripts/check-licenses.py --ecosystem go` → 0; ruff check/format and mypy as `ci-python.yml:57-58` do.
- [ ] **Step 6: Wire CI.** `license-compliance.yml` paths already cover `go/**/go.mod`/`go.sum`; confirm, no edit unless missing.
- [ ] **Step 7: Draft** the matching ArcadeDB `CLAUDE.md` line into the scratchpad (`scratchpad/arcadedb-claude-md-mit0.md`), not the repo.
- [ ] **Step 8: Commit** `feat(licenses): allow MIT-0 for buf's segmentio/asm; check the gRPC module`.

### Task 4: Client, auth interceptors and guards

**Files:**
- Create: `go/arcadedbgrpc/client.go`, `auth.go`, `errors.go`, `fake_test.go`
- Test: `go/arcadedbgrpc/client_test.go`

**Interfaces:**
- Produces:
  - `var ErrInsecureChannel = errors.New(...)`; `var ErrNoTransactionID`, `var ErrNotCommitted` (declared here, used in Task 7).
  - `type Option func(*config)`; `WithPasswordAuth(user, password, database string) Option`; `WithBearerToken(token string) Option`; `WithTransportCredentials(creds credentials.TransportCredentials) Option`; `WithInsecure() Option`; `WithDialOptions(opts ...grpc.DialOption) Option`.
  - `func NewClient(target string, opts ...Option) (*Client, error)`; `(*Client) Raw() generated.ArcadeDbServiceClient`; `(*Client) RawAdmin() (generated.ArcadeDbAdminServiceClient, error)`; `(*Client) Close() error`.
  - unexported `(*Client) conn *grpc.ClientConn`, `raw generated.ArcadeDbServiceClient` for Tasks 5–7.
  - `fake_test.go`: `func newFake(t *testing.T, svc generated.ArcadeDbServiceServer, admin generated.ArcadeDbAdminServiceServer, opts ...Option) *Client` — bufconn listener, server registered with both, client dialled via `WithDialOptions(grpc.WithContextDialer(...))` plus `WithInsecure()` unless the test passes its own; `t.Cleanup` stops both. A recording fake helper that captures incoming metadata per call shape.

- [ ] **Step 1: Write the failing tests.**

```go
func TestPasswordAuthOverPlaintextIsRefused(t *testing.T)   // NewClient(target, WithPasswordAuth(...)) → errors.Is(err, ErrInsecureChannel); message names WithInsecure and WithTransportCredentials
func TestBearerOverPlaintextIsAllowed(t *testing.T)
func TestPasswordAuthWithInsecureIsAllowed(t *testing.T)
func TestAuthMetadataOnEveryCallShape(t *testing.T)          // unary ExecuteQuery, server-stream StreamQuery, client-stream InsertStream, bidi InsertBidirectional: x-arcade-user/password/database present on each
func TestPasswordAuthOmitsEmptyDatabase(t *testing.T)
func TestBearerAuthHeader(t *testing.T)                      // authorization == "Bearer tok"
func TestAuthAppendsToCallerMetadata(t *testing.T)           // ctx with metadata.AppendToOutgoingContext("x-request-id","r1","x-arcade-database","other") → server sees x-request-id r1, both x-arcade-database values, auth present
func TestRawAdminRefusedWithoutTLSOrInsecure(t *testing.T)   // bearer auth, no WithInsecure → RawAdmin() err ErrInsecureChannel
func TestRawAdminAllowedWithInsecure(t *testing.T)
func TestRawAdminAllowedWithTransportCredentials(t *testing.T) // credentials.NewTLS(&tls.Config{}) — construction only, no RPC
func TestCloseTwiceIsSafe(t *testing.T)
func TestNewClientRejectsURLTarget(t *testing.T)             // "http://localhost:50051" and "https://h:1" → error mentioning "host:port"; "dns:///h:1" and "passthrough:///h:1" accepted
```
- [ ] **Step 2: Run** `go test -run 'Auth|RawAdmin|Close|NewClient|Bearer|Password' -v ./` → FAIL.
- [ ] **Step 3: Implement.** `grpc.NewClient` with transport credentials or `insecure.NewCredentials()`; `grpc.WithChainUnaryInterceptor` and `grpc.WithChainStreamInterceptor` that call `metadata.AppendToOutgoingContext`. URL check: reject targets whose scheme is `http` or `https` (case-insensitive) before dialling. Doc comments carry the spec §5 reasoning: why interceptors not `PerRPCCredentials`, why `RawAdmin` returns an error, why the admin guard covers Health/Ready, `WithInsecure` as the one opt-in, #5048.
- [ ] **Step 4: Run** → PASS; `go/scripts/lint.sh` → 0; `go test -race ./...` in `go/arcadedbgrpc` → ok.
- [ ] **Step 5: Commit** `feat(go): gRPC client, auth interceptors and security guards`.

### Task 5: Server streams — StreamQuery and TimeSeriesQuery

**Files:**
- Create: `go/arcadedbgrpc/stream.go`
- Test: `go/arcadedbgrpc/stream_test.go`

**Interfaces:**
- Consumes: `Client.raw`, `newFake` (Task 4).
- Produces: `(*Client) StreamQuery(ctx context.Context, req *generated.StreamQueryRequest, opts ...grpc.CallOption) iter.Seq2[*generated.GrpcRecord, error]`; `(*Client) TimeSeriesQuery(ctx context.Context, req *generated.TimeSeriesQueryRequest, opts ...grpc.CallOption) iter.Seq2[*generated.TimeSeriesQueryResult, error]`; unexported generic `recvAll[T any](ctx, open func(context.Context) (grpc.ServerStreamingClient[T], error)) iter.Seq2[*T, error]` reused by Task 7's bound streams.

- [ ] **Step 1: Write the failing tests.**

```go
func TestStreamQueryFlattensBatches(t *testing.T)           // fake sends QueryResult{2 records}, QueryResult{1} → 3 records in order
func TestStreamQueryPassesRequestUntouched(t *testing.T)    // RetrievalMode, BatchSize received as sent
func TestStreamQueryMidStreamErrorKeepsStatus(t *testing.T) // 1 batch then status.Error(codes.Aborted,"x") → 1 record, then err with status.Code(err)==codes.Aborted, then iteration ends
func TestStreamQueryBreakCancelsServerStream(t *testing.T)  // fake blocks after first batch; break → fake observes stream ctx Done
func TestStreamQueryEmptyStream(t *testing.T)               // zero batches → no events, no error
func TestTimeSeriesQueryYieldsWholeMessages(t *testing.T)   // two messages, last has Last=true, Truncated=true → both yielded, fields intact
func TestEachRangeIssuesANewRPC(t *testing.T)               // ranging twice → fake counts 2 calls
```
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** with a derived `context.WithCancel` cancelled on every exit; `io.EOF` ends normally. Doc comments: single-use iterators, Truncated only meaningful on Last.
- [ ] **Step 4: Run** → PASS with `-race`. **Step 5: Commit** `feat(go): gRPC server-stream iterators`.

### Task 6: Client streams — InsertStream and TimeSeriesWriteStream

**Files:**
- Create: `go/arcadedbgrpc/insert.go`
- Test: `go/arcadedbgrpc/insert_test.go`

**Interfaces:**
- Produces: `type InsertStreamRequest struct { Database string; Chunks iter.Seq[[]*generated.GrpcRecord]; Options *generated.InsertOptions; Credentials *generated.DatabaseCredentials; Transaction *generated.TransactionContext }`; `(*Client) InsertStream(ctx, InsertStreamRequest, ...grpc.CallOption) (*generated.InsertSummary, error)`; `type TimeSeriesWriteStreamRequest struct { Database, Type string; Precision <see Step 3>; Credentials *generated.DatabaseCredentials; Chunks iter.Seq[[]*generated.<point message type, from Step 1>] }` — `Precision` is `*generated.<precision enum>` if the enum's zero value is a real unit, else the plain enum with its zero rejected (Step 3 decides from Step 1's evidence and records it); `(*Client) TimeSeriesWriteStream(ctx, TimeSeriesWriteStreamRequest, ...grpc.CallOption) (*generated.TimeSeriesWriteSummary, error)`.

- [ ] **Step 1: Inspect the generated types** for `InsertChunk` (session_id, chunk_seq, last, database, options, credentials, transaction, records field name) and `TimeSeriesWriteChunk` (precision enum and its zero value). Record exact field names in the report.
- [ ] **Step 2: Write the failing tests.**

```go
func TestInsertStreamEnvelope(t *testing.T)               // 3 batches → 3 chunks; same non-empty session_id; chunk_seq 1,2,3; last only on 3rd; chunk 1 has Database and Options with Options.Database == req.Database; credentials+transaction on every chunk; returns server summary as sent
func TestInsertStreamCallerOptionsNotMutated(t *testing.T) // req.Options.Database stays as caller set it
func TestInsertStreamEmptyInputSendsOneLastChunk(t *testing.T) // nil Chunks and empty seq → exactly 1 chunk, seq 1, last true, 0 records
func TestInsertStreamEmptyMiddleBatchIsAChunk(t *testing.T)    // batches [a],[],[b] → 3 chunks, middle has 0 records, last only on 3rd
func TestInsertStreamNilBatchIsNotTheEnd(t *testing.T)    // batches [a], nil, [b] → 3 chunks
func TestInsertStreamSendErrorSurfacesServerStatus(t *testing.T) // fake returns status.Error(codes.InvalidArgument,"bad") after first Recv → InsertStream err has codes.InvalidArgument, not io.EOF
func TestInsertStreamStopsIteratingOnError(t *testing.T)  // endless seq + failing server → seq stops being pulled after the error
func TestTimeSeriesWriteStreamRepeatsHeaderFields(t *testing.T)
func TestTimeSeriesWriteStreamRequiresPrecision(t *testing.T)   // precision unset → error before any RPC (fake sees no call)
func TestTimeSeriesWriteStreamEmptyInputSendsZeroChunks(t *testing.T)
```
- [ ] **Step 3: Implement.** Iterate the caller's seq on the caller goroutine via `iter.Pull` for one-batch lookahead; `session_id` from `crypto/rand` (hex, 16 bytes); on a `Send` error call `CloseAndRecv` and return its error. "Precision required": if the generated enum's zero value is a real unit (ms), model the field as a pointer (`Precision *generated.X`) so unset is detectable; otherwise reject the zero/UNSPECIFIED value. Document whichever applies. Doc comments: caller-goroutine iteration (no pipe, panics stay on the caller), non-atomic writes, the `Send`/`RecvMsg` trap.
- [ ] **Step 4: Run** → PASS with `-race`. **Step 5: Commit** `feat(go): gRPC client-stream wrappers`.

### Task 7: Transactions and the binding handle

**Files:**
- Create: `go/arcadedbgrpc/transaction.go`
- Test: `go/arcadedbgrpc/transaction_test.go`

**Interfaces:**
- Consumes: `Client.raw`, `recvAll` (Task 5), errors (Task 4).
- Produces: `(*Client) Transaction(ctx context.Context, database string, fn func(tx *TxHandle) error) (err error)`; `type TxError struct { Err, RollbackErr error }` with `Error()` and `Unwrap() error` (Err only); `type TxHandle struct` with methods `ExecuteQuery, ExecuteCommand, CreateRecord, UpdateRecord, DeleteRecord, LookupByRid, VectorSearch, HybridSearch, FullTextSearch, TimeSeriesLatest` — each `(ctx, *generated.XRequest, ...grpc.CallOption) (*generated.XResponse, error)` — plus `StreamQuery` and `TimeSeriesQuery` with the Task 5 signatures.

- [ ] **Step 1: Write the failing tests.**

```go
func TestTransactionCommits(t *testing.T)                     // Begin(database) → bound call → Commit with TransactionContext{id, db}
func TestTransactionRollsBackOnError(t *testing.T)            // errors.Is(err, errX); Rollback called, Commit not
func TestTransactionRollbackFailureIsTxError(t *testing.T)    // fn returns a status error, rollback returns another → errors.As finds fn's (status.Code matches fn's)
func TestTransactionRePanicsOriginalValue(t *testing.T)
func TestTransactionNilPanicIsAnError(t *testing.T)           // default semantics: re-panics *runtime.PanicNilError; GODEBUG=panicnil=1 child process (as go/arcadedb/transaction_test.go does) → non-nil error, not nil
func TestTransactionCommitFailureRollsBack(t *testing.T)
func TestTransactionNotCommitted(t *testing.T)                // Commit answers Success=true, Committed=false, Message="reaped" → errors.Is(err, ErrNotCommitted) and message contains "reaped"
func TestTransactionBlankIDIsError(t *testing.T)              // Begin returns "  " → ErrNoTransactionID, fn not called, no Rollback
func TestTransactionRollsBackAfterContextCancel(t *testing.T) // rollback reaches the server
func TestTxHandleForcesDatabaseAndTransaction(t *testing.T)   // caller req Database "other", Transaction{TransactionId:"stale", Begin:true} → server sees db, {id, db}, Begin false
func TestTxHandleNeverMutatesCallerRequest(t *testing.T)      // after tx.ExecuteQuery(ctx, req): req.Database and req.Transaction unchanged; reusing req via c.Raw() later sends no transaction
func TestTxHandleBoundStreams(t *testing.T)                   // StreamQuery and TimeSeriesQuery carry the bound context
func TestTxHandleCoversEveryUnaryMethod(t *testing.T)         // table over the 10 methods: each binds
```
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** One unexported generic binder `bind[T interface{ proto.Message; GetDatabase() string }](...)` or per-type setters — whichever keeps the 12 methods free of duplicated logic blocks; `proto.Clone` then set `Database` and replace `Transaction` wholesale. Mirror `go/arcadedb/transaction.go`'s contract code paths (named result, `returned` flag, `context.WithoutCancel`, `errPanicNilOrGoexit`). Doc comments: three clauses + committed=false, #5040 aliasing, why InsertStream/TimeSeriesWriteStream are absent (#46; no transaction field).
- [ ] **Step 4: Run** → PASS with `-race`. **Step 5: Commit** `feat(go): gRPC transactions with a binding handle`.

### Task 8: e2e against a real gRPC server

**Files:**
- Create: `go/e2e/grpc_main_test.go` (shared container lifecycle extended), `go/e2e/grpc_test.go`
- Modify: `go/e2e/main_test.go` (start the second container in the same `TestMain`/`run` with teardown on every path), `go/e2e/go.mod` (require + replace `../arcadedbgrpc`)

**Interfaces:**
- Produces: helpers `grpcTarget string`, `newGrpcClient(t, opts ...arcadedbgrpc.Option) *arcadedbgrpc.Client` (password auth root/playwithdata/db + `WithInsecure`), `newGrpcDatabase(t) string` (creates a database and the `Person`, `VectorItem` (LSM_VECTOR dim 4 + FULL_TEXT) and `GrpcTsPoint` schema over HTTP — port the DDL verbatim from `python/e2e/conftest.py`).

- [ ] **Step 1:** Start the gRPC container per Global Constraints; wait strategies: HTTP 204 on `/api/v1/ready` then `wait.ForLog("gRPC server started on 0.0.0.0:50051")`, 90 s.
- [ ] **Step 2: Write tests mirroring `python/e2e/test_grpc.py`:**

```go
func TestGrpcPasswordAuth(t *testing.T)
func TestGrpcBearerAuth(t *testing.T)              // token via HTTP POST /api/v1/login, starts with "AU-"
func TestGrpcStreamQuery(t *testing.T)
func TestGrpcInsertStream(t *testing.T)            // Inserted == 3 and rows queryable
func TestGrpcEmptyInsertStream(t *testing.T)       // Inserted 0, Failed 0
func TestGrpcTransactionCommitAndRollback(t *testing.T) // rollback: errors.Is sentinel, no rows remain
func TestGrpcVectorHybridFulltextRaw(t *testing.T) // count 3, Truncated false, first distance 0 sorted; Fused true; fulltext count 2
func TestGrpcSearchThroughTxHandle(t *testing.T)
func TestGrpcTimeSeriesWriteQueryLatest(t *testing.T) // received/written/dropped 3/3/0; Latest Found true
func TestGrpcEmptyTimeSeriesWriteStream(t *testing.T) // all-zero summary
func TestGrpcRawAdminHealth(t *testing.T)          // RawAdmin() with WithInsecure → Health ok
```
- [ ] **Step 3: Run** `cd go/e2e && go test -v ./...` (Docker) → all PASS, HTTP tests still PASS. If a test exposes a facade bug, `t.Skip("facade bug: …")` and report DONE_WITH_CONCERNS.
- [ ] **Step 4:** `go/scripts/lint.sh && go/scripts/check-drift.sh` → 0. **Step 5: Commit** `test(go): gRPC end-to-end suite`.

### Task 9: Release table — the second goproxy row

**Files:**
- Modify: `scripts/release-packages.py` (`PACKAGES` ~49-110, `check` ~327-370 where goproxy compares to `openapi_versions` only), `scripts/tests/test_release_packages.py`, `.github/workflows/ci-release.yml` (paths)

**Interfaces:**
- Produces: row `{"id": "go-arcadedbgrpc", "language": "go", "manifest": "go/arcadedbgrpc/version.go", "lockfile": "", "registry": "goproxy", "name": "github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc", "workflow": "publish-go.yml", "package_input": "arcadedbgrpc"}` appended last; a per-row contract choice: a new optional row key `"contract": "openapi" | "proto"` (default by registry as today), with `go-arcadedb` → `openapi`, `go-arcadedbgrpc` → `proto`. If adding a key would break `_ROW_KEYS` pinning, derive it instead from the module path suffix — choose one, document it in the docstring.

- [ ] **Step 1: Write failing tests.**

```python
def test_json_lists_every_package_with_every_field()  # pinned ids + "go-arcadedbgrpc"
def test_go_grpc_server_version_checked_against_proto(tmp_path)   # proto filename 26.10.1, openapi info 26.9.9 → go-arcadedbgrpc ServerVersion 26.10.1 OK; go-arcadedb must match 26.9.9
def test_go_grpc_server_version_mismatch_reported(tmp_path)
def test_published_url_goproxy_grpc()                 # .../github.com/!arcade!data/arcadedb-drivers/go/arcadedbgrpc/@v/v0.2.0.info
def test_set_writes_both_go_versions(tmp_path)
```
Extend `fixture_repo` with `go/arcadedbgrpc/{version.go,go.mod}`.
- [ ] **Step 2: Run** `uv run --no-project --python 3.12 --with pytest python -m pytest scripts/tests/test_release_packages.py -v` → FAIL. **Step 3: Implement**; update the module docstring's sentence about the Go module being OpenAPI-only. **Step 4:** tests PASS; `./scripts/release-packages.py check 0.1.0 --allow-snapshot` → `OK: 6 packages`.
- [ ] **Step 5:** `ci-release.yml` paths gain `go/arcadedbgrpc/version.go` and `go/arcadedbgrpc/go.mod`. **Step 6: Commit** `feat(release): the Go gRPC module joins the lockstep table`.

### Task 10: Verify and publish — the arcadedbgrpc branch

**Files:**
- Modify: `scripts/release/verify-go.sh` (`case` ~15-16, server-version block ~38-60), `go/tools/cmd/checkzip/main.go` (`required` ~30, args ~33), `.github/workflows/publish-go.yml` (choice options ~38-39)

**Interfaces:**
- Produces: `checkzip <module-path> <version> <dir> <required-file>...` (required files become trailing arguments; at least one required); `verify-go.sh arcadedb|arcadedbgrpc`.

- [ ] **Step 1: checkzip.** Required files from args; usage error with fewer than 4 args. Prove: real `arcadedb` with `go.mod LICENSE version.go generated/client.gen.go` → 0; real `arcadedbgrpc` with `go.mod LICENSE version.go generated/arcadedb_server.pb.go generated/arcadedb_server_grpc.pb.go` → 0; a missing required file → 1.
- [ ] **Step 2: verify-go.sh.** `case` accepts `arcadedbgrpc`; its server-version branch resolves the proto with `../scripts/resolve-proto-contract.sh` and compares `ServerVersion` with the filename version (the `arcadedb` branch keeps the OpenAPI comparison); unit tests run `go test -race ./...` in `go/$PKG`; checkzip gets each module's required list. Run `verify-go.sh arcadedb` → 0, `verify-go.sh arcadedbgrpc` → 0, `verify-go.sh nope` → 1 with usage.
- [ ] **Step 3: publish-go.yml.** `package` options gain `arcadedbgrpc`; nothing else should be module-specific (it already derives the row and module from the package input) — confirm by reading, fix any remaining `arcadedb` literal. actionlint → 0. No push, no tag, no proxy contact.
- [ ] **Step 4: Commit** `feat(release): verify and publish the Go gRPC module`.

### Task 11: Dependabot, auto-merge guard, contract watch, adopt test

**Files:**
- Modify: `.github/dependabot.yml` (gomod `directories`), `.github/workflows/dependabot-auto-merge.yml` (`GUARDED` ~59), `.github/workflows/contract-watch.yml` (`Regenerate`, setup-go cache paths ~144-145, `verify_go` ~239-253), `scripts/tests/test-contract-scripts.sh` (`make_fixture` + one case)

- [ ] **Step 1:** dependabot `directories` gains `"/go/arcadedbgrpc"`. `GUARDED` gains `go/arcadedbgrpc/generated/`; verify `echo go/arcadedbgrpc/generated/arcadedb_server.pb.go | grep -qE "$GUARDED"` matches and `go/arcadedbgrpc/client.go` does not.
- [ ] **Step 2:** contract-watch `Regenerate` gains `(cd go && ./scripts/generate-grpc.sh)`; setup-go cache paths gain `go/arcadedbgrpc/go.sum`; `verify_go` gains `(cd go/arcadedbgrpc && go test ./...)` and the `TestEveryRPCIsGenerated` PASS check captured into a variable like the existing one. `REFRESH_PATHS` unchanged (already `go`). actionlint → 0.
- [ ] **Step 3: adopt test.** `make_fixture` gains `go/arcadedbgrpc/version.go`; new case `"rewrites ServerVersion in every Go module"` asserts both `go/arcadedb/version.go` and `go/arcadedbgrpc/version.go` are rewritten and both `Version` lines untouched. Run `scripts/tests/test-contract-scripts.sh` → `failed: 0`.
- [ ] **Step 4: Commit** `ci: Dependabot, auto-merge and contract watch cover the Go gRPC module`.

### Task 12: Documentation

**Files:**
- Create: `go/arcadedbgrpc/README.md`
- Modify: `go/CLAUDE.md`, `CLAUDE.md`, `README.md`

- [ ] **Step 1: `go/CLAUDE.md`** gains commands (`generate-grpc.sh`, tests per module) and a gRPC section covering every item in spec §8, plus the Task 3 override and the Task 6 precision-representation decision as built. Read the code; document what exists.
- [ ] **Step 2: `go/arcadedbgrpc/README.md`** in the shape of `python/packages/driver-grpc/README.md`: install, usage, both auth modes, plaintext vs TLS and `WithInsecure`, `RawAdmin` and body-carried admin credentials, `TxHandle` (forced binding, absent methods and why), streams, errors as status codes, endpoints reachable only through `Raw()`, compatibility table (header + `| 0.2.0 (unreleased) | 26.10.1-SNAPSHOT |` as the other READMEs present it), release paragraph (tag `go/arcadedbgrpc/v<version>`, permanence, `retract`, `/v2`).
- [ ] **Step 3: Root `CLAUDE.md`:** `go/` hosts two modules; workflow entries (`ci-go.yml` buf.yaml path, `publish-go.yml` two packages, contract-watch, license-compliance, dependabot-auto-merge); extend the M3b `adopt-contract-version.sh` paragraph with the Go gRPC outcome; the MIT-0 text already added in Task 3 — re-read for consistency. Root `README.md`: package list.
- [ ] **Step 4: Final verification.** Run: `go/scripts/lint.sh && go/scripts/check-drift.sh && (cd go/arcadedb && go test -race ./...) && (cd go/arcadedbgrpc && go test -race ./...) && (cd go/e2e && go test ./...) && scripts/tests/test-contract-scripts.sh && ./scripts/check-licenses.py && ./scripts/release-packages.py check 0.1.0 --allow-snapshot && scripts/release/verify-go.sh arcadedb && scripts/release/verify-go.sh arcadedbgrpc` → every command exits 0.
- [ ] **Step 5: Commit** `docs(go): the gRPC module's README and guides`.
