# @arcadedb/driver

A TypeScript/JavaScript HTTP client for [ArcadeDB](https://arcadedb.com), generated from ArcadeDB's
OpenAPI contract.

If your workload is throughput-sensitive server-to-server streaming instead - large query result
sets, bulk inserts - see [`@arcadedb/driver-grpc`](../driver-grpc/README.md), which streams
natively over gRPC rather than paging through repeated HTTP calls.

Published on npm as [`@arcadedb/driver`](https://www.npmjs.com/package/@arcadedb/driver), with a
provenance attestation: every release is built and published by `publish.yml` from a clean
checkout of this repository, never from anyone's laptop.

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
  params: { 1: 21 },
});
```

A bearer token (for example, a session token returned by `/api/v1/login`) works the same way:

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
}
```

`truncated` is `true` when the server's serializer hit its row cap while a query still had more
rows to write - `result` is then a partial answer, not a short-but-complete one. A client that
returned only `result` would hand back an array a caller cannot tell apart from a complete result
set; the array looks the same shape either way. Always check `truncated` before treating `result`
as the whole answer, and re-query with a narrower filter or a higher `limit` (via
`QueryOptions.limit`) when it is `true` - though a value large enough to exceed the server's hard
ceiling (`arcadedb.server.httpQueryMaxResultRows`) is refused with 413 rather than truncated, so a
narrower filter is the only fix once you're past that ceiling.

`truncated === false` used to be a client-side default rather than a server guarantee: until
26.10.1-SNAPSHOT, `QueryResponse` declared no required fields, so `limit`, `returned` and
`truncated` were all synthesised when the response omitted them. That caveat is retired. The
schema now marks all three **required** and the server sends all three on every query and
command. `result` stayed optional and still defaults to `[]`.

`result` also became a **union** in the same release: an array of rows under the default `record`
serializer, and a single `{ vertices, edges }` object - plus `records` under `studio` - under the
two graph serializers. `QueryEnvelope<T>["result"]` is `T[]` and cannot carry the second shape,
so `query`/`command` throw an `ArcadeDBError` if it ever arrives. It cannot today: this client
sends no `serializer` field, so the server always picks `record`.

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
raises `ArcadeDBError` for it, with a `status` of 200 - honest, since that is the status the
exchange actually carried - exactly as `query`/`command` throw `ArcadeDBError` for a non-2xx
response, so both paths fail the same way; any event already yielded before the error stays
delivered to the caller.

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
`NdJsonBatchEvent`'s error object is the one genuine gap: it declares only `commitIndex`, `status`
and `statusMapped`, not the `error` message and `exception` the server actually sends with them,
so `NdJsonBatchEvent` is widened here by exactly those two fields. That widening was established
against a live 26.10.1-SNAPSHOT server, is reported upstream as
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

One field on that error event is worth branching on. When `statusMapped` is `false`, `status` is
an unclassified 500 fallback rather than the status the buffered encoding would have chosen (an
engine failure raised after the stream had already started). Key on `exception` there, not on
`status`; the thrown `ArcadeDBError` carries `exception` and its `detail` says why.

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

`err.status` is whatever the exchange actually carried, and there is one case where that is `200`:
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

## `exists` cannot prove absence

```ts
const present = await server.exists("mydb");
```

`exists` returns `false` both when the database genuinely does not exist and when it exists but
the authenticated caller is not authorized to see it - the server's response does not distinguish
the two cases, so this client cannot either. Do not treat `false` as proof that a database is
absent; it only means "not visible to this caller right now."

## Contract version and compatibility

This package was generated from `contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json`, recorded in
`package.json` as `arcadedb.serverVersion`:

```json
{
  "arcadedb": {
    "serverVersion": "26.10.1-SNAPSHOT"
  }
}
```

| `@arcadedb/driver` | ArcadeDB server |
| --- | --- |
| 0.1.0 | 26.9.1 |
| 0.2.0 (unreleased) | 26.10.1-SNAPSHOT |

The client speaks ArcadeDB's HTTP API as described by that contract. Pointing it at a server on a
materially different release may work for the endpoints both versions share, but is not tested or
supported.

## Bundling and tree-shaking

`db.ts`, `db.grafana`, `db.promql`, and `db.vector` each load their implementation with a dynamic
`import()` rather than a static one. On a bundler that supports code splitting - Vite, webpack,
Rollup, or esbuild run with `--splitting` - code that only calls `query`, `command`, and
`transaction` gets a chunk that excludes the time-series, Grafana, PromQL, and vector-search
modules; they load only if and when `db.ts`, `db.grafana`, `db.promql`, or `db.vector` is actually
reached. Without code splitting, a bundler inlines those dynamic imports into the single output
file, and all four modules ship regardless of whether they're used. This is verified by
`test/treeshake.test.ts`, which bundles a data-plane-only entry point with esbuild's `splitting`
option on and asserts the PromQL, Grafana, time-series, and vector route markers are all absent
from the chunk reachable via static imports alone - it does not claim, and this README does not
claim, that the package sheds unused code under every bundler configuration.

## License

Apache-2.0.
