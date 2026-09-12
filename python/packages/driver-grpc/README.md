# arcadedb-driver-grpc

A Python gRPC client for [ArcadeDB](https://arcadedb.com)'s data plane, generated from ArcadeDB's
protobuf contract (`contracts/arcadedb-server-*.proto`), with a hand-written facade on top for
authentication, the two streaming RPCs, and explicit transactions.

If you want an HTTP client instead - including one that works from environments gRPC cannot reach -
see [`arcadedb-driver`](../driver/README.md).

Published on PyPI as [`arcadedb-driver-grpc`](https://pypi.org/project/arcadedb-driver-grpc/), with
attestations: every release is built and published by `publish-python.yml`, dispatched with
`package=driver-grpc`, from a clean checkout of this repository through PyPI's trusted publishing,
with no long-lived token anywhere in the chain.

## Requirements

- Python `>=3.10`.
- An ArcadeDB server with the gRPC plugin enabled, at or near the version in the compatibility
  table below.

## Installation

```bash
pip install arcadedb-driver-grpc
```

or, in a [uv](https://docs.astral.sh/uv/) project:

```bash
uv add arcadedb-driver-grpc
```

## Quick start

```python
from arcadedb_driver_grpc import create_client, messages

with create_client("localhost:50051", insecure=True) as client:
    response = client.raw.ExecuteQuery(
        messages.ExecuteQueryRequest(database="mydb", query="SELECT FROM Person WHERE age > 21", language="sql")
    )
    for result in response.results:
        for record in result.records:
            print(record.rid, dict(record.properties))
```

`target` is gRPC's native `host:port` form - `"localhost:50051"`, not a URL. There is no scheme to
parse and nothing to default: pass `credentials=grpc.ssl_channel_credentials()` for TLS, or
`insecure=True` to say explicitly that you want a plaintext channel.

`raw` is the generated stub for `com.arcadedb.grpc.ArcadeDbService` - every RPC the `.proto`
contract declares is reachable through it. `create_client` adds five wrappers on top for the RPCs
the generated stub alone handles badly: `stream_query`, `insert_stream`, `time_series_query`,
`time_series_write_stream`, and `transaction`. Everything else - the unary CRUD calls,
`VectorSearch`/`HybridSearch`/`FullTextSearch`, `BulkInsert`, `InsertBidirectional`,
`GraphBatchLoad`, `TimeSeriesWrite`, `TimeSeriesLatest` - is used directly through `raw` at the top
level, exactly as in the example above; the CRUD calls, the three search RPCs, and
`TimeSeriesLatest` also get a `TransactionHandle` wrapper once a transaction is open (see
"Transactions", "Vector, hybrid and full-text search", and "Time series" below) - `BulkInsert`,
`InsertBidirectional`, `GraphBatchLoad`, and `TimeSeriesWrite` never do, at any level.

The async facade mirrors the sync one method-for-method:

```python
import asyncio

from arcadedb_driver_grpc.aio import create_client
from arcadedb_driver_grpc import messages


async def main() -> None:
    async with create_client("localhost:50051", insecure=True) as client:
        response = await client.raw.ExecuteQuery(
            messages.ExecuteQueryRequest(database="mydb", query="SELECT FROM Person WHERE age > 21", language="sql")
        )
        for result in response.results:
            for record in result.records:
                print(record.rid, dict(record.properties))


asyncio.run(main())
```

The two `create_client`s are deliberately two functions rather than one function with a sync/async
switch: `arcadedb_driver_grpc.create_client` returns `ArcadeDBGrpcClient`, `arcadedb_driver_grpc.aio.create_client`
returns `AsyncArcadeDBGrpcClient`, and importing from `.aio` is the signal for which one you get.

## Authentication, and why `client.raw` is authenticated too

```python
from arcadedb_driver_grpc import bearer_auth, create_client, password_auth

bearer_auth("AU-...")  # authorization: Bearer <token>
password_auth("root", "playwithdata", "mydb")  # x-arcade-user / x-arcade-password / x-arcade-database
```

Both helpers return an `Auth` value that `create_client` turns into a **channel** interceptor, not
per-call metadata. That is not a stylistic choice: the top-level client wraps only five things -
`stream_query`, `insert_stream`, `time_series_query`, `time_series_write_stream`, and the three
transaction RPCs (`BeginTransaction`, `CommitTransaction`, `RollbackTransaction`) that
`transaction` manages internally. The six CRUD RPCs (`ExecuteQuery`, `ExecuteCommand`,
`CreateRecord`, `UpdateRecord`, `DeleteRecord`, `LookupByRid`) plus the three search RPCs
(`VectorSearch`, `HybridSearch`, `FullTextSearch`) and `TimeSeriesLatest` get a wrapper only once a
transaction is open, through `TransactionHandle` / `AsyncTransactionHandle` - outside a
transaction they reach the server through `raw` directly - and `BulkInsert`,
`InsertBidirectional`, `GraphBatchLoad`, and `TimeSeriesWrite` have no wrapper anywhere, ever.
Attaching auth as per-call metadata on just the top-level wrappers would leave every one of those
other calls silently anonymous. Attaching it to the channel instead makes that impossible -
`client.raw.ExecuteCommand(...)` carries the same headers `client.stream_query(...)` does.

### The async side needs four interceptor objects, not one

`create_client` and `aio.create_client` both authenticate via a channel interceptor, but the async
facade cannot use a single object implementing all four of grpc's client-interceptor protocols the
way the sync side's `_SyncAuthInterceptor` does. `grpc.aio.Channel.__init__` sorts every
interceptor it is given into one of four buckets with an `isinstance(...)`/`elif` chain and stops
at the first match, so a combined object - an instance of all four protocol classes at once - lands
in only the first bucket (unary-unary) and is never invoked for the other three call shapes.
`sync_interceptors` is unaffected: the sync side's `grpc.intercept_channel` checks all four
independently. `async_interceptors` therefore returns four separate interceptor objects, one per
RPC shape, so that `stream_query` (unary-stream), `insert_stream` (stream-unary) and
`InsertBidirectional` (stream-stream) get authenticated exactly as `ExecuteCommand` (unary-unary)
does. A single combined object was this module's original shape and passed the whole unit suite,
because the in-process fake server that suite drives had only ever been exercised through a
unary-unary call under auth; the gap surfaced only once the async facade's transaction and
streaming paths were run against a real server (see `e2e/test_grpc_aio.py`), where `stream_query`
came back `UNAUTHENTICATED` moments after `ExecuteCommand`, over the same authenticated client,
succeeded.

### The insecure-channel guard

`password_auth` sends the password in plaintext gRPC metadata, so `create_client` **refuses** to
pair it with a channel that has no transport credentials, unless you pass `insecure=True`:

```python
import grpc

create_client("localhost:50051", auth=password_auth("root", "playwithdata"))
# raises InsecureChannelError: refusing to send a plaintext password over an insecure
# channel to "localhost:50051" ...

create_client("localhost:50051", auth=password_auth("root", "playwithdata"), insecure=True)
# fine - you opted in

create_client("localhost:50051", auth=password_auth("root", "playwithdata"), credentials=grpc.ssl_channel_credentials())
# also fine - the channel is encrypted, so there is nothing to opt into
```

The check keys on whether channel `credentials` were supplied, not on parsing `target` for a
scheme - there is no scheme in gRPC's `host:port` form to parse in the first place, unlike the
TypeScript sibling, which has to defend against `new URL("localhost:50051").protocol` evaluating
to `"localhost:"` rather than `"http:"`. A bearer token is not a password and never trips this
guard, since `bearer_auth` does not set `Auth.sends_plaintext_password`.

## Streaming queries: `stream_query`

```python
for record in client.stream_query(
    messages.StreamQueryRequest(
        database="mydb",
        query="SELECT FROM Person",
        language="sql",
        retrieval_mode=messages.StreamQueryRequest.RetrievalMode.CURSOR,
        batch_size=500,
    )
):
    print(record.rid, dict(record.properties))
```

or, on the async facade, `async for record in client.stream_query(...)`.

`stream_query` flattens the server's stream of `QueryResult` batches into one `GrpcRecord` at a
time, so calling code never unwraps `QueryResult.records` itself. That is the *only* thing it
does: it picks no default for `retrieval_mode` or `batch_size`. The three retrieval modes the
`.proto` contract defines differ materially in memory and consistency behaviour, and only the
caller can judge which one a given query needs:

- `CURSOR` (proto default `0`) - runs the query once and streams results as you iterate.
- `MATERIALIZE_ALL` - loads the entire result set on the server first, then emits it in batches.
- `PAGED` - re-issues the query with `LIMIT`/`SKIP` per batch.

Leaving `retrieval_mode` and `batch_size` unset sends the wire zero values for both (`CURSOR`,
`batch_size=0`, meaning "server chooses") - that is protobuf's own default, not a choice this
wrapper makes on your behalf.

## Streaming inserts: `insert_stream`

```python
from arcadedb_driver_grpc import InsertStreamRequest, messages


def rows() -> list[list[messages.GrpcRecord]]:
    return [
        [messages.GrpcRecord(type="Person", properties={"name": messages.GrpcValue(string_value="Alice")})],
        [messages.GrpcRecord(type="Person", properties={"name": messages.GrpcValue(string_value="Bob")})],
    ]


summary = client.insert_stream(
    InsertStreamRequest(
        database="mydb",
        options=messages.InsertOptions(target_class="Person"),
        chunks=rows(),
    )
)
print(summary.inserted, summary.failed)
```

`chunks` is an iterable of row batches - one element becomes exactly one wire `InsertChunk`. The
sync facade accepts a synchronous `Iterable`; the async facade (`arcadedb_driver_grpc.aio`) accepts
either a synchronous `Iterable` *or* an `AsyncIterable`, so an async caller who already has a plain
list is not forced to wrap it in an async generator first.

The caller decides how rows are batched and when to produce the next batch. `insert_stream` owns
only the envelope bookkeeping around those batches, which is easy to get wrong by hand:

- one `session_id` (a fresh UUID, generated once), stable for the whole stream
- `chunk_seq` starting at 1 and incrementing by 1 per chunk
- `database` set on the first chunk only, per the `.proto` contract (`InsertChunk.database` is
  documented `// REQUIRED` there for exactly that chunk)
- `last=True` on the final chunk only

### The `options.database` mirror

`insert_stream` also sets `options.database` to the same value as the first chunk's `database`.
This is a compatibility workaround, established empirically against a real server: on ArcadeDB
**26.8.1 and every earlier release**, the server builds its `InsertContext` from
`InsertOptions.database` **alone** and never reads `InsertChunk.database` at all, despite the
`.proto` documenting the latter as required. Without this mirror, a stream against such a server
inserts nothing - the server reports the rows as `received` with `inserted=0`, or fails at the
deferred commit with `Invalid database name: name is required` - even though `database` was sent
exactly as the contract specifies. A server carrying the fix for
[ArcadeData/arcadedb#6597](https://github.com/ArcadeData/arcadedb/issues/6597) (`7ccade7348`,
**released in 26.9.1**) prefers a non-empty `InsertChunk.database` and falls back to
`InsertOptions.database`, so setting both to the same value is correct on either side of that fix.

That boundary is measured, not inferred. A single-chunk stream carrying `database` on the chunk
with `options.database` left empty inserts **0 of 2** rows on `arcadedata/arcadedb:26.8.1` and
**2 of 2** on both `26.9.1` and `26.10.1-SNAPSHOT`; `7ccade7348` is an ancestor of the `26.9.1`
tag and not of `26.8.1`. So **every server version this package claims support for carries the
fix** (the compatibility table below starts at 26.9.1), and the mirror is belt-and-braces rather
than load-bearing today. It is still sent, because removing it would be a behaviour change;
retiring it is tracked as a follow-up.

An empty stream is not an error. A caller whose row source produces zero batches (a filter that
matched nothing, say) gets a single wire chunk with zero rows and `last=True`, and whatever
`InsertSummary` the server answers for it - not an exception and not an invented result. A filter
matching nothing is a legitimate outcome, and turning it into an error would be the wrong failure
mode for the common case of "there was nothing to insert this time."

`insert_stream` is **not** available on a `TransactionHandle` - see below.

## Transactions: `transaction`

```python
with client.transaction("mydb") as tx:
    tx.execute_command(messages.ExecuteCommandRequest(command="INSERT INTO Account SET balance = 100", language="sql"))
    response = tx.execute_query(
        messages.ExecuteQueryRequest(query="SELECT sum(balance) as total FROM Account", language="sql")
    )
    total = response.results[0].records[0]
```

or, async:

```python
async with client.transaction("mydb") as tx:
    await tx.execute_command(
        messages.ExecuteCommandRequest(command="INSERT INTO Account SET balance = 100", language="sql")
    )
```

`transaction(database)` returns a context manager whose `__enter__`/`__aenter__` begins a
server-side transaction (`BeginTransaction`) and hands back a `TransactionHandle` /
`AsyncTransactionHandle` - a second object, distinct from the client itself. Every call made
through that handle (`execute_query`, `execute_command`, `create_record`, `update_record`,
`delete_record`, `lookup_by_rid`, `stream_query`, `vector_search`, `hybrid_search`,
`full_text_search`) carries the transaction's id; a call made
through the outer `client` while the transaction is open does **not** take part in it, the same
distinction `arcadedb-driver`'s `Transaction` documents for its second database handle.

This is spelled as a context manager - `with client.transaction("db") as tx:` - rather than a
callback taking a function, specifically so a caller moving between `arcadedb-driver` (HTTP) and
this package does not have to relearn the shape; the TypeScript sibling instead spells this
`grpc.transaction(database, async (tx) => { ... })`, because Connect-ES has no equivalent
convention to match.

### The binding override

`TransactionHandle._bind` forces `database` and `transaction` onto every request the handle sends,
overriding whatever the caller supplied - including a transaction id or database name set on the
request object before it reached the handle. This override *is* the safety mechanism, not an
incidental detail: it is what makes transaction hijack, silent data loss, and leaked transactions
(filed against ad hoc transaction code as ArcadeData/arcadedb#5040 through #5042) unrepeatable
through this handle. A request that arrived naming another database, or carrying another
transaction's id, leaves the handle naming this transaction's database and id instead.

The binding happens on a **copy**: the request object you passed in comes back unchanged. That
matters because the alternative reintroduces #5040 by aliasing - a request bound in place would
keep the handle's `database` and a now-committed transaction's id after the block ended, and
reusing it (through `client.raw`, or in a later transaction before `_bind` ran) would send that
dead id to the server.

### The commit-flag check

On a clean exit, `transaction` calls `CommitTransaction` and checks the response's `committed`
field - not `success`. A transaction id the server no longer recognises (for example, one already
reaped past `arcadedb.server.httpTxExpireTimeout`) answers `success=true, committed=false`, with no
error status at all. Trusting `success` alone would report the commit as having gone through while
silently losing every write the transaction made; checking `committed` instead raises
`RuntimeError` (including the server's own message) so that failure cannot pass unnoticed. The same
check exists on both facades. `BeginTransaction`'s response is checked the same way: a missing or
blank `transaction_id` raises immediately, before the block runs, rather than handing back a handle
that would silently auto-commit every call outside any real transaction.

On any other exit - the block raises - the transaction rolls back and the block's own exception
propagates; a rollback failure attaches as `__cause__` rather than replacing it. If the commit
call itself raises, a best-effort rollback is attempted first (its own failure discarded) so the
server-side transaction is not left open until it is reaped, and then the commit's error
propagates.

### `insert_stream` and `bulk_insert` cannot join a `transaction()` on this server

On **26.8.1 and every earlier server**, `ArcadeDbGrpcService#insertStream` and `#bulkInsert`
never read a request's `TransactionContext` - each builds its own `InsertContext`, resolves its own
database, and commits independently, regardless of any
`BeginTransaction`/`CommitTransaction`/`RollbackTransaction` issued around it. Adding them to
`TransactionHandle` would silently misrepresent this: their writes would not actually be part of
the transaction, would commit even if the transaction's body raised, and would survive a rollback.
Both remain reachable outside a transaction - `client.insert_stream(...)` and
`client.raw.BulkInsert(...)` - but never through `tx`.

[ArcadeData/arcadedb#6607](https://github.com/ArcadeData/arcadedb/issues/6607) was filed against
this gap and **has since landed**: its fix (`79d931070b`) is an ancestor of the `26.9.1` tag and
not of `26.8.1`. Measured against real servers - begin over `BeginTransaction`, run an
`InsertStream` carrying that server-issued `transaction_id`, then roll back - the rows survive the
rollback on `26.8.1` and are correctly discarded on both `26.9.1` and `26.10.1-SNAPSHOT`, with a
commit persisting them on all three. So the restriction is now **removable** for every server
version this package supports. It is kept for now because lifting it adds public surface, a
deliberate release decision rather than a documentation fix; it is tracked as a follow-up.

## Time series: `time_series_write_stream`, `time_series_query`, `time_series_latest`, `TimeSeriesWrite`

Four RPCs, four different treatments:

| RPC | Reached how |
| --- | --- |
| `TimeSeriesWriteStream` | `client.time_series_write_stream` - a client-streaming wrapper, like `insert_stream` |
| `TimeSeriesQuery` | `client.time_series_query` outside a transaction, `tx.time_series_query` bound to one |
| `TimeSeriesLatest` | `tx.time_series_latest` only - no top-level alias exists |
| `TimeSeriesWrite` (the unary write) | `client.raw.TimeSeriesWrite` only - no wrapper at any level |

```python
from arcadedb_driver_grpc import TimeSeriesWriteStreamRequest, messages


def points() -> list[list[messages.TimeSeriesPoint]]:
    return [
        [messages.TimeSeriesPoint(timestamp=1000, fields={"value": messages.GrpcValue(double_value=22.5)})],
        [messages.TimeSeriesPoint(timestamp=2000, fields={"value": messages.GrpcValue(double_value=23.1)})],
    ]


summary = client.time_series_write_stream(
    TimeSeriesWriteStreamRequest(
        database="mydb",
        type="Temperature",
        precision=messages.TimeSeriesPrecision.TS_PRECISION_MILLISECONDS,
        chunks=points(),
    )
)
print(summary.written, summary.dropped)

for result in client.time_series_query(messages.TimeSeriesQueryRequest(database="mydb", type="Temperature")):
    print(result.rows)

with client.transaction("mydb") as tx:
    latest = tx.time_series_latest(messages.TimeSeriesLatestRequest(type="Temperature"))
```

### `precision` is required, not defaulted

`TimeSeriesWriteStreamRequest.precision` has no default - every call must set it, unlike almost
every other field this package passes straight through unchanged. `TimeSeriesPrecision`'s proto3
zero value is `TS_PRECISION_MILLISECONDS`, so a caller who omits the field and one who explicitly
chose milliseconds produce the **identical** wire message - the server has no way to tell "you
didn't say" from "you said milliseconds". That collision matters more than a typical proto3
default-value gotcha because of what ArcadeDB's other time-series ingest path does: HTTP's
`POST /api/v1/ts/{database}/write` speaks InfluxDB Line Protocol, whose own omitted-precision
default is **nanoseconds** - a factor of 10\*\*6 away from gRPC's default of milliseconds. A
caller porting a working HTTP ingest pipeline to this client who drops the field would have every
timestamp misread by a million, silently, with no error raised on either side. Making `precision`
a required (no-default) field on the dataclass turns that into a `TypeError` at construction
instead of a silent data-corruption bug.

**The same trap is wide open on the raw unary path, where nothing can protect you.**
`TimeSeriesWriteRequest.precision` is field 4 of the same enum, with the same proto3 zero value,
and `TimeSeriesWrite` is reachable only as `client.raw.TimeSeriesWrite` (see the table above) - a
generated protobuf message this package does not wrap and cannot make any field required on. A
caller who follows that table to `raw.TimeSeriesWrite` for one-shot writes and omits `precision`
hits exactly the 10\*\*6 misread described here, with no wrapper standing in the way. Set
`precision` explicitly on **every** `raw.TimeSeriesWrite` call. This is not an argument for
wrapping `TimeSeriesWrite` - the reasons it stays `raw`-only are below, and they still hold - it
is a warning that the protection above stops at the streaming wrapper's edge.

### `database`, `type` and `precision` repeat on every chunk, not just the first

Unlike `insert_stream`'s envelope (`database` on the first chunk only, `last=True` on the final
one), `TimeSeriesWriteChunk` declares no `session_id`, `chunk_seq` or `last` field on the wire at
all. `time_series_write_stream` therefore simply sets `database`, `credentials`, `type` and
`precision` on **every** chunk it builds, and `insert_stream`'s `options.database` mirroring
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

### An empty `chunks` sends zero wire chunks, not one - and the server accepts it

`insert_stream`'s empty case sends a single chunk with zero rows and `last=True`, because
`InsertChunk` needs that flag to ever become `True` and `database` needs to land on some chunk.
`TimeSeriesWriteChunk` has neither field, so an empty `chunks` here sends **zero** wire chunks -
the server is never told `database`, `type` or `precision` at all. Verified against a real server:
this is accepted cleanly, not rejected, and comes back as a `TimeSeriesWriteSummary` with every
count (`received`, `written`, `dropped`, and all three type lists below) at zero.

### A successful write can still report `written < received`

`TimeSeriesWriteStream` is not atomic: each measurement's batch commits its own shard transaction
as it is appended, so a failure partway through leaves everything before it durable. The returned
`TimeSeriesWriteSummary` always carries `received`, `written`, `dropped`, plus three separate
reasons a point can be dropped:

- `unknown_types` - no type with this name exists (create it first with `CREATE TIMESERIES TYPE`)
- `non_time_series_types` - the type exists, but is not a TIMESERIES type
- `unavailable_types` - the type is a TIMESERIES type, but its storage engine failed to load

**Checking only that the call returned without raising is not checking that the data landed** - a
call can succeed and still report `dropped > 0`. Always read the summary.

### Two RPCs with no wrapper or binding - for two different reasons, with two different futures

`TimeSeriesWrite` has no wrapper at any level, and `TimeSeriesLatest` has no top-level alias. Both
look like the same shape of gap from the outside, but they are not the same kind of gap, and
should not be described the same way:

- **`TimeSeriesWrite` is `raw`-only because its message carries no `transaction` field at all** -
  a **contract** limit. `TimeSeriesWriteRequest` simply never declares a field to bind, the same
  way `TimeSeriesWriteChunk` (the streaming version) never does. No server release, however
  capable, can make `client.raw.TimeSeriesWrite` transaction-aware without the `.proto` itself
  growing a `transaction` field first - there is nothing this package could do differently today.
- **`insert_stream`'s absence from `TransactionHandle` is a server bug, already fixed, not a
  contract limit.** `InsertStreamRequest`/`InsertChunk` DO carry a `transaction` field on the
  wire, and it is forwarded on every chunk (see "Streaming inserts" above). The exclusion exists
  because, on 26.8.1 and earlier, the server's `InsertContext` construction ignored that field
  entirely ([ArcadeData/arcadedb#6607](https://github.com/ArcadeData/arcadedb/issues/6607)). That
  bug is fixed as of 26.9.1, measured against a real server (see "`insert_stream` and
  `bulk_insert` cannot join a `transaction()`" above) - the exclusion is now **removable with no
  contract change**, and is kept only because lifting it adds public surface, a deliberate release
  decision rather than a documentation fix.

So `TimeSeriesWrite`'s status is not on the same follow-up list as `insert_stream`'s: one needs the
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

Both rules are enforced **server-side**, the same way `ef_search` and the vector/full-text
result-limit fields are (see "Vector, hybrid and full-text search" below): this package validates
neither a tag name against a schema it does not have nor `limit` against a ceiling it does not
know, so a violation surfaces as a `grpc.RpcError` from the server's response, not a client-side
exception before the request is ever sent.

## Vector, hybrid and full-text search: `VectorSearch`, `HybridSearch`, `FullTextSearch`

```python
# Outside a transaction: through raw, like any other unary RPC.
nearest = client.raw.VectorSearch(
    messages.VectorSearchRequest(database="mydb", index_name="myIndex", query_vector=[0.1, 0.2, 0.3], k=5)
)

# Inside one: through the handle, which forces `database` and `transaction` the same way every
# other bound call does (see "The binding override" above).
with client.transaction("mydb") as tx:
    fused = tx.hybrid_search(
        messages.HybridSearchRequest(
            vector_index_name="myIndex",
            query_vector=[0.1, 0.2, 0.3],
            fulltext_index_name="myTextIndex",
            fulltext_query="cat",
        )
    )
    matches = tx.full_text_search(messages.FullTextSearchRequest(query_text="cat"))
```

These three RPCs are reached exactly two ways, and no third: `client.raw.VectorSearch` /
`.HybridSearch` / `.FullTextSearch` outside any transaction, and `tx.vector_search` /
`.hybrid_search` / `.full_text_search` bound to one once it is open - the same `TransactionHandle`
the six CRUD RPCs already go through (see "Authentication, and why `client.raw` is authenticated
too" above for where these three sit relative to the CRUD RPCs and the four calls with no
wrapper at any level - `BulkInsert`, `InsertBidirectional`, `GraphBatchLoad`, `TimeSeriesWrite`).
There is deliberately **no top-level `client.vector_search`** alongside
`stream_query`/`insert_stream`/`transaction`: those three exist because the generated stub alone
handles them badly - `stream_query` needs its batches flattened, `insert_stream` needs envelope
bookkeeping, `transaction` needs begin/commit/rollback sequencing. A unary RPC the generated stub
already calls directly and correctly gains nothing from a same-shaped top-level alias; the only
thing worth hand-writing for `VectorSearch`/`HybridSearch`/`FullTextSearch` was the transaction
binding, which is exactly what `_bind` already provides for the CRUD RPCs.

Each call returns the whole generated response message, never unwrapped to `results` alone:
`VectorSearchResponse` and `HybridSearchResponse` carry `truncated` alongside `results`, `count`,
and `scoring`. `truncated` is `True` when the search's bounded candidate window was filled, meaning
more matches may exist beyond what `results` holds - a caller who reads `.results` and never checks
`.truncated` works off a partial answer without being told. `FullTextSearchResponse` carries **no**
`truncated` field at all in the `.proto` contract - not `False`, simply absent from the message -
because full-text search has no candidate-window concept to overflow the way a vector search does.

`ef_search` (the dense-index search beam width) and each RPC's result-limit field (`k` for
`VectorSearchRequest`/`HybridSearchRequest`, `limit` for `FullTextSearchRequest`) are bounded, but
the bound is enforced **server-side**. Neither `raw` nor the handle validates them locally, so an
out-of-range value surfaces as a `grpc.RpcError` from the server's response, not as a client-side
exception before the request is ever sent.

## The control plane: `raw_admin`

The `.proto` contract declares a second service beside `ArcadeDbService`: `ArcadeDbAdminService`,
ArcadeDB's control plane - database lifecycle, users, groups, API tokens, server and database
settings, backups, the profiler, cluster and shutdown operations, and the two probes. Both
`create_client`s build a stub for it from the **same** channel they build `raw` from, and expose it
as `raw_admin`:

```python
import grpc

from arcadedb_driver_grpc import create_client, messages

with create_client("localhost:50051", credentials=grpc.ssl_channel_credentials()) as client:
    info = client.raw_admin.GetServerInfo(
        messages.GetServerInfoRequest(
            credentials=messages.DatabaseCredentials(username="root", password="playwithdata")
        )
    )
```

`aio.create_client` gives the same property on `AsyncArcadeDBGrpcClient`, awaited rather than
called: `await client.raw_admin.GetServerInfo(...)`.

No facade wraps any of it, and that is the design rather than an omission. `stream_query`,
`insert_stream`, `time_series_write_stream` and `transaction` exist because the generated stub alone
handles those RPCs badly - batches to flatten, envelope bookkeeping to get right, a
begin/commit/rollback sequence to hold together across two facades. 41 of the admin service's 44
RPCs are plain unary calls: build a request message, read one response message back. Wrapping one
would be a renamed passthrough, which is the same bar `VectorSearch` and `TimeSeriesWrite` are held
to above - and the bill would be paid twice here, once per facade.

### The 44 RPCs

Every backticked name between the two markers below is one RPC of `ArcadeDbAdminService`, and a test
asserts that this set equals the generated stub's own method set. A hand-written list of 44 names is
exactly the kind of prose that rots on the next contract bump, and a stale list is worse than no
list, because a reader trusts it.

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

Authorization is the server's business and is not uniform across that table: `Ping`,
`GetServerInfo`, `ListDatabases`, `ExistsDatabase` and `GetDatabaseInfo` need only a valid account,
`GetProgress` needs an account granted the database it names, and every other RPC needs the
server-admin (root) principal. `CreateDatabase`, `DropDatabase`, `CreateUser`, `DeleteUser`,
`RestoreBackup`, `RestoreDatabase` and `ImportDatabase` are additionally refused on a cluster
follower, with `FAILED_PRECONDITION` and the leader's address on the `arcadedb-leader-*` trailers -
gRPC has no request proxy, so the caller redirects itself instead of being forwarded.

### The three server-streaming RPCs

`RestoreBackup`, `RestoreDatabase` and `ImportDatabase` return `stream RestoreProgress` /
`stream ImportProgress` rather than a single response, and the shape is deliberate: a restore or an
import can run for minutes, so the server reports progress as it goes and the call stays cancellable
throughout, instead of being one opaque call that either returns or times out.

They are also the three the bare stub drives least comfortably. A unary admin call is one line; a
server-streaming one is an iterator (`for progress in client.raw_admin.RestoreDatabase(...)`, or
`async for` on the async facade) that has to decide what to do with each progress message and to
treat an abandoned loop as a cancellation whose effect on the restore is the server's to decide.
Nothing here smooths that over. If any admin RPC ever earns a wrapper, these three are the
candidates, on exactly the grounds `stream_query` earned its own.

### `Health` and `Ready` take empty request messages

`HealthRequest` and `ReadyRequest` declare no fields at all - not even `credentials`. They are
exempt from the server's auth interceptor, exactly as `GET /health` and `GET /ready` are
unauthenticated over HTTP, so a container orchestrator can probe a node without an account.
`client.raw_admin.Health(messages.HealthRequest())` is the whole call, and there is nothing left for
a facade to simplify.

### `auth` does nothing for the admin service

42 of the 44 RPCs above authenticate from a `DatabaseCredentials` field **inside the request
message** - the `credentials=messages.DatabaseCredentials(...)` in the example at the top of this
section, set per call - rather than from channel metadata, the way every data-plane call does. This
is a property of the contract, not of this client, and it is the single most surprising thing about
`raw_admin`: `bearer_auth` and `password_auth` authenticate the **data plane** only. Pass either as
`auth` and its metadata is still attached to an admin call, and the server still authenticates that
call from the request body and ignores it. (`Health` and `Ready` are the other two, and they carry
no credentials because they are not authenticated at all.)

That placement also defeats the insecure-channel guard described under "Authentication" above. That
check keys on `Auth.sends_plaintext_password`, a field on the `Auth` dataclass the interceptors are
built from - not a marker on the interceptor itself, the way the TypeScript sibling attaches one to
the `Interceptor` value `passwordAuth` returns - so it can only ever see a password that `Auth`'s
metadata is about to carry; a password sitting in a request body is invisible to it. `raw_admin`
therefore carries its **own** guard against the same hazard, and raises the same
`InsecureChannelError`:

```python
client = create_client("localhost:50051", insecure=True)
client.raw.ExecuteQuery(...)  # fine, unchanged

create_client("localhost:50051")  # constructed with neither credentials nor insecure=True
# ...and then, on the client it returned:
client.raw_admin
# raises InsecureChannelError: refusing to expose ArcadeDbAdminService over a channel that
# may be insecure ...

create_client("localhost:50051", insecure=True).raw_admin  # fine - you opted in
create_client("localhost:50051", credentials=grpc.ssl_channel_credentials()).raw_admin  # fine - encrypted
```

Five things about that guard are deliberate:

- **It fires when `raw_admin` is read, not when the client is constructed.** A caller who only ever
  touches the data plane over an insecure channel is entirely unaffected: their client is built
  exactly as it always was, and nothing about exposing the admin stub can raise at them.
- **It is unconditional on `auth`.** The credentials at risk are in the request body, not in
  anything an interceptor puts on the wire, so the refusal is identical with `bearer_auth`, with
  `password_auth`, and with no `auth` at all.
- **`Health` and `Ready` are refused too**, even though they carry no credentials. The guard
  protects the stub as a whole rather than a per-RPC list, and carving those two back out would mean
  wrapping the other 42 - the facade this package deliberately does not have. Probing health over a
  plaintext channel costs one `insecure=True`, which is the cheaper end of that trade.
- **Constructing `ArcadeDBGrpcClient` yourself blocks `raw_admin` until you say otherwise**, even
  when the channel you hand it was built with genuine `grpc.ssl_channel_credentials()`. The class
  cannot inspect an arbitrary `grpc.Channel` for encryption, so it takes the safe default and a
  direct caller opts in with `ArcadeDBGrpcClient(channel, allow_admin=True)`. `create_client`
  computes that argument for its own callers, as `credentials is not None or insecure` - the same
  test it applies to its own plaintext-password guard. The keyword is `allow_admin` on the class and
  `insecure` on `create_client`; they are not the same knob and are deliberately not spelled alike.
- **It raises `InsecureChannelError`, an exported, catchable type** - not a bare `ValueError`
  construction that would leave a caller with nothing but string-matching on the message to tell
  "channel is insecure" apart from any other bad argument. (It is *also* a `ValueError` under the
  hood, so a handler written against the builtin still catches it.) The TypeScript sibling's
  equivalent guard throws a plain `Error`; see that package's README for why the two packages
  differ here on purpose.

### `CreateApiToken` returns secret material, and nothing here reads it

`CreateApiTokenResponse.token` is a freshly minted API token in cleartext - the only time the server
will ever show it, which is why `DeleteApiToken` revokes by hash and refuses to accept the token
itself. The server enforces that independently of anything in this package: `CreateApiToken` is
refused with `FAILED_PRECONDITION` over a cleartext channel to a remote host, and answered only over
TLS or from a loopback peer. `insecure=True` does not reach that check - it lifts this client's own
guard on `raw_admin`, not the server's separate one on this single RPC, so a caller who opted in to
unblock `raw_admin` over a plaintext channel to a remote host can still watch `CreateApiToken` refuse
to mint anything. This package never touches that response. All four `intercept_*` methods, sync and async
alike, add metadata to the outgoing call and `return continuation(...)` without looking at what
comes back; they are request-side by construction, and the package contains no logging at all - no
`logging`, no `print`. A token cannot reach a log sink through this client, which is the property
[ArcadeData/arcadedb#7309](https://github.com/ArcadeData/arcadedb/issues/7309) argues for
server-side. A test pins it rather than leaving it as a reading of the source, so an interceptor
that started inspecting responses, or a stray `print`, fails the suite.

## Errors: `grpc.RpcError`, not a package-specific error

A failed call raises `grpc.RpcError` (sync) or `grpc.aio.AioRpcError` (async) directly - this
package does not wrap it in a package-specific exception:

```python
import grpc

try:
    client.raw.ExecuteQuery(messages.ExecuteQueryRequest(database="mydb", query="SELECT FROM NoSuchType"))
except grpc.RpcError as err:
    print(err.code(), err.details())
```

This is the same asymmetry `python/CLAUDE.md` documents for the TypeScript sibling's
`ConnectError` versus `@arcadedb/driver`'s `ArcadeDBError`, and is deliberate rather than an
oversight to fix later. `arcadedb-driver` (the HTTP client) needs its own error type because the
HTTP contract answers `200` with a body that may itself describe a failure - there is an envelope
to unwrap, and `_internal/unwrap.py` is what unwraps it. gRPC has no equivalent shape: a failed
call is a failed call at the transport level, carried as a status code and a details string, and
there is nothing this package's own type could add by standing between the caller and
`grpc.RpcError`.

## Async-specific hazards

Two behaviours below were settled deliberately during implementation rather than fixed as bugs.
Both are documented at length in the code itself; this section summarizes them.

### Cancelling a transaction body does roll back; cancelling it twice does not

The obvious reading - that `asyncio.CancelledError` inherits from `BaseException` rather than
`Exception` and so slips past `__aexit__` - is wrong, and this README said it for a while.
`__aexit__`'s guard is `if exc is not None`, not an `isinstance(exc, Exception)` test, so a
cancelled body takes the rollback branch like any other failure; and after a single `task.cancel()`
the `CancelledError` has already been delivered and the task's `_must_cancel` flag cleared, so the
`await` inside the rollback does not immediately re-raise.
`test_cancelling_the_body_still_rolls_back` asserts the server saw exactly `BeginTransaction`,
`RollbackTransaction`.

The real limitation is narrower. A **second** cancellation, landing while that rollback is still in
flight, is raised at the `await` and escapes `__aexit__` uncaught - replacing whatever the body
raised, and leaving the transaction open on the server until
`arcadedb.server.httpTxExpireTimeout` reaps it, the leaked-transaction shape
(ArcadeData/arcadedb#5042) this package otherwise exists to prevent. `_safe_rollback`, on the
commit-failure path, has the same gap in a smaller form: its `contextlib.suppress(Exception)`
genuinely does not cover `CancelledError`, so a cancellation there replaces the commit error the
caller was meant to see.

This is accepted rather than silently overlooked: a real fix (a shielded rollback via
`asyncio.shield`, say) trades a reaped transaction for a task that can hang against an unresponsive
server, which is a design decision for this repository's owner, not something to settle
unilaterally. A caller who needs the rollback to be certain even under repeated cancellation should
issue it themselves rather than rely on this context manager.

### `insert_stream`'s close-forwarding is best-effort

When the async facade abandons an in-progress `chunks` source early - the RPC aborts mid-stream, or
nothing pulls the rest - it tries to forward that closure to the caller's source, so a generator
wrapping a file handle or a database cursor gets its `finally` block run. It forwards to the
**iterator** it is actually driving (`iter(chunks)` / `chunks.__aiter__()`), not to the
`Iterable`/`AsyncIterable` it was handed: for a bare generator the two are the same object, but for
a class whose `__aiter__` is an async generator function they are not, and closing the wrong one
forwards the close to nothing. That forwarding then calls `close()`/`aclose()` via `getattr`,
because an arbitrary `Iterable` or `AsyncIterable` is not required to have either - only generators
are. A caller-supplied iterator with its own cleanup protocol that is *not* a generator (no
`close`/`aclose` method) gets no forwarded close at all; this package cannot invent a protocol the
object does not already implement.

## Contract version and compatibility

This package was generated from `contracts/arcadedb-server-26.10.1-SNAPSHOT.proto`, recorded in
`pyproject.toml` as `tool.arcadedb.server-version`:

```toml
[tool.arcadedb]
server-version = "26.10.1-SNAPSHOT"
```

| `arcadedb-driver-grpc` | ArcadeDB server |
| --- | --- |
| 0.1.0 | 26.9.1 |
| 0.2.0 (unreleased) | 26.10.1-SNAPSHOT |

This table is a historical record tied to a package version, not something derived
automatically: `scripts/adopt-contract-version.sh` deliberately does not touch it when it retires
an old contract and adopts a new one. Adding a row is a human decision made at release time, not a
side effect of a contract bump.

The client speaks ArcadeDB's gRPC data plane as described by that contract. Pointing it at a
server on a materially different release may work for the RPCs both versions share, but is not
tested or supported.

## License

Apache-2.0.
