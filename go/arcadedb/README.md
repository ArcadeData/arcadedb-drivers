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

The module requires the generated client's three runtime dependencies
(`github.com/oapi-codegen/runtime`, `github.com/apapsch/go-jsonmerge/v2`, `github.com/google/uuid`)
and one WebSocket library for the insert session, `github.com/coder/websocket` (ISC). The test and
tool dependencies live in separate modules and never reach your build.

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

The language is a `QueryLanguage`: `SQL`, `SQLScript` (several `;`-separated SQL statements run as
one script, usually through `Command`), `Cypher`, `Gremlin`, `GraphQL` and `Mongo`. It is a plain
string type, so any other language the server has enabled can be passed as `QueryLanguage("...")`;
a language the server does not have is refused by the server, not by this client.

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
	Result      []map[string]any
	Limit       int
	Returned    int
	Truncated   bool
	Explain     string
	ExplainPlan map[string]any
}
```

`Truncated` is `true` when the server's serializer hit its row cap while the query still had rows
to write: `Result` is then a partial answer, not a short-but-complete one, and the two are
indistinguishable by shape. Always check `Truncated` before treating `Result` as the whole answer.
`Query` accepts `arcadedb.WithLimit(n)` to set the cap for one call (`-1` for none); `Command` does
not take a limit, as in the other drivers. Raising the limit is not always the fix: a result larger
than the server's hard ceiling (`arcadedb.server.httpQueryMaxResultRows`) is refused with 413
rather than truncated, and past that ceiling a narrower filter is the only way forward.

### Labelling work: `WithQueryTag`

`arcadedb.WithQueryTag("nightly-report")` sends the `X-ArcadeDB-Query-Tag` request header, an
opaque label the server shows in `list queries` and that `terminate queries tag nightly-report`
stops. `srv.ListQueries` and `srv.TerminateQueriesByTag` issue those two commands for you (see
"Running work" below). `Query`, `QueryStream`, `Command`, `CommandStream` and `Transaction` all take it; a batch
load takes it as `generated.ExecuteBatchParams.XArcadeDBQueryTag`, beside the load's other options,
and sends it as the same header. An empty tag sends nothing. On `Transaction` the tag goes on the
begin request **only**: the server labels every statement of the transaction session that carries
no tag of its own, so the statements your callback runs inherit it without resending it, and a
statement given its own `WithQueryTag` inside the callback is labelled with that one instead.

```go
err := db.Transaction(ctx, func(tx *arcadedb.Database) error {
	_, err := tx.Command(ctx, arcadedb.SQL, "UPDATE Account SET flagged = true WHERE balance < 0", nil) // tagged "audit"
	return err
}, arcadedb.WithQueryTag("audit"))
```

The tag is not validated here: the contract allows at most 256 printable characters, but that is
the server's rule, and a 26.11.1-SNAPSHOT server accepted a 257-character tag without complaint, so
do not count on a refusal either. Repeating the rule client-side would only drift from the
server's. `WithLimit` is a `QueryOption` only, so passing it to `Command` does not compile.

When the server omits a field, the envelope reads `Result` as an empty, non-nil slice, `Limit` as
`-1` (uncapped), `Returned` as `0` and `Truncated` as `false`. The contract marks `limit`,
`returned` and `truncated` required and today's server sends all three, but this client does not
fail on a response that omits one: it applies the default. Those defaults are the most reassuring
possible reading of "the server did not say", so `Truncated == false` is only as good as the
server's promise to send it.

An `EXPLAIN` or `PROFILE` statement, or any statement run with `profileExecution`, answers with
its execution plan instead of rows: `Explain` holds it as indented text and `ExplainPlan` as the
same plan in structured form, while `Result` is empty and `Returned` is `0`. An empty `Result`
there is not "no rows matched"; the plan is the answer and is not repeated as a row. On any other
statement `Explain` is `""` and `ExplainPlan` is `nil`.

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
`*ArcadeDBError`, exactly once, and the iteration then stops. Rows yielded before it stay
delivered. Every field of the event reaches the error:

- `Status` is the event's own `status`, the one the buffered call would have answered the same
  failure with (503 for a retryable conflict, 409 for a duplicated key, 413 when
  `arcadedb.server.httpQueryMaxResultRows` cut the result short, 500 for an unexpected failure).
  Only an event that carries no usable status reads as 200; anything but a positive whole number
  counts as none (a batch stream falls back to 500 by the same rule). Key retries on it, never on the message.
- `ErrorMessage` is the event's classified `error` label (what a buffered error body carries in
  `error`), falling back to its raw `message`.
- `Exception`, `Detail` and `ExceptionArgs` are the same-named event fields.
- `RequestID` is the response's `X-Request-Id`, falling back to the event's `requestId`.
- `RetryAfter` is the event's `retryAfter`: a header can no longer be added once the stream has
  started, so the back-off travels in band. The event carries no commit index.

**Breaking in 0.3.0:** up to 0.2.0 an in-band error always carried `Status` 200, chosen when the
event had no status of its own. Code that recognised an in-band failure by `Status == 200` must
recognise it by the loop's `err` instead. Events of a kind this client does not know are skipped, so a newer server can
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

The contract declares the in-band error object's `commitIndex`, `status`, `exceptionArgs` and
`retryAfter`; the server also sends `error` and `exception`, and all six reach the error.
`RetryAfter` and `CommitIndex` come from `retryAfter` and `commitIndex` in band, or from the
`Retry-After` and `X-ArcadeDB-Commit-Index` headers of a non-2xx answer. `CommitIndex` on a failed
load bookmarks the chunks committed before the failure (see "Two error models" for using it).

`params.XArcadeDBQueryTag` labels the load with `X-ArcadeDB-Query-Tag` (see `WithQueryTag`); it is
a request header, never a query parameter.

`text/csv` is not exposed: both methods always send `application/x-ndjson`.

## Duplex insert session: `db.InsertSession`

`/ws` carries a duplex insert session: you send a chunk, read its acknowledgement, and only then
decide what to send next, including whether to commit at all. `BatchLoad`'s commit policy, by
contrast, is fixed by query parameters before the load starts. The endpoint is not in the OpenAPI
contract, so this is hand-written, over `github.com/coder/websocket`, and uses the `Server`'s
credentials, headers and `http.Client`.

```go
s, err := db.InsertSession(ctx, arcadedb.WithInsertTargetType("Person"))
if err != nil {
	return err
}
defer s.Close() // rolls back if the session is still open; idempotent

ack, err := s.SendChunk(ctx, []map[string]any{{"name": "Alice"}, {"@class": "Company", "name": "Acme"}})
if err != nil {
	return err
}
// ack.Inserted, ack.Failed, ack.Errors ... decide here whether to go on.
res, err := s.Commit(ctx) // res.Outcome == "commit"
```

A record takes its type from its own `@class` or from `WithInsertTargetType`; an edge names its
endpoints with `@from`/`@to`. Options: `WithInsertTransactionMode` (`InsertPerStream`, the default,
`InsertPerBatch`, `InsertPerRow`), `WithInsertConflictMode`, `WithInsertKeyColumns`,
`WithInsertUpdateColumnsOnConflict`, `WithInsertValidateOnly`, `WithOnInsertAck` (called with every
acknowledgement before `SendChunk` returns it) and `WithInsertFrameTimeout` (default 60 s per
exchange, on top of each call's `ctx`).

**One session per goroutine.** The session is not safe for concurrent use, and it never pipelines
frames: each call writes one frame and waits for its one answer.

**Nothing is durable until you say so.** In the default `per_stream` mode `Commit` makes every chunk
durable and `Rollback` (or `Close`, or a lost connection) discards them. `per_batch` and `per_row`
commit as they go; their `Summary.PartialCommit` is true and a rollback cannot take back an
acknowledged chunk.

**Sequence numbers are managed for you.** They start at 1, are contiguous, and advance only after the
server has accepted the chunk. A chunk the server refuses as a whole, for carrying more rows than
`arcadedb.server.wsMaxInsertChunkRows` or arriving out of sequence, is an `*InsertSessionError`; the
session stays open and the next chunk takes the same number, so split the batch and send it again.
A `per_batch` chunk whose own transaction failed to commit (a unique index it trips, say) comes back
as an ordinary acknowledgement with `WholeChunkFailed` true (one error with `RowIndex == -1`): the server keeps its watermark where
it was, so the number is not advanced here either, and the next `SendChunk` replaces that attempt. A
**row** the server cannot apply is not a refusal at all: it is counted in `Failed`, described in
`Errors`, and the rest of the chunk still goes in.

**A chunk over `wsMaxInsertFrameSize` is not refused, the connection is dropped.** The server closes
it (status 1009) instead of answering, so `SendChunk` returns a connection error, the session is
closed and the server rolls it back. Keep chunks below that byte limit; the row cap is the one to
reason about.

**Joining a transaction.** Inside `Transaction`, `tx.InsertSession(ctx, ..., WithJoinCurrentTransaction())`
writes into that transaction (mode `none`). The session's `Commit` and `Rollback` then answer
`Outcome == InsertOutcomeDetached` and decide nothing: the rows are durable only when `Transaction`
commits, and undone if it rolls back. Called on a handle that is not inside a transaction it returns
`ErrNoTransactionToJoin` before connecting.

**A late `error` frame is reported, not skipped.** The server pushes one unsolicited when its idle
sweep (`wsInsertSessionExpireTimeout`) rolls back a session you walked away from. The next call
returns it as an `*InsertSessionError` with `Title` "Insert session expired" and the session is then
closed, whatever that call was. `IsOpen` tells you.

**Some error frames end the session, others do not.** `InsertSessionError.SessionEnded` tells them
apart, and `IsOpen` follows it. It is false only for refusals that leave the session usable: the row
cap, a chunk that skips ahead, and malformed options or data. It is true, and the session is closed,
for an expiry; for a "Security error" (a revoked grant, which the server has already rolled back, or
a principal that is no longer valid, which also closes the connection); for an "Insert session
error" saying the session is "not found or expired" or "is closed"; and for an "Internal error". The
server sends no structured marker, so this is matched on the frame's title and detail.

**Timeouts and cancellation end the session.** If a frame's answer does not arrive within the frame
timeout or `ctx` is cancelled, the connection is dropped (the late answer could no longer be matched
to its frame) and the server rolls the session back. The error wraps `context.DeadlineExceeded` or
`context.Canceled`.

**Session ids.** Leave `WithInsertSessionID` out and the server generates one (`s.SessionID()`). An id
you choose lives in ONE server-wide namespace shared by every user, database and connection, so two
clients that both pick `batch-1` collide.

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
  session is not left for `arcadedb.server.httpSessionExpireTimeout` to reap, and the commit's
  error is returned.

Rollbacks run on `context.WithoutCancel(ctx)`, so a callback that failed because `ctx` was
cancelled still gets its transaction rolled back. `panic(nil)` is re-raised as the
`*runtime.PanicNilError` Go recovers it as; under `GODEBUG=panicnil=1` it recovers as `nil`, and
`Transaction` then rolls back and returns an error rather than `nil`, which would read as
committed.

**A rollback cannot undo a partial commit.** A statement inside the callback can publish a commit
while it runs: an explicit `BATCH n` boundary, or a statement with its own `COMMIT`. The server
then answers it with the response header `arcadedb-session-partial-commit: true`, and that part of
the transaction is already durable: none of the three clauses' rollbacks can take it back. Code
that replays a transaction block on a conflict must not replay one that partially committed. This
client does not surface the header; read it through `Raw()`.

`arcadedb.WithQueryTag(label)`, passed after the callback, labels the whole session: it is sent on
the begin only, and every statement in the callback that carries no tag of its own inherits it
server-side.

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

When `Write` drops samples the server answers 400 with a `TimeSeriesWriteError` body, and the call
returns an `*arcadedb.TimeSeriesWriteError`. It embeds the usual `*ArcadeDBError`, so `errors.As`
matches either type:

```go
var werr *arcadedb.TimeSeriesWriteError
if errors.As(err, &werr) {
	fmt.Println(werr.Written, werr.Dropped, werr.UnknownTypes, werr.UndeclaredKeys, werr.Status)
}
```

**A write is not atomic:** `Written` samples landed even though the call failed, and re-sending the
whole payload writes them twice. The four lists say why the rest were dropped: `UnknownTypes`
(measurements naming a type that does not exist), `NonTimeSeriesTypes` (a type that exists but is
not a time-series type), `UnavailableTypes` (a time-series type whose storage engine failed to
load; the server log says why) and `UndeclaredKeys` (tag or field keys the type does not declare in
that role, capped at 100 entries). Setting `arcadedb.timeSeriesUndeclaredKeys=ignore` on the server
stores such samples with the undeclared keys discarded instead of dropping them. A list the body
omits is `nil`, and an omitted `Written` or `Dropped` is 0. Only a 400 with a JSON-object body becomes a
`*TimeSeriesWriteError`; every other failure is a plain `*ArcadeDBError`.

`db.PromQL()` uses the generated typed models (`Query`, `QueryRange`, `Labels`, `LabelValues`,
`Series`). The metric name for a time-series type is the **type name itself** (`Sensor`), not
`Sensor_value`. Read `Data.Result` according to `Data.ResultType` (`vector`, `matrix` or `scalar`).

`LabelValues(ctx, name, params)` lists the values one label carries, restricted to the
`params.Start`/`params.End` range (Unix seconds, both optional; omit both for the whole series).
The name `"__name__"` is special: it lists the time-series **type names** rather than a tag's
values, since a type name is the metric name. The server answers an empty success, not an error, for a label no series carries, so an empty
list does not mean the name was misspelled. Pass the name unescaped; the client percent-encodes it.

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

It carries `Status`, `ErrorMessage`, `Exception`, `Detail`, `RequestID`, `Help`, `ExceptionArgs`,
`RetryAfter` and `CommitIndex`. Every field but `Status` may be empty: parsing an error body never
itself fails, so an absent or non-JSON body yields an error with just the status. `RequestID` is the
`X-Request-Id` the server sets on every response. The body's `error` string is `ErrorMessage`, not
`Error`, because Go forbids a field and a method with one name; `Help` has no underscore, unlike the
Python driver's `help_`. An `*ArcadeDBError` is not always a non-2xx status: an unrepresentable
graph-serializer result carries `Status` 200, and so does an in-band stream error whose event
reports no status of its own.

- `RetryAfter` (a `time.Duration`) is how long the server asked you to wait before retrying: the
  `Retry-After` header of a non-2xx response, or the `retryAfter` of an in-band stream or batch
  error. Only a whole number of seconds is read; an HTTP-date or a malformed value leaves it 0, so
  0 means "absent or no wait". The server sends it on a 503 when the node cannot run the request
  yet (a snapshot install, say) and on a 409 for an identical request still in flight.
- `CommitIndex` (an `int64`) is the last applied Raft index: the `X-ArcadeDB-Commit-Index` header
  of a non-2xx response, or the `commitIndex` of an in-band batch error. It is 0 when absent, which
  it always is on a standalone (non-replicated) database. It is still a valid read-after barrier on
  an error: send it back as the `X-ArcadeDB-Read-After` request header (through `Raw()`; the facade
  has no per-call header) and a later read sees everything committed up to it, a failed batch load's earlier
  chunks included.

**409 has two meanings.** "An identical request is still in flight" is retryable after
`RetryAfter`, and carries `Exception` `...RequestStillInFlightException` and a `Retry-After`. "Query
terminated", by `terminate query`, `terminate queries` or `terminate transaction`, had its writes
rolled back and must **not** be retried. This client retries neither; retry logic of your own must
tell them apart by `Exception` or `RetryAfter`, never by `Status` alone.

`TS().Write` returns a `*TimeSeriesWriteError`, which embeds `*ArcadeDBError`, for a 400 (see the
time-series section).

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

## Administration: databases, users and groups

```go
if err := srv.CreateDatabase(ctx, "tenant_a"); err != nil { ... }
err := srv.CreateUser(ctx, "alice", "a-long-password",
	map[string][]string{"tenant_a": {"admin"}}) // database ("*" = every database) -> groups
users, err := srv.ListUsers(ctx)
err = srv.UpdateUser(ctx, "alice", arcadedb.UserUpdate{Password: "another-password"})
err = srv.DropUser(ctx, "alice")
err = srv.DropDatabase(ctx, "tenant_a")
```

All of these are root-only, and every failure is an `*ArcadeDBError`, as for any facade method.
Users and groups have dedicated endpoints with a structured body (`/api/v1/server/users`,
`/api/v1/server/groups`): `CreateUser`, `UpdateUser`, `DropUser`, `ListUsers`, `SaveGroup`,
`DeleteGroup`, `ListGroups`. Databases have none, so `CreateDatabase` and `DropDatabase` send
`create database <name>` and `drop database <name>` through `POST /api/v1/server`. They refuse an
empty name, or one with leading or trailing white space, with `ErrInvalidName` before sending
anything, because the server trims the name it reads out of the command and would act on a
different database than the one you named. Anything else in the name is sent as given, embedded
spaces included: one request runs one command, so a name cannot smuggle in a second command, but
validate a name built from untrusted input yourself.

**"Already exists" is a 409 for users and databases alike.** Both statuses were measured against a
real server; they are what the e2e suite pins.

- A user that already exists is a **409** (`ErrorMessage` "User already exists"), so a 409 from
  `CreateUser` means "already there" and create-if-absent can check for it. Servers built before
  ArcadeData/arcadedb#10076 answer **403** "Security error" instead, which is also what a
  non-root caller gets; against those, do not read 403 as "already exists".
- A database that already exists is a **409** too (`ErrorMessage` "Database already exists", the
  name in `Detail`). Servers built before ArcadeData/arcadedb#10079 answer **400** "Cannot
  execute command" instead, the status every invalid server command gets; against those,
  ask `Exists` first to create a database only when it is missing (as root it sees every database,
  so its `false` is reliable there), knowing another client can still create it in between.

`UpdateUser` leaves a zero field alone: an empty `Password` keeps the current one, and a nil
`Databases` keeps the current assignments, while a non-nil empty map removes them all.

`srv.ServerCommand(ctx, command)` runs any other server command and returns the whole JSON body as
a `map[string]any`. It decodes the body itself rather than through the generated typed parser,
because the contract declares an array `result` where administrative commands answer
`{"result": "ok"}` and other commands answer shapes of their own. The command string is sent as
given.

## Running work: list and terminate queries and transactions, and `Progress`

```go
qs, err := srv.ListQueries(ctx, arcadedb.ListQueriesOptions{Tag: "nightly-report"}) // or Database, or neither
rs, err := srv.TerminateQueriesByTag(ctx, "nightly-report", arcadedb.TerminateOptions{Wait: 3 * time.Second})
r, err := srv.TerminateQuery(ctx, qs[0].ID, arcadedb.TerminateOptions{})
txs, err := srv.ListTransactions(ctx)
r, err = srv.TerminateTransaction(ctx, txs[0].ID)
p, err := srv.DB("tenant_a").Progress(ctx) // long-running maintenance operations, step by step
```

Unlike the administration methods above, these are open to **any authenticated user**: root sees
and stops every statement, another user only their own, and someone else's statement is answered
`QueryNotFound`, never "forbidden". They go through `POST /api/v1/server`, and `Progress` through
`GET /api/v1/progress/{database}`.

**Each server sees only its own work.** None of these is forwarded to the cluster leader. Behind
a load balancer, the server this client reaches may not be the one running the statement, and
then `ListQueries` does not show it and terminating it answers `QueryNotFound`.

A terminate waits for the statements to stop, up to `TerminateOptions.Wait` (zero leaves the
server's default of 5 seconds, and the server caps it at 10), then answers each with a
`QueryStatus`. **Which one you get decides whether you have anything to undo:**

| status | meaning |
|---|---|
| `QueryTerminated` | it stopped, and what it wrote was rolled back |
| `QueryCompleted` | it finished on its own before it noticed, so **what it did stands** |
| `QueryTerminating` | not stopped yet when the wait ended; some statements (SQL `SLEEP`, for one) notice only when they end, so the request's own outcome is the answer |
| `QueryNotFound` | no such statement on this server, or another user's |

Terminating a **command** inside a transaction ends the transaction too, rolling it back, while
terminating a read leaves it open; `TerminateResult.SessionID` and `SessionOpen` say which, and
`SessionOpen` is only the state at the time of the answer for a `QueryTerminating` statement. A
script counts as a command.

**The stopped request gets a 409, and `arcadedb.IsQueryTerminated(err)` recognises it.** The server
answers it 409 "Query terminated", but a 409 is also what a request still in flight under the same
`X-Request-Id` gets, so the status alone cannot tell "someone stopped me" from a conflict.
`IsQueryTerminated` matches the error's `Exception`, `com.arcadedb.exception.QueryTerminatedException`,
which the server sends as a structured field, not the message text. It is not retryable: somebody
stopped this work on purpose.

**`TerminateTransaction` does not reach the client that owned the transaction at commit.** It rolls
the transaction back, and a statement sent on it afterwards gets a 404, but a commit naming the
vanished session is answered 204, exactly like a real commit: a `Transaction` whose callback ran no
statement after the terminate returns nil for work that is gone. Measured against
26.11.1-SNAPSHOT and pinned by the e2e suite.

Ids, session ids and the `Database` filter must not be empty (where required) or contain a space
or control character (anything at or below U+0020), because the server reads each as one word; a
tag must not start or end with one, because the server trims it. A no-break space is not one, as
the server sees it. Each is refused with `ErrInvalidName` before anything is sent.
A tag is otherwise sent as given, spaces and quotes included: the server takes the rest of the
command as the tag.

`Progress` returns the generated `*generated.ProgressResponse`, whose `Result` is empty when
nothing is running. The server reads a lock-free snapshot, so polling it at any rate cannot slow
down the operation being watched.

## Sessions and API tokens

```go
// Per-user isolation: log in as the user once, then keep a client holding only the token.
login, err := srv.LoginAs(ctx, "alice", "a-long-password") // or srv.Login(ctx): the client's own credentials
alice := srv.WithToken(login.Token)                      // srv itself is unchanged
dbs, err := alice.ListDatabases(ctx)                     // only what alice may see
err = alice.Logout(ctx)                                  // the token is now refused everywhere

// A long-lived machine credential (root only).
created, err := srv.CreateAPIToken(ctx, arcadedb.APITokenRequest{Name: "ci", Database: "tenant_a"})
store(created.Token)                                     // the only time the plaintext exists
tokens, err := srv.ListAPITokens(ctx)                    // metadata only, never the token
err = srv.DeleteAPIToken(ctx, created.TokenHash)         // by hash, never by token
```

`Login` and `LoginAs` return the session token (prefixed `AU-`) and leave the client alone;
`WithToken` returns a **new** `Server` presenting it as a bearer token, sharing the original's base
URL, extra headers and `http.Client`. Nothing mutates a shared client's headers, so one root
client can hand out a token client per user from many goroutines. A token is a credential: whoever
holds it acts as that user until it is logged out or the server drops it. Keeping the token rather
than the password is the point.

The server drops a session on its own in three cases, after which the token gets a 401 like a
logged-out one:

- after 30 minutes without a request (`arcadedb.server.httpAuthSessionExpireTimeout`; each request
  restarts the clock), and, only if `arcadedb.server.httpAuthSessionAbsoluteTimeout` is set, that
  long after login whatever the activity;
- **when the same user logs in a 101st time**: each user holds at most 100 sessions
  (`arcadedb.server.httpAuthSessionMaxPerUser`), and a further login silently evicts that user's
  oldest. Log in once per user and reuse the token, not once per request;
- never by a count across users: past 10,000 sessions in all (`arcadedb.server.httpAuthSessionMax`)
  a new login is refused with a **503** instead, and existing sessions are kept.

What each failure looks like, measured against a real server and pinned by the e2e suite:

- **Wrong Basic credentials are a 403** "Security error", not a 401. The server answers every
  failed password check that way, on every endpoint, so a `LoginAs` 403 cannot be told apart from
  a forbidden user (ArcadeData/arcadedb#10109 asks for 401). **401** is what an invalid, expired or
  logged-out bearer token gets.
- **`Logout` only ends a session token.** The server answers 204 to a logout carrying Basic
  credentials or an API token and invalidates nothing, so `Logout` on a client that does not
  present an `AU-` token returns `ErrNotSessionToken` without sending anything. Logging out a
  token that is no longer valid is a 401.
- **`ListSessions` is root-only** (403 otherwise) and lists every user's live session token. Treat
  its result as you would the users' passwords. These are login sessions, not the transaction
  sessions `Transaction` opens.

API tokens:

- **The plaintext is returned exactly once**, in `CreatedAPIToken.Token`. The server stores only
  its SHA-256 hash, so a lost token cannot be recovered, only deleted and reissued. This client
  never logs or keeps it.
- **`DeleteAPIToken` takes the hash** (`TokenHash`, from `ListAPITokens` or `CreateAPIToken`).
  Anything but 64 lowercase hexadecimal characters is refused with `ErrInvalidTokenHash` before a
  request is sent, because the argument travels in the query string, where proxies and access logs
  record it, and the likeliest mistake is the plaintext token. The error does not repeat the
  argument. A hash no token has is a **404**, a status the contract does not list (ArcadeData/arcadedb#10110).
- **A taken name is a 409.** The contract describes its 409 only as a replayed `X-Request-Id`;
  the server also uses it for a duplicate name.
- **412 means the transport is not confidential.** With
  `arcadedb.server.apiTokenRequireSecureTransport` on, the server refuses to send a token back over
  cleartext HTTP to a non-loopback client, unless a proxy listed in
  `arcadedb.server.apiTokenTrustedProxies` terminated TLS. The setting is off by default until
  ArcadeDB 27.1.1, which turns it on; until then such a mint succeeds and the server logs a warning.
- `ExpiresAt` is the zero `time.Time` for a token that never expires. An expired token
  authenticates nobody, and stays in `ListAPITokens` (with `Expired` set) until the next token
  change retires it. `Permissions` takes the shape a group's `types` map takes.
- `Logout` on a client holding an API token returns `ErrNotSessionToken`: an API token is revoked
  with `DeleteAPIToken`, not logged out.

## Endpoints this client does not wrap

Everything the Python driver leaves to its `.raw` this client leaves to `Raw()`: the cluster, AI,
MCP and metrics operations, and the two protobuf PromQL remote read/write routes (reachable as
`...WithBody` methods taking an `io.Reader`).

The cluster override endpoints are raw-only on purpose: `AcceptClusterDatabaseCopy` (`POST
/api/v1/cluster/accept-copy/{database}`), `AcceptClusterDivergedDatabase` (`POST
/api/v1/cluster/accept-diverged/{database}`) and `AcceptClusterStaleSnapshot` (`POST
/api/v1/cluster/accept-stale-snapshot`) are root-only operator overrides that accept a copy of the
data without a resync. No facade method wraps any `/cluster/*` endpoint.

Through `Raw()`, `POST /api/v1/server` needs care: the server answers `{"result": "ok"}`, a
string, where the contract declares an array, and the typed `ExecuteServerCommandWithResponse`
reports `Limit`, `Returned` and `Truncated` as zero values the wire never carried. Use
`srv.ServerCommand` (above) instead.

## Contract version and compatibility

This module was generated from `contracts/arcadedb-openapi-26.11.1-SNAPSHOT.json`, recorded in
`version.go` as `ServerVersion`:

```go
const ServerVersion = "26.11.1-SNAPSHOT"
```

| `github.com/ArcadeData/arcadedb-drivers/go/arcadedb` | ArcadeDB server |
| --- | --- |
| 0.2.0 | 26.10.1 |
| 0.3.0 (unreleased) | 26.11.1-SNAPSHOT |

The Go module had no 0.1.0 release: it joined the lockstep at 0.2.0, its first published
version. This table is a historical record tied to a module version, not something derived
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
