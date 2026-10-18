# arcadedb-driver

A Python HTTP client for [ArcadeDB](https://arcadedb.com), generated from ArcadeDB's OpenAPI
contract, with a hand-written facade on top for the data plane, transactions, and the pieces of
the contract the generator cannot model.

Published on PyPI as [`arcadedb-driver`](https://pypi.org/project/arcadedb-driver/), with
attestations: every release is built and published by `publish-python.yml` (dispatched by
`release.yml`) from a clean checkout of this repository through PyPI's trusted publishing, with no
long-lived token anywhere in the chain.

Releases are cut for every package at once: bump all versions with
`scripts/set-release-version.sh <version>` in a reviewed PR, merge it, dispatch `release.yml` on
`main`, then review and publish the draft GitHub release it creates. Publishing the draft is what
starts the registry publish.

## Requirements

- Python `>=3.10`.
- An ArcadeDB server at or near the version in the compatibility table below.

## Installation

```bash
pip install arcadedb-driver
```

or, in a [uv](https://docs.astral.sh/uv/) project:

```bash
uv add arcadedb-driver
```

## Quick start

```python
from arcadedb_driver import ArcadeDBServer, basic_auth

with ArcadeDBServer(base_url="http://localhost:2480", auth=basic_auth("root", "playwithdata")) as srv:
    db = srv.db("mydb")
    envelope = db.query(language="sql", command="SELECT FROM Person WHERE age > ?", params={"0": 21})
    print(envelope.result)
```

A bearer token (for example, a session token from `srv.login()`; see "Sessions and API tokens")
works the same way:

```python
from arcadedb_driver import ArcadeDBServer, bearer_auth

with ArcadeDBServer(base_url="http://localhost:2480", auth=bearer_auth("AU-...")) as srv:
    ...
```

The async facade mirrors the sync one method-for-method:

```python
import asyncio

from arcadedb_driver import AsyncArcadeDBServer, basic_auth


async def main() -> None:
    async with AsyncArcadeDBServer(base_url="http://localhost:2480", auth=basic_auth("root", "playwithdata")) as srv:
        db = srv.db("mydb")
        envelope = await db.query(language="sql", command="SELECT FROM Person WHERE age > ?", params={"0": 21})
        print(envelope.result)


asyncio.run(main())
```

`language` is a `QueryLanguage`: `"sql"`, `"sqlscript"` (several `;`-separated SQL statements run
as one script, usually through `command`), `"cypher"`, `"gremlin"`, `"graphql"` or `"mongo"`.

## The result envelope, and why `truncated` matters

`query` and `command` do not return bare rows. They return the whole response envelope:

```python
@dataclass(frozen=True, slots=True)
class QueryEnvelope:
    result: list[dict[str, Any]]
    limit: int
    returned: int
    truncated: bool
    explain: str | None = None
    explain_plan: dict[str, Any] | None = None
```

`truncated` is `True` when the server's serializer hit its row cap while a query still had more rows
to write - `result` is then a partial answer, not a short-but-complete one. A caller that reads
`result` and ignores `truncated` can silently work off a partial answer, because a truncated list
and a complete one are indistinguishable by shape alone. Always check `truncated` before treating
`result` as the whole answer, and re-run with a narrower filter or a higher `limit` (accepted by
`query` and `command` and their streaming twins) when it is `True` - though raising `limit` is not
always the fix: a result whose true size exceeds the server's hard ceiling
(`arcadedb.server.httpQueryMaxResultRows`) is refused outright with 413 rather than truncated, so
once you are past that ceiling a narrower filter is the only way forward.

An EXPLAIN or PROFILE statement - or any statement run with `profileExecution` - answers with its
execution plan instead of rows: `explain` holds it as indented text, one line per step, and
`explain_plan` as the same plan in structured form. `result` is then empty and `returned` is `0`,
because the plan is the answer and is not repeated as a row, so an empty `result` there does not
mean "no rows matched". Both fields are `None` on every other answer.

`truncated is False` used to be a client-side default rather than a server guarantee: until
26.10.1, `QueryResponse` declared no required fields, so the envelope's `limit`,
`returned` and `truncated` were all synthesised when the response omitted them. That caveat is
retired. The contract now marks all three **required**, the server sends all three on every
query and command, and a response missing one is a contract violation that surfaces as a
`KeyError` out of the generated model rather than as a quietly invented `False`. `result` stayed
optional and still defaults to `[]`.

`result` also became a **union** in the same release: an array of rows under the default `record`
serializer, and a single `{vertices, edges}` object - plus `records` under `studio` - under the
two graph serializers. `QueryEnvelope.result` is a list of rows and cannot carry the second
shape, so `query`/`command` raise `ArcadeDBError` if it ever arrives. It cannot today: this client
sends no `serializer` field, so the server always picks `record`.

## Streaming a query or command: `query_stream`/`command_stream`

`query` and `command` buffer the whole result server-side before answering. `query_stream` and
`command_stream` are a separate pair of methods for the same two endpoints, requesting
`application/x-ndjson` instead of a buffered JSON body and returning a generator a caller iterates
directly (the async facade's twins are `async for`-able instead):

```python
for event in db.query_stream(language="sql", command="SELECT FROM Person"):
    if not isinstance(event.record, Unset):
        print(event.record.to_dict())
    if not isinstance(event.stats, Unset):
        print(f"returned {event.stats.returned}, truncated: {event.stats.truncated}")
```

They yield **events**, not rows. Each `NdJsonQueryEvent` carries exactly one of `record` (one
result row, shaped like an element of `query`'s `result` list), `stats`, or `error` - never more
than one, and a caller who only ever reads `event.record` will silently skip both of the others.

`stats` is a trailer, always the last event of a complete stream, carrying the same
`limit`/`returned`/`truncated` `QueryEnvelope` reports at the top level for the buffered path.
Ignoring it loses exactly what ignoring `.truncated` loses above: the only way to tell a complete
answer from one the server's row cap cut short. A caller who iterates `record` events and stops
there has no way to know whether they saw everything.

`error` is a failure the server can only report **after** the 200 status line was already sent -
unlike the buffered path, where a failure still in progress when the response starts can be
reported as a non-2xx status, a streamed response has committed to 200 before the first row is
known to exist, and that status line cannot be taken back once the stream has started. That is why
the contract puts this failure in band, as an event, rather than as an HTTP status. This client
raises `ArcadeDBError` for it - exactly as `query`/`command` raise `ArcadeDBError` for a non-2xx
response - so both paths fail the same way; any event already yielded before the error stays
delivered to the caller.

The raised error is filled from the event field by field, so it reads like the error the buffered
call would have raised for the same failure:

| `ArcadeDBError` | from the in-band `error` event |
| --- | --- |
| `status` | `status` - the status the buffered encoding would have answered with (503 for a retryable conflict, 409 for a duplicated key, 413 for the row cap, ...); **200 only when the event carries none** (anything but a positive integer counts as none; a batch stream falls back to 500 by the same rule) |
| `error` | `error`, the classified label; `message` when the event has no `error` |
| `exception`, `detail`, `exception_args` | the same-named fields |
| `request_id` | the response's `X-Request-Id` header, else the event's `requestId` |
| `retry_after` | `retryAfter` - a header cannot be added once the stream has started, so the back-off travels in band |
| `commit_index` | always `None`: the event carries none |

**Breaking change in 0.3.0:** earlier releases raised this error with `status` 200 whatever the
event said, a rule chosen when the event carried no `status` at all. The contract now tells clients
to key retries on the in-band `status`, the batch stream below already used its own, and a
`retry_after` beside a 200 would be unreadable. Code that recognised a mid-stream failure by
`err.status == 200` must now look at the real status instead.

`query` and `command` themselves are unchanged: they still return `QueryEnvelope` and still send no
`Accept` header. Streaming is two additional methods, not a mode either existing one can be put
into.

`command_stream` only ever succeeds for a **read-only** statement. A mutating one - `UPDATE`,
`INSERT`, DDL, `UPDATE ... RETURN AFTER` included - is refused before it produces a single row,
because a streamed response starts sending rows to the caller before the surrounding transaction
commits, and that commit can still roll back; the server will not let you observe rows from a
write that might never actually happen. Use the buffered `command` for a mutating statement - it
is unaffected by any of this. As with the `ef_search`/result-limit bounds above, this rule is
enforced **server-side** and this client does not pre-empt it by inspecting the statement first, so
the rejection surfaces as an `ArcadeDBError` raised from the server's response (HTTP 400), not a
local exception before the request is even sent.

You are free to stop early, and that is most of the point of a streaming API. `break`ing out of
the loop, or calling the generator's `.close()`/`.aclose()`, **closes the response**: `httpx`'s
`.stream()` context manager lives inside the generator body, so the `GeneratorExit` that
abandonment throws into the suspended `yield` unwinds through it and releases the connection.
`@arcadedb/driver` gives the same guarantee through its own idiom, an explicit `reader.cancel()`.

Line splitting is hand-rolled here rather than delegated to `httpx`'s `iter_lines()`, and that is
load-bearing: `iter_lines()` follows `str.splitlines()`, which breaks on U+0085, U+2028 and U+2029
as well as `\n` - and all three are legal raw characters inside a JSON string, which ArcadeDB does
not escape. A record carrying one would be cut in half and surface as a bare `json.JSONDecodeError`
partway through an otherwise healthy stream. This client splits on `\n` alone, exactly as
`@arcadedb/driver` does, so such a record arrives intact.

Both the sync and async versions reach the server through the generated `Client`'s own pooled
`httpx.Client`/`httpx.AsyncClient`, via its `.stream()` context manager, rather than a hand-rolled
request or a `httpx.Client` of their own; that is what lets them reuse the same base URL, auth
headers, and timeout every other call on this client already goes through. Anyone adding another
streaming endpoint to this package should do the same rather than standing up a new `httpx.Client`.

## Batch loading: `batch_load`/`batch_load_stream`

`POST /api/v1/batch/{database}` bulk-loads vertices and edges from one ndjson payload. The
contract schematizes a single *line* of that payload - `BatchLine`, a union over `BatchVertexLine`
and `BatchEdgeLine` - but not the body, which is a newline-delimited sequence of them; `text/csv`
has no schema at all. So there is nothing `openapi-python-client` can generate a call from, and -
like `db.ts.write` above - both `batch_load` and `batch_load_stream` are hand-written, issuing
their request through the same generated `Client`'s own pooled `httpx.Client`/`httpx.AsyncClient`
rather than a `httpx.Client` of their own:

```python
from arcadedb_driver import VertexRow, EdgeRow

vertices: list[VertexRow] = [{"type": "Person", "id": "p1", "properties": {"name": "Alice"}}]
edges: list[EdgeRow] = [{"type": "Knows", "from_": "p1", "to": "#1:7"}]

summary = db.batch_load(vertices=vertices, edges=edges, options={"commitEvery": 5000})
```

`EdgeRow`'s source endpoint is spelled `from_`, not `from`, because `from` is a Python keyword and
cannot be a `TypedDict` key. Properties live in their own `properties` dict rather than being
merged into the row: the server accepts a top-level key literally named `properties` and stores it
as an ordinary property, silently, so keeping structure and data apart in the type is what makes
that mistake impossible to make by construction. Every vertex is always sent before any edge,
regardless of the order passed in - the server resolves an edge's `from_`/`to` only against ids
declared earlier in the SAME payload, and this client enforces that ordering unconditionally
rather than exposing a way to get it wrong.

`options` is `BatchOptions`, the 17 tuning parameters the contract accepts as query parameters,
named exactly as the contract names them and sent only when present: an option a caller does not
set is left off the URL entirely rather than sent as an empty value, so the server applies its own
default instead of parsing `""`.

`_internal/batch_rows.py` owns the line format the rows are serialized into. It was established
against a live server and reported upstream as
[ArcadeData/arcadedb#7570](https://github.com/ArcadeData/arcadedb/issues/7570) when no schema
described it; the contract now declares it as `BatchLine` and the two agree field for field. That
schema covers one line rather than the whole body, so it does not remove the need for this module -
but it does mean the format is now documented upstream rather than only here. `VertexRow` and
`EdgeRow` are consequently the only way in: a hand-built payload string is not a supported input
to either method.

### A load is not atomic

This is the paragraph to read before using either method. The server commits every
`options["commitEvery"]` records, so a load that fails partway through leaves every chunk before
the failure **durably committed** - an `ArcadeDBError` raised from a failed `batch_load` still
corresponds to real, already-durable data, not to a load that undid itself. Because temporary ids
are not keys, **retrying the whole payload duplicates every vertex that already committed** rather
than resuming cleanly; there is no server-side idempotency to lean on, and this client does not
invent one. The counters that come back with a 400 (`verticesCreated` and `edgesCreated`, beside a
`partialCommit` flag) are records *attempted* before the failure - an upper bound on what is
durable, not a count of it, and the two do not even overshoot by the same rule: vertices are
committed as the load flushes, while edges are buffered and written when it ends. Treat a failed
load as something to inspect and reconcile against the database, never as something to re-send.

Temporary ids are **request-scoped**, which is the other half of the same design. An id means
something only to the payload that declared it, so a vertex loaded by an earlier call cannot be
referenced by its temp id from a later one - the server will not resolve it, and `"#1:7"` in the
example above is the alternative: a vertex already in the database is referenced by its RID,
`#bucket:position`, which is exactly what the summary's `idMapping` returns a temp id for.

`bytesRead` on the summary is how a caller verifies that a chunked upload arrived whole: compare
it against the bytes sent. A body that ends before its announced length is answered **408** with
the same partial-commit counters, never a 200 carrying a truncated count - so a short `bytesRead`
on a 200 means the server consumed less than you believe you sent, not that it quietly accepted a
half-load.

### Streaming: what the summary carries, and what it does not

`batch_load_stream` streams the same load as `application/x-ndjson` instead: a `progress` event as
the load proceeds, then exactly one `summary` event carrying the same fields the buffered call
returns, plus `idMappingStreamed: true` - a field `BatchResponse`, the buffered shape it otherwise
matches, does not declare, because a buffered load never sends it. The field is not missing from
the contract entirely, though: the TypeScript client's generated schema declares it on
`NdJsonBatchEvent["summary"]`, the streaming path's own type - this client just has no generated
model of either shape to declare it on (see above). `idMappingStreamed` is sent only on a streamed
load and is distinct from `idMappingOmitted` (*omitted* means too large to return; *streamed*
means already delivered, piecemeal, in the `progress` events that preceded the summary). Each
`progress` event's `idMapping` is only the fragment that chunk resolved and is never merged across
events - accumulating it here would reintroduce, client-side, the memory cost streaming a
million-vertex load exists to avoid. An in-band `error` event raises `ArcadeDBError` instead of
being yielded, exactly like `query_stream`/`command_stream` above: a failure after the stream has
started cannot be reported as an HTTP status, because the 200 status line is already on the wire,
so it travels in band instead and fails the caller the same way a failure before the stream started
does. Any event already yielded before the error stays delivered - a partial commit is durable, and
those progress counts are how a caller learns what may have landed.

The two encodings therefore disagree about the mapping, deliberately: `batch_load`'s summary
carries `idMapping`, the whole temp-id-to-RID map in one dict, while the streamed `summary` event
carries `idMappingStreamed: true` and `idMappingSize`, with **no map at all**. A caller who
genuinely needs the whole mapping from a streamed load accumulates the fragments as they arrive -
checking the total against `idMappingSize`, since a mapping delivered in pieces can lose one to a
truncated response without any single piece looking wrong - or calls `batch_load` and accepts the
memory cost, which is a good trade right up until the map stops fitting.

A streamed `error` event's `status` is exact, not a fallback: an engine failure raised after the
stream had already started carries the status the standard error mapping gives it - 409 for a
duplicated key, 503 for a retryable conflict - so branching on `status` works the same on both
channels. The raised `ArcadeDBError` also carries `exception` and, when the failure has any,
`exception_args`, plus the event's `retryAfter` as `retry_after` and its `commitIndex` as
`commit_index` - the in-band equivalents of the `Retry-After` and `X-ArcadeDB-Commit-Index`
headers a failure before the stream started carries. `commit_index` is a valid read-after barrier
even on a failed load (see "Two error models" below). `error` and `exception` are two more fields
the server sends that no schema declares (the contract's streamed error object declares only
`commitIndex`, `exceptionArgs`, `retryAfter` and `status`), read off the raw event here and
reported upstream on the same issue as `idMappingStreamed`,
[ArcadeData/arcadedb#7570](https://github.com/ArcadeData/arcadedb/issues/7570).

### This is `batch_load`, not `bulk_insert`

[`arcadedb-driver-grpc`](../driver-grpc/README.md)'s `bulk_insert` is a **different operation** -
it inserts records into one target type and knows nothing about edges or temporary ids. The gRPC
counterpart of the endpoint documented here is `GraphBatchLoad`, which that package reaches
through `raw` and wraps nowhere.

### `text/csv` is not exposed

The endpoint accepts `application/jsonl`, `application/x-ndjson` and `text/csv`. Both methods
always send `application/x-ndjson` - the contract makes `application/jsonl` identical in meaning,
so there is nothing to choose between them - and neither exposes CSV. Its dialect is as
undocumented as the ndjson line format, and a rows-in API has nowhere to put a header row. Convert
a CSV file into `VertexRow`/`EdgeRow` yourself, or post the bytes through `srv.raw`'s pooled httpx
client.

## A duplex insert session: `insert_session`

`batch_load` fixes its commit policy by query parameters before the load starts. An **insert
session** on the server's `/ws` WebSocket endpoint lifts that: you send a chunk, read its
acknowledgement, and only then decide what to send next - including whether to `commit()` or
`rollback()` at all. It is the counterpart of the Java client's `RemoteInsertSession`.

```python
with db.insert_session(target_type="Person") as session:
    for batch in batches:
        ack = session.send_chunk(batch)  # the server's batchAck, as a dict
        if ack["failed"]:
            session.rollback()
            break
    else:
        session.commit()  # the `committed` frame: outcome, summary
```

`AsyncArcadeDBDatabase.insert_session()` returns an `AsyncInsertSession` with the same surface,
awaited (`async with ... as session:`, `await session.send_chunk(...)`). Records are plain
dicts; a record's own `"@class"` overrides `target_type`, and an edge names its endpoints with
`"@from"` / `"@to"`. Options: `session_id`, `target_type`, `transaction_mode` (`per_stream` -
the default -, `per_batch`, `per_row`, `none`), `conflict_mode` (`error`, `update`, `ignore`,
`abort`) with `key_columns` / `update_columns_on_conflict`, `validate_only`,
`join_current_transaction`, `on_batch_ack` (called with every ack before `send_chunk` returns
it) and `timeout`. `session_id`, `transaction_mode`, `external_transaction_id`,
`last_chunk_seq` and `is_open` are readable properties.

`websockets` is a runtime dependency of this package (BSD-3-Clause). The connection reuses the
server's base URL and `auth` headers (`http` becomes `ws`, `https` becomes `wss`) and honours
`verify_ssl`.

Things that look like bugs and are not:

- **The session id is the server's unless you choose one, and a chosen one is shared.** A
  client-chosen `session_id` lives in ONE server-wide namespace - not per user, not per
  database - so two unrelated clients that both pick `batch-1` collide, and the second `start` is
  refused. Leave it out unless the session must be nameable.
- **A chunk the server refuses as a whole does not consume a sequence number.** `chunkSeq`
  starts at 1 and is managed for you; it advances only after the acknowledgement. A chunk over
  `arcadedb.server.wsMaxInsertChunkRows`, or out of sequence, raises `InsertSessionError` with
  `session_closed=False`: the session is still usable, `last_chunk_seq` did not move, and a
  smaller chunk sent next takes the **same** number. A row the server cannot apply is not a
  refusal at all: it is counted in the ack's `failed`, described in `errors`, and the rest of the
  chunk still goes in - so always read `failed`.
- **A chunk whose transaction fails comes back as an ack, and is replayed under the same number.**
  Under `per_batch` - and only there, since it is the one mode where each chunk commits in a
  transaction of its own - a failure of that transaction (a duplicate key the engine reports on
  commit, for one) undoes the whole chunk. The server answers a normal
  `batchAck` - `failed == received`, an `errors` entry with `rowIndex` -1 - and does NOT advance its
  watermark. `send_chunk` raises nothing for it and `on_batch_ack` still sees it, but the returned
  ack carries `whole_chunk_failed: True` (a key this client adds; snake_case because the server
  never sends it) and `last_chunk_seq` does not move: the next `send_chunk` is the replay of that
  sequence number. Moving on without fixing and resending those rows loses them.
- **A chunk over `arcadedb.server.wsMaxInsertFrameSize` bytes is not refused, it kills the
  connection.** The server answers an oversized frame with a WebSocket close, not an `error`
  frame, so the session is gone (and rolled back server-side) and the error has
  `session_closed=True` and `frame=None`. The issue text this client was written from lists the
  frame cap alongside the row cap as "refused, retry reuses the seq"; against a real server only
  the row cap and a sequence error behave that way. Size chunks by rows, below the byte cap.
- **Under `per_stream`, a commit-time failure arrives on `commit()`.** Nothing commits per chunk,
  so a duplicate key the engine only checks at commit fails the `commit()` call with
  `InsertSessionError`, and the session - every chunk it acknowledged - is gone.
- **Some `error` frames end the session, others do not.** `session_closed` tells them apart. It
  is `False` only for a refusal of that one frame (the row cap, a sequence that skips ahead, a
  malformed record or option). It is `True` for `"Insert session expired"` (idle sweep),
  `"Security error"` (the grant was revoked and the session rolled back, or the principal is no
  longer valid and the connection is closing), `"Internal error"` (state unknown, treated as gone)
  and an `"Insert session error"` saying the session is `not found or expired` or `is closed`;
  the session is then marked closed and further calls raise. An error title this client does not
  recognise is `False`, as in the Go and TypeScript clients: if the server has in fact dropped the
  session, the next frame is answered `not found or expired`, which closes it.
- **An `error` frame can arrive at any time.** The server's idle sweep rolls a session back and
  pushes an unsolicited `error`; whichever call reads it raises `InsertSessionError`
  (`session_closed=True`) instead of skipping it for the answer it was waiting for. The rows
  already acknowledged are gone with the session.
- **Every wait is bounded by `timeout`** (default 60 s). A timeout, a dropped connection or an
  out-of-step answer ends the session, because a late answer could no longer be matched to its
  frame - the server rolls it back when the connection closes. The synchronous client's *send* is
  not bounded by `timeout` (the underlying `websockets` sync client has none); the async one's is.
  Interrupting a call mid-exchange (`KeyboardInterrupt` on the sync client, task cancellation on
  the async one) ends the session the same way.
- **`close()` rolls back.** Leaving the `with` block, or calling `close()`, on a session that is
  still open sends `rollback` and closes the connection; it is idempotent, so it is safe after
  `commit()`. Failures while rolling back are swallowed - the connection closing rolls the
  session back anyway.
- **Joining a transaction.** `join_current_transaction=True`, called on the handle
  `db.transaction()` yields, writes into that HTTP transaction and implies
  `transaction_mode="none"`; passing any other explicit mode with it raises `InsertSessionError`
  rather than being silently overridden, as in the Go and TypeScript clients. The session's `commit()` and `rollback()` then both answer
  `outcome == "detached"`: neither decides anything, the `with db.transaction()` block does - the
  rows are durable only when it exits cleanly, and a block that raises undoes them. Calling it on
  a handle with no open transaction raises `InsertSessionError` immediately, rather than quietly
  opening a server-managed session.
- **`per_stream` is the only mode that can undo acknowledged chunks.** After `rollback()` the
  `committed` frame's `summary.partialCommit` says whether anything stayed.
- **Not thread-safe**, like the database handle: one session per thread (or per task, with one call
  in flight at a time). The protocol allows pipelining frames; this client deliberately does not.
- **Failures are `InsertSessionError`, not `ArcadeDBError`**: there is no HTTP status to carry.
  `frame` holds the server's `error` frame when there was one, `session_id` the session concerned.

## Sync and async

`ArcadeDBServer` and `AsyncArcadeDBServer` expose the same methods; the async one awaits them.
Both are context managers - `with` for the sync client, `async with` for the async one - because
each owns an `httpx` client with its own connection pool that must be released. Use the context
manager form where you can; call `close()` (sync) or `await aclose()` (async) yourself otherwise.

```python
srv = ArcadeDBServer(base_url="http://localhost:2480")
try:
    ...
finally:
    srv.close()
```

Both constructors take a `timeout: httpx.Timeout | None = None`, and omitting it disables
timeouts entirely - it is not "use httpx's default" (5 seconds), it is no timeout at all, because
in httpx an explicit `timeout=None` means exactly that. This is deliberate: the generated `Client`
these facades wrap defaults its own timeout to `None` and forwards it the same way, and
`@arcadedb/driver` has no default timeout either, since `fetch` doesn't have one. Pass an
`httpx.Timeout` if you want requests bounded:

```python
srv = ArcadeDBServer(base_url="http://localhost:2480", timeout=httpx.Timeout(5.0))
```

## Transactions

```python
with srv.db("mydb").transaction() as tx:
    tx.command(language="sql", command="INSERT INTO Account SET balance = 100")
    total = tx.query(language="sql", command="SELECT sum(balance) as total FROM Account").result[0]["total"]
```

or, async:

```python
async with srv.db("mydb").transaction() as tx:
    await tx.command(language="sql", command="INSERT INTO Account SET balance = 100")
```

`transaction()` returns a context manager whose `__enter__` (`__aenter__`) begins a server-side
transaction and hands back a SECOND database handle carrying its session id. Every call made
through that `tx` handle - not through the outer `db` object used to open the transaction - takes
part in it; a call made through the outer handle while a transaction is open auto-commits on its
own, outside the transaction, exactly as if no transaction were open at all.

The commit/rollback contract has three clauses:

- The block exits cleanly: the transaction commits.
- The block raises: the transaction rolls back and the block's exception propagates. If that
  rollback itself also fails, the rollback's error is attached as `__cause__` on the block's
  exception rather than replacing it - the block's own error is what the caller asked about - and
  the attach is silently skipped if `__cause__` is already set or if attaching it fails outright.
- The commit itself fails: a best-effort rollback is issued first (its own failure discarded) so
  the server-side session is not left open until `arcadedb.server.httpSessionExpireTimeout` reaps
  it, and then the commit's error is re-raised.

A rollback cannot always undo the whole block. A statement inside it that publishes a commit while
it runs - an explicit `BATCH n` boundary, or a statement with its own `COMMIT` - makes part of the
transaction durable before the block ends, and the server flags that response with
`arcadedb-session-partial-commit: true`. This client does not surface the header (it is reachable
through `.raw`), so a caller that replays a transaction block on conflict must know, from the
statements it runs, whether the block can partially commit - and must not replay one that did.

## Labelling statements: `query_tag`

`query`, `command`, `query_stream`, `command_stream`, `batch_load`, `batch_load_stream` and
`transaction()` (sync and async) take an optional `query_tag`, sent as the
`X-ArcadeDB-Query-Tag` request header:

```python
db.query(language="sql", command="SELECT FROM Event", query_tag="nightly-report")

with db.transaction(query_tag="etl-run-42") as tx:
    tx.command(language="sql", command="INSERT INTO Event SET n = 1")  # labelled etl-run-42
    tx.command(language="sql", command="DELETE FROM Staging", query_tag="etl-cleanup")  # its own label
```

The label is opaque to the server: `list queries` shows it, and `terminate queries tag <label>`
stops every statement carrying it. `srv.list_queries` and `srv.terminate_queries_by_tag` issue those
two commands for you (see "Running work" below). On `transaction()` it is sent **only** on the begin request -
not on the statements, the commit or the rollback - and the server applies it to every statement of
the transaction that carries no label of its own; a statement that passes its own `query_tag`
overrides it. On `batch_load`/`batch_load_stream` it is a header like everywhere else, never a
query parameter beside `options`. No header is sent when the tag is `None` or empty. The client
does not check the tag's length or characters: the contract caps it at 256 printable characters,
but that is the server's rule, and a second copy of it here would only drift from the first. Do not
count on a refusal either - a 26.11.1-SNAPSHOT server was observed accepting a 257-character tag.

## Vector, hybrid and full-text search: `db.vector`

```python
nearest = db.vector.search(index_name="myIndex", query_vector=[0.1, 0.2, 0.3], k=5)
fused = db.vector.hybrid(
    vector_index_name="myIndex",
    query_vector=[0.1, 0.2, 0.3],
    fulltext_index_name="myTextIndex",
    fulltext_query="cat",
)
matches = db.vector.fulltext(query_text="cat")
```

`hybrid`'s `fusion_strategy` takes a `HybridSearchRequestFusionStrategy` - `RRF`, `DBSF` or
`LINEAR` - not a bare string. It was `str | Unset` until 26.10.1 turned the contract's
free-form field into an enum:

```python
from arcadedb_driver._generated.models.hybrid_search_request_fusion_strategy import (
    HybridSearchRequestFusionStrategy,
)

fused = db.vector.hybrid(
    vector_index_name="myIndex",
    query_vector=[0.1, 0.2, 0.3],
    fusion_strategy=HybridSearchRequestFusionStrategy.RRF,
)
```

The enum is a `str` subclass, so an existing call passing `"RRF"` still works on the wire and only
the typechecker complains - but a call passing `"rrf"` was always wrong and the server always
rejected it. Reading the enum off `_generated` mirrors how `expand` and `weights` already work on
this method; it is not re-exported at the top level, because a name re-exported from `_generated`
turns every contract bump into a breaking change to this package's public API.

Full-text responses carry `similarity` as an enum for the same reason, `BM25` or `CLASSIC`.

`search` runs a kNN query over a dense `LSM_VECTOR` or sparse `LSM_SPARSE_VECTOR` index; `hybrid`
fuses a vector leg with an optional full-text leg and an optional graph-expansion leg into one
ranked list; `fulltext` runs a Lucene-syntax query over a `FULL_TEXT` index. Each returns the whole
generated response model - `VectorSearchResponse`, `HybridSearchResponse`, `FullTextSearchResponse`
- never unwrapped to bare rows the way `QueryEnvelope` unwraps `query`/`command`. `results` sits
alongside `count`, `truncated` (search and hybrid only, see below), `scoring`, and the rest, all
still reachable on the object `db.vector.search(...)` hands back.

That matters most for `truncated`. `search` and `hybrid` both inspect a bounded candidate window
before ranking, and `truncated` is `True` when that window was filled - meaning more matches may
exist beyond what `results` shows, the same hazard the result envelope's `truncated` documents
above for `query`. A caller who reads `.results` off a vector search and ignores `.truncated` works
off a partial answer without being told; raise `k` and search again if you need to see further.

`fulltext`'s response, `FullTextSearchResponse`, has **no `truncated` attribute at all** - not
`False`, absent (`hasattr(resp, "truncated")` is `False`). That is the contract's shape, not a
field the server forgot to send: full-text search has no candidate-window concept to overflow the
way a vector search does, so there is nothing for a `truncated` flag to report either way.

`ef_search` (the dense-index search beam width) and each method's result-limit parameter (`k` for
`search`/`hybrid`, `limit` for `fulltext`) are bounded, but the bound is enforced **server-side**.
This client sends whatever value it is given without checking it first, so a value outside the
allowed range surfaces as an `ArcadeDBError` raised from the server's response, not as a local
exception before the request is even sent.

### Reading a hit

Two shapes stand between you and a field on a hit, both consequences of returning the generated
response whole. `VectorSearchResponse` carries no `required` list in the contract, so every one of
its fields defaults to `UNSET` and `results` is typed `list[VectorSearchResponseResultsItem] |
Unset` - a type checker will not let you iterate it unnarrowed. And a hit's `properties` is itself
a generated `attrs` model, `VectorSearchResponseResultsItemProperties`, not a `dict`: the record's
own fields live in its `additional_properties` mapping, so `hit.properties.name` raises
`AttributeError` rather than returning a value.

Neither is something the facade can strip on your behalf. Flattening `results` into `list[dict]`
the way `QueryEnvelope` flattens `query`/`command` rows would leave `truncated`, `count` and
`scoring` describing rows that no longer travel with them, and flattening only the rows would
manufacture a third shape - typed top-level fields above untyped rows - worse than either shape
this client already has (`facade/vector.py`'s module docstring argues this at length). So the
unwrapping is two lines at the call site:

```python
resp = db.vector.search(index_name="myIndex", query_vector=[0.1, 0.2, 0.3], k=5)

for hit in resp.results or []:
    props = hit.properties.to_dict() if hit.properties else {}
    print(hit.rid, hit.distance, props.get("name"))
```

`or []` is enough to discharge the `Unset`: `Unset.__bool__` is declared to return
`Literal[False]`, so a type checker narrows the loop's subject to the list without an `isinstance`
call. `to_dict()` copies the additional-properties mapping into a plain `dict`; if you would rather
not copy, `hit.properties["name"]` and `hit.properties.additional_properties["name"]` reach the
same value directly. `hybrid` and `fulltext` hits read identically, with their own per-element
model classes.

One asymmetry with `@arcadedb/driver` is worth knowing if you work in both clients:
`VectorSearchRequest.k`, `HybridSearchRequest.k`, and `FullTextSearchRequest.limit` all carry an
OpenAPI `default: 10` outside their schema's `required` list, and the two generators treat that
differently. `openapi-python-client` bakes the default straight into the generated model's own
constructor - `k: int | Unset = 10` is `VectorSearchRequest`'s actual field default here, so
`db.vector.search()`'s `k`/`limit` parameters stay optional with no extra work, and this facade
passes `UNSET` through rather than re-asserting `10` itself (see `facade/vector.py`'s module
docstring). `openapi-typescript` does the opposite: it emits a property carrying a `default` as
**required** on the generated TypeScript type, so `@arcadedb/driver`'s equivalent option types need
a hand-written widening back to optional (`WithOptionalDefaults` in `facade/vector.ts`) that this
client never needed.

## Time series: a rejected `db.ts.write` raises `TimeSeriesWriteError`

`POST /api/v1/ts/{database}/write` answers 204 when every sample landed, and 400 with the counts
when some or all could not be applied. `db.ts.write` raises `TimeSeriesWriteError` for that 400 - a
subclass of `ArcadeDBError`, so `except ArcadeDBError` still catches it and every usual field is
filled - carrying the body:

```python
from arcadedb_driver import TimeSeriesWriteError

try:
    db.ts.write(line_protocol=payload)
except TimeSeriesWriteError as err:
    print(err.written, err.dropped)  # samples that landed, samples that did not
    print(err.unknown_types, err.non_time_series_types, err.unavailable_types, err.undeclared_keys)
```

The four lists say why samples were dropped, and each is empty when the server sent none:

- `unknown_types`: measurements naming a type that does not exist.
- `non_time_series_types`: measurements naming a type that exists but is not a time-series type.
- `unavailable_types`: measurements naming a time-series type whose storage engine failed to load
  (the server log says why).
- `undeclared_keys`: `'<measurement>.<key> (tag|field)'` entries for keys the type does not declare
  in that role; the samples carrying them were dropped. The server caps this list at 100 entries.
  A server started with `arcadedb.timeSeriesUndeclaredKeys=ignore` stores such samples with the
  undeclared keys discarded instead of dropping them.

**A write is not atomic.** Each measurement's batch commits as it is appended, so the `written`
samples are durable even though the call raised - and a rollback of a surrounding transaction does
not take them back either. Retry the dropped measurements, never the whole payload, or the written
ones land twice. `written` and `dropped` are `None` only if a server omits them. Every other
failure - a 401, a 413, a 400 whose body is not a JSON object - raises a plain `ArcadeDBError`.

## Time series: `db.ts.query`'s `tags` and `db.ts.latest`'s `tag` are enforced server-side

A name in `db.ts.query`'s `tags` body field, or in `db.ts.latest`'s `tag` parameter, that is not
one of the type's declared TAG columns is not dropped from the filter - it is **refused** with a
400 response naming the offending tag and listing the type's declared TAG columns. Silently
ignoring it would widen the query to the whole range, and a caller has no way to tell that result
apart from a filter that legitimately matched everything. `db.ts.latest`'s `tag` is also refused
the same way when it is not in `name:value` form - a missing `:` separator is an error, not a
skipped filter.

Both rules are enforced **server-side**, the same way `ef_search` and the vector/full-text
result-limit parameters are (see "Vector, hybrid and full-text search" above): this client sends
`tags`/`tag` unchanged and does not check either against a schema it does not have, so a violation
surfaces as an `ArcadeDBError` raised from the server's response, not a local exception before the
request is even sent.

## PromQL: `db.promql`

`db.promql` is the Prometheus-compatible query surface, returning the generated models: `query`,
`query_range`, `labels`, `label_values` and `series`, each with an async twin. The metric name for a
time-series type is the **type name itself** (`Sensor`), not `Sensor_value`.

```python
db.promql.label_values("sensor")  # every value of the `sensor` tag
db.promql.label_values("sensor", start="1700000000", end="1700003600")  # only values in that range
db.promql.label_values("__name__")  # the time-series type names
```

`label_values` lists the values one label carries, restricted to `start`/`end` (Unix seconds, both
optional; omit both for the whole series). The name `"__name__"` is special: it lists the
time-series **type names** rather than a tag's values, since a type name is the metric name. The
server answers an empty success, not an error, for a label no series carries, so an empty
list does not mean the name was misspelled. Pass the name unescaped; the client percent-encodes it.

## Two error models

The facade methods (`query`, `command`, `transaction`, `list_databases`, `exists`, `server_info`,
`health`, `ready`, the `ts`/`grafana`/`promql` namespaces, ...) raise `ArcadeDBError` on any
non-2xx response:

```python
from arcadedb_driver import ArcadeDBError

try:
    db.query(language="sql", command="SELECT FROM NoSuchType")
except ArcadeDBError as err:
    print(err.status, err.error, err.detail, err.request_id, err.help_)
```

Two fields come from the response's headers rather than its body:

- `err.retry_after`: seconds to wait before retrying, from `Retry-After`. The server sends it on a
  refusal that carries a back-off - 503 when the node cannot execute the request yet (a snapshot
  install, for instance), 409 when an identical request is still in flight. `None` when the header
  is absent or is not a plain non-negative integer; an HTTP-date `Retry-After` is not parsed.
- `err.commit_index`: the Raft commit index the response was produced at, from
  `X-ArcadeDB-Commit-Index`. It is still a valid read-after barrier on an error: send it back as
  `X-ArcadeDB-Read-After` (through `ArcadeDBServer(headers=...)` or `.raw`) to read at least the
  state the server had committed. `None` on a standalone database, which sends no such header.

A streamed call's in-band error carries the same two fields from the event instead (see the
streaming and batch sections above), since a header cannot be added once the stream has started.

**A 409 has two meanings, and `status` alone cannot tell them apart.** One is "an identical request
is still in flight": the request was not executed again, `exception` is
`RequestStillInFlightException` and `retry_after` is set, and retrying after that many seconds (with
the same `X-Request-Id`) returns the result of the execution in progress. The other is "the query
was terminated" by `terminate query`, `terminate queries` or `terminate transaction`: its writes
were rolled back, and it is **not** retryable - someone stopped it on purpose. This client retries
neither. Retry logic of your own must tell them apart by `exception` / `retry_after`, never by the
status alone.

`err.help_` is spelled with a trailing underscore to match the field name on the generated
`ErrorResponse` model, which is reachable through `.raw` - `help` alone would shadow the Python
builtin, and picking a different spelling for the same field on the two error surfaces this
package exposes would be worse than one awkward name used consistently.

`server.raw`, the underlying generated client, does **not** raise. Every one of its operations
returns a `Response` whose `status_code` and `parsed` the caller inspects directly:

```python
from arcadedb_driver._generated.api.database import list_databases

response = list_databases.sync_detailed(client=srv.raw)
if response.status_code >= 300:
    ...  # handle it yourself; srv.raw never raises
```

These are two deliberately different contracts in one package. Use the facade for the ergonomics
of `try`/`except`; use `.raw` when you want to branch on a status code without exceptions. Mixing
assumptions about which one you're calling is the most common way to end up with an unhandled
exception or a silently ignored error.

## `exists` cannot prove absence

```python
present = srv.exists("mydb")
```

`exists` returns `False` both when the database genuinely does not exist and when it exists but
the authenticated caller is not authorized to see it - the server's response does not distinguish
the two cases, so this client cannot either. Do not treat `False` as proof that a database is
absent; it only means "not visible to this caller right now."

## Administration: databases, users and groups

```python
with ArcadeDBServer(base_url="http://localhost:2480", auth=basic_auth("root", "playwithdata")) as srv:
    srv.create_database("tenant_a")
    srv.create_user("alice", "a-long-password", databases={"tenant_a": ["admin"]})  # "*" = every database
    users = srv.list_users()  # [{"name": "alice", "databases": {"tenant_a": ["admin"]}}, ...]
    srv.update_user("alice", password="another-password")
    srv.drop_user("alice")
    srv.drop_database("tenant_a")
```

`AsyncArcadeDBServer` has the same methods, awaited. All of them are root-only, and every failure
raises `ArcadeDBError`, as for any facade method. Users and groups have dedicated endpoints with a
structured body (`/api/v1/server/users`, `/api/v1/server/groups`): `create_user`, `update_user`,
`drop_user`, `list_users`, `save_group`, `delete_group`, `list_groups`. Databases have none, so
`create_database` and `drop_database` send `create database <name>` and `drop database <name>`
through `POST /api/v1/server`. They raise `ValueError` for an empty name, or one with leading or
trailing white space, before sending anything, because the server trims the name it reads out of
the command and would act on a different database than the one you named. Anything else in the
name is sent as given, embedded spaces included: one request runs one command, so a name cannot
smuggle in a second command, but validate a name built from untrusted input yourself.

**"Already exists" is a 409 for users and databases alike.** Both statuses were measured against a
real server; they are what the e2e suite pins.

- A user that already exists is a **409** (`error` "User already exists"), so a 409 from
  `create_user` means "already there" and create-if-absent can catch it. Servers built before
  ArcadeData/arcadedb#10076 answer **403** "Security error" instead, which is also what a
  non-root caller gets; against those, do not read 403 as "already exists".
- A database that already exists is a **409** too (`error` "Database already exists", the
  name in `detail`). Servers built before ArcadeData/arcadedb#10079 answer **400** "Cannot
  execute command" instead, the status every invalid server command gets; against those,
  call `exists` first to create a database only when it is missing (as root it sees every database,
  so its `False` is reliable there), knowing another client can still create it in between.

`update_user` and `save_group` send only the arguments you pass: one left as `None` keeps the
server's current value. `update_user(name, databases={})` sends the empty mapping, which removes
every assignment. `list_users` and `list_groups` return plain dicts, not generated models.

`srv.server_command(command)` runs any other server command and returns the whole JSON body as a
`dict`. It decodes the body itself rather than through the generated model, because the contract
declares an array `result` where administrative commands answer `{"result": "ok"}`, which makes
the generated `from_dict` raise; other commands answer shapes of their own. The command string is
sent as given.

## Running work: list and terminate queries and transactions, and `progress`

```python
from datetime import timedelta
from arcadedb_driver import is_query_terminated

running = srv.list_queries(tag="nightly-report")  # or database=..., or neither
results = srv.terminate_queries_by_tag("nightly-report", wait=timedelta(seconds=3))
result = srv.terminate_query(running[0].id)
open_txs = srv.list_transactions()
result = srv.terminate_transaction(open_txs[0].id)
progress = srv.db("tenant_a").progress()  # long-running maintenance operations, step by step
```

Every method has an async twin on `AsyncArcadeDBServer` and `AsyncArcadeDBDatabase`. Unlike the
administration methods above, these are open to **any authenticated user**: root sees and stops
every statement, another user only their own, and someone else's statement is answered
`"not found"`, never "forbidden". They go through `POST /api/v1/server`, and `progress` through
`GET /api/v1/progress/{database}`. Results are the frozen dataclasses `RunningQuery`,
`TerminateResult` and `OpenTransaction`, with times as timezone-aware `datetime` and `timedelta`.

**Each server sees only its own work.** None of these is forwarded to the cluster leader. Behind a
load balancer, the server this client reaches may not be the one running the statement, and then
`list_queries` does not show it and terminating it answers `"not found"`.

**A statement shows up before its text does.** The server lists a request the moment it is
admitted, and for a brief window that entry's `language` is `None` and its `text` is the request
line (`POST /api/v1/command/<database>`); both are filled in once the statement starts. To read the
statement itself, poll until `language` is set.

Each of the three terminate methods waits for the statements to stop, up to `wait` (omitted or zero leaves the server's
default of 5 seconds, and the server caps it at 10), then answers each with a `status`, typed as
`QueryStatus`. **Which one you get decides whether you have anything to undo:**

| `status` | meaning |
|---|---|
| `"terminated"` | it stopped, and what it wrote was rolled back |
| `"completed"` | it finished on its own before it noticed, so **what it did stands** |
| `"terminating"` | not stopped yet when the wait ended; some statements (SQL `SLEEP`, for one) notice only when they end, so the request's own outcome is the answer |
| `"not found"` | no such statement on this server, or another user's |

Terminating a **command** inside a transaction ends the transaction too, rolling it back, while
terminating a read leaves it open; `TerminateResult.session_id` and `session_open` say which, and
`session_open` is only the state at the time of the answer for a `"terminating"` statement. A
script counts as a command.

**The stopped request raises a 409, and `is_query_terminated(error)` recognises it.** The server
answers it 409 "Query terminated", but a 409 is also what a request still in flight under the same
`X-Request-Id` gets, so the status alone cannot tell "someone stopped me" from a conflict.
`is_query_terminated` matches the error's `exception`,
`com.arcadedb.exception.QueryTerminatedException`, which the server sends as a structured field, not
the message text. It is not retryable: somebody stopped this work on purpose.

**`terminate_transaction` reaches the client that owned the transaction at commit.** It rolls the
transaction back, a statement sent on it afterwards raises a 404, and so does the commit: the
owner's `with db.transaction()` block raises that 404 `ArcadeDBError` ("Remote transaction session
not found or expired") on exit. Servers built before ArcadeData/arcadedb#10164 (2026-10-16) answer
that commit 204, exactly like a real commit, so against those a block that ran no statement after
the terminate exits cleanly for work that is gone. Measured against 26.11.1-SNAPSHOT and pinned by
the e2e suite.

Ids, session ids and the `database` filter must not be empty (where required) or contain a space
or control character (anything at or below U+0020), because the server reads each as one word; a
tag must not start or end with one, because the server trims it. A no-break space is not one, as
the server sees it. Each raises `ValueError` before anything is sent. A tag is
otherwise sent as given, spaces and quotes included: the server takes the rest of the command as the
tag.

`progress()` returns the generated `ProgressResponse`, whose `result` is empty when nothing is
running. The server reads a lock-free snapshot, so polling it at any rate cannot slow down the
operation being watched.

## Sessions and API tokens

```python
with ArcadeDBServer(base_url="http://localhost:2480", auth=basic_auth("root", "playwithdata")) as srv:
    # Per-user isolation: log in as the user once, then keep a client holding only the token.
    login = srv.login_as("alice", "a-long-password")  # or srv.login(): the client's own credentials
    with srv.with_token(login.token) as alice:  # srv itself is unchanged
        dbs = alice.list_databases()  # only what alice may see
        alice.logout()  # the token is now refused everywhere

    # A long-lived machine credential (root only).
    created = srv.create_api_token("ci", database="tenant_a")
    store(created.token)  # the only time the plaintext exists
    tokens = srv.list_api_tokens()  # metadata only, never the token
    srv.delete_api_token(created.token_hash)  # by hash, never by token
```

`AsyncArcadeDBServer` has the same methods, awaited, except `with_token`, which sends nothing and
so is a plain call returning an `AsyncArcadeDBServer`.

`login` and `login_as` return a `LoginResult` carrying the session token (prefixed `AU-`) and
leave the client alone: `login_as` sends the user's credentials on that one request only.
`with_token` returns a **new** server presenting the token as a bearer token, with the original's
base URL, extra headers, timeout and TLS verification. It has its own connection pool, so close it
or use it in a `with` block; closing one server does not close the other. A token is a credential:
whoever holds it acts as that user until it is logged out or the server drops it, which is why
`LoginResult`, `Session` and `CreatedAPIToken` leave their tokens out of `repr()`. Keeping the
token rather than the password is the point.

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
  `login_as` 403 cannot be told apart from a forbidden user.
- **`logout` only ends a session token.** The server answers 204 to a logout carrying Basic
  credentials or an API token and invalidates nothing, so `logout` on a client that does not
  present an `AU-` token raises `NotSessionTokenError` without sending anything. Logging out a
  token that is no longer valid is a 401.
- **`list_sessions` is root-only** (403 otherwise) and lists every user's live session token. Treat
  its result as you would the users' passwords. These are login sessions, not the transaction
  sessions `transaction()` opens. Times are timezone-aware UTC `datetime`s, `elapsed` a
  `timedelta`, and a field the server does not know (`source_ip`, `user_agent`, `country`, `city`,
  `issuer`) is `None`.

API tokens:

- **The plaintext is returned exactly once**, in `CreatedAPIToken.token`. The server stores only
  its SHA-256 hash, so a lost token cannot be recovered, only deleted and reissued. This client
  never logs or keeps it.
- **`delete_api_token` takes the hash** (`token_hash`, from `list_api_tokens` or
  `create_api_token`). Anything but 64 lowercase hexadecimal characters raises `ValueError` before
  a request is sent, because the argument travels in the query string, where proxies and access
  logs record it, and the likeliest mistake is the plaintext token. The error does not repeat the
  argument. A hash no token has is a **404**, a status the contract does not list
  (ArcadeData/arcadedb#10110).
- **A taken name is a 409.** The contract describes its 409 only as a replayed `X-Request-Id`;
  the server also uses it for a duplicate name.
- **412 means the transport is not confidential.** With
  `arcadedb.server.apiTokenRequireSecureTransport` on, the server refuses to send a token back over
  cleartext HTTP to a non-loopback client, unless a proxy listed in
  `arcadedb.server.apiTokenTrustedProxies` terminated TLS. The setting is off by default until
  ArcadeDB 27.1.1, which turns it on; until then such a mint succeeds and the server logs a warning.
- `expires_at` is `None` for a token that never expires. Passed to `create_api_token`, it must be
  timezone-aware and after the Unix epoch, or `ValueError` is raised before sending: a naive time
  would be read in whatever timezone the client runs in, and the server reads an expiry of 0 as
  "never", so an epoch expiry would issue a token that never expires. An expired token
  authenticates nobody, and stays in `list_api_tokens` (with `expired` set) until the next token
  change retires it. `permissions` takes the shape a group's `types` map takes.
- `logout` on a client holding an API token raises `NotSessionTokenError`: an API token is revoked
  with `delete_api_token`, not logged out.

## Endpoints this client does not wrap

Two distinct things are true about parts of the contract, and they should not be confused with
each other.

**Not wrapped at all.** `POST /api/v1/ts/{database}/prom/read` and
`POST /api/v1/ts/{database}/prom/write` (protobuf bodies) are endpoints the generator cannot model -
it has no way to describe a non-JSON request body, so it prints a warning, skips the endpoint
entirely, and exits 0. Nothing downstream notices on its own: a skipped endpoint leaves no trace in
the generated tree for `git diff` to flag. This package pins the exact skip set in
`scripts/check_codegen_skips.py`, which re-runs the generator against the committed contract and
fails if the set of skipped operations changes - so a future contract that starts describing either
endpoint in a way the generator *can* model, or drops one of them, cannot pass unnoticed.

`db.ts.write` (`POST /api/v1/ts/{database}/write`, InfluxDB line protocol as `text/plain`) and
`batch_load`/`batch_load_stream` (`POST /api/v1/batch/{database}`, a jsonl/ndjson/csv body) have
the same generator limitation - both endpoints are also in `EXPECTED_SKIPS` above - but both are
hand-written rather than left unwrapped: a time-series namespace that could query samples but never
ingest any, or a client with no way to bulk-load a graph at all, would be an odd thing to ship. See
"Batch loading" above for `batch_load`/`batch_load_stream`.

**Cluster override endpoints are deliberately raw-only.** `acceptClusterDatabaseCopy`
(`POST /api/v1/cluster/accept-copy/{database}`), `acceptClusterDivergedDatabase`
(`POST /api/v1/cluster/accept-diverged/{database}`) and `acceptClusterStaleSnapshot`
(`POST /api/v1/cluster/accept-stale-snapshot`) are root-only operator overrides that make a node
accept a copy of a database without a resync - a decision about which data survives, not an
operation for application code. No facade method wraps any `/cluster/*` endpoint; reach them through
`.raw`'s generated operations when an operator means to.

`POST /api/v1/server` reached through `.raw` returns a body that does not conform to its declared
`QueryResponse` schema (`{"result": "ok"}` where an array is declared), so the generated model
raises on an otherwise successful call. Use `srv.server_command` (see "Administration" above)
instead.

**Wrapped, but returning `dict[str, Any]` instead of a generated model.** Unlike `batch`,
`prom/read`, and `prom/write` above, these three routes describe a JSON body the generator *can*
model, and it does generate operation functions and response models for them -
`_generated/api/time_series/query_time_series.py`, `get_time_series_latest.py`, and
`_generated/api/grafana/query_grafana.py` all exist on disk. But `db.ts.query`, `db.ts.latest`,
and `db.grafana.query` do not call any of those generated operations - they are hand-written, and
none of the three generated modules above is imported anywhere outside its own package. Each
method builds the request URL itself and issues it directly through the same pooled httpx client
the generated operations use (`self._client.get_httpx_client()`, or its async twin), returning the
parsed JSON body rather than routing the response through a generated model at all.

The reason is the same in all three: the contract types each of these responses' per-element
scalar values (a timestamp, a numeric measurement, a DataFrame cell) as `"type": "object"`, so the
generated per-element model's `from_dict` calls `dict(value)` on every element - which raises
`TypeError` on an ordinary scalar like a float or an int. Had these methods routed through the
generated operations instead, `db.ts.query`'s `oneOf` response parser would have caught that
`TypeError` and silently fallen through to the aggregated-response model, whose fields are all
optional and so "parses" anything - every raw (non-aggregated) query response would come back
mis-typed as an empty-looking aggregated one instead of raising. `db.ts.latest` and
`db.grafana.query` have no such fallback branch and would simply raise `TypeError` on any real
response. `@arcadedb/driver`, the TypeScript sibling, is unaffected only because `openapi-fetch`
performs no runtime validation of its own - the raw JSON passes through unexamined. Bypassing the
generated operations and returning the parsed body directly is the Python equivalent, and the only
correct behaviour, until the contract is fixed upstream to type these fields correctly; fixing the
contract is also what would let these three methods move onto the generated operations and return
generated models, the same way `db.promql.*` already does - `db.promql.*` is unaffected by any of
this today because its response schemas do not have this shape.

## Contract version and compatibility

This package was generated from `contracts/arcadedb-openapi-26.11.1-SNAPSHOT.json`, recorded in
`pyproject.toml` as `tool.arcadedb.server-version`:

```toml
[tool.arcadedb]
server-version = "26.11.1-SNAPSHOT"
```

| `arcadedb-driver` | ArcadeDB server |
| --- | --- |
| 0.1.0 | 26.9.1 |
| 0.2.0 | 26.10.1 |
| 0.3.0 | 26.10.2 |

This table is a historical record tied to a package version, not something derived automatically:
`scripts/adopt-contract-version.sh` deliberately does not touch it when it retires an old contract
and adopts a new one. Adding a row is a human decision made at release time, not a side effect of
a contract bump.

The client speaks ArcadeDB's HTTP API as described by that contract. Pointing it at a server on a
materially different release may work for the endpoints both versions share, but is not tested or
supported.

## License

Apache-2.0.
