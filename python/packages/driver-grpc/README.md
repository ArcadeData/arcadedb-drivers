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
contract declares is reachable through it. `create_client` adds three wrappers on top for the RPCs
the generated stub alone handles badly: `stream_query`, `insert_stream`, and `transaction`.
Everything else - the unary CRUD calls, `BulkInsert`, `InsertBidirectional`, `GraphBatchLoad` - is
used directly through `raw`, exactly as in the example above.

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
per-call metadata. That is not a stylistic choice: the top-level client wraps only three things -
`stream_query`, `insert_stream`, and the three transaction RPCs (`BeginTransaction`,
`CommitTransaction`, `RollbackTransaction`) that `transaction` manages internally. The six CRUD
RPCs (`ExecuteQuery`, `ExecuteCommand`, `CreateRecord`, `UpdateRecord`, `DeleteRecord`,
`LookupByRid`) get a wrapper only once a transaction is open, through `TransactionHandle` /
`AsyncTransactionHandle` - outside a transaction they reach the server through `raw` directly - and
`BulkInsert`, `InsertBidirectional`, and `GraphBatchLoad` have no wrapper anywhere, ever. Attaching
auth as per-call metadata on just the top-level wrappers would leave every one of those other calls
silently anonymous. Attaching it to the channel instead makes that impossible -
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
26.10.1-SNAPSHOT and every earlier release, the server builds its `InsertContext` from
`InsertOptions.database` **alone** and never reads `InsertChunk.database` at all, despite the
`.proto` documenting the latter as required. Without this mirror, every stream against such a
server fails at the deferred commit with `Invalid database name: name is required` - even though
`database` was sent exactly as the contract specifies. A server carrying the fix for
[ArcadeData/arcadedb#6597](https://github.com/ArcadeData/arcadedb/issues/6597) prefers a non-empty
`InsertChunk.database` and falls back to `InsertOptions.database`, so setting both to the same
value is correct on either side of that fix and safe to keep sending once it ships.

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
`delete_record`, `lookup_by_rid`, `stream_query`) carries the transaction's id; a call made
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

On this server, `ArcadeDbGrpcService#insertStream` and `#bulkInsert` never read a request's
`TransactionContext` - each builds its own `InsertContext`, resolves its own database, and commits
independently, regardless of any `BeginTransaction`/`CommitTransaction`/`RollbackTransaction`
issued around it. Adding them to `TransactionHandle` would silently misrepresent this: their writes
would not actually be part of the transaction, would commit even if the transaction's body raised,
and would survive a rollback. Both remain reachable outside a transaction -
`client.insert_stream(...)` and `client.raw.BulkInsert(...)` - but never through `tx`. See
[ArcadeData/arcadedb#6607](https://github.com/ArcadeData/arcadedb/issues/6607), filed against this
gap; this restriction is removable once that lands server-side.

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

This table is a historical record tied to a package version, not something derived
automatically: `scripts/adopt-contract-version.sh` deliberately does not touch it when it retires
an old contract and adopts a new one. Adding a row is a human decision made at release time, not a
side effect of a contract bump.

The client speaks ArcadeDB's gRPC data plane as described by that contract. Pointing it at a
server on a materially different release may work for the RPCs both versions share, but is not
tested or supported.

## License

Apache-2.0.
