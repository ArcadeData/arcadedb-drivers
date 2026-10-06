# arcadedb (Go)

A Go HTTP client for [ArcadeDB](https://arcadedb.com), generated from ArcadeDB's OpenAPI contract,
with a hand-written facade on top for the data plane, transactions, streaming, batch loading, vector
search and time series.

The module is `github.com/ArcadeData/arcadedb-drivers/go/arcadedb`, fetched through the Go module
proxy like any other. Go has no registry to upload to: a version is the git tag
`go/arcadedb/v<version>`, pushed by `publish-go.yml` (dispatched by `release.yml`) on the commit
the repository-wide release tag names, and the first fetch through `proxy.golang.org` is what
publishes it.

Releases are cut for every package at once: bump all versions with
`scripts/set-release-version.sh <version>` in a reviewed PR, merge it, dispatch `release.yml` on
`main`, then review and publish the draft GitHub release it creates. Publishing the draft is what
starts the publish. See "Releases are permanent" below before cutting one.

## Requirements

- Go `>=1.26` (the `go` line in `go.mod`). The iterators below are range-over-func, Go 1.23+.
- An ArcadeDB server at or near the version in the compatibility table below.

## Installation

```bash
go get github.com/ArcadeData/arcadedb-drivers/go/arcadedb@latest
```

The module requires only the generated client's three runtime dependencies
(`github.com/oapi-codegen/runtime`, `github.com/apapsch/go-jsonmerge/v2`, `github.com/google/uuid`).
The test and tool dependencies live in separate modules and never reach your build.

## Quick start

```go
package main

import (
	"context"
	"fmt"
	"log"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
)

func main() {
	ctx := context.Background()

	srv, err := arcadedb.NewServer("http://localhost:2480",
		arcadedb.WithBasicAuth("root", "playwithdata")) // or arcadedb.WithBearerToken(token)
	if err != nil {
		log.Fatal(err)
	}
	defer srv.Close()

	db := srv.DB("mydb")

	env, err := db.Query(ctx, arcadedb.SQL,
		"SELECT FROM Person WHERE age > :min", map[string]any{"min": 18})
	if err != nil {
		log.Fatal(err)
	}
	if env.Truncated {
		log.Print("partial answer: narrow the query or raise the limit")
	}
	for _, row := range env.Result { // []map[string]any
		fmt.Println(row["name"])
	}
}
```

`NewServer` takes options: `WithBasicAuth`, `WithBearerToken`, `WithHeader` (added to every
request, overriding a built-in header of the same name) and `WithHTTPClient`. Every request also
carries `User-Agent: arcadedb-go/<version>`. A `*Server` is safe for concurrent use; `srv.DB(name)`
returns a handle and performs no request. `Close` releases idle connections, including those of a
client you passed in with `WithHTTPClient`, which may be shared.

Every call takes a `context.Context` first. There is no async variant of anything: run calls in
goroutines when you want them concurrent.

## No timeout by default

A `Server` built without `WithHTTPClient` uses a bare `http.Client`, which has **no timeout**: a
call against a stalled connection can block forever. That is Go's own default, and it matches the
other drivers in this repository (`fetch` has none; the Python driver passes `timeout=None`).
Deadlines belong to the context each call takes:

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
env, err := db.Query(ctx, arcadedb.SQL, "SELECT FROM Person", nil)
```

or pass a client of your own: `arcadedb.WithHTTPClient(&http.Client{Timeout: 30 * time.Second})`.
A client-level `Timeout` also cuts off a long `QueryStream` or `BatchLoadStream` mid-body, so for
streaming prefer a per-call context.

## The result envelope, and why `Truncated` matters

`Query` and `Command` do not return bare rows. They return the whole envelope:

```go
type QueryEnvelope struct {
	Result    []map[string]any
	Limit     int
	Returned  int
	Truncated bool
}
```

`Truncated` is `true` when the server's serializer hit its row cap while the query still had rows
to write: `Result` is then a partial answer, not a short-but-complete one, and the two are
indistinguishable by shape. Always check `Truncated` before treating `Result` as the whole answer.
`Query` accepts `arcadedb.WithLimit(n)` to set the cap for one call (`-1` for none); `Command` does
not take a limit, as in the other drivers. Raising the limit is not always the fix: a result larger
than the server's hard ceiling (`arcadedb.server.httpQueryMaxResultRows`) is refused with 413
rather than truncated, and past that ceiling a narrower filter is the only way forward.

When the server omits a field, the envelope reads `Result` as an empty, non-nil slice, `Limit` as
`-1` (uncapped), `Returned` as `0` and `Truncated` as `false`. The contract marks `limit`,
`returned` and `truncated` required and today's server sends all three, but this client does not
fail on a response that omits one: it applies the default. Those defaults are the most reassuring
possible reading of "the server did not say", so `Truncated == false` is only as good as the
server's promise to send it.

Rows are `map[string]any` decoded with `encoding/json`: numbers arrive as `float64`, so an integer
above 2^53 loses precision, exactly as in the TypeScript driver.

`QueryResponse.result` can also be a `{vertices, edges}` object under the two graph serializers.
The envelope cannot carry that shape, so `Query`/`Command` return an `*ArcadeDBError` if it ever
arrives. It cannot today: this client never sends a `serializer`, so the server always picks
`record`.

## Streaming a query or command: `QueryStream`/`CommandStream`

`QueryStream` and `CommandStream` ask for `application/x-ndjson` and return an
`iter.Seq2[StreamEvent, error]`. The request is issued on the first iteration, and again on every
later range over the same iterator, so treat it as single-use:

```go
for ev, err := range db.QueryStream(ctx, arcadedb.SQL, "SELECT FROM Person", nil) {
	if err != nil {
		return err // transport, decode, non-2xx, or an in-band error: yielded once, then the loop ends
	}
	if ev.Stats != nil {
		fmt.Println("returned", ev.Stats.Returned, "truncated", ev.Stats.Truncated)
		continue
	}
	use(ev.Record)
}
```

They yield **events**, not rows: each `StreamEvent` has exactly one of `Record` or `Stats` set. The
`Stats` trailer is always the last event of a complete stream and carries the same
`Limit`/`Returned`/`Truncated` the buffered envelope reports. A caller who reads only `Record`
loses the only way to tell a complete answer from a capped one, and a stream that ends **without**
a `Stats` event was cut short (a server write timeout, a dropped connection): the rows seen may be
a partial answer.

A failure after the 200 status line has been sent cannot be reported as an HTTP status, so the
server sends it in band, as an `{"error": ...}` line. This client yields it as the loop's `err`, an
`*ArcadeDBError` with `Status` 200 and the response's `X-Request-Id` as `RequestID`, exactly once,
and the iteration then stops. Rows yielded before
it stay delivered. Events of a kind this client does not know are skipped, so a newer server can
add kinds without breaking it.

Leaving the loop early, by `break`, `return` or a panic, closes the response body. Lines are split
on `\n` only - U+2028, U+2029 and U+0085 are legal raw characters inside a JSON string - and there
is no line-length limit.

`CommandStream` only ever succeeds for a **read-only** statement: the server refuses a mutating
one with 400 before it produces a row, because streamed rows would reach you before the surrounding
commit, which can still roll back. Use `Command` for writes.

## Batch loading: `BatchLoad`/`BatchLoadStream`

`POST /api/v1/batch/{database}` bulk-loads vertices and edges from one ndjson body. Rows go in as
two sequences, so vertices are always sent before edges whatever order you built them in (the
server resolves an edge's `From`/`To` only against ids declared earlier in the same payload):

```go
commitEvery := 5000
summary, err := db.BatchLoad(ctx,
	slices.Values([]arcadedb.VertexRow{
		{Type: "Person", ID: "p1", Properties: map[string]any{"name": "Alice"}},
	}),
	slices.Values([]arcadedb.EdgeRow{
		{Type: "Knows", From: "p1", To: "#1:7"},
	}),
	&generated.ExecuteBatchParams{CommitEvery: &commitEvery}) // params may be nil
```

`summary` is the server's JSON summary as a `map[string]any`, unaltered (`verticesCreated`,
`edgesCreated`, `idMapping`, ...). `ID` is a temporary id an edge in the same call can reference;
`From`/`To` also take a literal `#bucket:position` RID for a vertex already in the database.
Properties are flattened beside the control keys, and a property named `@type`, `@class`, `@id`,
`@from` or `@to` is refused with an error wrapping `ErrPropertyShadowsControlKey` (match it with
`errors.Is`). The Python and TypeScript drivers let such a property silently override the control
key; this one refuses the row.

The body is streamed: your sequences are consumed on a separate goroutine as the upload proceeds,
through a 64 KiB write buffer, so a load larger than memory is never buffered (rows reach the wire
a buffer at a time, not one by one). The call always waits for that goroutine before returning, so
no sequence is iterated after the call returns. A panic inside one of your sequences does not kill
the process from that goroutine: it aborts the upload and is re-raised, with its original value, on
the goroutine that called `BatchLoad` (or ranged over `BatchLoadStream`), where you can recover it.

### A load is not atomic

The server commits every `commitEvery` records, so a load that fails partway through leaves every
chunk before the failure **durably committed**: an error from `BatchLoad` can still correspond to
real data. Temporary ids are not keys, so **retrying the whole payload duplicates** whatever already
committed rather than resuming. The same holds for a row this client refuses: the upload stops at
that row, which is never sent, but rows before it may already have landed. Treat a failed load as
something to inspect and reconcile, never as something to re-send.

### Streaming the load

`BatchLoadStream` runs the same load but asks for ndjson and yields each event as a
`map[string]any`: a `progress` event as chunks commit, then one `summary` event carrying
`idMappingStreamed: true` in place of `idMapping`. Each progress event's `idMapping` is only the
fragment that chunk resolved and is never merged across events; collect the fragments yourself if
you need the whole mapping. A failure before the first line (a real non-2xx) and one after it (an
in-band `error` event) are both yielded as an `*ArcadeDBError`, once, and iteration then stops;
events yielded before it stay delivered, and those progress counts are how you learn what may have
landed. The iterator issues the request when you range over it, so ranging over it twice runs the
load twice. Breaking out of the loop aborts the upload.

`text/csv` is not exposed: both methods always send `application/x-ndjson`.

## Transactions

```go
err := db.Transaction(ctx, func(tx *arcadedb.Database) error {
	if _, err := tx.Command(ctx, arcadedb.SQL, "INSERT INTO Account SET balance = 100", nil); err != nil {
		return err
	}
	_, err := tx.Query(ctx, arcadedb.SQL, "SELECT sum(balance) AS total FROM Account", nil)
	return err
})
```

`Transaction` begins a server-side transaction and calls your function with a SECOND `*Database`
carrying its session id. Only calls made through that `tx` handle take part in the transaction; a
call made through the outer `db` auto-commits on its own, exactly as if no transaction were open.
Calling `tx.Transaction` inside the callback is refused by the server (409) rather than silently
opening an independent transaction.

It is a callback, not a `Begin()` that returns a handle, because Go has no `with` or
try-with-resources: a handle depends on every caller remembering `defer tx.Rollback()`, while a
callback cannot leak a session. The contract has three clauses:

- The function returns `nil`: the transaction commits.
- The function returns an error or panics: the transaction rolls back, and the error is returned
  or the panic re-raised with its original value. If the rollback also fails after an error, the
  result is a `*TxError{Err, RollbackErr}` whose `Unwrap` returns **only** `Err`, so `errors.Is`
  and `errors.As` see the error your code produced and never the rollback's; `RollbackErr` stays on
  the struct. (`errors.Join` is deliberately not used: it unwraps to both, and `errors.As` could
  then match the rollback's `*ArcadeDBError`.) After a panic, a failed rollback is discarded.
- The commit itself fails: a best-effort rollback is issued (its own error discarded) so the
  session is not left for `arcadedb.server.httpTxExpireTimeout` to reap, and the commit's error is
  returned.

Rollbacks run on `context.WithoutCancel(ctx)`, so a callback that failed because `ctx` was
cancelled still gets its transaction rolled back. `panic(nil)` is re-raised as the
`*runtime.PanicNilError` Go recovers it as; under `GODEBUG=panicnil=1` it recovers as `nil`, and
`Transaction` then rolls back and returns an error rather than `nil`, which would read as
committed.

**A batch load cannot join a transaction.** `POST /api/v1/batch/{database}` takes no session id,
so a load sent from `tx` would run outside the transaction and commit on its own, whatever the
transaction later did. `tx.BatchLoad` therefore returns `ErrBatchInTransaction`, and
`tx.BatchLoadStream` yields it once, before anything is sent or any sequence iterated; match it
with `errors.Is`. Run the load from the outer `db` instead, knowing it is not atomic with the
transaction.

## Vector, hybrid and full-text search: `db.Vector()`

```go
k := 5
res, err := db.Vector().Search(ctx, generated.VectorSearchRequest{
	IndexName: "Doc[embedding]", QueryVector: []float32{0.1, 0.2, 0.3}, K: &k,
})
if err != nil {
	return err
}
if res.Truncated {
	// the candidate window filled: more matches may exist, raise K
}
for _, hit := range res.Results {
	fmt.Println(hit.Rid, hit.Properties["name"]) // hit.Distance is a *float32: nil on a scored (sparse) hit
}
```

`Search`, `Hybrid` and `Fulltext` take the generated request struct and return the **whole**
generated response, never unwrapped to `Results`: `Truncated`, `Count` and `Scoring` stay attached
to the hits they describe. `Truncated` on a vector or hybrid search means the bounded candidate
window was filled and more matches may exist. It is a plain `bool` in the generated model, so a
response that omitted it would read `false`. `FullTextSearchResponse` has no `Truncated` at all:
full-text search has no candidate window to overflow. Hits are generated structs, not the
`map[string]any` rows `Query` returns; that difference is deliberate (`vector.go` argues it).
Leave `K`/`Limit` nil to get the server's own default of 10. Bounds on `K`, `Limit` and
`EfSearch` are enforced server-side, so a value out of range comes back as an `*ArcadeDBError`.

## Time series, Grafana and PromQL

```go
err := db.TS().Write(ctx, "Sensor,sensor=a value=1.5 1000\n", "ms") // "" precision means nanoseconds
res, err := db.TS().Query(ctx, map[string]any{"type": "Sensor"})    // map[string]any
latest, err := db.TS().Latest(ctx, "Sensor", "sensor:a")            // tag filter, "" for none
frames, err := db.Grafana().Query(ctx, map[string]any{"from": 0, "to": 10000,
	"targets": []map[string]any{{"refId": "A", "type": "Sensor"}}})
q, err := db.PromQL().Query(ctx, generated.PromQLQueryParams{Query: "Sensor"})
```

`TS().Query`, `TS().Latest` and `Grafana().Query` return the parsed JSON body as `map[string]any`
rather than a generated model. For `TS().Query` that is forced: the contract's raw/aggregated
`oneOf` has no discriminator, so the generated union accepts either shape as either, and the typed
raw model has no `truncated`. Check `res["truncated"]` on a raw query: it is `true` when the row
limit cut the answer short. The other two return a map for the same shape across the family. A 200
from Grafana can still carry a per-target failure in `results[refId]["error"]`.

A name in `TS().Query`'s `tags`, or `Latest`'s `tag`, that is not a TAG column of the type is
**refused** with a 400 rather than dropped, and `Latest`'s `tag` must be `name:value`; both are
checked server-side. A `Write` inside a `Transaction` joins the session only nominally: samples
are committed as they are appended, and a rollback does not remove them.

`db.PromQL()` uses the generated typed models (`Query`, `QueryRange`, `Labels`, `Series`). The
metric name for a time-series type is the **type name itself** (`Sensor`), not `Sensor_value`. Read
`Data.Result` according to `Data.ResultType` (`vector`, `matrix` or `scalar`).

## Two error models

Every facade method returns an `*ArcadeDBError` for a non-2xx response, except `Ready`, which
answers a 503 (up, but not ready) with `false` and no error. Match it with `errors.As`:

```go
_, err := db.Query(ctx, arcadedb.SQL, "SELECT FROM NoSuchType", nil)
var aerr *arcadedb.ArcadeDBError
if errors.As(err, &aerr) {
	fmt.Println(aerr.Status, aerr.ErrorMessage, aerr.Detail, aerr.RequestID, aerr.Help)
}
```

It carries `Status`, `ErrorMessage`, `Exception`, `Detail`, `RequestID`, `Help` and
`ExceptionArgs`. Every field but `Status` may be empty: parsing an error body never itself fails,
so an absent or non-JSON body yields an error with just the status. `RequestID` is the
`X-Request-Id` the server sets on every response. The body's `error` string is `ErrorMessage`, not
`Error`, because Go forbids a field and a method with one name; `Help` has no underscore, unlike the
Python driver's `help_`. An `*ArcadeDBError` is not always a non-2xx status: an in-band stream
error and an unrepresentable graph-serializer result both carry `Status` 200.

A 2xx answer with an empty or `null` body, where a method needs a document to return
(`ServerInfo`, the `Vector()`, `PromQL()`, `TS()` and `Grafana()` methods), is `ErrEmptyBody`,
matched with `errors.Is`, never a `nil` result with a `nil` error that would read as a successful
empty answer. `ListDatabases` and `Exists`, for which an empty body has a meaning, never return it.

`srv.Raw()`, the generated `*generated.ClientWithResponses`, does **not** return an error for a
non-2xx status. You inspect the response yourself:

```go
resp, err := srv.Raw().ListDatabasesWithResponse(ctx)
if err != nil {
	return err // transport failure only
}
if resp.StatusCode() >= 300 {
	// handle it yourself; Raw never turns a status into an error
}
```

Through `Raw()`, a nullable or optional field is a pointer, so `null` and an absent key both read
as `nil`; a field the contract marks required is a plain value, and an absent one reads as its zero
value. Mixing assumptions about which surface you are calling is the most common way to end up
with an unhandled failure or a silently ignored one.

## `Exists` cannot prove absence

```go
present, err := srv.Exists(ctx, "mydb")
```

`Exists` returns `false` both when the database does not exist and when it exists but the caller
is not authorized to see it: the server answers the two identically, so this client cannot tell
them apart. Do not treat `false` as proof that a database is absent. `ListDatabases` likewise lists
only what the caller may see.

`Health` succeeds only on 204; `Ready` returns `false` with no error on 503 (up, but not ready).

## Endpoints this client does not wrap

Everything the Python driver leaves to its `.raw` this client leaves to `Raw()`: the security,
cluster, auth, AI, MCP and metrics operations, and the two protobuf PromQL remote read/write routes
(reachable as `...WithBody` methods taking an `io.Reader`).

`POST /api/v1/server` (administrative commands, including `create database`) is not wrapped
either, and needs care through `Raw()`: the server answers `{"result": "ok"}`, a string, where the
contract declares an array, and the typed `ExecuteServerCommandWithResponse` reports `Limit`,
`Returned` and `Truncated` as zero values the wire never carried. Call the plain
`ExecuteServerCommandWithBody`, check the status, and read the body yourself.

## Contract version and compatibility

This module was generated from `contracts/arcadedb-openapi-26.10.1.json`, recorded in
`version.go` as `ServerVersion`:

```go
const ServerVersion = "26.10.1"
```

| `github.com/ArcadeData/arcadedb-drivers/go/arcadedb` | ArcadeDB server |
| --- | --- |
| 0.2.0 | 26.10.1 |

The Go module had no 0.1.0 release: it joins the lockstep at the next version every package ships
at. This table is a historical record tied to a module version, not something derived
automatically: `scripts/adopt-contract-version.sh` deliberately does not touch it. Adding a row is
a human decision made at release time.

The client speaks ArcadeDB's HTTP API as described by that contract. Pointing it at a server on a
materially different release may work for the endpoints both versions share, but is not tested or
supported.

## Releases are permanent

A Go module version, once fetched through `proxy.golang.org`, is recorded in `sum.golang.org`, a
public append-only checksum log. It can be neither deleted nor replaced: moving or deleting the tag
afterwards changes nothing except to break anyone who fetches around the proxy. The only remedy for
a bad version is a `retract` directive in `go.mod`, shipped in the **next** version. That is why the
release checks the module zip before the tag exists, and why a fix is always a new version.

The module is tagged `go/arcadedb/v<version>` beside the repository-wide `v<version>`, because the
Go toolchain finds a module in a subdirectory only by a tag carrying that subdirectory's prefix.

When the lockstep version reaches 2.0.0, the module path becomes
`github.com/ArcadeData/arcadedb-drivers/go/arcadedb/v2` in that same release, and every import
changes with it; the release tooling refuses a 2.0.0 or later version on a path without the `/v2`.

## License

Apache-2.0.
