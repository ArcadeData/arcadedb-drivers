# arcadedbgrpc (Go)

A Go gRPC client for [ArcadeDB](https://arcadedb.com), generated from ArcadeDB's protobuf contract
(`contracts/arcadedb-server-*.proto`), with a hand-written facade on top for authentication, the
four streaming RPCs, and transactions.

If you want an HTTP client instead, including one that works where gRPC cannot reach, see
[`go/arcadedb`](../arcadedb/README.md). The two modules share no code and no dependency: using one
never downloads the other's.

The module is `github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc`, fetched through the Go
module proxy like any other. Go has no registry to upload to: a version is the git tag
`go/arcadedbgrpc/v<version>`, pushed by `publish-go.yml` (dispatched by `release.yml` with
`package=arcadedbgrpc`) on the commit the repository-wide release tag names, and the first fetch
through `proxy.golang.org` is what publishes it.

Releases are cut for every package at once: bump all versions with
`scripts/set-release-version.sh <version>` in a reviewed PR, merge it, dispatch `release.yml` on
`main`, then review and publish the draft GitHub release it creates. Publishing the draft is what
starts the publish. See "Releases are permanent" below before cutting one.

## Requirements

- Go `>=1.26` (the `go` line in `go.mod`). The iterators below are range-over-func, Go 1.23+.
- An ArcadeDB server with the gRPC plugin enabled, at or near the version in the compatibility
  table below. The plugin is off by default: start the server with
  `-Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin` and it listens on
  50051.

## Installation

```bash
go get github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc@latest
```

The module requires only `google.golang.org/grpc` and `google.golang.org/protobuf` (and what those
two pull in). The code generator, the linters and the test containers live in separate modules and
never reach your build.

## Quick start

```go
package main

import (
	"context"
	"fmt"
	"log"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc/status"
)

func main() {
	ctx := context.Background()

	c, err := arcadedbgrpc.NewClient("localhost:50051",
		arcadedbgrpc.WithPasswordAuth("root", "playwithdata", "mydb"),
		arcadedbgrpc.WithInsecure()) // plaintext, opted into explicitly
	if err != nil {
		log.Fatal(err)
	}
	defer c.Close()

	resp, err := c.Raw().ExecuteQuery(ctx, &generated.ExecuteQueryRequest{
		Database: "mydb",
		Query:    "SELECT FROM Person WHERE age > 21",
		Language: "sql",
	})
	if err != nil {
		log.Fatal(status.Code(err), err)
	}
	for _, result := range resp.GetResults() {
		for _, rec := range result.GetRecords() {
			fmt.Println(rec.GetRid(), rec.GetProperties()["name"].GetStringValue())
		}
	}
}
```

`target` is grpc-go's native target form: `"localhost:50051"`, `"[::1]:50051"`, or a
resolver-prefixed name such as `"dns:///db.example.com:50051"` or `"unix:/path/to.sock"`. It is
**not** a URL, and `NewClient` refuses one starting with `http://` or `https://` rather than let
grpc-go read the scheme as an unknown resolver name. `NewClient` performs no I/O, like
`grpc.NewClient`: the connection is made on the first call. A `*Client` is safe for concurrent use,
and `Close` is safe to call twice (the second call returns nil).

`Raw()` is the generated client for `com.arcadedb.grpc.ArcadeDbService`, the data plane: every RPC
of that service is reachable through it. The contract's other service, `ArcadeDbAdminService`, the
control plane, is a separate handle, `RawAdmin()`; see "The control plane: `RawAdmin`" below. The
facade adds five things on top, for the RPCs the generated client alone handles badly:
`StreamQuery`, `TimeSeriesQuery`, `InsertStream`, `TimeSeriesWriteStream` and `Transaction`.
Everything else (the unary CRUD calls, `VectorSearch`/`HybridSearch`/`FullTextSearch`,
`TimeSeriesLatest`, `TimeSeriesWrite`, `BulkInsert`, `InsertBidirectional`, `GraphBatchLoad`) is
called directly through `Raw()`, exactly as above. The CRUD calls, the three searches,
`TimeSeriesLatest`, `StreamQuery`, `TimeSeriesQuery` and `InsertStream` also get a bound method on
`TxHandle` once a transaction is open; the rest never do.

Every call takes a `context.Context` first, and there is **no default timeout**: bound a call with
a `ctx` deadline. Every facade method also takes trailing `...grpc.CallOption`s, passed to grpc-go
unchanged. There is no async variant of anything: run calls in goroutines when you want them
concurrent.

## Authentication, and why `Raw()` is authenticated too

```go
arcadedbgrpc.WithBearerToken(token)                        // authorization: Bearer <token>
arcadedbgrpc.WithPasswordAuth("root", "playwithdata", "mydb") // x-arcade-user / x-arcade-password / x-arcade-database
```

`database` may be empty, and `x-arcade-database` is then not sent. An empty user or an empty token
is an error from `NewClient`. A later auth option replaces an earlier one.

Auth is installed as a pair of **connection** interceptors, one unary and one stream, not as
per-call metadata on the facade methods. Most RPCs are reachable only through `Raw()`, so per-call
metadata on the five facade methods would leave every other call silently anonymous; on the
connection, `c.Raw().ExecuteCommand(...)` carries the same metadata `c.StreamQuery(...)` does.
grpc-go splits interceptors by call shape, and the pair covers all four (unary, server-stream,
client-stream, bidi): installing only one would leave whole shapes anonymous, which is the defect
the Python client's async facade once shipped.

The metadata is **appended** to whatever the caller already set on the outgoing context, never
replacing it: a request id you add with `metadata.AppendToOutgoingContext` reaches the server
beside the auth pairs.

`grpc.PerRPCCredentials` is deliberately not used: grpc-go refuses to send it over a connection
without transport security, and password auth over an explicit plaintext connection is a
configuration this client supports.

### Plaintext, TLS, and the insecure-channel guard

Without transport credentials the connection is plaintext (`insecure.NewCredentials()`). That is
fine for a bearer token or for no auth at all, but a password would cross the wire as cleartext
metadata, so `NewClient` **refuses** to pair `WithPasswordAuth` with a plaintext connection unless
you say so (ArcadeData/arcadedb#5048):

```go
arcadedbgrpc.NewClient("localhost:50051",
	arcadedbgrpc.WithPasswordAuth("root", "playwithdata", ""))
// error: errors.Is(err, arcadedbgrpc.ErrInsecureChannel) - pass TLS, switch to a token, or opt in

arcadedbgrpc.NewClient("localhost:50051",
	arcadedbgrpc.WithPasswordAuth("root", "playwithdata", ""),
	arcadedbgrpc.WithInsecure())
// fine: you opted in

arcadedbgrpc.NewClient("db.example.com:50051",
	arcadedbgrpc.WithPasswordAuth("root", "playwithdata", "mydb"),
	arcadedbgrpc.WithTransportCredentials(credentials.NewTLS(&tls.Config{})))
// fine: the connection is encrypted, so there is nothing to opt into
```

The check keys on whether transport credentials were **stated**, never on inspecting the target. A
bearer token is not a password and never trips it.

**Pass TLS through `WithTransportCredentials`, not `WithDialOptions`.** `WithDialOptions` is the
escape hatch for anything this package has no option of its own for (keepalive, a custom dialer,
message size limits). A `grpc.WithTransportCredentials` given there is honoured and never
downgraded: the package's plaintext default is applied before your dial options, so it takes effect
only when nothing there overrides it. But the guards cannot see credentials inside
`WithDialOptions`, so they assume plaintext and stay closed: password auth and `RawAdmin` still
demand `WithTransportCredentials` or `WithInsecure`. When both carry transport credentials,
`WithTransportCredentials` wins.

`WithInsecure()` is the single explicit opt-in to carrying credentials over plaintext, and it
satisfies both this guard and the one on `RawAdmin` below.

## Streaming queries: `StreamQuery`

```go
for rec, err := range c.StreamQuery(ctx, &generated.StreamQueryRequest{
	Database:      "mydb",
	Query:         "SELECT FROM Person",
	Language:      "sql",
	RetrievalMode: generated.StreamQueryRequest_CURSOR,
	BatchSize:     500,
}) {
	if err != nil {
		return err // a grpc-go status error; records already yielded stay yielded
	}
	fmt.Println(rec.GetRid())
}
```

`StreamQuery` returns an `iter.Seq2[*generated.GrpcRecord, error]` that flattens the server's
`QueryResult` batches into one record at a time; batch boundaries are not surfaced. That is the
only thing it does: the request is sent as given, so it picks no default for `RetrievalMode` or
`BatchSize`. The three retrieval modes differ materially in memory and consistency, and only the
caller can judge which a query needs:

- `CURSOR` (the proto zero value): runs the query once and streams results as you iterate.
- `MATERIALIZE_ALL`: loads the whole result set on the server first, then emits it in batches.
- `PAGED`: re-issues the query with `LIMIT`/`SKIP` per batch.

The iterator is lazy and re-rangeable: nothing is sent until the first iteration, and **each range
issues a new RPC**, re-running the query. Treat it as single-use. Leaving the loop early (`break`,
`return`) cancels the server stream. A failure, including one in the middle of the stream, arrives
once as a final `(nil, err)` pair and ends the iteration.

## Time series: `TimeSeriesQuery` and `TimeSeriesWriteStream`

| RPC | Reached how |
| --- | --- |
| `TimeSeriesQuery` | `c.TimeSeriesQuery` outside a transaction, `tx.TimeSeriesQuery` bound to one |
| `TimeSeriesWriteStream` | `c.TimeSeriesWriteStream`, a client-stream wrapper; never on `TxHandle` |
| `TimeSeriesLatest` | `c.Raw().TimeSeriesLatest` outside a transaction, `tx.TimeSeriesLatest` bound to one |
| `TimeSeriesWrite` (the unary write) | `c.Raw().TimeSeriesWrite` only |

### `TimeSeriesQuery` yields whole messages

```go
for msg, err := range c.TimeSeriesQuery(ctx, &generated.TimeSeriesQueryRequest{
	Database: "mydb", Type: "Temperature", Limit: 10_000,
}) {
	if err != nil {
		return err
	}
	fmt.Println(len(msg.GetRows()))
	if msg.GetLast() && msg.GetTruncated() {
		log.Print("partial answer: the limit cut the series short")
	}
}
```

Unlike `StreamQuery`, it does not flatten: each `TimeSeriesQueryResult` is yielded whole, with its
rows, buckets and running total. Only the final message has `Last` set, and `Truncated` is
meaningful **only there**: it says the request's `limit` cut the answer short, so the stream does
not hold every matching row. Flattening to rows would throw that flag away. The iterator has
`StreamQuery`'s lazy, re-rangeable, cancel-on-break and error behaviour.

A tag name in `Tags` that is not one of the type's declared TAG columns is refused by the server
with `InvalidArgument` rather than silently widening the query, and a `Limit` above
`arcadedb.server.grpcTimeSeriesMaxResultRows` is refused with `ResourceExhausted` before the first
message. Both checks are the server's; this package validates neither.

### `TimeSeriesWriteStream`

```go
point := func(ts int64, v float64) *generated.TimeSeriesPoint {
	return &generated.TimeSeriesPoint{Timestamp: ts, Fields: map[string]*generated.GrpcValue{
		"value": {Kind: &generated.GrpcValue_DoubleValue{DoubleValue: v}},
	}}
}
points := func(yield func([]*generated.TimeSeriesPoint) bool) {
	yield([]*generated.TimeSeriesPoint{point(1000, 22.5), point(2000, 23.1)})
}

sum, err := c.TimeSeriesWriteStream(ctx, arcadedbgrpc.TimeSeriesWriteStreamRequest{
	Database:  "mydb",
	Type:      "Temperature",
	Precision: generated.TimeSeriesPrecision_TS_PRECISION_MILLISECONDS.Enum(),
	Chunks:    points,
})
if err != nil {
	return err
}
if sum.GetWritten() < sum.GetReceived() {
	log.Printf("dropped %d: unknown %v, not time series %v, unavailable %v",
		sum.GetDropped(), sum.GetUnknownTypes(), sum.GetNonTimeSeriesTypes(), sum.GetUnavailableTypes())
}
```

`Chunks` is an `iter.Seq[[]*generated.TimeSeriesPoint]`; each batch becomes exactly one wire
`TimeSeriesWriteChunk`.

**`Precision` is required, and it is a pointer.** The generated `TimeSeriesPrecision` has no
"unspecified" value: its zero value is `TS_PRECISION_MILLISECONDS`, a real unit, so a plain field
could not tell "you didn't say" from "you said milliseconds". That matters because ArcadeDB's other
ingest path, HTTP's `POST /api/v1/ts/{database}/write`, speaks InfluxDB line protocol, whose
omitted precision means **nanoseconds**, a factor of 10^6 away. An ingest ported from HTTP that
forgot the field would have every timestamp silently misread. A nil `Precision` is therefore an
error before any RPC is made; `.Enum()` on a generated constant gives you the pointer.

The same trap is wide open on `c.Raw().TimeSeriesWrite`, the unary write: its `Precision` is the
same enum with the same zero value, in a generated message this package cannot make any field
required on. Set it explicitly on every raw call.

`Database`, `Type`, `Precision` and `Credentials` are repeated on every chunk: the message has no
session, sequence or last field, and the server ignores `database` after the first chunk, so the
repetition is harmless and spares a first-chunk special case. One stream-wide `Type` cannot express
the contract's per-chunk default measurement; to mix measurements in one stream, set `Type` on each
`TimeSeriesPoint` instead. An empty `Chunks` sends **zero** wire chunks, and the server answers
with an all-zero summary, which is returned as is.

**A write that returns no error can still have dropped points.** The write is not atomic: each
measurement's batch commits its own shard transaction as it is appended. The summary carries
`Received`, `Written`, `Dropped`, and three separate reasons: `UnknownTypes` (no such type; create
it with `CREATE TIMESERIES TYPE`), `NonTimeSeriesTypes` (the type exists but is not a time-series
type) and `UnavailableTypes` (its storage engine failed to load). Read the summary.

## Streaming inserts: `InsertStream`

```go
person := func(name string) *generated.GrpcRecord {
	return &generated.GrpcRecord{Type: "Person", Properties: map[string]*generated.GrpcValue{
		"name": {Kind: &generated.GrpcValue_StringValue{StringValue: name}},
	}}
}
batches := func(yield func([]*generated.GrpcRecord) bool) {
	if !yield([]*generated.GrpcRecord{person("Alice")}) {
		return
	}
	yield([]*generated.GrpcRecord{person("Bob")})
}

sum, err := c.InsertStream(ctx, arcadedbgrpc.InsertStreamRequest{
	Database: "mydb",
	Options:  &generated.InsertOptions{TargetClass: "Person"},
	Chunks:   batches,
})
if err != nil {
	return err
}
fmt.Println(sum.GetInserted(), sum.GetFailed())
```

`Chunks` is an `iter.Seq[[]*generated.GrpcRecord]`; each batch becomes exactly one wire
`InsertChunk`, so how rows are batched, and when the next batch is produced, is your choice.
`InsertStream` owns only the envelope around those batches, which is easy to get wrong by hand:

- one `session_id` per call (16 random bytes, hex-encoded), stable for the whole stream;
- `chunk_seq` 1, 2, 3, ...;
- `Database` on the first chunk only, as the `.proto` specifies;
- your `Options`, `Credentials` and `Transaction` on every chunk, as given. `InsertStream` never
  sets `options.database`. Servers before 26.9.1, which are outside the compatibility table, read
  the database from `InsertOptions` alone (ArcadeData/arcadedb#6597): against them the stream
  reports its rows as received with `inserted=0`, as a successful call, and inserts nothing. 0.2.0
  mirrored `Database` into `options.database` to cover them; 0.3.0 retired the mirror;
- `last=true` on the final chunk only, found by one batch of lookahead, so a `nil` or empty batch
  in the middle of the sequence is sent as a zero-row chunk, never mistaken for the end.

Your `Options`, `Credentials` and `Transaction` are never modified. An empty input is not an error:
it sends one chunk with `chunk_seq` 1, `last=true` and no rows, and returns whatever summary the
server answers. The summary is returned unchanged.

Inside a transaction, call `tx.InsertStream` on the `TxHandle` instead: the same envelope, with
`Database` and `Transaction` bound to the handle's transaction, so the rows commit or roll back
with it. See "Transactions" below.

### Both client streams run your sequence on your goroutine

`InsertStream` and `TimeSeriesWriteStream` iterate your sequence on the calling goroutine, the one
grpc-go's `Send` runs on. There is no background writer, so a panic in your sequence surfaces from
the call itself, and nothing the call started outlives it: the sequence is always stopped before
the call returns, and if the RPC fails part-way the rows already sent stay sent and the rest are
never pulled.

Two consequences to know:

- **Cancelling `ctx` does not interrupt a sequence that is blocked producing its next batch.** The
  call regains control only when your sequence yields. A sequence that waits on a channel, a file
  or the network should watch `ctx` itself.
- **The summary, not a nil error, says how many rows landed.** grpc-go reports a `Send` on a stream
  the server has already ended as a bare `io.EOF`, with the real outcome on the receive side, so
  both wrappers answer a failed `Send` with `CloseAndRecv`'s result. A server-side failure therefore
  surfaces as its own status (`InvalidArgument`, `PermissionDenied`, ...), never as `io.EOF`; and a
  server that ends the stream early with a summary makes the call return that summary with a nil
  error. Read `Inserted`/`Failed` (or `Written`/`Dropped`) rather than trusting the nil.

## Transactions: `Transaction` and `TxHandle`

```go
err := c.Transaction(ctx, "mydb", func(tx *arcadedbgrpc.TxHandle) error {
	if _, err := tx.ExecuteCommand(ctx, &generated.ExecuteCommandRequest{
		Command:  "INSERT INTO Account SET balance = 100",
		Language: "sql",
	}); err != nil {
		return err // rolls back
	}
	_, err := tx.ExecuteQuery(ctx, &generated.ExecuteQueryRequest{
		Query:    "SELECT sum(balance) AS total FROM Account",
		Language: "sql",
	})
	return err // nil commits
})
```

`Transaction` calls `BeginTransaction`, hands `fn` a `*TxHandle` bound to the transaction id the
server returned, and commits or rolls back. Only calls made **through the handle** take part in the
transaction; calls through `c` or `c.Raw()` while `fn` runs do not. It is a callback rather than a
`Begin()`-returning handle because Go has no `with` or try-with-resources: a handle depends on every
caller remembering to end it on every path (the leaked-transaction footgun,
ArcadeData/arcadedb#5042), and a callback makes leaking one structurally impossible. The shape and
the contract are the same as `go/arcadedb`'s `Transaction`:

1. **`fn` returns nil: commit.**
2. **`fn` returns an error or panics: roll back**, then return the error or re-panic with the
   original value. If the rollback also fails after an error, the result is a
   `*arcadedbgrpc.TxError{Err, RollbackErr}` whose `Unwrap` returns **only** `Err`, so
   `status.Code(err)` and `errors.As` see the error your code produced, not the rollback's. After a
   panic, a failed rollback is discarded and the panic wins. `runtime.Goexit` (`t.FailNow` in a
   test) rolls back and is never mistaken for a nil return.
3. **The commit fails: a best-effort rollback** (its own error discarded), then the commit's status
   error, unwrapped.

Two more cases, ported from the Python client:

- **A blank transaction id from `BeginTransaction` is `ErrNoTransactionID`**, returned before `fn`
  runs: every call `fn` made would otherwise carry an empty id and run outside any transaction.
- **A commit answering `committed=false` is `ErrNotCommitted`**, wrapped with the server's message.
  That is how the server answers a commit for a transaction it has already reaped
  (`success=true, committed=false`, no error status); reporting success would silently lose `fn`'s
  writes. The check reads `committed`, never `success`. No rollback follows: there is nothing left
  to roll back.

Both rollbacks run under `context.WithoutCancel(ctx)`: the commonest reason `fn` fails is that
`ctx` was cancelled or timed out, and a rollback bound to that `ctx` would never reach the server.

### What the handle binds, and why it copies

`TxHandle` has the ten unary data-plane methods that carry a transaction (`ExecuteQuery`,
`ExecuteCommand`, `CreateRecord`, `UpdateRecord`, `DeleteRecord`, `LookupByRid`, `VectorSearch`,
`HybridSearch`, `FullTextSearch`, `TimeSeriesLatest`) plus bound `StreamQuery`, `TimeSeriesQuery` and
`InsertStream`. Each takes the request and sends a **copy** of it with `Database`
forced to the transaction's database and the whole `Transaction` field **replaced** by
`TransactionContext{TransactionId, Database}`. That override is the safety mechanism: it makes
transaction hijack (ArcadeData/arcadedb#5040) unrepeatable through the handle, since a request that
arrived naming another database or another transaction leaves naming this one. It is a replace,
never a merge, so inline `begin`/`commit`/`rollback` flags you set are wiped; the inline model is
still reachable through `c.Raw()`. A request's own `Credentials` field passes through unbound.

The request you pass in is **never mutated**. Binding it in place would leave it carrying this
transaction's id after the transaction ended, and reusing it, through `c.Raw()` or in a later
transaction, would send that dead id to the server: #5040's shape reached by aliasing. For the two
query streams, the copy is taken when you call the method, not when you range over the result.
`InsertStream` takes its `InsertStreamRequest` by value and replaces `Database` and `Transaction`
on that copy; your `Options` and `Credentials` are sent as given, `Transaction` on every chunk.

`tx.InsertStream`'s rows are discarded when the transaction rolls back and kept when it commits on
every server this module supports. Servers before 26.9.1, outside the compatibility table, ignored
an insert stream's `TransactionContext` (ArcadeData/arcadedb#6607), so against them its rows would
survive a rollback.

**Do not keep the handle.** Once `Transaction` returns, the handle's calls carry an id the server
has already committed or rolled back, and the server refuses them with `FailedPrecondition`
("Unknown or expired transaction id").

### What the handle does not have

`TimeSeriesWriteStream` is absent from `TxHandle`, as in the Python and TypeScript clients: it
cannot join a transaction at all, because `TimeSeriesWriteChunk` has no transaction field on the
wire. Neither does the unary `TimeSeriesWrite`. Only a contract change upstream could alter that.

`BulkInsert`, `InsertBidirectional` and `GraphBatchLoad` are raw-only at every level, as in the
Python and TypeScript clients.

## Vector, hybrid and full-text search

Outside a transaction, call `c.Raw().VectorSearch`, `.HybridSearch` and `.FullTextSearch`
directly; inside one, use the handle's methods of the same names, which bind the way every other
handle method does. There is deliberately no top-level `c.VectorSearch`: a unary RPC the generated
client already calls correctly gains nothing from a same-shaped alias.

Each returns the whole generated response, never unwrapped to `Results`: `VectorSearchResponse` and
`HybridSearchResponse` carry `Truncated` beside `Results`, `Count` and `Scoring`. `Truncated` is
true when the search's bounded candidate window filled, so more matches may exist than `Results`
holds. `FullTextSearchResponse` has no `Truncated` field at all. `EfSearch` and each request's
result limit (`K`, or `Limit` for full-text) are bounded by the server, not checked here; an
out-of-range value comes back as a status error.

## The control plane: `RawAdmin`

The contract's second service, `ArcadeDbAdminService`, is ArcadeDB's control plane: 44 RPCs for
database lifecycle, users, groups, API tokens, server and database settings, backups, the profiler,
cluster and shutdown operations, and the `Health` and `Ready` probes. `RawAdmin()` returns its
generated client, built on the same connection as `Raw()`:

```go
c, err := arcadedbgrpc.NewClient("db.example.com:50051",
	arcadedbgrpc.WithTransportCredentials(credentials.NewTLS(&tls.Config{})))
if err != nil {
	return err
}
defer c.Close()

admin, err := c.RawAdmin()
if err != nil {
	return err // ErrInsecureChannel: neither TLS nor WithInsecure
}
info, err := admin.GetServerInfo(ctx, &generated.GetServerInfoRequest{
	Credentials: &generated.DatabaseCredentials{Username: "root", Password: "playwithdata"},
})
```

No facade method wraps any of it, by design: 41 of the 44 are plain unary calls, and a wrapper would
be a renamed passthrough. `RestoreBackup`, `RestoreDatabase` and `ImportDatabase` are
server-streaming (progress messages), and you drive them through the generated stream client
yourself. `TestEveryRPCIsGenerated` holds the generated client to every RPC in the contract.

### Your auth option does not authenticate admin calls

42 of the 44 RPCs authenticate from a `DatabaseCredentials` field **inside the request message**,
set per call as in the example above, not from connection metadata. That is a property of the
contract, not of this client: `WithPasswordAuth` and `WithBearerToken` authenticate the **data
plane** only. Their metadata is still attached to admin calls, and the server ignores it there.
`Health` and `Ready` take empty request messages and need no credentials at all: they are
unauthenticated, as `GET /health` and `GET /ready` are over HTTP.

Authorization is the server's business and not uniform: `Ping`, `GetServerInfo`, `ListDatabases`,
`ExistsDatabase` and `GetDatabaseInfo` need only a valid account, `GetProgress` an account granted
the database it names, and every other RPC the server-admin (root) principal.

### The admin guard

Because those credentials travel in the request body, the insecure-channel guard on
`WithPasswordAuth` cannot see them. `RawAdmin` therefore carries its own: it returns
`ErrInsecureChannel` unless the client was built with `WithTransportCredentials` or `WithInsecure`.

```go
plain, _ := arcadedbgrpc.NewClient("localhost:50051") // neither TLS nor WithInsecure
plain.Raw().ExecuteQuery(ctx, req)                    // fine: the data plane is unaffected
_, err := plain.RawAdmin()                            // errors.Is(err, arcadedbgrpc.ErrInsecureChannel)
```

Four things about it are deliberate:

- **It is unconditional on auth.** The credentials at risk are in the request body, so the refusal
  is the same with a password, a token, or no auth option at all.
- **`Health` and `Ready` are refused too**, although they carry no credentials. The guard protects
  the client as a whole; carving two RPCs back out would mean wrapping the other 42. Probing health
  over plaintext costs one `WithInsecure()`.
- **It returns an error rather than refusing in `NewClient`**, so a plaintext client keeps working
  for the data plane; only asking for the admin client fails. (The Python client raises when its
  `raw_admin` property is read; Go returns an error, its idiom for a recoverable refusal.)
- **TLS passed only through `WithDialOptions` does not satisfy it**, because the guard cannot see
  it. Pass TLS through `WithTransportCredentials`.

The server has a separate check of its own on one RPC: `CreateApiToken`, whose response carries a
freshly minted token in cleartext, is refused with `FailedPrecondition` over a plaintext connection
to a remote host. `WithInsecure` lifts this client's guard, not that one.

## Errors: grpc-go status errors, not a package error type

A failed RPC returns grpc-go's status error unchanged, from `Raw()`, `RawAdmin()` and every facade
method alike. Match it with `status.Code(err)` or `status.FromError(err)`:

```go
_, err := c.Raw().ExecuteQuery(ctx, &generated.ExecuteQueryRequest{
	Database: "mydb", Query: "SELECT FROM NoSuchType", Language: "sql",
})
if st, ok := status.FromError(err); ok && st.Code() != codes.OK {
	fmt.Println(st.Code(), st.Message())
}
```

This is the same choice the Python gRPC client (`grpc.RpcError`) and the TypeScript one
(`ConnectError`) make. `go/arcadedb` needs its own `*ArcadeDBError` because the HTTP API has an
error envelope to unwrap; gRPC carries a failure as a status code and a message, and a package type
standing in between would add nothing.

The facade's own refusals, raised before or instead of an RPC, are:

| Error | When |
| --- | --- |
| `ErrInsecureChannel` | `NewClient` with a password over plaintext without `WithInsecure`; `RawAdmin` without TLS or `WithInsecure` |
| `ErrNoTransactionID` | `BeginTransaction` answered a blank transaction id; `fn` never ran |
| `ErrNotCommitted` | the commit answered `committed=false` |
| `*TxError` | `fn` failed and the rollback that followed also failed |

Match the sentinels with `errors.Is` (the returned errors wrap them with a message naming the way
out) and `*TxError` with `errors.As`. A malformed option, a URL target and a nil `Precision` are
plain errors from the call that received them.

## Contract version and compatibility

This module was generated from `contracts/arcadedb-server-26.11.1-SNAPSHOT.proto`, recorded in
`version.go` as `ServerVersion`:

```go
const ServerVersion = "26.11.1-SNAPSHOT"
```

| `github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc` | ArcadeDB server |
| --- | --- |
| 0.2.0 | 26.10.1 |
| 0.3.0 (unreleased) | 26.11.1-SNAPSHOT |

The module had no 0.1.0 release: it joined the lockstep at 0.2.0, its first published version.
This table is a historical record tied to a module version, not something derived automatically:
`scripts/adopt-contract-version.sh` deliberately does not touch it. Adding a row is a human
decision made at release time.

The client speaks ArcadeDB's gRPC API as described by that contract. Pointing it at a server on a
materially different release may work for the RPCs both versions share, but is not tested or
supported.

## Releases are permanent

A Go module version, once fetched through `proxy.golang.org`, is recorded in `sum.golang.org`, a
public append-only checksum log. It can be neither deleted nor replaced: moving or deleting the tag
afterwards changes nothing except to break anyone who fetches around the proxy. The only remedy for
a bad version is a `retract` directive in `go.mod`, shipped in the **next** version. That is why the
release checks the module zip before the tag exists, and why a fix is always a new version.

The module is tagged `go/arcadedbgrpc/v<version>` beside the repository-wide `v<version>`, because
the Go toolchain finds a module in a subdirectory only by a tag carrying that subdirectory's prefix.

When the lockstep version reaches 2.0.0, the module path becomes
`github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/v2` in that same release, and every import
changes with it, the `generated` package's included; the release tooling refuses a 2.0.0 or later
version on a path without the `/v2`.

## License

Apache-2.0.
