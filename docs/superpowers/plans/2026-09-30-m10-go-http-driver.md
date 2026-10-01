# M10 Go HTTP Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Go module `github.com/ArcadeData/arcadedb-drivers/go/arcadedb`, an OpenAPI-generated HTTP client with a hand-written facade at parity with the Python HTTP driver, wired into this repository's drift gates, license gate, contract watch, Dependabot and lockstep release.

**Architecture:** `oapi-codegen` generates one committed file under `go/arcadedb/generated/`; a hand-written facade in package `arcadedb` calls only generated methods (the plain `Client` for streaming and defect workarounds, `ClientWithResponses` otherwise). Three Go modules (`arcadedb`, `e2e`, `tools`) joined by `go/go.work`. Publishing is a path-prefixed git tag plus a proxy fetch.

**Tech Stack:** Go 1.26 (floor) / 1.27 (e2e); oapi-codegen v2.8.0; staticcheck; go-licenses v2; testcontainers-go; `golang.org/x/mod/zip`; bash + Python 3 for repo scripts; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-30-m10-go-http-driver-design.md` — read it first; this plan argues from it.

## Global Constraints

- Generated code under `go/arcadedb/generated/` is never hand-edited; fix `oapi-codegen.yaml`/`overlay.yaml` instead.
- Module path: `github.com/ArcadeData/arcadedb-drivers/go/arcadedb`; package name `arcadedb`; generated package name `generated`.
- `go` directive `1.26` in every `go.mod` and in `go.work`. CI: build job Go `1.26`, e2e job Go `1.27`.
- `arcadedb/go.mod` requires only the generator's runtime deps (`oapi-codegen/runtime`, `go-jsonmerge`, `google/uuid`). No testify, no protobuf, nothing else.
- Tool versions pinned exactly in `go/tools/go.mod` via `tool` directives: oapi-codegen `v2.8.0`, staticcheck `v0.8.1` (`honnef.co/go/tools`), go-licenses `v2.0.1`. **Never** golangci-lint (GPL-3.0).
- Every public call takes `ctx context.Context` first; errors are returned, never panicked (except re-panicking a caller's panic in `Transaction`).
- `Raw()` never returns an error for a non-2xx status; every facade method does, as `*ArcadeDBError`.
- `QueryEnvelope` defaults when the server omits a field: `Result` → empty slice, `Limit` → `-1`, `Returned` → `0`, `Truncated` → `false`.
- Session header: `arcadedb-session-id`. Request-id header: `X-Request-Id`. ndjson media type: `application/x-ndjson`.
- Default e2e image `arcadedata/arcadedb:26.10.1-SNAPSHOT`, overridable by `ARCADEDB_DOCKER_IMAGE`; root password `playwithdata` via `JAVA_OPTS=-Darcadedb.server.rootPassword=playwithdata`.
- Release tag for this module: `go/arcadedb/v<version>`. Release-table row id `go-arcadedb`, registry `goproxy`, workflow `publish-go.yml`, package input `arcadedb`.
- Actions are pinned by full commit SHA with a `# vX.Y.Z` comment, as every existing workflow does.
- Load-bearing prose moves with behaviour (root `CLAUDE.md`, "Prose conventions").

## Review Focus

1. **An ndjson line longer than 64 KiB** (a record with a large property): `bufio.Scanner`'s default token limit would fail it. Expect the row to arrive intact. → Task 7 test `TestStreamLineLongerThan64KiB`.
2. **`ctx` cancelled while the transaction callback runs:** a rollback issued on the same `ctx` fails instantly and leaks the session. Expect the rollback to be issued on `context.WithoutCancel(ctx)`. → Task 6 test `TestTransactionRollsBackAfterContextCancel`.
3. **A database name with a space or slash** (`"my db/x"`): expect it percent-escaped as one path segment, never a new path segment. → Task 4 test `TestDatabaseNameIsEscapedAsOneSegment`.
4. **A batch row property named like a control key** (`@type`, `@class`, `@id`, `@from`, `@to`): flattening would silently overwrite the control key. Expect an error before any request is sent. → Task 8 test `TestBatchRejectsPropertyShadowingControlKey`.
5. **A non-JSON error body** (an HTML 502 from a proxy): expect `*ArcadeDBError` carrying only the status and `X-Request-Id`, never a decode error. → Task 3 test `TestErrorFromHTMLBody`.

---

## File Structure

```
go/go.work                                   workspace: ./arcadedb ./e2e ./tools
go/CLAUDE.md                                 workspace guide (Task 17)
go/scripts/generate.sh                       contract → generated/client.gen.go
go/scripts/check-drift.sh                    4-part drift gate
go/scripts/lint.sh                           gofmt + vet + staticcheck per module
go/tools/go.mod, go/tools/cmd/checkzip/main.go
go/arcadedb/go.mod  README.md  LICENSE
go/arcadedb/version.go                       Version, ServerVersion
go/arcadedb/generated/{oapi-codegen.yaml,overlay.yaml,client.gen.go}
go/arcadedb/contract_test.go                 contract-reading tests (coverage, overlay expiry, ServerVersion)
go/arcadedb/errors.go  internal/unwrap/unwrap.go
go/arcadedb/server.go  auth.go  database.go  envelope.go  transaction.go
go/arcadedb/stream.go  internal/ndjson/ndjson.go
go/arcadedb/batch.go   internal/batchrows/batchrows.go
go/arcadedb/vector.go  timeseries.go  dashboards.go  promql.go
go/arcadedb/*_test.go                        unit tests, httptest fakes (fakes_test.go holds shared helpers)
go/e2e/go.mod  e2e/main_test.go  e2e/*_test.go
.github/workflows/ci-go.yml  publish-go.yml
scripts/release/verify-go.sh
```

Modified: `scripts/adopt-contract-version.sh`, `scripts/tests/test-contract-scripts.sh`, `scripts/check-licenses.py`, `scripts/tests/test_check_licenses.py`, `scripts/release-packages.py`, `scripts/tests/test_release_packages.py`, `scripts/report-contract-watch.sh`, `.github/workflows/{release,ci-release,contract-watch,license-compliance,dependabot-auto-merge}.yml`, `.github/dependabot.yml`, `CLAUDE.md`, `README.md`.

---

### Task 1: Workspace, tools, and deterministic generation

**Files:**
- Create: `go/go.work`, `go/tools/go.mod`, `go/tools/go.sum`, `go/arcadedb/go.mod`, `go/arcadedb/go.sum`, `go/arcadedb/LICENSE` (copy of root `LICENSE`), `go/arcadedb/version.go`, `go/arcadedb/generated/oapi-codegen.yaml`, `go/arcadedb/generated/overlay.yaml`, `go/arcadedb/generated/client.gen.go`, `go/scripts/generate.sh`
- Test: `go/arcadedb/contract_test.go`

**Interfaces:**
- Produces: package `generated` (types `Client`, `ClientWithResponses`, `QueryRequest`, `CommandRequest`, `QueryResponse`, `ServerInfo`, `ExecuteQueryPostParams`, `ExecuteBatchParams`, `PromQLQueryParams`, `PromQLSeriesParams`, `GetTimeSeriesLatestParams`, `VectorSearchRequest`, `HybridSearchRequest`, `FullTextSearchRequest`, response wrappers suffixed `Resp`); `const Version = "<current lockstep version>"` and `const ServerVersion = "26.10.1-SNAPSHOT"` in `version.go`; helper `findContract(t *testing.T) string` in `contract_test.go` (walks up from the test's working directory to the directory holding `contracts/`, resolves the single `arcadedb-openapi-*.json`, calls `t.Skip` if none is found).

- [ ] **Step 1: Create the tools module**

From `go/tools`: `go mod init github.com/ArcadeData/arcadedb-drivers/go/tools`, then
`go get -tool github.com/oapi-codegen/oapi-codegen/v2/cmd/oapi-codegen@v2.8.0`,
`go get -tool honnef.co/go/tools/cmd/staticcheck@v0.8.1`,
`go get -tool github.com/google/go-licenses/v2@v2.0.1`. Set the `go` line to `1.26`. If a tool's own `go.mod` demands a higher `go`, stop and report — it breaks the floor.

- [ ] **Step 2: Create the driver module and workspace**

`go/arcadedb`: `go mod init github.com/ArcadeData/arcadedb-drivers/go/arcadedb`, `go 1.26`. `go/go.work`: `go 1.26`, `use (./arcadedb ./tools)` (`./e2e` is added in Task 11). Confirm `go tool oapi-codegen -version` works from `go/arcadedb` (tool resolution through the workspace). If it does not, `generate.sh` runs the tool from `go/tools` with an absolute output path instead; record which in the script's comment.

- [ ] **Step 3: Write `oapi-codegen.yaml` and `overlay.yaml`**

Config: `package: generated`, `output: client.gen.go`, `generate: {models: true, client: true}`, `output-options: {response-type-suffix: Resp, overlay: {path: overlay.yaml}}`. Overlay (OpenAPI Overlay 1.0.0): one action targeting the `"/unreadableFiles"` property (JSONPath `$..properties["/unreadableFiles"]`) with `update: {x-go-name: UnreadableFiles}`. A header comment in each file says why (spec §6).

- [ ] **Step 4: Write `go/scripts/generate.sh`**

`set -euo pipefail`; resolve the contract with `../scripts/resolve-openapi-contract.sh` (relative to `go/`); `cd arcadedb/generated`; run oapi-codegen with the config and the contract path; then `(cd arcadedb && go mod tidy)`. Callable from any cwd (`cd "$(dirname "$0")/.."` first).

- [ ] **Step 5: Generate, build, vet**

Run: `go/scripts/generate.sh && (cd go/arcadedb && go build ./... && go vet ./...)`
Expected: success, and `grep -n 'UnreadableFiles.*json:"/unreadableFiles' go/arcadedb/generated/client.gen.go` matches (exported field). If the overlay path key or JSONPath form differs in v2.8.0, fix the config — never the output.

- [ ] **Step 6: Verify determinism across two runs and two OSes**

Run: `sha256sum go/arcadedb/generated/client.gen.go; go/scripts/generate.sh; sha256sum go/arcadedb/generated/client.gen.go`, then the same inside `docker run --rm -v "$PWD":/w -w /w golang:1.26 go/scripts/generate.sh` (Linux).
Expected: identical hashes, and `git status --porcelain go/` unchanged after the Linux run. Any difference blocks the task.

- [ ] **Step 7: Write the failing contract tests**

```go
func TestEveryOperationIsGenerated(t *testing.T)   // every operationId → method on *generated.Client named strings.ToUpper(id[:1])+id[1:]; list all missing
func TestOverlayStillNeeded(t *testing.T)          // contract text contains `"/unreadableFiles"`; failure message: "upstream fixed /unreadableFiles: delete generated/overlay.yaml and its config key"
func TestServerVersionMatchesContract(t *testing.T) // ServerVersion == contract info.version
```
Reflection: `reflect.TypeOf(&generated.Client{}).MethodByName(name)`. Operation ids are read from every path item's `get/post/put/delete/patch/head` (72 today, all `[a-z][A-Za-z0-9]*`).

- [ ] **Step 8: Run tests**

Run: `cd go/arcadedb && go test -run 'TestEveryOperationIsGenerated|TestOverlayStillNeeded|TestServerVersionMatchesContract' -v ./...`
Expected: three `--- PASS` lines (they pass against the generated output from Step 5; confirm each fails when broken by temporarily editing `ServerVersion`, then revert).

- [ ] **Step 9: Commit**

```bash
git add go/ && git commit -m "feat(go): workspace, pinned tools and generated HTTP client"
```

### Task 2: Lint, drift gate, and `ci-go.yml` build job

**Files:**
- Create: `go/scripts/lint.sh`, `go/scripts/check-drift.sh`, `.github/workflows/ci-go.yml`

**Interfaces:**
- Consumes: `go/scripts/generate.sh`, `TestEveryOperationIsGenerated` (Task 1).
- Produces: `go/scripts/lint.sh` and `go/scripts/check-drift.sh`, both exit non-zero on failure and runnable from any cwd; used by Tasks 11, 15, 16.

- [ ] **Step 1: Write `lint.sh`**

For each module dir listed in `go.work` that contains `.go` files: `gofmt -l .` must print nothing (print the list and exit 1 otherwise), `go vet ./...`, `go tool staticcheck ./...`. `gofmt` skips nothing: generated output is gofmt-clean by construction.

- [ ] **Step 2: Write `check-drift.sh`**

Four parts, each with the error message style of `ci-python.yml:64-79`:
1. `generate.sh`, then `git diff --exit-code -- go/arcadedb/generated`.
2. `git status --porcelain -- go/arcadedb/generated` must be empty.
3. `go test -run '^TestEveryOperationIsGenerated$' -v ./` in `go/arcadedb`; fail unless the output contains `--- PASS: TestEveryOperationIsGenerated` (a skip is a failure).
4. `go mod tidy` in every module, then `git diff --exit-code -- 'go/**/go.mod' 'go/**/go.sum'` and no untracked `go.sum`.

- [ ] **Step 3: Prove each part fails**

Run each and expect exit 1: append a comment line to `client.gen.go`; `touch go/arcadedb/generated/extra.go`; rename `executeBatch` in a scratch copy of the contract is not possible without editing `contracts/`, so instead temporarily make `findContract` unable to find it (e.g. run from a copied module dir) and confirm part 3 fails on the skip; add an unused requirement with `go get github.com/google/uuid@latest` in `tools/`. Restore with `git checkout -- go/ && git clean -fd go/`. Then run `go/scripts/check-drift.sh` clean → exit 0.

- [ ] **Step 4: Write `ci-go.yml`**

Triggers mirror `ci-python.yml:3-22` with paths `go/**`, `contracts/**`, `scripts/**`, `.gitignore`, `.github/workflows/ci-go.yml`. Job `build` ("Lint, drift gate and unit tests"): checkout, `actions/setup-go` (`go-version: '1.26'`, `cache-dependency-path: go/**/go.sum`), `go/scripts/lint.sh`, `go/scripts/check-drift.sh`, `cd go/arcadedb && go test -race ./...`. The `e2e` job is added in Task 11. A top comment explains why `buf.yaml` is not in paths (M10b adds it).

- [ ] **Step 5: Validate and commit**

Run: `go/scripts/lint.sh && go/scripts/check-drift.sh` → exit 0; `actionlint .github/workflows/ci-go.yml` if installed (otherwise `python3 -c 'import yaml,sys;yaml.safe_load(open(sys.argv[1]))' .github/workflows/ci-go.yml`).

```bash
git add go/scripts .github/workflows/ci-go.yml && git commit -m "ci(go): lint and four-part drift gate"
```

### Task 3: Errors and unwrapping

**Files:**
- Create: `go/arcadedb/errors.go`, `go/arcadedb/internal/unwrap/unwrap.go`
- Test: `go/arcadedb/errors_test.go`

**Interfaces:**
- Produces:
  - `type ArcadeDBError struct { Status int; ErrorMessage, Exception, Detail, RequestID, Help, ExceptionArgs string }` with `func (e *ArcadeDBError) Error() string` — message is `ErrorMessage`, else `Detail`, else `fmt.Sprintf("ArcadeDB request failed with status %d", Status)`.
  - `func newError(status int, body []byte, requestID string) *ArcadeDBError` — never fails; non-JSON / non-object body yields only `Status` and `RequestID`; a non-string field is left empty; `RequestID` falls back to body `requestId` when the header is empty.
  - `func errorFromResponse(resp *http.Response) *ArcadeDBError` — reads (and closes) the body, header `X-Request-Id`.
  - `internal/unwrap`: `func Check(resp *http.Response, body []byte) error` returns nil for 2xx, else an error built by a constructor injected at package init (`var NewError func(status int, body []byte, requestID string) error`) — the indirection exists only to avoid the import cycle, as `_internal/unwrap.py` does.

- [ ] **Step 1: Write the failing tests**

```go
func TestErrorFieldsFromBody(t *testing.T)        // body {"error":"e","exception":"x","detail":"d","help":"h","exceptionArgs":"a","requestId":"b"}, header X-Request-Id "r" → RequestID "r", others mapped
func TestErrorRequestIDFallsBackToBody(t *testing.T) // no header → RequestID "b"
func TestErrorMessageFallbacks(t *testing.T)       // {"detail":"d"} → "d"; {} status 503 → "ArcadeDB request failed with status 503"
func TestErrorNonStringFieldIgnored(t *testing.T)  // {"error":42} → ErrorMessage ""
func TestErrorFromHTMLBody(t *testing.T)           // body "<html>502</html>", header X-Request-Id "r" → Status 502, RequestID "r", all else ""
func TestErrorFromEmptyBody(t *testing.T)
func TestErrorsAsFindsArcadeDBError(t *testing.T)  // fmt.Errorf("wrap: %w", err) → errors.As succeeds
```

- [ ] **Step 2: Run** `cd go/arcadedb && go test -run TestError -v ./` → FAIL (undefined).
- [ ] **Step 3: Implement** in `errors.go` and `internal/unwrap/unwrap.go`. Doc comment on `ArcadeDBError` states the `ErrorMessage`/`Help` naming reasons (spec §7) and that `ExceptionArgs` is a plain string despite its plural name.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(go): ArcadeDBError and response unwrapping`.

### Task 4: Server, auth, database handle, server-level calls

**Files:**
- Create: `go/arcadedb/server.go`, `go/arcadedb/auth.go`, `go/arcadedb/database.go`, `go/arcadedb/fakes_test.go`
- Test: `go/arcadedb/server_test.go`

**Interfaces:**
- Consumes: `errorFromResponse`, `unwrap.Check` (Task 3).
- Produces:
  - `type Option func(*config)`; `WithBasicAuth(user, password string) Option`; `WithBearerToken(token string) Option`; `WithHeader(name, value string) Option`; `WithHTTPClient(c *http.Client) Option`.
  - `func NewServer(baseURL string, opts ...Option) (*Server, error)` — every request carries the auth header, extra headers, and `User-Agent: arcadedb-go/<Version>`; default client `&http.Client{}` (no timeout, deliberately).
  - `(*Server) DB(name string) *Database`; `Raw() *generated.ClientWithResponses`; `Close() error` (calls `CloseIdleConnections` on the client); `ListDatabases(ctx) ([]string, error)` (nil result → empty slice); `Exists(ctx, name string) (bool, error)`; `ServerInfo(ctx) (*generated.ServerInfo, error)`; `Health(ctx) error` (204 only); `Ready(ctx) (bool, error)` (2xx → true, 503 → false, other → error).
  - `type Database struct` (unexported fields `srv *Server`, `name string`, `sessionID string`); `(*Database) Name() string`; unexported `(*Database) sessionParam() *string` (nil outside a transaction).
  - `fakes_test.go`: `func fakeServer(t *testing.T, h http.HandlerFunc) *Server` (httptest server + `NewServer` with basic auth root/pw, cleaned up via `t.Cleanup`).

- [ ] **Step 1: Write the failing tests**

```go
func TestBasicAuthHeader(t *testing.T)            // Authorization == "Basic " + base64("root:pw"); UTF-8 credential "ü:pä" round-trips
func TestBearerAuthHeader(t *testing.T)
func TestUserAgentCarriesVersion(t *testing.T)    // "arcadedb-go/" + Version
func TestListDatabasesEmptyWhenResultMissing(t *testing.T) // {} → []string{} (non-nil, len 0)
func TestExists(t *testing.T)                     // {"result":true} → true; {} → false
func TestHealthRequires204(t *testing.T)          // 200 → *ArcadeDBError
func TestReady(t *testing.T)                      // 204 → true; 503 → false,nil; 500 → error
func TestRawDoesNotErrorOnNon2xx(t *testing.T)    // Raw().GetServerInfoWithResponse → err nil, StatusCode 500
func TestDatabaseNameIsEscapedAsOneSegment(t *testing.T) // Exists(ctx,"my db/x") hits RawPath/EscapedPath "/api/v1/exists/my%20db%2Fx"
```

- [ ] **Step 2: Run** `go test -run 'Auth|UserAgent|ListDatabases|Exists|Health|Ready|Raw|Escaped' -v ./` → FAIL.
- [ ] **Step 3: Implement.** Headers are injected with a `generated.WithRequestEditorFn`. `auth.go` carries the one-line note that Go has neither `btoa` hazard (spec §7). `Exists`'s doc comment reproduces why `false` cannot prove absence (unauthorized looks identical). If the escaping test shows the generated client does not escape `/`, fix it with a request editor that sets `URL.RawPath` — never by editing generated code — and note it in `database.go`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(go): server, auth and server-level calls`.

### Task 5: Query language, envelope, Query and Command

**Files:**
- Create: `go/arcadedb/envelope.go`
- Modify: `go/arcadedb/database.go`
- Test: `go/arcadedb/query_test.go`

**Interfaces:**
- Produces:
  - `type QueryLanguage string`; consts `SQL = "sql"`, `Cypher = "cypher"`, `Gremlin = "gremlin"`, `GraphQL = "graphql"`, `Mongo = "mongo"`.
  - `type QueryEnvelope struct { Result []map[string]any; Limit, Returned int; Truncated bool }`.
  - `type QueryOption func(*queryOptions)`; `WithLimit(n int) QueryOption`.
  - `(*Database) Query(ctx, lang QueryLanguage, command string, params map[string]any, opts ...QueryOption) (QueryEnvelope, error)` via `ExecuteQueryPostWithResponse`.
  - `(*Database) Command(ctx, lang QueryLanguage, command string, params map[string]any) (QueryEnvelope, error)` via `ExecuteCommandWithResponse`; never sends `limit`.
  - unexported `toEnvelope(*generated.QueryResponse) (QueryEnvelope, error)` and `buildQueryRequest`/`buildCommandRequest` (reused by Task 7).

- [ ] **Step 1: Write the failing tests**

```go
func TestQueryBodyOmitsUnsetFields(t *testing.T)  // nil params, no limit → body keys exactly {"command","language"}; never "serializer"
func TestQueryBodyCarriesParamsAndLimit(t *testing.T) // WithLimit(-1) → "limit":-1
func TestCommandNeverSendsLimit(t *testing.T)
func TestEnvelopeDefaults(t *testing.T)           // {} → Result len 0 non-nil, Limit -1, Returned 0, Truncated false
func TestEnvelopeReadsTruncated(t *testing.T)     // {"result":[{"a":1}],"limit":1,"returned":1,"truncated":true}
func TestEnvelopeRejectsGraphShape(t *testing.T)  // {"result":{"vertices":[],"edges":[]}} → *ArcadeDBError Status 200
func TestQueryNon2xxIsArcadeDBError(t *testing.T) // 400 {"error":"bad"} → ErrorMessage "bad"
func TestQueryOutsideTransactionSendsNoSessionHeader(t *testing.T)
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** If the generated `QueryResponse.Result` cannot hold the graph shape, the rejection happens where the parse error surfaces; `TestEnvelopeRejectsGraphShape` pins the outcome, not the mechanism. `QueryEnvelope`'s doc comment carries the "most reassuring reading" warning from spec §7 verbatim in substance.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(go): query and command with the normalised envelope`.

### Task 6: Transactions

**Files:**
- Create: `go/arcadedb/transaction.go`
- Test: `go/arcadedb/transaction_test.go`

**Interfaces:**
- Consumes: `(*Database).sessionParam`, `Query`, `Command` (Tasks 4–5).
- Produces: `(*Database) Transaction(ctx context.Context, fn func(tx *Database) error) error`; `type TxError struct { Err, RollbackErr error }` with `Error() string` (both messages) and `Unwrap() error` returning `Err` only.

- [ ] **Step 1: Write the failing tests** (fake server records the sequence of paths and session headers)

```go
func TestTransactionCommitsOnNil(t *testing.T)              // begin → query with header "s1" → commit with "s1"
func TestTransactionOuterHandleNotInTransaction(t *testing.T) // db.Query inside fn sends no session header
func TestTransactionRollsBackOnError(t *testing.T)          // fn returns errX → rollback; returned err == errX (errors.Is)
func TestTransactionRollbackFailureWrapsInTxError(t *testing.T) // fn errX, rollback 500 → *TxError; errors.Is(err, errX); errors.As(err,&arcErr) finds NOT the rollback's error when errX is not an ArcadeDBError
func TestTransactionRePanics(t *testing.T)                  // fn panics "boom" → rollback issued, recover() == "boom"
func TestTransactionPanicWinsOverRollbackFailure(t *testing.T)
func TestTransactionCommitFailureRollsBackAndReturnsCommitError(t *testing.T) // commit 500 → rollback issued; err is the commit's *ArcadeDBError
func TestTransactionMissingSessionHeader(t *testing.T)      // begin 204 without header → *ArcadeDBError "begin_transaction did not return a session id"-equivalent, fn not called
func TestTransactionRollsBackAfterContextCancel(t *testing.T) // fn cancels ctx then returns ctx.Err() → rollback still reaches the server
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Session id read from the typed begin 204 header field if the generator emits one, else from `HTTPResponse.Header`. Rollbacks (clause 2 and clause 3) use `context.WithoutCancel(ctx)`. Doc comment on `Transaction` states the three clauses, the second-handle rule, and why `errors.Join` is not used (spec §7).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(go): transactions with the three-clause contract`.

### Task 7: ndjson streaming

**Files:**
- Create: `go/arcadedb/stream.go`, `go/arcadedb/internal/ndjson/ndjson.go`
- Test: `go/arcadedb/stream_test.go`, `go/arcadedb/internal/ndjson/ndjson_test.go`

**Interfaces:**
- Consumes: `buildQueryRequest`, `buildCommandRequest`, `errorFromResponse`.
- Produces:
  - `internal/ndjson`: `func Lines(r io.Reader) iter.Seq2[[]byte, error]` — splits on `'\n'` only, skips blank lines, flushes a final unterminated line, no line-length limit (`bufio.Reader.ReadSlice`/`ReadBytes`, not `bufio.Scanner`).
  - `type StreamStats struct { Limit, Returned int; Truncated bool }`; `type StreamEvent struct { Record map[string]any; Stats *StreamStats }`.
  - `(*Database) QueryStream(ctx, lang, command string, params map[string]any, opts ...QueryOption) iter.Seq2[StreamEvent, error]`; `(*Database) CommandStream(ctx, lang, command string, params map[string]any) iter.Seq2[StreamEvent, error]`. Both call the plain generated `Client` (`ExecuteQueryPost` / `ExecuteCommand`) with the `Accept` param set to `application/x-ndjson` and the session param.

- [ ] **Step 1: Write the failing tests**

```go
// internal/ndjson
func TestLinesSplitsOnNewlineOnly(t *testing.T)   // "{\"a\":\"x y\"}\n{\"b\":1}" → 2 lines, first contains U+2028 raw
func TestLinesSkipsBlankAndFlushesTail(t *testing.T)
// stream
func TestStreamYieldsRecordsThenStats(t *testing.T) // 2 records + {"stats":{...,"truncated":true}} → events[2].Stats.Truncated
func TestStreamWithoutTrailerEndsWithoutStats(t *testing.T) // parity: no error, no Stats event
func TestStreamInBandErrorYieldedOnce(t *testing.T) // {"error":{"message":"m"}} → err *ArcadeDBError{Status:200, ErrorMessage:"m"}, then iteration ends
func TestStreamInBandErrorWithoutMessage(t *testing.T) // → ErrorMessage "the stream reported an error"
func TestStreamNon2xxIsArcadeDBError(t *testing.T)
func TestStreamBreakClosesBody(t *testing.T)      // handler blocks after first line; break → handler sees request context done
func TestStreamSendsAcceptAndSessionHeaders(t *testing.T)
func TestStreamLineLongerThan64KiB(t *testing.T)  // one record with a 200 KiB string property arrives intact
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Request issued on first iteration. Doc comments state: the trailer is last in a complete stream, so its absence means the stream was cut short (spec §7); `CommandStream` accepts read-only statements only.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(go): ndjson query and command streams`.

### Task 8: Batch load

**Files:**
- Create: `go/arcadedb/batch.go`, `go/arcadedb/internal/batchrows/batchrows.go`
- Test: `go/arcadedb/batch_test.go`, `go/arcadedb/internal/batchrows/batchrows_test.go`

**Interfaces:**
- Consumes: `internal/ndjson.Lines`, `errorFromResponse`.
- Produces:
  - `type VertexRow struct { Type, ID string; Properties map[string]any }`; `type EdgeRow struct { Type, From, To string; Properties map[string]any }` (in package `arcadedb`; `batchrows` takes its own mirror types or plain args to avoid a cycle).
  - `batchrows.Write(w io.Writer, vertices iter.Seq[VertexRow], edges iter.Seq[EdgeRow]) error` — vertices first, then edges, one JSON object + `"\n"` each; control keys first in the order `@type, @class, @id` / `@type, @class, @from, @to`, then properties in sorted key order; `@id` only when `ID != ""`.
  - `(*Database) BatchLoad(ctx, vertices iter.Seq[VertexRow], edges iter.Seq[EdgeRow], params *generated.ExecuteBatchParams) (map[string]any, error)`; `(*Database) BatchLoadStream(same) iter.Seq2[map[string]any, error]` — both via `ExecuteBatchWithBody` with content type `application/x-ndjson`, body fed through `io.Pipe`; the stream variant sets `Accept: application/x-ndjson` through a request editor or the generated param if one exists. nil `vertices`/`edges` mean none.

- [ ] **Step 1: Write the failing tests**

```go
func TestBatchLineFormat(t *testing.T)            // matches python batch_rows.py:12-13 example byte for byte (modulo key order rule above)
func TestBatchVerticesBeforeEdges(t *testing.T)
func TestBatchOmitsEmptyID(t *testing.T)
func TestBatchRejectsPropertyShadowingControlKey(t *testing.T) // Properties{"@class":"X"} → error; fake server receives no request
func TestBatchLoadSendsNdjsonAndParams(t *testing.T) // Content-Type application/x-ndjson; params.CommitEvery → ?commitEvery=
func TestBatchLoadReturnsRawSummary(t *testing.T)
func TestBatchStreamProgressThenSummary(t *testing.T)
func TestBatchStreamInBandError(t *testing.T)     // {"error":{"status":409}} → *ArcadeDBError Status 409, ErrorMessage "the batch load reported an error"; status absent → 500
func TestBatchStreamsBodyWithoutBuffering(t *testing.T) // an iter.Seq yielding 100k vertices; server reads first line before the seq finishes (use a channel handshake)
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Doc comments: not atomic (commits every `commitEvery`), `From`/`To` take a temp id from the same payload or a `#bucket:position` RID, stream progress `idMapping` fragments are never merged.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(go): batch load, buffered and streamed`.

### Task 9: Vector namespace

**Files:**
- Create: `go/arcadedb/vector.go`
- Test: `go/arcadedb/vector_test.go`

**Interfaces:**
- Produces: `(*Database) Vector() *Vector`; `(*Vector) Search(ctx, req generated.VectorSearchRequest) (*generated.VectorSearchResponse, error)`; `Hybrid(ctx, req generated.HybridSearchRequest) (*generated.HybridSearchResponse, error)`; `Fulltext(ctx, req generated.FullTextSearchRequest) (*generated.FullTextSearchResponse, error)`. All send the session param when present.

- [ ] **Step 1: Write the failing tests**

```go
func TestVectorSearchPassesRequestThrough(t *testing.T) // unset K → no "k" key in body (server default 10 applies)
func TestVectorSearchReturnsWholeResponse(t *testing.T) // truncated/count survive
func TestVectorNon2xx(t *testing.T)
func TestHybridAndFulltextRoutes(t *testing.T)           // POST /api/v1/vector/{db}/hybrid and /fulltext
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**; doc comment on `Vector` gives the whole-response reasoning (spec §7, `facade/vector.py`) and notes `Fulltext` has no `truncated`. **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(go): vector, hybrid and full-text search`.

### Task 10: Time series, Grafana, PromQL — verify the defects, then wrap

**Files:**
- Create: `go/arcadedb/timeseries.go`, `go/arcadedb/dashboards.go`, `go/arcadedb/promql.go`
- Test: `go/arcadedb/timeseries_test.go`, `go/arcadedb/promql_test.go`

**Interfaces:**
- Produces:
  - `(*Database) TS() *TimeSeries`; `(*TimeSeries) Write(ctx, lineProtocol string, precision string) error` (`precision` `""` omitted; `ns|us|ms|s`; `text/plain`; expects 204); `Query(ctx, body map[string]any) (map[string]any, error)`; `Latest(ctx, typ, tag string) (map[string]any, error)` (`tag` `""` omitted).
  - `(*Database) Grafana() *Grafana`; `(*Grafana) Query(ctx, body map[string]any) (map[string]any, error)`.
  - `(*Database) PromQL() *PromQL`; `Query(ctx, params generated.PromQLQueryParams) (*generated.PromQLDataResponse, error)`; `QueryRange(ctx, params generated.PromQLQueryRangeParams) (*generated.PromQLDataResponse, error)`; `Labels(ctx) (*generated.PromQLLabelsResponse, error)`; `Series(ctx, params generated.PromQLSeriesParams) (*generated.PromQLSeriesResponse, error)`.

- [ ] **Step 1: Verify each defect against a live server (spec §8, "Verify, don't assume")**

Start `arcadedata/arcadedb:26.10.1-SNAPSHOT` with the e2e env, create a database and a time-series type, write two points, then through `Raw()`'s `...WithResponse` methods call `QueryTimeSeries` (raw and aggregated), `GetTimeSeriesLatest`, `QueryGrafana`, `ExecuteServerCommand`. Record for each: parses cleanly / parse error / silently wrong. Throwaway program under the scratchpad, not in the repo.

- [ ] **Step 2: Write the failing tests** (fake-server payloads with scalar elements, copied from the live responses in Step 1)

```go
func TestTSWriteSendsTextPlainAndPrecision(t *testing.T)
func TestTSQueryReturnsScalarsIntact(t *testing.T)    // rows [[1700000000000, 21.5]] survive as []any{float64,float64}
func TestTSLatestOmitsEmptyTag(t *testing.T)
func TestGrafanaQueryReturnsRawJSON(t *testing.T)
func TestPromQLSeriesSendsMatchArray(t *testing.T)    // wire param "match[]" repeated
func TestPromQLQueryPassesParams(t *testing.T)
```

- [ ] **Step 3: Implement.** For each path Step 1 found broken through the typed parser, call the plain `Client` and decode into `map[string]any`, with the "do not route back through the typed parser" doc comment (spec §8). For any path Step 1 found clean, return the result decoded the same way anyway only if the typed model loses scalar values; otherwise note in `go/CLAUDE.md` (Task 17) that the defect does not bite Go there.
- [ ] **Step 4: Run** `go test -run 'TS|Grafana|PromQL' -v ./` → PASS.
- [ ] **Step 5: Commit** `feat(go): time series, Grafana and PromQL namespaces`.

### Task 11: e2e module and CI job

**Files:**
- Create: `go/e2e/go.mod`, `go/e2e/go.sum`, `go/e2e/main_test.go`, `go/e2e/data_plane_test.go`, `go/e2e/batch_test.go`, `go/e2e/timeseries_test.go`
- Modify: `go/go.work` (add `./e2e`), `.github/workflows/ci-go.yml` (add `e2e` job)

**Interfaces:**
- Consumes: the whole facade.
- Produces: package `e2e` with `TestMain` starting one container; helpers `baseURL string`, `newServer(t) *arcadedb.Server`, `newDatabase(t) *arcadedb.Database` (creates a uniquely named database through `Raw().ClientInterface`'s plain `ExecuteServerCommand`, decoding the response itself — upstream defect 2).

- [ ] **Step 1: Create the module**

`go mod init github.com/ArcadeData/arcadedb-drivers/go/e2e`, `go 1.26`, `require github.com/ArcadeData/arcadedb-drivers/go/arcadedb v0.0.0` plus `replace github.com/ArcadeData/arcadedb-drivers/go/arcadedb => ../arcadedb` (without it `go mod tidy` would try the proxy), `go get github.com/testcontainers/testcontainers-go@latest`.

- [ ] **Step 2: Write `main_test.go`**

`DEFAULT_ARCADEDB_IMAGE` literal `"arcadedata/arcadedb:26.10.1-SNAPSHOT"` (a literal, so `adopt-contract-version.sh` rewrites it), env override `ARCADEDB_DOCKER_IMAGE`, `JAVA_OPTS` root password, port `2480/tcp`, wait strategy `wait.ForHTTP("/api/v1/ready").WithPort("2480/tcp").WithStatusCodeMatcher(func(s int) bool { return s == 204 })`, startup timeout 90s.

- [ ] **Step 3: Write the e2e tests, mirroring `python/e2e/test_data_plane.py` and `test_batch.py`**

```go
func TestRoundTrip(t *testing.T)                 // Ready, ListDatabases contains db, Exists, Command insert, Query reads it back
func TestTransactionCommitAndRollback(t *testing.T)
func TestBadQueryCarriesRequestID(t *testing.T)  // *ArcadeDBError with RequestID != ""
func TestVectorSearchHybridFulltext(t *testing.T) // incl. Truncated with a small K
func TestQueryStreamRecordsAndTrailer(t *testing.T) // rows equal buffered Query rows; low limit → Stats.Truncated
func TestCommandStreamReadOnly(t *testing.T)
func TestBatchLoadAndStream(t *testing.T)        // properties stored as real fields; progress before summary
func TestTimeSeriesWriteQueryLatest(t *testing.T)
func TestGrafanaAndPromQL(t *testing.T)
```

- [ ] **Step 4: Run** `cd go/e2e && go test -v ./...` (Docker required) → PASS.
- [ ] **Step 5: Add the `e2e` job to `ci-go.yml`**: `needs: build`, `timeout-minutes: 15`, Go `1.27`, `cd go/e2e && go test -v ./...`. Run `go/scripts/lint.sh && go/scripts/check-drift.sh` (e2e now in the workspace) → exit 0.
- [ ] **Step 6: Commit** `test(go): end-to-end suite against a real server`.

### Task 12: `adopt-contract-version.sh` learns Go

**Files:**
- Modify: `scripts/adopt-contract-version.sh:106-126` (LANGUAGES), after `:295-304` (new `version.go` rewrite)
- Test: `scripts/tests/test-contract-scripts.sh` (`make_fixture` at `:35-93`, new cases after `:283`)

**Interfaces:**
- Produces: LANGUAGES row `"go": {"suffixes": (".go", ".md"), "skip_dirs": {"generated", ".git", "docs"}}`; rewrite of `^(const ServerVersion = ")[^"]*(")` in every `go/*/version.go`, exactly once per file, else `SystemExit` naming the file and count.

- [ ] **Step 1: Extend `make_fixture`** with `go/arcadedb/version.go` holding `const Version = "0.1.0"` and `const ServerVersion = "${version}"`, and `go/arcadedb/generated/client.gen.go` containing the literal old version.
- [ ] **Step 2: Write the failing cases**

```
"rewrites ServerVersion in go/arcadedb/version.go"
"leaves Version in go/arcadedb/version.go untouched"          (still "0.1.0")
"leaves go/arcadedb/generated untouched"                       (literal old version still present)
"refuses a version.go carrying two ServerVersion consts"       (rc 1)
"refuses a version.go with no ServerVersion const"             (rc 1)
```

- [ ] **Step 3: Run** `scripts/tests/test-contract-scripts.sh` → the five new cases FAIL.
- [ ] **Step 4: Implement** mirroring the pyproject block. Also add `go` to the prose `CHANGES`-style lists if the script reports per language.
- [ ] **Step 5: Run** → `failed: 0`.
- [ ] **Step 6: Commit** `feat(scripts): adopt-contract-version.sh rewrites the Go client`.

### Task 13: License checker reads Go

**Files:**
- Modify: `scripts/check-licenses.py` (new collector beside `collect_python` `:526-563`; `main` `:617-642`; `report` total==0 message `:590-592`), `.github/workflows/license-compliance.yml` (paths `:12-34`; steps)
- Test: `scripts/tests/test_check_licenses.py`

**Interfaces:**
- Produces: `collect_go(go_dir: Path) -> list[Record]` — for `arcadedb` and `e2e` runs `go tool go-licenses report --include_tests ./...` in the module dir; for `tools` runs it over `go list tool`'s packages; parses the CSV (`module,url,license`); excludes modules prefixed `github.com/ArcadeData/arcadedb-drivers/`; dedupes by module; `Record("go", module, version, license, "go-licenses")` where version comes from `go list -m -json all`; raises `CollectorError` below `_MIN_PLAUSIBLE_GO_MODULES` and on a non-zero exit. `--ecosystem` choices gain `"go"`.

- [ ] **Step 1: Measure.** Run the three reports by hand; confirm `--include_tests` exists in v2.0.1 and that `e2e` reports testcontainers-go. If the flag does not exist, enumerate with `go list -deps -test ./...` and pass the package list instead; record which in the collector's docstring. Set `_MIN_PLAUSIBLE_GO_MODULES` to half the observed count, with the observed count in a comment.
- [ ] **Step 2: Write the failing tests** (monkeypatch `cl.subprocess.run` as `:295-313` does)

```python
def test_go_collector_parses_report_and_excludes_own_modules(...)
def test_go_collector_refuses_an_implausibly_small_module_set(...)
def test_go_collector_raises_on_tool_failure(...)
def test_go_unknown_license_is_a_violation(...)   # license "Unknown" → violation via check()
```

- [ ] **Step 3: Run** `cd python && uv run python -m pytest ../scripts/tests/test_check_licenses.py -v` → FAIL.
- [ ] **Step 4: Implement.** Then `./scripts/check-licenses.py --ecosystem go` → exit 0. A spelling miss goes into `NORMALISE`, never `ALLOWED_IDS`.
- [ ] **Step 5: Wire CI.** `license-compliance.yml` paths gain `"go/**/go.mod"` and `"go/**/go.sum"` in both lists; steps gain `actions/setup-go` (`1.26`) before the check. Run ruff and mypy on the two Python files as `ci-python.yml:57-58` does.
- [ ] **Step 6: Commit** `feat(licenses): check Go dependencies, tools and tests included`.

### Task 14: `release-packages.py` learns `goproxy`

**Files:**
- Modify: `scripts/release-packages.py` (`PACKAGES` `:49-90`, readers/writers `:119-199`, `REGISTRIES` `:211-226`, `check` `:271-287`, `set_version` `:292-305`, `_REGISTRY_URLS` `:308-311`, `is_published` `:330-345`), `.github/workflows/ci-release.yml` (paths `:10-27`)
- Test: `scripts/tests/test_release_packages.py`

**Interfaces:**
- Produces:
  - Row `{"id": "go-arcadedb", "language": "go", "manifest": "go/arcadedb/version.go", "lockfile": "", "registry": "goproxy", "name": "github.com/ArcadeData/arcadedb-drivers/go/arcadedb", "workflow": "publish-go.yml", "package_input": "arcadedb"}` appended last.
  - `_go_read_version`, `_go_read_server_version` (regex on the two consts, exactly once), `_go_write_version` (via `_sub_exactly_once`); lock callables raise `ReleaseError("goproxy has no lockfile")`.
  - `check` and `set_version` skip lockfile handling when `row["lockfile"] == ""`.
  - `check` also: for `goproxy` rows, `go.mod`'s `module` line beside the manifest equals `row["name"]`; and for a version with major ≥ 2, `row["name"]` ends in `/v<major>`.
  - `_goproxy_escape(path: str) -> str` (each uppercase letter → `!` + lowercase); URL `https://proxy.golang.org/{escaped}/@v/v{version}.info`.
  - `is_published`: 404 **and 410** → False (proxy answers 410 for unknown versions).

- [ ] **Step 1: Write the failing tests**

```python
def test_json_lists_every_package_with_every_field()  # update pinned id list: + "go-arcadedb"
def test_table_paths_exist_in_this_repository()      # empty lockfile skipped
def test_goproxy_escape():  assert rp._goproxy_escape("github.com/ArcadeData/x") == "github.com/!arcade!data/x"
def test_published_url_goproxy()                     # .../@v/v0.2.0.info
def test_is_published_maps_410_to_false()
def test_check_go_version_mismatch_reported(tmp_path)
def test_check_go_module_line_must_match_name(tmp_path)
def test_check_refuses_v2_without_path_suffix(tmp_path)
def test_set_writes_go_version_and_not_server_version(tmp_path)
def test_set_refuses_version_go_with_two_version_consts(tmp_path)
```
Extend `fixture_repo` (`:87-95`) with a `go/arcadedb/version.go` and `go.mod`.

- [ ] **Step 2: Run** `uv run --no-project --python 3.12 --with pytest python -m pytest scripts/tests/test_release_packages.py -v` → new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS; `./scripts/release-packages.py check "$(jq -r .version typescript/packages/driver/package.json)" --allow-snapshot` → exit 0 (Task 1 set `Version` to that value).
- [ ] **Step 5: Wire CI.** `ci-release.yml` paths gain `go/arcadedb/version.go` and `go/arcadedb/go.mod`.
- [ ] **Step 6: Commit** `feat(release): the Go module joins the lockstep table`.

### Task 15: `verify-go.sh`, `publish-go.yml`, and `release.yml`

**Files:**
- Create: `scripts/release/verify-go.sh`, `go/tools/cmd/checkzip/main.go`, `.github/workflows/publish-go.yml`
- Modify: `.github/workflows/release.yml` (`prepare-dry-run` `:172-224`)

**Interfaces:**
- Consumes: `go/scripts/lint.sh`, `go/scripts/check-drift.sh`, `release-packages.py`.
- Produces:
  - `verify-go.sh <arcadedb>`: package validated by `case` like `verify-pypi.sh:14-21`; runs lint, `go test -race ./...` in `go/arcadedb`, `check-drift.sh`, `ServerVersion` == OpenAPI `info.version`, then `go run ./cmd/checkzip <module path> v<Version> ../arcadedb` from `go/tools`.
  - `checkzip`: `zip.CheckDir(dir)` from `golang.org/x/mod/zip`; prints omitted/invalid files; exits 1 if any are invalid or if `go.mod`, `LICENSE`, `version.go` or `generated/client.gen.go` is omitted.

- [ ] **Step 1: Write `checkzip`, then prove it:** `go run ./cmd/checkzip ... ../arcadedb` → exit 0; with a file named `bad:name.go` in a temp copy → exit 1.
- [ ] **Step 2: Write `verify-go.sh`;** run `scripts/release/verify-go.sh arcadedb` → exit 0; `verify-go.sh nope` → exit 1 with the usage message.
- [ ] **Step 3: Write `publish-go.yml`.** Header comment modelled on `publish-python.yml`'s (dispatched by `release.yml`; hand dispatch is recovery only and bypasses the lockstep check; exact recovery command `gh workflow run publish-go.yml --ref v<version> -f package=arcadedb -f version=<version>`; a fetched version is permanent, the remedy is `retract`). `run-name: Publish Go ${{ inputs.package }} ${{ inputs.version }}`. Inputs: `package` (choice: `arcadedb`), `version` (string). `permissions: contents: write`. Steps: the ref-refusal step copied from `publish-python.yml:67-76` (workflow name adjusted); checkout with `fetch-depth: 0`; setup-go `1.26`; dispatch input equals `Version` const; `verify-go.sh`; tag step — `TAG=go/$PKG/v$VERSION`; if `git ls-remote --tags origin "refs/tags/$TAG^{}"` names `HEAD`'s commit, continue; if it names another, fail; else `git tag -a "$TAG" -m "$TAG" HEAD && git push origin "refs/tags/$TAG"`; proxy step — `GOPROXY=https://proxy.golang.org GOFLAGS=-mod=mod go list -m "<module>@v$VERSION"` retried, then poll `release-packages.py is-published go-arcadedb "$VERSION"` every 15s up to 10 minutes until `true`.
- [ ] **Step 4: Edit `release.yml` `prepare-dry-run`.** First step `Refuse a registry this workflow has no steps for`: `if: ${{ !contains(fromJSON('["npm","pypi","goproxy"]'), matrix.package.registry) }}` → `exit 1` with a message naming the registry. Add `Setup Go` (`if: matrix.package.registry == 'goproxy'`, `1.26`, `cache-dependency-path: go/**/go.sum`) and `Verify the package (Go)` running `./scripts/release/verify-go.sh "$PACKAGE_INPUT"`.
- [ ] **Step 5: Validate** all three workflows with `actionlint` (or YAML parse), and dry-run the tag step's shell logic locally against a throwaway bare remote (`git init --bare`) for the three cases: absent, same commit, other commit.
- [ ] **Step 6: Commit** `feat(release): publish the Go module by tag and proxy fetch`.

### Task 16: Contract watch, Dependabot, auto-merge guard

**Files:**
- Modify: `.github/workflows/contract-watch.yml` (setup `:107-137`, `Regenerate` `:153-158`, `CHANGES` `:160-180`, verify `:182-212`, summary `:214-231`, report env `:237-250`), `scripts/report-contract-watch.sh` (`:17-18`, `verify_line` `:29-40`, `finding_fingerprint` `:50-54`, main `:205-208`), `.github/dependabot.yml`, `.github/workflows/dependabot-auto-merge.yml:59`
- Test: `scripts/tests/test-contract-scripts.sh` (fingerprint cases `:468-511`)

**Interfaces:**
- Produces: `VERIFY_GO` consumed by `report-contract-watch.sh`, included in `finding_fingerprint` after `VERIFY_PY`, required in main's `:?` list; `CHANGED_FILES` and `CHANGES` path lists gain `go`.

- [ ] **Step 1: Write the failing fingerprint cases**

```
"fingerprint moves when the Go verdict flips alone"
"verify_line names the Go client when it fails"   (- `github.com/ArcadeData/arcadedb-drivers/go/arcadedb` (Go): **failing**)
"main refuses to run without VERIFY_GO"
```
- [ ] **Step 2: Run** `scripts/tests/test-contract-scripts.sh` → FAIL. **Step 3: Implement** the script changes (the "Both clients" wording becomes "All clients"). **Step 4: Run** → `failed: 0`.
- [ ] **Step 5: Edit `contract-watch.yml`:** setup-go `1.27`; `(cd go && ./scripts/generate.sh)` in `Regenerate`; `go` in the `git status --porcelain` list; step `verify_go` (`continue-on-error: true`, env `ARCADEDB_DOCKER_IMAGE`) running `go/scripts/lint.sh`, `(cd go/arcadedb && go test ./...)`, the coverage test, `(cd go/e2e && go test ./...)`; `VERIFY_GO` in the summary's quiet condition and the report env. Add a comment that the first run after this change posts one "the finding changed" comment.
- [ ] **Step 6: Edit `dependabot.yml`:** a `gomod` entry, `directories: ["/go/arcadedb", "/go/e2e", "/go/tools"]`, weekly, group `gomod-minor-and-patch` for `minor`/`patch`.
- [ ] **Step 7: Edit the auto-merge guard** `GUARDED` regex to add `go/arcadedb/generated/`; verify with `echo go/arcadedb/generated/client.gen.go | grep -qE "$GUARDED"` → match, and `go/tools/go.mod` → no match.
- [ ] **Step 8: Commit** `ci: contract watch, Dependabot and auto-merge cover the Go client`.

### Task 17: Documentation and the upstream issue

**Files:**
- Create: `go/CLAUDE.md`, `go/arcadedb/README.md`, scratchpad file `upstream-unreadableFiles-issue.md` (not committed)
- Modify: `CLAUDE.md` (opening paragraph, contracts section's `LANGUAGES` note, Workflows list, license section if Task 13 added entries), `README.md` (package list)

- [ ] **Step 1: Write `go/CLAUDE.md`** with the section shape of `python/CLAUDE.md`: Commands (`go/scripts/generate.sh`, `lint.sh`, `check-drift.sh`, `go test ./...` in `arcadedb`, `go test ./...` in `e2e`, running one test with `-run`), the three-module layout and why, Generation (config, overlay and its expiry test), Deliberate asymmetries (`ErrorMessage`, `Help`, callback transactions, `TxError` vs `errors.Join`, no sync/async split, no timeout by default, `Raw` null-vs-absent, no golangci-lint and why), the three contract defects with Task 10's recorded findings, and the release permanence note.
- [ ] **Step 2: Write `go/arcadedb/README.md`**: install (`go get github.com/ArcadeData/arcadedb-drivers/go/arcadedb@latest`), the §7 usage example, timeout warning, `Exists` caveat, streaming trailer, transactions, `Raw`, endpoints not wrapped, compatibility table (header only plus the current row as the other READMEs show it — adding rows stays a human decision), release paragraph (`set-release-version.sh` + `release.yml`; permanence; `retract`; v2 path).
- [ ] **Step 3: Update root `CLAUDE.md` and `README.md`**: `go/` as a language directory; `ci-go.yml` and `publish-go.yml` entries in Workflows written in the existing voice; `release.yml` entry mentions the fail-closed registry step; the third contract defect.
- [ ] **Step 4: Draft the upstream issue** for ArcadeData/arcadedb: title "OpenAPI: property named `/unreadableFiles` (leading slash) in the checksum response", the contract location, the effect on generated Go, the fix (rename to `unreadableFiles`). Leave it in the scratchpad for the human to file.
- [ ] **Step 5: Final verification**

Run: `go/scripts/lint.sh && go/scripts/check-drift.sh && (cd go/arcadedb && go test -race ./...) && (cd go/e2e && go test ./...) && scripts/tests/test-contract-scripts.sh && ./scripts/check-licenses.py && ./scripts/release-packages.py check "$(jq -r .version typescript/packages/driver/package.json)" --allow-snapshot && scripts/release/verify-go.sh arcadedb`
Expected: every command exits 0.

- [ ] **Step 6: Commit** `docs(go): workspace guide, package README and root docs`.
