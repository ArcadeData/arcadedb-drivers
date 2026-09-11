# @arcadedb/driver-grpc

A TypeScript/JavaScript gRPC client for ArcadeDB's data plane, generated from ArcadeDB's Protobuf
contract with [Connect-ES](https://connectrpc.com/).

If you want an HTTP client instead - including from a browser - see
[`@arcadedb/driver`](../driver/README.md).

Published on npm as [`@arcadedb/driver-grpc`](https://www.npmjs.com/package/@arcadedb/driver-grpc),
with a provenance attestation: every release is built and published by `publish.yml`, dispatched
with `package=driver-grpc`, from a clean checkout of this repository, never from anyone's laptop.

## Requirements

- Node.js `>=20`, Bun, or Deno. See "Runtime targets" below for what that means in practice.
- ESM only. The package has no CommonJS build and no `require()` entry point; import it with
  `import`, not `require`.

## Installation

```bash
npm install @arcadedb/driver-grpc
```

## Runtime targets: Node, Bun, Deno - not browsers

This package targets Node, Bun, and Deno. The underlying transport,
[`@connectrpc/connect-node`](https://www.npmjs.com/package/@connectrpc/connect-node), is built on
Node's `node:http2` module, which Bun and Deno both also implement well enough to run it. Node is
what this repository's CI actually exercises today; Bun and Deno are intended targets that have
not (yet) got a CI job of their own, so treat them as likely-to-work rather than verified.

There is no browser build, and there will not be one until the server changes. This is a server
capability question, not a packaging one: ArcadeDB's `GrpcServerPlugin` is plain grpc-java over
HTTP/2, built on Netty's `NettyServerBuilder`, with no gRPC-Web handler, no Connect protocol, and
no servlet adapter in front of it. A browser cannot speak raw HTTP/2 gRPC framing at all - there
is no protocol translation layer for it to go through - so no client library, however written,
can reach this server from a browser. Anyone who needs a browser client uses
[`@arcadedb/driver`](../driver/README.md) over HTTP instead.

## Quick start

```ts
import { createClient, passwordAuth } from "@arcadedb/driver-grpc";

const grpc = createClient({
  baseUrl: "https://localhost:50051",
  auth: passwordAuth("root", "playwithdata", "mydb"),
});

const response = await grpc.raw.executeQuery({
  database: "mydb",
  query: "SELECT FROM Person WHERE age > 21",
  language: "sql",
});
```

`raw` is the generated Connect client for `ArcadeDbService` (the data plane) - every RPC the
`.proto` contract declares is callable through it. `createClient` adds three ergonomic wrappers
on top for the RPCs the generated client alone handles badly: `streamQuery`, `insertStream`, and
`transaction`. Everything else - the unary CRUD calls, `vectorSearch`/`hybridSearch`/
`fullTextSearch`, `insertBidirectional`, `graphBatchLoad` - is used directly through `raw` at the
top level; the CRUD calls and the three search RPCs also get a `TransactionHandle` wrapper once a
transaction is open (see "Transactions" and "Vector, hybrid and full-text search" below) -
`insertBidirectional` and `graphBatchLoad` never do, at any level.

## Authentication

Two helpers build an `Interceptor` to pass as `auth`:

```ts
import { bearerAuth, passwordAuth } from "@arcadedb/driver-grpc";

bearerAuth("AU-..."); // sets `authorization: Bearer <token>` metadata
passwordAuth("root", "playwithdata", "mydb"); // sets x-arcade-user / x-arcade-password / x-arcade-database metadata
```

`passwordAuth` sends the password in plaintext gRPC metadata, so `createClient` **refuses** to
pair it with a non-TLS (`http://`) `baseUrl` unless you pass `insecure: true` explicitly:

```ts
createClient({ baseUrl: "http://localhost:50051", auth: passwordAuth("root", "pw") });
// throws: refusing to send a plaintext password over insecure baseUrl "http://localhost:50051"

createClient({ baseUrl: "http://localhost:50051", auth: passwordAuth("root", "pw"), insecure: true });
// fine - you opted in
```

Be aware of the limits of this check: it recognizes only the exact `Interceptor` value
`passwordAuth` itself returned (via an internal marker on that value), not any interceptor that
happens to set the same headers - and not any interceptor other than the one `passwordAuth`
returned, including a wrapper around it. Composing `passwordAuth(...)` with another interceptor
(logging, retry, call-recording) produces a new function value that does not carry the marker, so
the refusal is silently skipped even though a real `passwordAuth` password is still being sent in
plaintext underneath. A hand-rolled interceptor that sets `x-arcade-password` directly is not
caught either. This check is a safety net for callers who pass `passwordAuth(...)` straight
through as `auth`, not a general scan of outgoing metadata.

## Streaming queries: `streamQuery`

```ts
for await (const row of grpc.streamQuery({
  database: "mydb",
  query: "SELECT FROM Person",
  language: "sql",
})) {
  console.log(row.rid, row.properties);
}
```

`streamQuery` flattens the server's stream of row batches into one row at a time, so the calling
code never has to unwrap `QueryResult.records` itself. That is the only thing it does - it does
not choose `retrievalMode` or `batchSize` for you. `retrievalMode` is deliberately the caller's
choice, because the three modes the `.proto` contract defines differ materially in memory and
consistency behavior:

- `CURSOR` (the default) - runs the query once and streams results as you iterate.
- `MATERIALIZE_ALL` - loads the entire result set on the server first, then emits it in batches.
- `PAGED` - re-issues the query with `LIMIT`/`SKIP` per batch.

Pick `CURSOR` for a large result set you want to bound memory on; `MATERIALIZE_ALL` when you need
a stable snapshot and can afford to hold it server-side; `PAGED` when you want each batch's
consistency independent of the others. This wrapper does not, and should not, guess which one a
given query needs.

## Streaming inserts: `insertStream`

```ts
async function* rows() {
  yield [{ type: "Person", properties: { name: { kind: { case: "stringValue", value: "Alice" } } } }];
  yield [{ type: "Person", properties: { name: { kind: { case: "stringValue", value: "Bob" } } } }];
}

const summary = await grpc.insertStream({
  database: "mydb",
  options: { targetClass: "Person" },
  chunks: rows(),
});

console.log(summary.inserted, summary.failed);
```

`chunks` is an `AsyncIterable` of row batches - one element becomes exactly one wire
`InsertChunk`. The caller decides how many rows go in each batch and when to yield the next one;
`insertStream` owns only the envelope bookkeeping around those batches, which it would otherwise
be easy to get wrong by hand:

- one `session_id` (a fresh UUID), stable for the whole stream
- `chunk_seq` starting at 1 and incrementing by 1 per chunk
- `database` set on the first chunk only, per the `.proto` contract
- `last: true` on the final chunk only

An empty `chunks` iterable is not an error. A filter that matched nothing is a legitimate reason
to have zero rows to insert, and this package should not turn that into an exception - the same
principle `@arcadedb/driver`'s README documents for `truncated`. `insertStream` sends a single
chunk with zero rows and `last: true`, and returns whatever `InsertSummary` the server gives back
for it (verified against a real server: this is accepted cleanly, in under 100ms, and comes back
as an all-zero summary) - it does not invent a summary itself.

### The `InsertOptions.database` workaround

`insertStream` also sets `options.database` to the same value as the first chunk's `database`.
This is a compatibility workaround for servers older than the fix for
[ArcadeData/arcadedb#6597](https://github.com/ArcadeData/arcadedb/issues/6597) (merged in
`7ccade7348`, **released in 26.9.1**): `InsertChunk.database` is marked `// REQUIRED` on the first
chunk in `arcadedb-server.proto`, but on **26.8.1 and every earlier release** the server's
`InsertContext` construction only reads `InsertOptions.database` - it never looks at
`InsertChunk.database` at all. Without this mirroring, a stream against such a server inserts
nothing: the server reports the rows as `received` with `inserted: 0`, or fails at the deferred
commit with `Invalid database name: name is required`, even though `database` was sent exactly as
the contract specifies. A server carrying the #6597 fix prefers a non-empty `InsertChunk.database`
and falls back to `InsertOptions.database`, so setting both to the same value here can never
disagree.

That boundary is measured, not inferred. A single-chunk stream carrying `database` on the chunk
with `options.database` left empty inserts **0 of 2** rows on `arcadedata/arcadedb:26.8.1` and
**2 of 2** on both `26.9.1` and `26.10.1-SNAPSHOT`; `7ccade7348` is an ancestor of the `26.9.1`
tag and not of `26.8.1`. Earlier revisions of this paragraph said the fix was "not yet in a
release", which was already stale when written and which the mechanical version rewrite in
`scripts/adopt-contract-version.sh` then compounded into a claim about 26.10.1-SNAPSHOT.

The consequence: **every server version this package claims support for carries the fix** (the
compatibility table below starts at 26.9.1), so the mirror is belt-and-braces rather than
load-bearing today. It is still sent, because removing it would be a behaviour change; retiring it
is tracked as a follow-up.

## Transactions: `transaction`

```ts
const totalRow = await grpc.transaction("mydb", async (tx) => {
  await tx.executeCommand({ command: "INSERT INTO Account SET balance = 100", language: "sql" });
  const { results } = await tx.executeQuery({ query: "SELECT sum(balance) as total FROM Account", language: "sql" });
  return results[0]?.records[0];
});
```

`transaction` begins a server-side transaction, hands the callback a `TransactionHandle` whose
calls (`executeQuery`, `executeCommand`, `createRecord`, `updateRecord`, `deleteRecord`,
`lookupByRid`, `streamQuery`, `vectorSearch`, `hybridSearch`, `fullTextSearch`) all carry the transaction's id automatically, and ends the
transaction on both the success and failure paths: the callback resolving commits, the callback
throwing or rejecting rolls back and re-throws the callback's own error. This is the safety net
against forgetting, dropping, or mismatching a transaction id by hand - the exact class of defect
a 2026 gRPC audit found three times in ad hoc transaction code.

A resolved `commitTransaction` call is not, by itself, proof of a commit: the server answers a
transaction id it no longer recognises (for example, one reaped after sitting idle past the
server's idle timeout) with `success=true, committed=false` and no error status at all. `transaction`
reads `committed` and throws - including the server's own message - rather than reporting success
for a transaction whose writes were silently lost. `beginTransaction`'s response is checked the
same way: a missing or blank transaction id throws immediately instead of running the callback
against a handle that would silently auto-commit every statement.

`beginTransaction`, `commitTransaction`, and `rollbackTransaction` are the calls `transaction`
manages for you; the `.proto` contract also lets a request carry inline `begin` / `commit` flags
on individual RPCs, so a call can begin or end a transaction as a side effect without a separate
`BeginTransaction`/`CommitTransaction` round trip. This wrapper deliberately does not wrap those
flags - they are reachable through `grpc.raw` for callers who want that shape, but `transaction`
only ever manages transactions the explicit way.

### `bulkInsert` and `insertStream` cannot join a `transaction()` on this server

`TransactionHandle` deliberately does **not** include `bulkInsert` or `insertStream`. On **26.8.1
and every earlier release**, `ArcadeDbGrpcService#bulkInsert` and `#insertStream` never read the
request's transaction context at all: each builds its own `InsertContext`, which resolves its own
`Database` and commits independently, regardless of any
`BeginTransaction`/`CommitTransaction`/`RollbackTransaction` the caller issued around it. Binding
them into a `TransactionHandle` would silently lie about this: their writes are **not** part of the
transaction, they commit even when the transaction's callback throws, and they survive a rollback.
Both remain available outside a transaction - `grpc.insertStream`/`grpc.raw.insertStream` and
`grpc.raw.bulkInsert` - but never through `tx`.

[ArcadeData/arcadedb#6607](https://github.com/ArcadeData/arcadedb/issues/6607) was filed against
this gap and **has since landed**: its fix (`79d931070b`) is an ancestor of the `26.9.1` tag and
not of `26.8.1`. Measured against real servers - begin a transaction over `BeginTransaction`, run
an `InsertStream` carrying that server-issued `transaction_id`, then roll back - the rows survive
the rollback on `26.8.1` and are correctly discarded on both `26.9.1` and `26.10.1-SNAPSHOT`, with
a commit persisting them on all three. So the restriction is now **removable** for every server
version this package supports. It is kept for now because lifting it adds public surface, which is
a deliberate release decision rather than a documentation fix; it is tracked as a follow-up.

## Vector, hybrid and full-text search: `VectorSearch`, `HybridSearch`, `FullTextSearch`

```ts
// Outside a transaction: through raw, like any other unary RPC.
const nearest = await grpc.raw.vectorSearch({ database: "mydb", indexName: "myIndex", queryVector: [0.1, 0.2, 0.3], k: 5 });

// Inside one: through the handle, which forces `database` and `transaction` the same way every
// other bound call does.
await grpc.transaction("mydb", async (tx) => {
  const fused = await tx.hybridSearch({ vectorIndexName: "myIndex", queryVector: [0.1, 0.2, 0.3], fulltextIndexName: "myTextIndex", fulltextQuery: "cat" });
  const matches = await tx.fullTextSearch({ queryText: "cat" });
});
```

These three RPCs are reached exactly two ways, and no third: `raw.vectorSearch` / `raw.hybridSearch`
/ `raw.fullTextSearch` outside any transaction, and `tx.vectorSearch` / `tx.hybridSearch` /
`tx.fullTextSearch` bound to one once it is open (see "Transactions" above for the full list of
what `tx` carries). There is deliberately **no top-level `grpc.vectorSearch`** alongside
`streamQuery`/`insertStream`/`transaction`: those three exist because the generated client alone
handles them badly - `streamQuery` needs its batches flattened, `insertStream` needs envelope
bookkeeping, `transaction` needs begin/commit/rollback sequencing. A unary RPC the generated stub
already calls directly and correctly gains nothing from a same-shaped top-level alias; the only
thing worth hand-writing for `VectorSearch`/`HybridSearch`/`FullTextSearch` was the transaction
binding, which is exactly what the handle provides.

Each call returns the whole generated response message, never unwrapped to `results` alone:
`VectorSearchResponse` and `HybridSearchResponse` carry `truncated` alongside `results`, `count`,
and `scoring`. `truncated` is `true` when the search's bounded candidate window was filled, meaning
more matches may exist beyond what `results` holds - a caller who reads `results` and never checks
`truncated` works off a partial answer without being told. `FullTextSearchResponse` carries **no**
`truncated` field at all in the `.proto` contract - not `false`, simply absent from the message -
because full-text search has no candidate-window concept to overflow the way a vector search does.

`efSearch` (the dense-index search beam width) and each RPC's result-limit field (`k` for
`VectorSearchRequest`/`HybridSearchRequest`, `limit` for `FullTextSearchRequest`) are bounded, but
the bound is enforced **server-side**. Neither `raw` nor the handle validates them locally, so an
out-of-range value surfaces as a `ConnectError` from the server's response, not as a client-side
`throw` before the request is ever sent.

## The admin service is not a supported path

The `.proto` contract also defines `ArcadeDbAdminService` (`Ping`, `GetServerInfo`,
`ListDatabases`, `ExistsDatabase`, `CreateDatabase`, `DropDatabase`, `GetDatabaseInfo`,
`CreateUser`, `DeleteUser`). `createClient` does not wire up a client for it, and this package
does not export one. There is no deep import that gets you one either: the `exports` map in
`package.json` exposes only this package's own entry point, so `@arcadedb/driver-grpc/gen/...` is
not a reachable path for an installed copy. If you need it, generate your own Connect client
against `contracts/arcadedb-server-<version>.proto` the same way this package's own `raw` client
is generated - the `.proto` is a plain source file, not something only this package can read.

The reason is its auth model, not an oversight: every `ArcadeDbAdminService` RPC authenticates
from a `credentials` field inside the request message itself, rather than from gRPC metadata the
way every data-plane call in this package does. Wrapping it here would mean this package's
`auth` option meant one thing for `raw` and `streamQuery`/`insertStream`/`transaction`, and
something else again for admin calls. `@arcadedb/driver` already covers the admin service's
actual job - server discovery and database lifecycle (`listDatabases`, `exists`, create/drop) -
over HTTP, so there is no gap this package needs to fill.

## Errors: `ConnectError`, not `ArcadeDBError`

A failed call throws Connect's own `ConnectError`, not the `ArcadeDBError` that
`@arcadedb/driver`'s facade methods throw:

```ts
import { ConnectError } from "@connectrpc/connect";

try {
  await grpc.raw.executeQuery({ database: "mydb", query: "SELECT FROM NoSuchType", language: "sql" });
} catch (err) {
  if (err instanceof ConnectError) {
    console.error(err.code, err.message, err.details);
  }
}
```

This is a deliberate asymmetry with `@arcadedb/driver`, not an inconsistency to be fixed later.
The two transports carry genuinely different error information - a gRPC status code and details
message versus an HTTP status and a JSON error body - and translating one into the other's shape
would either drop information or invent fields the underlying transport never provided. Each
client surfaces the error its own transport actually gives it.

## Contract version and compatibility

This package was generated from `contracts/arcadedb-server-26.10.1-SNAPSHOT.proto`, recorded in
`package.json` as `arcadedb.serverVersion`:

```json
{
  "arcadedb": {
    "serverVersion": "26.10.1-SNAPSHOT"
  }
}
```

| `@arcadedb/driver-grpc` | ArcadeDB server |
| --- | --- |
| 0.1.0 | 26.9.1 |
| 0.2.0 (unreleased) | 26.10.1-SNAPSHOT |

Pointing it at a server on a materially different release may work for the RPCs both versions
share, but is not tested or supported.

## License

Apache-2.0.
