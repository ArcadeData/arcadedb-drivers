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

`limit` and `truncated` in the envelope above both default when the server's response omits them
(`limit` to `-1`, meaning uncapped; `truncated` to `false`) - `QueryResponse` has no required
fields in the generated schema, so both are, strictly, optional on the wire. In practice the
server always sends both today, but a caller relying on `truncated === false` as proof of
completeness is trusting a client-side default, not a server guarantee.

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

Both methods reach the server through the generated client's own streaming primitive -
`client.POST(..., { parseAs: "stream" })` - rather than a hand-rolled `fetch` or a second HTTP
client of their own; that is what lets them reuse the same base URL, auth, and error mapping every
other call on this client already goes through. Anyone adding another streaming endpoint to this
package should do the same rather than reaching for a bare `fetch`.

Streaming `/batch` is not part of this client; see
[#52](https://github.com/ArcadeData/arcadedb-drivers/issues/52).

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
