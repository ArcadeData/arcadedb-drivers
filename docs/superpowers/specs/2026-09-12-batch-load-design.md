# Streaming bulk load over HTTP: wrapping `/batch` in both clients

**Issue:** [#52](https://github.com/ArcadeData/arcadedb-drivers/issues/52) — split out of #39.
**Upstream:** ArcadeData/arcadedb#7311 (closed), and four defects this design work filed:
arcadedb#7567, #7568, #7569, #7570.
**Date:** 2026-09-12.

## 1. What this builds

`POST /api/v1/batch/{database}` streams vertices and then edges into a database through ArcadeDB's
GraphBatch API. Neither client wraps it. This design adds one facade surface per client, in both
the buffered and the streamed response modes, and documents three failure modes that are easy to
meet and expensive to discover.

## 2. The premise, corrected

Issue #52 says `/batch` is "entirely unwrapped in both clients today" and that this work
"introduces the endpoint". That is true of the **facades** and false of **reachability**, and the
two languages differ — which changes the shape of the work in each.

| | Today | What this design adds |
|---|---|---|
| **TypeScript** | `raw.POST("/api/v1/batch/{database}")` **already works**, fully typed, `NdJsonBatchEvent` included (`src/generated/schema.ts:159`). `openapi-typescript` emits types for every path regardless of media type, and `openapi-fetch` dispatches on the typed path. | A facade over a path that already exists: row serialization, and the streamed decoder. |
| **Python** | **Unreachable.** `openapi-python-client` drops any non-JSON request body, so `_generated/api/batch/__init__.py` is a 56-byte empty stub. `POST /api/v1/batch/{database}` is one of the four pinned `EXPECTED_SKIPS`. | The whole operation, hand-written over the generated client's pooled httpx client — the same shape as `ts.write`. |

`EXPECTED_SKIPS` is **not** touched. The endpoint remains skipped by the generator; we wrap it by
hand. Removing an entry there to make something pass is forbidden, and nothing here needs it.

This is the fourth consecutive milestone whose spec premise was false when checked. It is also a
second instance of the rule already recorded in `python/CLAUDE.md`: a skipped endpoint says what
the generator dropped, never what a user can call.

## 3. The wire format, established empirically

**Nothing in the OpenAPI contract describes the request payload.** All three request media types
are declared `{"type": "string"}` with a one-line description. The format below was reverse-engineered
against `arcadedata/arcadedb:26.10.1-SNAPSHOT` and reported upstream as arcadedb#7570.

```
{"@type":"vertex","@class":"Person","@id":"p1","name":"Alice"}
{"@type":"edge","@class":"Knows","@from":"p1","@to":"p2","since":2020}
```

- `@type` is the discriminator, exactly `"vertex"` or `"edge"`.
- `@class` is the type name. Required; its absence answers 400 "Missing @class at line N".
- `@id` is a vertex's temporary id, optional. Vertices without one are counted in
  `verticesWithoutId`; vertices with one appear in the response's `idMapping` as `tempId -> RID`.
- `@from` / `@to` are an edge's endpoints: a temp id declared **earlier in the same payload**, or a
  literal `#bucket:position` RID.
- **Properties sit flat beside the control keys.** They do not nest.

### The trap this format sets

The gRPC sibling `GraphBatchRecord` has a `properties` map field, so the natural guess is that the
JSON encoding nests properties too. It does not — and the nested form is **accepted**:

```
{"@type":"vertex","@class":"Person","properties":{"name":"Alice"}}
-> 200 {"verticesCreated":1, ...}
-> stored: {"@rid":"#1:0","@type":"Person","@cat":"v","properties":{"name":"Alice"}}
```

A property literally named `properties` is created. The load reports success, the counters are
correct, and the data is wrong; nothing fails until someone queries for `name`. **D2 below makes
this unreachable through our API rather than documenting it as a hazard.**

## 4. Decisions

### D1 — Vertices and edges are separate arguments, not one mixed iterable

The server requires every vertex to appear before the edges referencing it, and resolves temp ids
only within a single request's payload. The API therefore takes two collections and concatenates
them in the correct order:

```ts
db.batchLoad({ vertices, edges, options })
```

The ordering mistake becomes **unrepresentable** rather than validated. The two alternatives were
both worse: validating client-side means buffering every declared temp id in memory, which defeats
the streaming this endpoint exists for, and re-implements a rule the server already enforces with
better error messages than we would write; letting the server answer means the 400 arrives *after*
a partial commit may already be durable, and — because temp ids are not keys — retrying that load
**duplicates** whatever committed.

Cost, accepted: a caller cannot interleave, and a caller holding one mixed file must split it into
two streams rather than piping it through. Both are acceptable against a footgun that silently
duplicates data.

### D2 — Rows are structured; the client maps them to the wire

```ts
type VertexRow = { type: string; id?: string; properties?: Record<string, unknown> };
type EdgeRow   = { type: string; from: string; to: string; properties?: Record<string, unknown> };
```

The client emits the `@`-prefixed control keys and flattens `properties` beside them. Three things
follow, and the first is the reason:

1. **§3's corruption trap cannot reach a caller.** Nesting is what *our* type asks for, and
   flattening is our job, done once, correctly.
2. A property can never collide with a control key, because the two live in different places in
   our type. Passing the wire shape through would mean a property named `@class` silently becoming
   one.
3. It mirrors gRPC's `GraphBatchRecord` (`kind`/`type_name`/`temp_id`/`from_ref`/`to_ref`/
   `properties`), so bulk load reads alike across both protocols.

Cost: a mapping layer per language, and our docs no longer match ArcadeDB's own payload
documentation one-to-one. Worth it — and ArcadeDB has no payload documentation to match today.

### D3 — Two methods, not a mode

`batchLoad` returns a `BatchSummary`. `batchLoadStream` returns an async iterable of events. This is
the convention M7 established for `query`/`queryStream` and `command`/`commandStream`, and both
READMEs already argue for why streaming is a separate method rather than a flag on an existing one.

The request body streams in **both** cases — that is what the endpoint does. The distinction is
purely the response encoding, selected by `Accept`.

### D4 — All 17 tuning parameters are typed, flat

`batchSize`, `lightEdges`, `wal`, `parallelFlush`, `preAllocateEdgeChunks`, `edgeListInitialSize`,
`bidirectional`, `commitEvery`, `expectedEdgeCount`, `commitRetries`, `commitRetryDelayMs`,
`vertexBatchSize`, `expectedVertexCount`, `expectedRecords`, `ordinalBase`, `idMapping`, `refMode`.

One options object, names spelled exactly as the contract spells them, flat like every other
options object in both clients. A curated subset would mean deciding for the user which knobs are
real, and that line would be re-argued on every issue. The drift gate catches a contract change.

### D5 — `batchLoadStream` passes `idMapping` fragments through; it does not accumulate

The server reports the temp-id mapping differently per mode:

- **Buffered:** the summary carries the whole map, `{"p1":"#1:2"}`.
- **Streamed:** each `progress` line carries its own fragment, and the summary carries
  `idMappingStreamed: true` and `idMappingSize: N` **instead of** the map.

The facade preserves that. A caller who wants the complete mapping accumulates it from the progress
events, or uses `batchLoad`.

Normalising it — merging fragments so both methods return an identical summary — was tempting and
is what "envelope bookkeeping belongs in the client" would suggest. It is rejected because the
client would then hold the entire mapping in memory, which is exactly the cost the server streams
it to avoid: a million-vertex load means a million entries the caller never asked for. The
asymmetry is real and gets documented rather than hidden.

### D6 — The two error channels collapse into one

A streaming load can fail two ways, and the contract is explicit about it:

- **Before the first acknowledgement** the status line has not been sent, so the server answers
  with a real HTTP status (400, 408, 500) and the buffered error body.
- **After the first progress line** the status line is already sent and cannot be taken back, so
  the failure arrives in band, under a 200, as an `error` event carrying the `status` the buffered
  encoding would have used.

`batchLoadStream` raises `ArcadeDBError` in **both** cases, carrying the status from whichever
channel supplied it. A caller's `for await` therefore fails identically regardless of when the
failure happened, which is the only difference between the two channels.

Where the event carries `statusMapped: false`, `status` is an unclassified 500 fallback rather than
the status the buffered encoding would have chosen; the error records this and the docs say to key
on `exception` there, as the contract instructs.

This is the one decision here that hides something the server exposes, which cuts against how this
repository usually treats asymmetries. It is justified because the two channels are a transport
artifact of when the status line is flushed, not a semantic distinction a caller can act on
differently — unlike `truncated` or `exists`, where the asymmetry carries meaning.

## 5. Structure

| File | Language | Role |
|---|---|---|
| `typescript/packages/driver/src/facade/batch.ts` | TS | Row serialization, both methods, over the existing `raw` path. |
| `python/packages/driver/src/arcadedb_driver/facade/batch.py` | Py | Sync and async twins, hand-written over the pooled httpx client. |

TypeScript reuses M7's `parseAs: "stream"` decoder and its `reader.cancel()` teardown. Python
reuses M7's `_iter_ndjson_lines`/`_aiter_ndjson_lines`, which split on `"\n"` alone over
`iter_text()` — `httpx.iter_lines()` is unusable here, because it splits on `str.splitlines()`
semantics and a raw U+2028 inside a JSON string (which JSON permits) tears one record into two
unparseable fragments. Verified on httpx 0.28.1.

The namespace question — whether these hang off `db` directly or a `db.batch` namespace — follows
the existing convention: `db.batchLoad` / `db.batch_load` directly, since `ts`/`grafana`/`promql`/
`vector` are namespaces because they wrap *many* endpoints, and this wraps one.

### D7 — the name is `batchLoad`, deliberately not `bulkLoad`

`bulkInsert` / `bulk_insert` already exist in **`arcadedb-driver-grpc`**, wrapping the gRPC
`BulkInsert` RPC, which inserts plain records. This is a different operation: GraphBatch takes
vertices and edges and resolves temp-id references between them. Its actual cross-protocol sibling
is gRPC's `GraphBatchLoad`, not `BulkInsert`.

`bulkLoad` beside an existing `bulkInsert` would read as a variant of it, in two packages a user
commonly installs together. `batchLoad` is named for the endpoint it wraps, cannot be mistaken for
`bulkInsert`, and lets both READMEs say plainly which gRPC RPC it corresponds to. Both READMEs
should carry that sentence, because the near-miss is exactly the kind of thing a reader resolves
wrongly by guessing.

## 6. Documented as load-bearing prose

Three facts go in both READMEs, in the tradition of `truncated` and `exists`:

1. **A batch is not atomic.** It commits every `commitEvery` records, so a failure mid-stream leaves
   earlier chunks durably committed. Because temp ids are not keys, **retrying the whole payload
   duplicates the vertices that already committed.** The partial-commit counters on a 400 are an
   upper bound on what is durable, not an exact count.
2. **Temp ids are request-scoped.** A vertex loaded by an earlier request must be referenced by RID
   (`#bucket:position`); its temp id means nothing to a later call.
3. **`bytesRead` is how a chunked upload is verified.** A body that ends before its announced length
   answers 408 with partial-commit counters, never a 200 with a truncated count. Compare `bytesRead`
   against the bytes sent.

## 7. Testing

**Unit.** Serialization: vertices emitted before edges regardless of argument evaluation order;
`properties` flattened beside the control keys and never nested; an omitted `id` producing no `@id`.
The streamed decoder against records split mid-line across chunks, and against a record containing a
raw U+2028. Both error channels: a pre-acknowledgement HTTP error and a post-progress in-band error
raising the same way (D6).

**e2e, against a real container.** A load of vertices and edges asserting `verticesCreated`,
`edgesCreated`, and that `idMapping` resolves every declared temp id to a real RID. One assertion
that the `properties` corruption of §3 cannot be produced through our types. A streamed load
asserting at least one `progress` event precedes exactly one `summary`.

No test asserts a forward reference is rejected, because D1 makes one unrepresentable — a test
would have to construct the wire payload by hand, which tests the server rather than this client.

## 8. Out of scope

- **`text/csv`.** Its format is as undocumented as the ndjson one (arcadedb#7570 notes this), and
  the rows-in model of D2 does not express a header row. A caller with a CSV file converts it, or
  uses `raw` in TypeScript. Revisit if asked for.
- **`application/jsonl`.** Byte-identical in meaning to `application/x-ndjson` per the contract —
  the clients send `application/x-ndjson` and do not expose the choice.
- **The bidirectional shape.** arcadedb#7311 notes OpenAPI 3.0 cannot describe a bidirectional
  stream, and that it may belong to the WebSocket surface. Not this issue's problem.
- **Retry or resume.** Non-atomicity plus duplicate-on-retry means a safe retry needs server-side
  idempotency that does not exist. Documenting the hazard is the whole of the response here.
