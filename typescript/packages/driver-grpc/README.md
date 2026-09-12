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
`.proto` contract declares is callable through it. `createClient` adds five ergonomic wrappers
on top for the RPCs the generated client alone handles badly: `streamQuery`, `insertStream`,
`timeSeriesQuery`, `timeSeriesWriteStream`, and `transaction`. Everything else - the unary CRUD
calls, `vectorSearch`/`hybridSearch`/`fullTextSearch`, `insertBidirectional`, `graphBatchLoad`,
`TimeSeriesWrite`, `TimeSeriesLatest` - is used directly through `raw` at the top level; the CRUD
calls, the three search RPCs, and `TimeSeriesLatest` also get a `TransactionHandle` wrapper once a
transaction is open (see "Transactions", "Vector, hybrid and full-text search", and "Time series"
below) - `insertBidirectional`, `graphBatchLoad`, and `TimeSeriesWrite` never do, at any level.

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

## Time series: `timeSeriesWriteStream`, `timeSeriesQuery`, `timeSeriesLatest`, `TimeSeriesWrite`

Four RPCs, four different treatments:

| RPC | Reached how |
| --- | --- |
| `TimeSeriesWriteStream` | `grpc.timeSeriesWriteStream` - a client-streaming wrapper, like `insertStream` |
| `TimeSeriesQuery` | `grpc.timeSeriesQuery` outside a transaction, `tx.timeSeriesQuery` bound to one |
| `TimeSeriesLatest` | `tx.timeSeriesLatest` only - no top-level alias exists |
| `TimeSeriesWrite` (the unary write) | `grpc.raw.timeSeriesWrite` only - no wrapper at any level |

```ts
import { TimeSeriesPrecision } from "@arcadedb/driver-grpc";

async function* chunks() {
  yield [{ timestamp: 1_000n, fields: { value: { kind: { case: "doubleValue", value: 22.5 } } } }];
  yield [{ timestamp: 2_000n, fields: { value: { kind: { case: "doubleValue", value: 23.1 } } } }];
}

const summary = await grpc.timeSeriesWriteStream({
  database: "mydb",
  type: "Temperature",
  precision: TimeSeriesPrecision.TS_PRECISION_MILLISECONDS,
  chunks: chunks(),
});
console.log(summary.written, summary.dropped);

for await (const result of grpc.timeSeriesQuery({ database: "mydb", type: "Temperature" })) {
  console.log(result.rows);
}

const latest = await grpc.transaction("mydb", (tx) => tx.timeSeriesLatest({ type: "Temperature" }));
```

### `precision` is required, not defaulted

`TimeSeriesWriteStreamRequest.precision` carries no `?` - every call must set it, unlike almost
every other field this package passes straight through unchanged. `TimeSeriesPrecision`'s proto3
zero value is `TS_PRECISION_MILLISECONDS`, so a caller who omits the field and one who explicitly
wrote milliseconds produce the **identical** wire message - the server has no way to tell "you
didn't say" from "you said milliseconds". That collision matters more than a typical proto3
default-value gotcha because of what ArcadeDB's other time-series ingest path does: HTTP's
`POST /api/v1/ts/{database}/write` speaks InfluxDB Line Protocol, whose own omitted-precision
default is **nanoseconds** - a factor of 10^6 away from gRPC's default of milliseconds. A caller
porting a working HTTP ingest pipeline to this client who drops the field would have every
timestamp misread by a million, silently, with no error raised on either side. Requiring
`precision` on `TimeSeriesWriteStreamRequest` turns that into a compile-time error instead of a
silent data-corruption bug.

**The same trap is wide open on the raw unary path, where nothing can protect you.**
`TimeSeriesWriteRequest.precision` is field 4 of the same enum, with the same proto3 zero value,
and `TimeSeriesWrite` is reachable only as `grpc.raw.timeSeriesWrite` (see the table above) - a
generated request type this package does not wrap and cannot make any field required on. A caller
who follows that table to `raw.timeSeriesWrite` for one-shot writes and omits `precision` hits
exactly the 10^6 misread described here, with no wrapper standing in the way. Set `precision`
explicitly on **every** `raw.timeSeriesWrite` call. This is not an argument for wrapping
`TimeSeriesWrite` - the reasons it stays `raw`-only are below, and they still hold - it is a
warning that the protection above stops at the streaming wrapper's edge.

### `database`, `type` and `precision` repeat on every chunk, not just the first

Unlike `insertStream`'s envelope (`database` on the first chunk only, `last: true` on the final
one), `TimeSeriesWriteChunk` declares no `session_id`, `chunk_seq` or `last` field on the wire at
all. `timeSeriesWriteStream` therefore simply sets `database`, `credentials`, `type` and
`precision` on **every** chunk it sends, and `insertStream`'s `InsertOptions.database` mirroring
workaround (see above) has nothing to port here: `TimeSeriesWriteChunk` was never shown to share
`InsertChunk`'s bug (ArcadeData/arcadedb#6597).

That repetition is a deliberate **simplification on this wrapper's part, not something the
`.proto` requires** - an earlier version of this section said the contract asked for it, and the
contract says the opposite. `TimeSeriesWriteChunk.database` is documented there as "REQUIRED on
the first chunk; ignored on later ones (the server caches the first chunk's database)", so a
first-chunk-only semantic **does** exist on this RPC. Repeating `database` is safe precisely
because the server ignores the later copies, and it spares the wrapper a first-chunk special case
it has no other reason to carry.

The one thing repetition costs is `type`. The contract documents `TimeSeriesWriteChunk.type` as
the default measurement for points in **that** chunk, so a stream may switch measurement between
chunks without naming it on every point. `TimeSeriesWriteStreamRequest` takes a single stream-wide
`type` and sets it on every chunk, so **this wrapper does not expose that per-chunk default**. A
caller who needs to mix measurements in one stream sets `type` on each `TimeSeriesPoint` instead,
which still works and is unaffected by the chunk-level default.

### An empty `chunks` iterable sends zero wire chunks, not one - and the server accepts it

`insertStream`'s empty case sends a single chunk with zero rows and `last: true`, because
`InsertChunk` needs that flag to ever become `true` and `database` needs to land on some chunk.
`TimeSeriesWriteChunk` has neither field, so an empty `chunks` here sends **zero** wire chunks -
the server is never told `database`, `type` or `precision` at all. Verified against a real server:
this is accepted cleanly, not rejected, and comes back as a `TimeSeriesWriteSummary` with every
count (`received`, `written`, `dropped`, and all three type lists below) at zero.

### A successful write can still report `written < received`

`TimeSeriesWriteStream` is not atomic: each measurement's batch commits its own shard transaction
as it is appended, so a failure partway through leaves everything before it durable. The returned
`TimeSeriesWriteSummary` always carries `received`, `written`, `dropped`, plus three separate
reasons a point can be dropped:

- `unknownTypes` - no type with this name exists (create it first with `CREATE TIMESERIES TYPE`)
- `nonTimeSeriesTypes` - the type exists, but is not a TIMESERIES type
- `unavailableTypes` - the type is a TIMESERIES type, but its storage engine failed to load

**Checking only that the call resolved without throwing is not checking that the data landed** -
a call can succeed and still report `dropped > 0`. Always read the summary, the same way
`streamQuery`'s callers are expected to read `truncated` rather than trust an empty catch block.

### Two RPCs with no wrapper or binding - for two different reasons, with two different futures

`TimeSeriesWrite` has no wrapper at any level, and `TimeSeriesLatest` has no top-level alias.
Both look like the same shape of gap from the outside, but they are not the same kind of gap, and
should not be described the same way:

- **`TimeSeriesWrite` is `raw`-only because its message carries no `transaction` field at all** -
  a **contract** limit. `TimeSeriesWriteRequest` simply never declares a field to bind, the same
  way `TimeSeriesWriteChunk` (the streaming version) never does. No server release, however
  capable, can make `grpc.raw.timeSeriesWrite` transaction-aware without the `.proto` itself
  growing a `transaction` field first - there is nothing this package could do differently today.
- **`insertStream`'s absence from `TransactionHandle` is a server bug, already fixed, not a
  contract limit.** `InsertStreamRequest`/`InsertChunk` DO carry a `transaction` field on the
  wire - it is set and forwarded on every chunk (see "Streaming inserts" above). The exclusion
  exists because, on 26.8.1 and earlier, the server's `InsertContext` construction ignored that
  field entirely ([ArcadeData/arcadedb#6607](https://github.com/ArcadeData/arcadedb/issues/6607)).
  That bug is fixed as of 26.9.1, measured against a real server (see "`bulkInsert` and
  `insertStream` cannot join a `transaction()`" above) - the exclusion is now **removable with no
  contract change**, and is kept only because lifting it adds public surface, a deliberate release
  decision rather than a documentation fix.

So `TimeSeriesWrite`'s status is not on the same follow-up list as `insertStream`'s: one needs the
`.proto` contract to change upstream before this package could do anything about it; the other
needs only this package to decide to expose what the server can already do.

### `tags` and `limit` on `TimeSeriesQueryRequest` are enforced server-side

A name in `TimeSeriesTagFilter.equals` that is not one of the type's declared TAG columns is not
dropped from the filter - it is **refused**, with `INVALID_ARGUMENT` naming the offending tag and
listing the type's declared TAG columns. Silently ignoring it would widen the query to every
series, and a caller has no way to tell that result apart from a filter that legitimately matched
everything ([ArcadeData/arcadedb#7334](https://github.com/ArcadeData/arcadedb/issues/7334)).

`limit` bounds rows *or* aggregation buckets, whichever the query produces - not rows only.
Non-positive means "no limit of the client's own," not "use the server default." The server-side
ceiling is `arcadedb.server.grpcTimeSeriesMaxResultRows`, and a `limit` above it is refused with
`RESOURCE_EXHAUSTED` **before the first message is streamed**, so a caller can never mistake a
partial series for a complete one
([ArcadeData/arcadedb#7390](https://github.com/ArcadeData/arcadedb/issues/7390)).

Both rules are enforced **server-side**, the same way `efSearch` and the vector/full-text
result-limit fields are (see "Vector, hybrid and full-text search" below): this package validates
neither a tag name against a schema it does not have nor `limit` against a ceiling it does not
know, so a violation surfaces as a `ConnectError` from the server's response, not a client-side
`throw` before the request is ever sent.

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

## The control plane: `rawAdmin`

The `.proto` contract declares a second service alongside `ArcadeDbService`: `ArcadeDbAdminService`,
ArcadeDB's control plane - database lifecycle, users, groups, API tokens, server and database
settings, backups, the profiler, cluster and shutdown operations, and the two probes. `createClient`
builds a generated Connect client for it from the **same** transport it builds `raw` from, and
returns it as `rawAdmin`:

```ts
const grpc = createClient({ baseUrl: "https://localhost:50051" });

const info = await grpc.rawAdmin.getServerInfo({
  credentials: { username: "root", password: "playwithdata" },
});
```

There is no facade over it, and that is the design rather than an omission. `streamQuery`,
`insertStream`, `timeSeriesWriteStream` and `transaction` exist because the generated client alone
handles those four RPCs badly - batches to flatten, envelope bookkeeping to get right, a
begin/commit/rollback sequence to hold together. 41 of the admin service's 44 RPCs are plain unary
calls: build a request message, await one response message. A wrapper around any of those would be
a renamed passthrough, which is the bar `vectorSearch` and `timeSeriesWrite` are already held to
above.

### The 44 RPCs

Every backticked name between the two markers below is one RPC of `ArcadeDbAdminService`, and a
test asserts that this set equals the generated stub's own method set. A hand-written list of 44
names is exactly the kind of prose that rots on the next contract bump, and a stale list is worse
than no list, because a reader trusts it.

<!-- admin-rpcs:begin -->

| Group | RPCs |
| --- | --- |
| Databases | `CreateDatabase`, `DropDatabase`, `OpenDatabase`, `CloseDatabase`, `AlignDatabase`, `ExistsDatabase`, `GetDatabaseInfo`, `GetProgress` |
| Discovery and probes | `Ping`, `GetServerInfo`, `ListDatabases`, `Health`, `Ready` |
| Security | `CreateUser`, `UpdateUser`, `DeleteUser`, `ListUsers`, `ListGroups`, `SaveGroup`, `DeleteGroup`, `ListApiTokens`, `CreateApiToken`, `DeleteApiToken` |
| Settings | `SetServerSetting`, `SetDatabaseSetting` |
| Backup | `GetBackupConfig`, `SetBackupConfig`, `ListBackups`, `TriggerBackup`, `DeleteBackup` |
| Profiler | `ProfilerStart`, `ProfilerStop`, `ProfilerReset`, `ProfilerResults`, `ProfilerList`, `ProfilerLoad` |
| Server and cluster | `GetServerEvents`, `Shutdown`, `DisconnectCluster`, `ConnectCluster`, `ListSessions` |
| Restore and import (server-streaming) | `RestoreBackup`, `RestoreDatabase`, `ImportDatabase` |

<!-- admin-rpcs:end -->

Authorization is the server's business, not this client's, and it is not uniform across that table:
`Ping`, `GetServerInfo`, `ListDatabases`, `ExistsDatabase` and `GetDatabaseInfo` need only a valid
account, `GetProgress` needs an account granted the database it names, and everything else needs
the server-admin (root) principal. `CreateDatabase`, `DropDatabase`, `CreateUser`, `DeleteUser`,
`RestoreBackup`, `RestoreDatabase` and `ImportDatabase` are additionally refused on a cluster
follower with `FAILED_PRECONDITION` and the leader's address on the `arcadedb-leader-*` trailers -
gRPC has no request proxy, so the caller redirects itself rather than being forwarded.

### The three server-streaming RPCs

`RestoreBackup`, `RestoreDatabase` and `ImportDatabase` return `stream RestoreProgress` /
`stream ImportProgress` instead of a single response, and that shape is deliberate: a restore or an
import can run for minutes, so the server reports progress as it goes and the call stays cancellable
throughout rather than being a single opaque await that either returns or times out.

They are also the three the bare stub drives least comfortably. A unary admin call is one line; a
server-streaming one is a `for await` loop that has to decide what to do with each progress message,
and has to treat an abandoned loop as a cancellation that leaves the restore's fate up to the
server. Nothing in this package smooths that over - if these three ever earn a wrapper, they are the
candidates, on the same grounds `streamQuery` earned its own.

### `Health` and `Ready` take empty request messages

`HealthRequest` and `ReadyRequest` declare no fields at all - not even `credentials`. They are
exempt from the server's auth interceptor exactly as `GET /health` and `GET /ready` are
unauthenticated over HTTP, so a container orchestrator can probe a node without an account.
`grpc.rawAdmin.health({})` is the entire call; there is nothing left for a facade to simplify.

### `auth` does nothing for the admin service

42 of the 44 RPCs above authenticate from a `DatabaseCredentials` field **inside the request
message** - the `credentials: { username, password }` in the example at the top of this section, set
per call - rather than from gRPC metadata, the way every data-plane call in this package does. This
is a property of the contract, not of this client, and it is the single most surprising thing about
`rawAdmin`: `bearerAuth` and `passwordAuth` authenticate the **data plane** only. Pass one as `auth`
and its metadata is still sent on an admin call, and the server still authenticates that call from
the request body and ignores it. (`Health` and `Ready` are the other two, and they carry no
credentials because they are not authenticated at all.)

That placement also defeats the plaintext-password guard described under "Authentication" above.
That check keys on an internal marker attached to the `Interceptor` value `passwordAuth` returned,
so it can only ever see a password an interceptor is about to put in metadata; a password sitting in
a request body is invisible to it. `rawAdmin` therefore carries its **own** guard against the same
hazard:

```ts
const grpc = createClient({ baseUrl: "http://localhost:50051" });
await grpc.raw.executeQuery({ database: "mydb", query: "SELECT 1", language: "sql" }); // fine

grpc.rawAdmin;
// throws: refusing to expose ArcadeDbAdminService over insecure baseUrl "http://localhost:50051"

createClient({ baseUrl: "http://localhost:50051", insecure: true }).rawAdmin; // fine - you opted in
createClient({ baseUrl: "https://localhost:50051" }).rawAdmin; // fine - TLS, nothing to opt into
```

Three things about that guard are deliberate:

- **It fires when `rawAdmin` is read, not when `createClient` is called.** A caller who only ever
  touches the data plane over a plain `http://` baseUrl is entirely unaffected: their client is
  constructed exactly as it always was, and nothing about exposing the admin stub can throw at them.
- **It is unconditional on `auth`.** The credentials at risk are in the request body, not in
  anything an interceptor puts on the wire, so the refusal is identical with `bearerAuth`, with
  `passwordAuth`, and with no `auth` at all.
- **`Health` and `Ready` are refused too**, even though they carry no credentials. The guard
  protects the stub as a whole rather than a per-RPC list, and carving those two back out would mean
  wrapping the other 42 - the facade this package deliberately does not have. Probing health over a
  plaintext channel costs one `insecure: true`, and that is the cheaper end of the trade.

The check is `protocol !== "https:"`, not `=== "http:"`, for the reason "Authentication" gives:
`new URL("localhost:50051").protocol` is `"localhost:"`, so a strict `http:` comparison would wave
through exactly the schemeless `baseUrl` a caller who forgot the scheme would write.

### `CreateApiToken` returns secret material, and nothing here reads it

`CreateApiTokenResponse.token` is a freshly minted API token in cleartext - the only time the server
will ever show it, which is why `DeleteApiToken` revokes by hash and refuses to accept the token
itself. This package never touches that response. Both auth interceptors set request headers and
`return next(req)` without looking at what comes back; they are request-side by construction, and
the package contains no logging at all - no `console.*`, nothing. A token cannot reach a log sink
through this client, which is the property
[ArcadeData/arcadedb#7309](https://github.com/ArcadeData/arcadedb/issues/7309) argues for
server-side. That is pinned by a test rather than left as a reading of the source, so an interceptor
that started inspecting responses, or a stray `console.log`, fails the suite.

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
