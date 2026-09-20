# arcadedb-driver

A Python HTTP client for [ArcadeDB](https://arcadedb.com), generated from ArcadeDB's OpenAPI
contract, with a hand-written facade on top for the data plane, transactions, and the pieces of
the contract the generator cannot model.

Published on PyPI as [`arcadedb-driver`](https://pypi.org/project/arcadedb-driver/), with
attestations: every release is built and published by `publish-python.yml` from a clean checkout of
this repository through PyPI's trusted publishing, with no long-lived token anywhere in the chain.

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
    envelope = db.query(language="sql", command="SELECT FROM Person WHERE age > ?", params={"1": 21})
    print(envelope.result)
```

A bearer token (for example, a session token returned by `/api/v1/login`) works the same way:

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
        envelope = await db.query(language="sql", command="SELECT FROM Person WHERE age > ?", params={"1": 21})
        print(envelope.result)


asyncio.run(main())
```

## The result envelope, and why `truncated` matters

`query` and `command` do not return bare rows. They return the whole response envelope:

```python
@dataclass(frozen=True, slots=True)
class QueryEnvelope:
    result: list[dict[str, Any]]
    limit: int
    returned: int
    truncated: bool
```

`truncated` is `True` when the server's serializer hit its row cap while a query still had more
rows to write - `result` is then a partial answer, not a short-but-complete one. A caller that
reads `result` and ignores `truncated` can silently work off a partial answer, because a truncated
list and a complete one are indistinguishable by shape alone. Always check `truncated` before
treating `result` as the whole answer, and re-query with a narrower filter or a higher `limit`
when it is `True` - though raising `limit` is not always the fix: a result whose true size exceeds
the server's hard ceiling (`arcadedb.server.httpQueryMaxResultRows`) is refused outright with 413
rather than truncated, so once you are past that ceiling a narrower filter is the only way forward.

`truncated is False` used to be a client-side default rather than a server guarantee: until
26.10.1-SNAPSHOT, `QueryResponse` declared no required fields, so the envelope's `limit`,
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
response, with a `status` of 200 - so both paths fail the same way; any event already yielded
before the error stays delivered to the caller.

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

When a streamed `error` event's `statusMapped` is `False`, its `status` is an unclassified 500
fallback rather than the status the buffered encoding would have chosen - an engine failure raised
after the stream had already started. Key on `exception` there, not on `status`; the raised
`ArcadeDBError` carries `exception` and its `detail` says why. `error` and `exception` are two
more fields the server sends that no schema declares (the contract's streamed error object
declares only `commitIndex`, `status` and `statusMapped`), read off the raw event here and
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
  the server-side session is not left open until `arcadedb.server.httpTxExpireTimeout` reaps it,
  and then the commit's error is re-raised.

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
`LINEAR` - not a bare string. It was `str | Unset` until 26.10.1-SNAPSHOT turned the contract's
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

`POST /api/v1/server` (administrative commands) is likewise not wrapped by the facade, and reached
through `.raw` returns a body that does not conform to its declared `QueryResponse` schema
(`{"result": "ok"}` where an array is declared), so the generated model raises on an otherwise
successful call.

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

This package was generated from `contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json`, recorded in
`pyproject.toml` as `tool.arcadedb.server-version`:

```toml
[tool.arcadedb]
server-version = "26.10.1-SNAPSHOT"
```

| `arcadedb-driver` | ArcadeDB server |
| --- | --- |
| 0.1.0 | 26.9.1 |
| 0.2.0 (unreleased) | 26.10.1-SNAPSHOT |

This table is a historical record tied to a package version, not something derived automatically:
`scripts/adopt-contract-version.sh` deliberately does not touch it when it retires an old contract
and adopts a new one. Adding a row is a human decision made at release time, not a side effect of
a contract bump.

The client speaks ArcadeDB's HTTP API as described by that contract. Pointing it at a server on a
materially different release may work for the endpoints both versions share, but is not tested or
supported.

## License

Apache-2.0.
