# @arcadedb/driver

A TypeScript/JavaScript HTTP client for [ArcadeDB](https://arcadedb.com), generated from ArcadeDB's
OpenAPI contract.

If your workload is throughput-sensitive server-to-server streaming instead - large query result
sets, bulk inserts - see [`@arcadedb/driver-grpc`](../driver-grpc/README.md), which streams
natively over gRPC rather than paging through repeated HTTP calls.

Published on npm as [`@arcadedb/driver`](https://www.npmjs.com/package/@arcadedb/driver), with a
provenance attestation: every release is built and published by `publish.yml` (dispatched by
`release.yml`) from a clean checkout of this repository, never from anyone's laptop.

Releases are cut for every package at once: bump all versions with
`scripts/set-release-version.sh <version>` in a reviewed PR, merge it, dispatch `release.yml` on
`main`, then review and publish the draft GitHub release it creates. Publishing the draft is what
starts the registry publish.

## Requirements

- Node.js `>=20`.
- ESM only. The package has no CommonJS build and no `require()` entry point; import it with
  `import`, not `require`.

## Installation

```bash
npm install @arcadedb/driver
```

## Quick start

```ts
import { createClient, basicAuth } from "@arcadedb/driver";

const server = createClient({
  baseUrl: "http://localhost:2480",
  auth: basicAuth("root", "playwithdata"),
});

const db = server.db("mydb");
const { result } = await db.query({
  language: "sql",
  command: "SELECT FROM Person WHERE age > ?",
  params: { 0: 21 },
});
```

`language` is a `QueryLanguage`: `"sql"`, `"sqlscript"` (several `;`-separated SQL statements run as
one script, usually through `command`), `"cypher"`, `"gremlin"`, `"graphql"` or `"mongo"`.

A bearer token (for example, a session token from `server.login()`; see "Sessions and API
tokens") works the same way:

```ts
import { createClient, bearerAuth } from "@arcadedb/driver";

const server = createClient({
  baseUrl: "http://localhost:2480",
  auth: bearerAuth("AU-..."),
});
```

## The result envelope, and why `truncated` matters

`query` and `command` do not return bare rows. They return the whole response envelope:

```ts
interface QueryEnvelope<T> {
  result: T[];
  limit: number;
  returned: number;
  truncated: boolean;
  explain?: string; // EXPLAIN / PROFILE only
  explainPlan?: Record<string, unknown>; // present exactly when `explain` is
}
```

`truncated` is `true` when the server's serializer hit its row cap while a query still had more
rows to write - `result` is then a partial answer, not a short-but-complete one. A client that
returned only `result` would hand back an array a caller cannot tell apart from a complete result
set; the array looks the same shape either way. Always check `truncated` before treating `result`
as the whole answer, and re-run with a narrower filter or a higher `limit` (an option on both
`query` and `command`, and their streaming twins) when it is `true` - though a value large enough to exceed the server's hard
ceiling (`arcadedb.server.httpQueryMaxResultRows`) is refused with 413 rather than truncated, so a
narrower filter is the only fix once you're past that ceiling.

`truncated === false` used to be a client-side default rather than a server guarantee: until
26.10.1, `QueryResponse` declared no required fields, so `limit`, `returned` and
`truncated` were all synthesised when the response omitted them. That caveat is retired. The
schema now marks all three **required** and the server sends all three on every query and
command. `result` stayed optional and still defaults to `[]`.

`result` also became a **union** in the same release: an array of rows under the default `record`
serializer, and a single `{ vertices, edges }` object - plus `records` under `studio` - under the
two graph serializers. `QueryEnvelope<T>["result"]` is `T[]` and cannot carry the second shape,
so `query`/`command` throw an `ArcadeDBError` if it ever arrives. It cannot today: this client
sends no `serializer` field, so the server always picks `record`.

An `EXPLAIN` or `PROFILE` statement (or any statement run with `profileExecution`) answers with
its execution plan instead of rows: `explain` holds it as indented text, one line per step, and
`explainPlan` holds the same plan in structured form. `result` is then empty and `returned` is
`0` - the plan is the answer and is not repeated as a row - so an empty `result` there does not
mean "no rows matched". Both keys are absent on every other answer.

## Streaming a query or command: `queryStream`/`commandStream`

`query` and `command` buffer the whole result server-side before answering. `queryStream` and
`commandStream` are a separate pair of methods for the same two endpoints, requesting
`application/x-ndjson` instead of `application/json` and handing back an `AsyncGenerator` a caller
`for await`s over:

```ts
for await (const event of db.queryStream({ language: "sql", command: "SELECT FROM Person" })) {
  if (event.record) console.log(event.record);
  if (event.stats) console.log(`returned ${event.stats.returned}, truncated: ${event.stats.truncated}`);
}
```

They yield **events**, not rows. Each `NdJsonQueryEvent` carries exactly one of `record` (one
result row, shaped like an element of `query`'s `result` array), `stats`, or `error` - never more
than one, and a caller who only ever reads `event.record` will silently skip both of the others.

`stats` is a trailer, always the last event of a complete stream, carrying the same
`limit`/`returned`/`truncated` the buffered envelope reports at the top of its response. Ignoring
it loses exactly what ignoring `truncated` loses on the buffered path above: the only way to tell a
complete answer from one the server's row cap cut short. A caller who iterates `record` events and
stops there has no way to know whether they saw everything.

`error` is a failure the server can only report **after** the 200 status line was already sent -
unlike the buffered path, where a failure still in progress when the response starts can be
reported as a non-2xx status, a streamed response has committed to 200 before the first row is
known to exist, and that status line cannot be taken back once the stream has started. That is why
the contract puts this failure in band, as an event, rather than as an HTTP status. This client
raises `ArcadeDBError` for it, exactly as `query`/`command` throw `ArcadeDBError` for a non-2xx
response, so both paths fail the same way; any event already yielded before the error stays
delivered to the caller.

The error's `status` is the event's own in-band `status` - the status the buffered encoding would
have answered the same failure with: 503 for a retryable conflict, 409 for a duplicated key, 413
when `arcadedb.server.httpQueryMaxResultRows` cut the result short, 500 for an unexpected failure.
Only an event carrying no usable `status` falls back to 200, the status the exchange itself
carried; anything but a positive whole number counts as none. (A `batchLoadStream` error falls
back to 500 by the same rule.) **This changed in 0.3.0, and it is a breaking change**: up to 0.2.0 an in-band error was
always reported with `status` 200, a rule chosen when the event had no `status` to report. The
contract now says to key retries on that status, `batchLoadStream` already used its own in-band
status, and a `retryAfter` beside a 200 was a back-off nobody could act on. Code that recognised a
streamed failure by `err.status === 200` must now look at the real status instead.

The rest of the event maps across field by field: `error` is the event's classified `error`
label (what a buffered error body carries in `error`), falling back to its `message` when it has
none; `exception`, `detail` and `exceptionArgs` are copied as they are; `requestId` is the
response's `X-Request-Id` header when there is one, the event's own `requestId` otherwise; and
`retryAfter` is the event's `retryAfter`, because a `Retry-After` header cannot be added once the
stream has started. The event carries no `commitIndex`, so a streamed query error has none.

`query` and `command` themselves are unchanged: they still return `QueryEnvelope` and still send no
`Accept` header. Streaming is two additional methods, not a mode either existing one can be put
into.

`commandStream` only ever succeeds for a **read-only** statement. A mutating one - `UPDATE`,
`INSERT`, DDL, `UPDATE ... RETURN AFTER` included - is refused before it produces a single row,
because a streamed response starts sending rows to the caller before the surrounding transaction
commits, and that commit can still roll back; the server will not let you observe rows from a
write that might never actually happen. Use the buffered `command` for a mutating statement -
it is unaffected by any of this. As with the `efSearch`/result-limit bounds above, this rule is
enforced **server-side** and this client does not pre-empt it by inspecting the statement first, so
the rejection surfaces as an `ArcadeDBError` from the server's response (HTTP 400), not a local
`throw` before the request is even sent.

You are free to stop early, and that is most of the point of a streaming API. `break`ing out of
the `for await` loop (or calling the generator's `.return()`) **cancels the response body**, not
just the loop: the transfer is torn down and the connection goes back to the pool instead of
hanging mid-response. That takes an explicit `reader.cancel()` inside the decoder - a generator's
`finally` releasing its reader's lock is *not* cancelling, and a released-but-uncancelled body sits
there until garbage collection notices. `arcadedb-driver` (Python) gives the same guarantee through
its own idiom, `httpx`'s `.stream()` context manager unwinding on `GeneratorExit`.

Both methods reach the server through the generated client's own streaming primitive -
`client.POST(..., { parseAs: "stream" })` - rather than a hand-rolled `fetch` or a second HTTP
client of their own; that is what lets them reuse the same base URL, auth, and error mapping every
other call on this client already goes through. Anyone adding another streaming endpoint to this
package should do the same rather than reaching for a bare `fetch`.

## Bulk-loading a graph: `batchLoad`/`batchLoadStream`

`POST /api/v1/batch/{database}` loads vertices and edges from one ndjson payload. `batchLoad`
waits for the buffered summary; `batchLoadStream` asks the same load for `application/x-ndjson`
and hands back an `AsyncGenerator` that reports progress while the upload is still going:

```ts
const summary = await db.batchLoad({
  vertices: [
    { type: "Person", id: "p1", properties: { name: "Alice" } },
    { type: "Person", id: "p2", properties: { name: "Bob" } },
  ],
  edges: [{ type: "Knows", from: "p1", to: "p2", properties: { since: 2020 } }],
  options: { commitEvery: 5000 },
});

console.log(summary.verticesCreated, summary.edgesCreated, summary.idMapping);
```

Vertices and edges arrive as two arguments rather than one interleaved array because the server
resolves an edge's `from`/`to` against temporary ids declared **earlier in the same payload**, and
answers 400 for anything else. Two arguments let the serializer emit every vertex before any edge
unconditionally, which turns that ordering rule from something this README asks you to remember
into something the argument shape cannot express a violation of. `properties` is its own object
for the same kind of reason: flattened into the row it would be indistinguishable from a record
field literally named `properties`, which the server accepts, answers 200 for, and stores - so
nothing fails until a query months later looks for a field that was never written.

`options` is `BatchOptions`, the 17 tuning parameters the endpoint takes as query parameters,
spelled exactly as the contract spells them. An option you leave unset is omitted from the URL
rather than sent empty, so the server applies its own default instead of parsing `""`.

`src/internal/batch-rows.ts` owns the ndjson line format. It was established against a live server
and reported upstream as
[ArcadeData/arcadedb#7570](https://github.com/ArcadeData/arcadedb/issues/7570) when no schema
described it; the contract now declares it as `BatchLine` and the two agree field for field. The
module is still needed, because `BatchLine` types one *line* while the body is a newline-delimited
sequence of them - openapi-typescript therefore types the request body as a single line object,
which is not what the endpoint is sent. `text/csv` still has no schema at all. That is why
`VertexRow`/`EdgeRow` are the only way in: hand-built payload strings are not a supported input.

### A batch is not atomic

Read this paragraph before you use either method. The server commits every `commitEvery` records,
so a load that fails halfway leaves every chunk before the failure **durably committed**. The
`ArcadeDBError` thrown by a failed `batchLoad` describes real data that is already in the
database, not a load that undid itself. And because temporary ids are not keys, **retrying the
whole payload duplicates every vertex that already committed** - there is no server-side
idempotency to lean on, and this client does not invent one. The counters that come back on a 400
(`verticesCreated` and `edgesCreated`, beside a `partialCommit` flag) are records *attempted*
before the failure: an upper bound on what is durable, not a count of it. The two counters do not
even overshoot by the same rule - vertices are committed as the load flushes, while edges are
buffered and written when it ends. A failed load is something to inspect and reconcile against the
database, not something to re-send.

Temporary ids are **request-scoped**, which is the other half of the same design. An id means
something only for the payload that declared it: a vertex loaded by an earlier call cannot be
referenced by its temp id from a later one, and the server will not resolve it. Reference it by
its RID (`#bucket:position`) instead - which is exactly what the summary's `idMapping` returns
temp ids for.

`bytesRead` is how you verify a chunked upload arrived whole: compare it against the bytes you
sent. A body that ends before its announced length is answered **408** with the same
partial-commit counters, never a 200 carrying a truncated count, so `bytesRead` falling short on a
200 means the server consumed less than you believe you sent - not that it quietly accepted a
short load.

### Streaming: what the summary carries, and what it does not

```ts
for await (const event of db.batchLoadStream({ vertices, edges })) {
  if (event.progress) console.log(event.progress.phase, event.progress.verticesCreated);
  if (event.summary) console.log(event.summary.idMappingSize, event.summary.idMappingStreamed);
}
```

A `progress` event arrives at every vertex commit and every `commitEvery` edges, then exactly one
`summary`. The two encodings disagree about the temp-id mapping, deliberately. `batchLoad`'s
summary carries `idMapping`, the whole temp-id-to-RID map in one object. A streamed load puts that
map on the wire in fragments - each `progress` event's `idMapping` is only what that chunk
resolved - and its `summary` carries `idMappingStreamed: true` and `idMappingSize` with **no map
at all**.

This client yields progress events exactly as it receives them and never merges those fragments.
Accumulating them here would rebuild, client-side, the million-entry map that streaming exists to
avoid holding: the buffered encoding's size cap on `idMapping` is a symptom of the server having
to build the whole map before it can answer anything, and streaming removes that on both ends. A
caller who genuinely needs the whole mapping concatenates the fragments as they arrive - checking
the total against `idMappingSize`, since a map delivered in pieces can lose one to a truncated
response without any single piece looking wrong - or calls `batchLoad` and accepts the memory
cost, which is a perfectly good trade right up until the map stops fitting.

`idMappingStreamed` is a different condition from `idMappingOmitted`: *omitted* means the map was
too large to return, *streamed* means it was already delivered, piecemeal, in the progress events.
`BatchResponse` - the shape `batchLoad` returns - correctly has no `idMappingStreamed`, because a
buffered load never sends it; but the generator does declare the field where it belongs, on
`NdJsonBatchEvent["summary"]`, the streaming path's own type, alongside `commitIndex` and
`idMappingSize`. `BatchSummary` is a plain alias for `BatchResponse` and carries no widening.
`NdJsonBatchEvent`'s error object is the one genuine gap: it declares only `commitIndex`,
`exceptionArgs`, `retryAfter` and `status`, not the `error` message and `exception` the server
actually sends with them, so `NdJsonBatchEvent` is widened here by exactly those two fields. That widening was established
against a live 26.10.1 server, is reported upstream as
[ArcadeData/arcadedb#7570](https://github.com/ArcadeData/arcadedb/issues/7570), and should be
narrowed back to the generated type once the contract declares the fields.

### Both ways a load can fail throw the same thing

A failure **before** the first acknowledgement is reported as a real HTTP status with the buffered
error body - nothing has been written to the response yet, so the status line is still free. A
failure **after** the first progress line cannot be: the 200 is already on the wire and cannot be
taken back, so it travels in band as an `error` event carrying the status the buffered encoding
would have used. `batchLoadStream` throws `ArcadeDBError` for both, so a `for await` loop fails
identically whichever channel carried the failure; *when* the load failed is the only difference
between them, and it is not something a caller can branch on usefully. Every event already yielded
stays delivered - and per the non-atomicity paragraph above, those progress counters are the best
record you will get of what may already be durable.

The in-band `status` is exact, not a fallback: an engine failure raised after the stream had
already started carries the status the standard error mapping gives it - 409 for a duplicated
key, 503 for a retryable conflict - so branching on `status` works the same on both channels. The
thrown `ArcadeDBError` also carries `exception` and, when the failure has any, `exceptionArgs`.
`retryAfter` and `commitIndex` reach it on both channels too: from the `Retry-After` and
`X-ArcadeDB-Commit-Index` headers when the load failed before the stream started, and from the
error event's own `retryAfter` and `commitIndex` when it failed after, since neither can be a
header once the 200 is on the wire. A `commitIndex` on a failed load covers whatever chunks did
commit - see "Back-off and read-after hints on an error" below.

### This is `batchLoad`, not `bulkInsert`

[`@arcadedb/driver-grpc`](../driver-grpc/README.md)'s `bulkInsert` is a **different operation** -
it inserts records into one target type and knows nothing about edges or temporary ids. The gRPC
counterpart of the endpoint documented here is `GraphBatchLoad`, which that package exposes
through `raw` and wraps nowhere.

### `text/csv` is not exposed

The endpoint accepts `application/jsonl`, `application/x-ndjson` and `text/csv`. This client always
sends `application/x-ndjson` (the contract makes `application/jsonl` identical in meaning, so there
is nothing to choose between them) and does not expose CSV. The CSV dialect is as undocumented as
the ndjson line format, and a rows-in API has nowhere to put a header row. Convert a CSV file into
`VertexRow`/`EdgeRow` yourself, or send the bytes through `server.raw`.

## Transactions

```ts
const total = await db.transaction(async (tx) => {
  await tx.command({ language: "sql", command: "INSERT INTO Account SET balance = 100" });
  const { result } = await tx.query({ language: "sql", command: "SELECT sum(balance) as total FROM Account" });
  return result[0].total;
});
```

Every call made through the `tx` handle passed into the callback - not the outer `db` - takes part
in the transaction. `transaction` commits when the callback resolves and returns its value; it
rolls back and re-throws when the callback throws or rejects, synchronously or otherwise. The
error the caller sees is always the callback's own error, never the rollback's - if the rollback
itself also fails, that failure is attached as `err.cause` rather than replacing `err`. If the
commit itself fails, `transaction` issues a best-effort rollback (to release the server-side
session) before re-throwing the commit's error.

A rollback cannot undo everything, though. A statement inside the callback that publishes a commit
while it runs - an explicit `BATCH n` boundary, or a statement carrying its own `COMMIT` - makes
part of the transaction durable before `transaction` decides anything, and the server marks that
response `arcadedb-session-partial-commit: true`. This client does not surface the header (it is
reachable through `raw`). The consequence is for a caller that replays a whole `transaction` block
on a conflict: a block containing such statements must not be replayed, because its first run
already left part of its work behind, and a replay would apply that part twice.

## Labelling work: `queryTag`

`query`, `command`, `queryStream`, `commandStream`, `batchLoad` and `batchLoadStream` take an
optional `queryTag`, and `transaction` takes one as its second argument:

```ts
await db.query({ language: "sql", command: "SELECT FROM Orders", queryTag: "nightly-report" });

await db.transaction(
  async (tx) => {
    await tx.command({ language: "sql", command: "UPDATE Orders SET archived = true" });
    await tx.command({ language: "sql", command: "DELETE FROM Cart", queryTag: "cart-cleanup" });
  },
  { queryTag: "archive-run" },
);
```

The tag travels as the `X-ArcadeDB-Query-Tag` request header, never in the body or the query
string, and only when it is non-empty. On the server, `list queries` shows each running statement
under its tag and `terminate queries tag <label>` stops them. `server.listQueries` and
`server.terminateQueriesByTag` issue those two commands for you (see "Running work" below). `transaction`'s tag is sent on the
begin request **only**: the server applies it to every statement of the session that carries no
tag of its own, so the first `command` above runs as `archive-run`, while the second, which passes
its own tag, runs as `cart-cleanup`. Commit and rollback carry no tag.

The contract allows at most 256 printable characters. This client does not check that - the rule
is the server's, and a copy here would drift from it - and the contract does not say what the
server does with a longer tag either (a 26.11.1-SNAPSHOT server accepted a 257-character one
without complaint), so keep tags short rather than relying on a refusal.

## Duplex insert session: `db.insertSession`

`db.insertSession()` opens the duplex insert session on the server's `/ws` endpoint. Where
`batchLoad` fixes its commit policy before the load starts, a session lets the caller see the
acknowledgement of chunk *n* and only then decide what to send next - including whether to commit
or roll back at all.

```ts
const session = await db.insertSession({ targetType: "Person" });
try {
  const ack = await session.sendChunk([{ name: "a" }, { name: "b", "@class": "Employee" }]);
  console.log(ack.inserted, ack.failed, ack.errors);   // per-chunk tallies; nothing is durable yet
  const done = await session.commit();                 // or: await session.rollback()
  console.log(done.outcome, done.summary.inserted);
} finally {
  await session.close();                               // rolls back if still open; idempotent
}
```

`await using session = await db.insertSession(...)` works too on a runtime with explicit resource
management, and calls `close()` the same way.

Options: `sessionId`, `targetType` (a record's own `@class` overrides it), `transactionMode`
(`per_stream` default, `per_batch`, `per_row`, `none`), `conflictMode` (`error` default, `update`,
`ignore`, `abort`), `keyColumns`, `updateColumnsOnConflict`, `validateOnly`, `joinTransaction`,
`onBatchAck` (called with every acknowledgement before `sendChunk` returns it), `timeoutMs`
(per frame, and for the connect; default 60 s) and `WebSocket`.

Failure modes worth knowing before relying on it:

- **Sequence numbers are the session's job.** `chunkSeq` starts at 1 and advances only after the
  server has acknowledged the chunk. A chunk the server refuses with an "Insert session error" -
  more rows than `wsMaxInsertChunkRows`, a sequence that skips ahead, bad options or data - rejects
  with `ArcadeDBError` and leaves the session open with the sequence where it was, so you can split the batch and resend it under the
  same number (`session.lastChunkSeq` tells you where you are).
- **A chunk can fail as a whole and still resolve (`per_batch` only).** When the chunk's own
  transaction cannot commit (a duplicate key, say), the server answers a normal
  `batchAck` with `failed === received` and a single `errors` entry at `rowIndex: -1`, and does
  not advance its watermark. This client marks that ack `wholeChunkFailed: true` (still passed to
  `onBatchAck`) and does not advance `lastChunkSeq` either: nothing in the chunk is durable, and
  resending it goes out under the same sequence number. Treat it as "replay this chunk". Under
  `per_stream` the same kind of failure surfaces only at the end: a duplicate key found at commit
  time is an error answering `commit()`, and the session is then gone.
- **A row the server cannot apply is not a refusal**: the chunk is acknowledged, the row is
  counted in `ack.failed` and described in `ack.errors` (with its real `rowIndex`), and the rest
  of the chunk went in. Check `failed`; a resolved `sendChunk` does not mean every row was written.
- **A frame over `wsMaxInsertFrameSize` ends the session.** The byte cap is enforced before the
  frame is parsed, so the server sends no `error` frame: it closes the connection (status 1009).
  `sendChunk` rejects with "closed the /ws connection", the session is closed, and the server
  rolls back what it held - there is no sequence to reuse. Size chunks well under the cap.
- **Nothing is durable until `commit()`** (`per_stream`). `per_batch` and `per_row` commit as they
  go, so `rollback()` cannot take back an acknowledged chunk; `summary.partialCommit` says so.
- **Joining a transaction.** On the `tx` handle of `db.transaction()`,
  `insertSession({ joinTransaction: true })` writes into that transaction (it sends the
  transaction's id with `transactionMode: "none"`). The session's `commit()` and `rollback()`
  then answer `outcome: "detached"` and decide nothing: the rows become durable when the
  `transaction()` callback resolves and are undone if it throws. `joinTransaction` on any other
  handle, or combined with a `transactionMode` other than `"none"`, is refused client-side before
  any connection is made. Without `joinTransaction`, a session opened on a `tx` handle is an
  ordinary server-managed one and does not take part in the transaction.
- **Most `error` frames end the session.** Only the usable refusals above leave it open. These
  close it (`session.open` becomes `false`, later calls reject with "is closed"):
  "Security error" (the grant was revoked, which has already rolled the session back, or the
  principal is no longer valid, which closes the connection), "Insert session expired" (the idle
  sweep), "Internal error", and an "Insert session error" whose detail says the session is "not
  found or expired" or "is closed". An error title this client does not recognise leaves the
  session open, as the Go and Python clients do: if the server has in fact dropped it, the next
  frame is answered "not found or expired", which closes it, whereas a session wrongly marked
  closed is never rolled back by `close()`. Branch on `err.error` and `session.open`, not on the
  message.
- **An `error` frame can arrive at any time.** The server sweeps idle sessions and says so with an
  unsolicited `error` frame. It is reported - the next call rejects with it, and nothing is sent -
  never skipped, and the session is then closed. Likewise a connection the server drops, or a
  frame not answered within `timeoutMs`, rejects and closes the session.
- **Session ids share one server-wide namespace.** Leave `sessionId` out and the server generates
  one (`session.sessionId`). A client-chosen id collides with any other connection's session of
  that id, and the `start` is refused.
- **One session, one caller.** A second call made while a frame is in flight rejects immediately
  instead of being interleaved. A connection carries one session at a time.
- **Errors are `ArcadeDBError` with `status: 0`**, since a frame has no HTTP status; `error`,
  `detail` and `exception` carry what the server's `error` frame said, and `message` includes the
  detail. `close()` never throws.

**Runtimes and authentication.** The session needs a `WebSocket` that can send an `Authorization`
header, because that is how the server authenticates `/ws` - the same `basicAuth`/`bearerAuth` you
gave `createClient` is applied to the handshake.

- **Node 22+**: the global `WebSocket` is used, and sends the header (verified against a real
  server in `e2e/insert-session.test.ts`).
- **Node 20**: there is no stable global `WebSocket`. Install the [`ws`](https://www.npmjs.com/package/ws)
  package (MIT) and pass it: `createClient({ ..., WebSocket })` or `insertSession({ WebSocket })`.
  It is not a dependency of this package, so nothing is installed for callers who do not use
  sessions.
- **Browsers: authenticated sessions are not supported.** The browser `WebSocket` cannot set
  request headers, so a session against a server that requires credentials fails at the handshake.
  This is a limit of the platform, not something this client can work around, and the server
  accepts no credentials in the URL. The rest of this package works in a browser; only
  `insertSession` does not (unless the server is reachable without credentials, or a proxy in
  front of it adds the header).

## Vector, hybrid and full-text search: `db.vector`

```ts
const nearest = await db.vector.search({ indexName: "myIndex", queryVector: [0.1, 0.2, 0.3], k: 5 });
const fused = await db.vector.hybrid({
  vectorIndexName: "myIndex",
  queryVector: [0.1, 0.2, 0.3],
  fulltextIndexName: "myTextIndex",
  fulltextQuery: "cat",
});
const matches = await db.vector.fulltext({ queryText: "cat" });
```

`search` runs a kNN query over a dense `LSM_VECTOR` or sparse `LSM_SPARSE_VECTOR` index; `hybrid`
fuses a vector leg with an optional full-text leg and an optional graph-expansion leg into one
ranked list; `fulltext` runs a Lucene-syntax query over a `FULL_TEXT` index. As with `query` and
`command`, none of the three unwraps to bare rows - each returns the whole response object the
server sent, `results` alongside `count`, `truncated` (search and hybrid only, see below),
`scoring`, and the rest.

That matters most for `truncated`. `search` and `hybrid` both inspect a bounded candidate window
before ranking, and `truncated` is `true` when that window was filled - meaning more matches may
exist beyond what `results` shows, exactly the hazard the result envelope's `truncated` documents
above. A caller who reads `result.results` off a vector search and ignores `truncated` works off a
partial answer without being told; raise `k` and search again if you need to see further.

`fulltext`'s response, `FullTextSearchResponse`, has **no `truncated` field at all** - not `false`,
absent. That is the contract's shape, not a field the server forgot to send: full-text search has
no candidate-window concept to overflow the way a vector search does, so there is nothing for a
`truncated` flag to report either way.

`efSearch` (the dense-index search beam width) and each method's result-limit field (`k` for
`search`/`hybrid`, `limit` for `fulltext`) are bounded, but the bound is enforced **server-side**.
This client sends whatever value it is given without checking it first, so a value outside the
allowed range surfaces as an `ArcadeDBError` thrown from the server's response, not as a local
`throw` before the request is even sent.

### Reading a hit

`VectorSearchResponse` carries no `required` list in the contract, so `result.results` is
`... | undefined`, and `result.results[0]` does not compile unnarrowed
(`'result.results' is possibly 'undefined'`); `?? []` discharges it. `HybridSearchResponse` and
`FullTextSearchResponse` hits read the same way.

A hit's `properties` is generic, defaulting to `Record<string, unknown>`, so
`hit.properties?.someField` reads as `unknown` unless you pass your row shape:

```ts
const result = await db.vector.search<{ name: string }>({ indexName: "myIndex", queryVector: [0.1, 0.2, 0.3], k: 5 });

for (const hit of result.results ?? []) {
  console.log(hit.rid, hit.properties?.name); // `name` is `string`, typed for real
}
```

Omit the type argument and `hit.properties?.name` is `unknown` rather than `string` - a read into a
concrete type then needs its own narrowing, same as any other `unknown`. That default (not the
generic parameter itself) is what closes the historical hazard here: the contract declares a hit's
`properties` as a bare `{"type": "object"}` with no keys, which openapi-typescript renders as
`Record<string, never>` - and every value of an empty record is typed `never`, which is assignable
to *everything*, so `const n: number = hit.properties.name` used to typecheck and hand back a
string at runtime with no warning. `hybrid` and `fulltext` hits carried the identical artifact and
are fixed the same way.

## Time series: `db.ts.query`'s `tags` is enforced server-side

A name in `db.ts.query`'s `tags` body field that is not one of the type's declared TAG columns is
not dropped from the filter - it is **refused** with a 400 response naming the offending tag and
listing the type's declared TAG columns. Silently ignoring it would widen the query to the whole
range, and a caller has no way to tell that result apart from a filter that legitimately matched
everything.

That rule is enforced **server-side**, the same way `efSearch` and the vector/full-text
result-limit fields are (see "Vector, hybrid and full-text search" above): this client sends
`tags` unchanged and does not check it against a schema it does not have, so a violation surfaces
as an `ArcadeDBError` thrown from the server's response, not a local `throw` before the request is
even sent.

### A failed `db.ts.write` throws `TimeSeriesWriteError`

When the server refuses some samples it answers 400 with a body saying what happened to the rest,
and `db.ts.write` throws `TimeSeriesWriteError` - a subclass of `ArcadeDBError`, so an existing
`catch (err) { if (err instanceof ArcadeDBError) ... }` still catches it:

```ts
import { TimeSeriesWriteError } from "@arcadedb/driver";

try {
  await db.ts.write({ lineProtocol });
} catch (err) {
  if (err instanceof TimeSeriesWriteError) {
    console.error(`${err.written} written, ${err.dropped} dropped`, err.unknownTypes, err.undeclaredKeys);
  }
}
```

**A write is not atomic.** `written` samples landed even though the call failed; only the
`dropped` ones did not. Re-sending the whole batch writes the `written` ones a second time, so a
failed write is something to reconcile, not to retry blindly. The four reason lists each name what
caused a drop, and each is an empty array, never `undefined`, when the server reported nothing:

- `unknownTypes` - measurements naming a type that does not exist.
- `nonTimeSeriesTypes` - measurements naming a type that exists but is not a time-series type.
- `unavailableTypes` - measurements naming a time-series type whose storage engine failed to load;
  the server log says why.
- `undeclaredKeys` - tag or field keys the measurement's type does not declare in that role. The
  server caps this list at 100 entries, so a full list is not necessarily every key. A server
  started with `arcadedb.timeSeriesUndeclaredKeys=ignore` stores such samples with the undeclared
  keys discarded instead of dropping them.

Only a 400 whose body is a JSON object becomes a `TimeSeriesWriteError`. Every other failure of
`db.ts.write` - a 401, a 503, a 400 with a body that is not an object - stays a plain
`ArcadeDBError`.

## PromQL: `db.promql`

`db.promql` is the Prometheus-compatible query surface, returning the generated models: `query`,
`queryRange`, `labels`, `labelValues` and `series`. The metric name for a time-series type is the
**type name itself** (`Sensor`), not `Sensor_value`.

```ts
await db.promql.labelValues("sensor"); // every value of the `sensor` tag
await db.promql.labelValues("sensor", { start: "1700000000", end: "1700003600" }); // only values in that range
await db.promql.labelValues("__name__"); // the time-series type names
```

`labelValues` lists the values one label carries, restricted to `start`/`end` (Unix seconds, both
optional; omit both for the whole series). The name `"__name__"` is special: it lists the
time-series **type names** rather than a tag's values, since a type name is the metric name. The
server answers an empty success, not an error, for a label no series carries, so an empty
list does not mean the name was misspelled. Pass the name unescaped; the client percent-encodes it.

## Two error models

The facade methods (`query`, `command`, `transaction`, `listDatabases`, `exists`, `serverInfo`,
`health`, `ready`, ...) throw `ArcadeDBError` on any non-2xx response - and, in exactly one case
documented below, on a 2xx one:

```ts
import { ArcadeDBError } from "@arcadedb/driver";

try {
  await db.query({ language: "sql", command: "SELECT FROM NoSuchType" });
} catch (err) {
  if (err instanceof ArcadeDBError) {
    console.error(err.status, err.error, err.detail, err.requestId);
  }
}
```

`server.raw`, the underlying [openapi-fetch](https://openapi-ts.dev/openapi-fetch/) client, does
**not** throw. It returns `{ data, error }` and leaves handling the error to the caller:

```ts
const { data, error, response } = await server.raw.GET("/api/v1/server", {});
if (error) {
  // handle it yourself; server.raw never throws
}
```

These are two deliberately different contracts in one package. Use the facade for the ergonomics
of try/catch; use `raw` when you want to branch on `{ data, error }` without exceptions. Mixing
assumptions about which one you're calling is the most common way to end up with an unhandled
rejection or a silently ignored error.

### `ArcadeDBError` is not always a non-2xx status

For a buffered call `err.status` is whatever the exchange actually carried. (A streamed call's
in-band error is the exception the other way round: its exchange carried 200, and `err.status` is
the in-band status instead - see the streaming section - falling back to `200` only when the event
names none.) There is one buffered case where the status is `200`:
`query` and `command` throw `new ArcadeDBError(200, ...)` when the server answers 200 with a
streamed ndjson event rather than the buffered JSON envelope. This client never sends
`Accept: application/x-ndjson`, so it should not happen - but if it does, the alternative is to
hand back `{ result: [], limit: -1, returned: 0, truncated: false }`, an answer asserting a
completeness nobody gave. Reporting it is the honest option.

The practical consequence is for callers who classify failures by status alone. Code shaped like

```ts
catch (err) {
  if (err instanceof ArcadeDBError && err.status >= 500) return retry();
}
```

now has a case it cannot decide: a 200 here is a protocol mismatch, not a transient server fault,
and retrying will not help. If that distinction matters to you, branch on `err.error` as well as
`err.status`, or simply treat a 2xx `ArcadeDBError` as non-retryable.

### Back-off and read-after hints on an error

Two fields of `ArcadeDBError` come from the response rather than its body:

- `retryAfter` - seconds to wait before retrying. On a buffered response it is the `Retry-After`
  header; on a streamed one it is the in-band error's `retryAfter`, because a header cannot be added
  once the stream has started. The server sends it on a 503 when the node cannot execute the request
  yet (a snapshot install, for instance) and on a 409 when an identical request is still in flight.
  `0` means "retry now", so compare against `undefined` rather than testing truthiness.
- `commitIndex` - the last applied Raft index on the node that answered: the
  `X-ArcadeDB-Commit-Index` header, or the in-band `commitIndex` of a streamed batch error. It is
  still a valid read-your-writes barrier on a failure: whatever a partly-applied write did commit is
  covered by it, so sending it back as the `X-ArcadeDB-Read-After` header on a later read makes that
  read wait until those writes are visible. It is absent on a standalone (non-replicated) database.

Either is `undefined` when the server sent none, and a header that is not a plain non-negative
integer (an HTTP-date `Retry-After`, say) is read as absent rather than throwing.

**A 409 has two meanings, and the status alone cannot tell them apart.** It is either "an
identical request is still in flight" - the request carried an `X-Request-Id` the server is still
executing; this one is retryable, after `retryAfter` - or "query terminated", because an operator
ran `terminate query`, `terminate queries` or `terminate transaction` on it. A terminated statement's
writes were rolled back, and retrying it undoes the operator's decision. This client retries
neither. Retry logic of your own must tell them apart by `exception`
(`RequestStillInFlightException` for the in-flight case) and `retryAfter` (which only the in-flight
case carries), never by `status === 409`.

### Two things neither model catches

Both of the above describe how a completed HTTP exchange is reported. Two failure modes happen
before or after that exchange and are not translated into either model - a `catch` around a facade
call, or an `error` check on `raw`, will not see an `ArcadeDBError` for these:

- **A rejecting `fetch`** - DNS failure, connection refused, TLS error, an aborted request - throws
  whatever the underlying `fetch` implementation throws (typically a `TypeError`), not
  `ArcadeDBError`. There was no HTTP response to build one from.
- **A 2xx response with an unparsable body** - the server answered successfully but the body is
  not valid JSON - propagates a `SyntaxError` from the JSON parse, not `ArcadeDBError`, since
  `unwrap` only inspects `response.ok` and never sees a parse failure on the success path.

Neither is normalized into `ArcadeDBError` today; a `catch` around a facade call may see a
`TypeError` or `SyntaxError` instead of the `ArcadeDBError` this README otherwise promises.

## Administration: databases, users and groups

```ts
await server.createDatabase("tenant_a");
await server.createUser("alice", "a-long-password", { databases: { tenant_a: ["admin"] } }); // "*" = every database
const users = await server.listUsers(); // [{ name: "alice", databases: { tenant_a: ["admin"] } }, ...]
await server.updateUser("alice", { password: "another-password" });
await server.dropUser("alice");
await server.dropDatabase("tenant_a");
```

All of these are root-only, and every failure throws `ArcadeDBError`, as for any facade method.
Users and groups have dedicated endpoints with a structured body (`/api/v1/server/users`,
`/api/v1/server/groups`): `createUser`, `updateUser`, `dropUser`, `listUsers`, `saveGroup`,
`deleteGroup`, `listGroups`. Databases have none, so `createDatabase` and `dropDatabase` send
`create database <name>` and `drop database <name>` through `POST /api/v1/server`. They reject an
empty name, or one with leading or trailing white space, with a `RangeError` before sending
anything, because the server trims the name it reads out of the command and would act on a
different database than the one you named. Anything else in the name is sent as given, embedded
spaces included: one request runs one command, so a name cannot smuggle in a second command, but
validate a name built from untrusted input yourself.

**"Already exists" is a 409 for users and databases alike.** Both statuses were measured against a
real server; they are what the e2e suite pins.

- A user that already exists is a **409** (`error` "User already exists"), so a 409 from
  `createUser` means "already there" and create-if-absent can catch it. Servers built before
  ArcadeData/arcadedb#10076 answer **403** "Security error" instead, which is also what a non-root
  caller gets; against those, do not read 403 as "already exists".
- A database that already exists is a **409** too (`error` "Database already exists", the
  name in `detail`). Servers built before ArcadeData/arcadedb#10079 answer **400** "Cannot
  execute command" instead, the status every invalid server command gets; against those,
  call `exists` first to create a database only when it is missing (as root it sees every database,
  so its `false` is reliable there), knowing another client can still create it in between.

`updateUser` and `saveGroup` send only the fields you pass: one left out keeps the server's current
value. `updateUser(name, { databases: {} })` sends the empty object, which removes every assignment.

`server.serverCommand(command)` runs any other server command and returns the whole parsed body as a
`Record<string, unknown>`. The contract types that body as `QueryResponse`, with an array `result`,
but administrative commands answer `{"result": "ok"}` and other commands answer shapes of their
own; `openapi-fetch` does not validate, so through `raw` the same body arrives typed as something
it is not. The command string is sent as given.

## Running work: list and terminate queries and transactions, and `db.progress`

```ts
import { isQueryTerminated } from "@arcadedb/driver";

const running = await server.listQueries({ tag: "nightly-report" }); // or { database }, or neither
const results = await server.terminateQueriesByTag("nightly-report", { waitMs: 3000 });
const result = await server.terminateQuery(running[0].id);
const open = await server.listTransactions();
await server.terminateTransaction(open[0].id);
const progress = await server.db("tenant_a").progress(); // long-running maintenance operations, step by step
```

Unlike the administration methods above, these are open to **any authenticated user**: root sees
and stops every statement, another user only their own, and someone else's statement is answered
`"not found"`, never "forbidden". They go through `POST /api/v1/server`, and `progress` through
`GET /api/v1/progress/{database}`. Results are passed through as the server sends them, typed as
`RunningQuery`, `TerminateResult` and `OpenTransaction`; times are epoch milliseconds.

**Each server sees only its own work.** None of these is forwarded to the cluster leader. Behind a
load balancer, the server this client reaches may not be the one running the statement, and then
`listQueries` does not show it and terminating it answers `"not found"`.

**A statement shows up before its text does.** The server lists a request the moment it is
admitted, and for a brief window that entry's `language` is `null` and its `text` is the request
line (`POST /api/v1/command/<database>`); both are filled in once the statement starts. To read the
statement itself, poll until `language` is set.

Each of the three terminate methods waits for the statements to stop, up to `waitMs` (omitted or zero leaves the server's
default of 5000, and the server caps it at 10000), then answers each with a `status`, typed as
`QueryStatus`. **Which one you get decides whether you have anything to undo:**

| `status` | meaning |
|---|---|
| `"terminated"` | it stopped, and what it wrote was rolled back |
| `"completed"` | it finished on its own before it noticed, so **what it did stands** |
| `"terminating"` | not stopped yet when the wait ended; some statements (SQL `SLEEP`, for one) notice only when they end, so the request's own outcome is the answer |
| `"not found"` | no such statement on this server, or another user's |

Terminating a **command** inside a transaction ends the transaction too, rolling it back, while
terminating a read leaves it open; `TerminateResult.sessionId` and `sessionOpen` say which, and
`sessionOpen` is only the state at the time of the answer for a `"terminating"` statement. A script
counts as a command.

**The stopped request throws a 409, and `isQueryTerminated(err)` recognises it.** The server answers
it 409 "Query terminated", but a 409 is also what a request still in flight under the same
`X-Request-Id` gets, so the status alone cannot tell "someone stopped me" from a conflict.
`isQueryTerminated` matches the error's `exception`, `com.arcadedb.exception.QueryTerminatedException`,
which the server sends as a structured field, not the message text. It is not retryable: somebody
stopped this work on purpose.

**`terminateTransaction` reaches the client that owned the transaction at commit.** It rolls the
transaction back, a statement sent on it afterwards throws a 404, and so does the commit: the
owner's `transaction()` rejects with that 404 `ArcadeDBError` ("Remote transaction session not
found or expired"). Servers built before ArcadeData/arcadedb#10164 (2026-10-16) answer that commit
204, exactly like a real commit, so against those a `transaction()` callback that ran no statement
after the terminate resolves for work that is gone. Measured against 26.11.1-SNAPSHOT and pinned by
the e2e suite.

Ids, session ids and the `database` filter must not be empty (where required) or contain a space
or control character (anything at or below U+0020), because the server reads each as one word; a
tag must not start or end with one, because the server trims it. A no-break space is not one, as
the server sees it. Each rejects with a `RangeError` before anything is sent. A tag
is otherwise sent as given, spaces and quotes included: the server takes the rest of the command as
the tag.

`db.progress()` returns the contract's `ProgressResponse`, whose `result` is empty when nothing is
running. The server reads a lock-free snapshot, so polling it at any rate cannot slow down the
operation being watched.

## Sessions and API tokens

```ts
const root = createClient({ baseUrl: "http://localhost:2480", auth: basicAuth("root", "playwithdata") });

// Per-user isolation: log in as the user once, then keep a client holding only the token.
const login = await root.loginAs("alice", "a-long-password"); // or root.login(): the client's own credentials
const alice = root.withToken(login.token); // root itself is unchanged
const dbs = await alice.listDatabases(); // only what alice may see
await alice.logout(); // the token is now refused everywhere

// A long-lived machine credential (root only).
const created = await root.createAPIToken("ci", { database: "tenant_a" });
store(created.token); // the only time the plaintext exists
const tokens = await root.listAPITokens(); // metadata only, never the token
await root.deleteAPIToken(created.tokenHash); // by hash, never by token
```

`login` and `loginAs` resolve to a `LoginResult` carrying the session token (prefixed `AU-`) and
leave the client alone. `loginAs` sends the user's credentials through a separate client built
from the same `baseUrl` and `fetch`, because a per-call header would lose to the client's own
`auth` middleware. `withToken` returns a **new** `ArcadeDBServer` presenting the token through
`bearerAuth`, with the original's `baseUrl`, `fetch` and `WebSocket`; middleware added later with
`raw.use()` is not carried over. Both need a server built by `createClient`. A token is a
credential: whoever holds it acts as that user until it is logged out or the server drops it.
Keeping the token rather than the password is the point.

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

- **Wrong Basic credentials are a 401** "Authentication failed", on every endpoint, the same
  status an invalid, expired or logged-out bearer token gets; **403** means the caller
  authenticated but may not do this. Servers built before ArcadeData/arcadedb#10109 (2026-10-16)
  answer every failed password check with 403 "Security error" instead, so against those a
  `loginAs` 403 cannot be told apart from a forbidden user.
- **`logout` only ends a session token.** The server answers 204 to a logout carrying Basic
  credentials or an API token and invalidates nothing, so `logout` on a client whose `auth` does
  not present an `AU-` token rejects with `NotSessionTokenError` without sending anything. The
  token is read by running the `auth` middleware on a throwaway request, as the insert session
  does. Logging out a token that is no longer valid is a 401.
- **`listSessions` is root-only** (403 otherwise) and lists every user's live session token. Treat
  its result as you would the users' passwords. These are login sessions, not the transaction
  sessions `transaction()` opens. `createdAt` and `lastUpdate` are `Date`s, `elapsedMs` a number,
  `issuer` `undefined` for a session this node issued, and `sourceIp`, `userAgent`, `country` and
  `city` `null` when the server does not know them.

API tokens:

- **The plaintext is returned exactly once**, in `CreatedAPIToken.token`. The server stores only
  its SHA-256 hash, so a lost token cannot be recovered, only deleted and reissued. This client
  never logs or keeps it.
- **`deleteAPIToken` takes the hash** (`tokenHash`, from `listAPITokens` or `createAPIToken`).
  Anything but 64 lowercase hexadecimal characters throws `RangeError` before a request is sent,
  because the argument travels in the query string, where proxies and access logs record it, and
  the likeliest mistake is the plaintext token. The error does not repeat the argument. A hash no
  token has is a **404**, a status the contract does not list (ArcadeData/arcadedb#10110).
- **A taken name is a 409.** The contract describes its 409 only as a replayed `X-Request-Id`;
  the server also uses it for a duplicate name.
- **412 means the transport is not confidential.** With
  `arcadedb.server.apiTokenRequireSecureTransport` on, the server refuses to send a token back over
  cleartext HTTP to a non-loopback client, unless a proxy listed in
  `arcadedb.server.apiTokenTrustedProxies` terminated TLS. The setting is off by default until
  ArcadeDB 27.1.1, which turns it on; until then such a mint succeeds and the server logs a warning.
- `expiresAt` is `null` for a token that never expires. Passed to `createAPIToken`, it must be a
  valid `Date` after the Unix epoch, or `RangeError` is thrown before sending: the server reads an
  expiry of 0 as "never", so an epoch expiry would issue a token that never expires. An expired
  token authenticates nobody, and stays in `listAPITokens` (with `expired` set) until the next
  token change retires it. `permissions` takes the shape a group's `types` map takes.
- `logout` on a client holding an API token rejects with `NotSessionTokenError`: an API token is
  revoked with `deleteAPIToken`, not logged out.

The implementation is loaded with a dynamic `import()` on first use, like the `db.*` namespaces, so
a bundle that never logs in does not carry it (see "Bundling and tree-shaking").

## What only `raw` reaches

The facade wraps the data plane and a handful of server calls; everything else in the contract is
reachable only through `server.raw`. That includes, **deliberately**, the cluster override
endpoints `POST /api/v1/cluster/accept-diverged/{database}` (`acceptClusterDivergedDatabase`) and
`POST /api/v1/cluster/accept-stale-snapshot` (`acceptClusterStaleSnapshot`), new in 26.11.1, beside
the older `POST /api/v1/cluster/accept-copy/{database}`. They are root-only operator overrides
that make a node accept a copy of its data without a resync - a decision a person takes while
looking at a broken cluster, not something an application calls - and no facade method wraps any
`/cluster/*` endpoint.

## `exists` cannot prove absence

```ts
const present = await server.exists("mydb");
```

`exists` returns `false` both when the database genuinely does not exist and when it exists but
the authenticated caller is not authorized to see it - the server's response does not distinguish
the two cases, so this client cannot either. Do not treat `false` as proof that a database is
absent; it only means "not visible to this caller right now."

## Contract version and compatibility

This package was generated from `contracts/arcadedb-openapi-26.11.1-SNAPSHOT.json`, recorded in
`package.json` as `arcadedb.serverVersion`:

```json
{
  "arcadedb": {
    "serverVersion": "26.11.1-SNAPSHOT"
  }
}
```

| `@arcadedb/driver` | ArcadeDB server |
| --- | --- |
| 0.1.0 | 26.9.1 |
| 0.2.0 | 26.10.1 |
| 0.3.0 | 26.10.2 |

The client speaks ArcadeDB's HTTP API as described by that contract. Pointing it at a server on a
materially different release may work for the endpoints both versions share, but is not tested or
supported.

## Bundling and tree-shaking

`db.ts`, `db.grafana`, `db.promql`, `db.vector`, and `db.insertSession` each load their implementation with a dynamic
`import()` rather than a static one, and so do the server's administration, login, session,
API-token and running-work methods and `db.progress`. On a bundler that supports code splitting - Vite, webpack,
Rollup, or esbuild run with `--splitting` - code that only calls `query`, `command`, and
`transaction` gets a chunk that excludes the time-series, Grafana, PromQL, and vector-search
modules and the insert session; they load only if and when `db.ts`, `db.grafana`, `db.promql`,
`db.vector`, or `db.insertSession` is actually reached. Without code splitting, a bundler inlines those dynamic imports into the single output
file, and all four modules ship regardless of whether they're used. This is verified by
`test/treeshake.test.ts`, which bundles a data-plane-only entry point with esbuild's `splitting`
option on and asserts the PromQL, Grafana, time-series, vector route and insert-session markers are all absent
from the chunk reachable via static imports alone - it does not claim, and this README does not
claim, that the package sheds unused code under every bundler configuration.

## License

Apache-2.0.
