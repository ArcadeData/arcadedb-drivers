# Batch Load Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap `POST /api/v1/batch/{database}` in both clients as `batchLoad` / `batchLoadStream` (and Python's `batch_load` / `batch_load_stream`, sync and async), so a caller can bulk-load graph vertices and edges without hand-building an ndjson payload.

**Architecture:** A structured row type per client is serialized to the server's `@`-prefixed ndjson line format by one pure function, so the nested-`properties` corruption of the spec's §3 is unreachable through the public API. The buffered method returns the summary; the streamed method yields progress events and raises on an in-band error, reusing the ndjson decoder M7 already built and debugged. TypeScript rides its existing typed `raw` path; Python hand-writes the request over the generated client's pooled httpx client, because `openapi-python-client` dropped the operation.

**Tech Stack:** TypeScript — `openapi-fetch` (`parseAs: "stream"`), vitest. Python — `httpx` via the generated `Client`'s `get_httpx_client()` / `get_async_httpx_client()`, pytest, mypy strict, ruff.

**Spec:** `docs/superpowers/specs/2026-09-12-batch-load-design.md`

## Global Constraints

- **Generated code is never hand-edited.** Neither `typescript/packages/driver/src/generated/` nor `python/packages/driver/src/arcadedb_driver/_generated/` may be modified. CI's drift gate regenerates and diffs.
- **`EXPECTED_SKIPS` is not touched.** `POST /api/v1/batch/{database}` stays on the allowlist in `python/scripts/check_codegen_skips.py`; the endpoint remains generator-skipped and we wrap it by hand. Never remove or widen an entry to make a check pass.
- **The method is named `batchLoad` / `batch_load`, never `bulkLoad`** (spec D7). `bulkInsert` / `bulk_insert` already exist in the *gRPC* packages for a different operation.
- **Properties are flattened onto the wire line, never nested** (spec §3, D2). Nesting is accepted by the server and silently stores a property literally named `properties`.
- **Vertices are always serialized before edges** (spec D1). The public API takes them as separate arguments so the wrong order cannot be expressed.
- **Python's sync and async twins are hand-maintained and must stay in parity, docstrings included** (issue #30). `unasync` is an explicit non-goal.
- **No client-side validation of what the server owns.** No checking that a `from` temp id was declared, no enforcing server ceilings. The server's errors here are excellent; do not pre-empt them.
- **Load-bearing prose moves with the behaviour.** Both package READMEs document failure modes at length; a behaviour change without its prose is incomplete.
- Test commands: `cd typescript && npm run lint && npm run typecheck && npm test`; `cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.
- Baseline at plan start: TypeScript 143 tests, Python 231 tests.

---

### Task 1: Make the ndjson decoder reusable in both languages

M7 built a correct ndjson decoder in each client, but typed it to `NdJsonQueryEvent` and left it private to the streaming-query module. Batch needs the identical machinery for `NdJsonBatchEvent`. This task makes it generic and moves it to each package's existing internal module, changing no behaviour — M7's own tests are the safety net.

**Files:**
- Create: `typescript/packages/driver/src/internal/ndjson.ts`
- Modify: `typescript/packages/driver/src/facade/stream.ts` (delete `decodeNdJson`, import it instead)
- Create: `python/packages/driver/src/arcadedb_driver/_internal/ndjson.py`
- Modify: `python/packages/driver/src/arcadedb_driver/facade/stream.py` (delete `_iter_ndjson_lines` / `_aiter_ndjson_lines`, import them instead)
- Test: existing `typescript/packages/driver/test/stream.test.ts` and `python/packages/driver/tests/test_stream.py` must pass unchanged.

**Interfaces:**
- Consumes: nothing.
- Produces:
  - TS: `export async function* decodeNdJson<T>(stream: ReadableStream<Uint8Array>): AsyncGenerator<T>`
  - Python: `def iter_ndjson_lines(chunks: Iterator[str]) -> Iterator[str]` and `async def aiter_ndjson_lines(chunks: AsyncIterator[str]) -> AsyncIterator[str]` (note: public names, no leading underscore, since they now cross a module boundary).

- [ ] **Step 1: Move the TypeScript decoder, generic over the event type**

Create `typescript/packages/driver/src/internal/ndjson.ts`. Move `decodeNdJson` from `facade/stream.ts` **verbatim including its entire doc comment** — that comment records two chunk-boundary defects and one cancellation defect, each of which cost real debugging, and it must not be summarized. Change only the signature:

```ts
export async function* decodeNdJson<T>(stream: ReadableStream<Uint8Array>): AsyncGenerator<T> {
```

and the two `yield JSON.parse(line) as NdJsonQueryEvent;` sites to `yield JSON.parse(line) as T;`.

Add one sentence at the top of the moved doc comment saying why it lives here now:

```
 * Generic over the event type because two endpoints stream ndjson with different event
 * shapes - `NdJsonQueryEvent` from query/command, `NdJsonBatchEvent` from batch. The decoding
 * is identical; only the parsed type differs.
```

- [ ] **Step 2: Point `stream.ts` at it**

In `typescript/packages/driver/src/facade/stream.ts`, delete the moved function and add:

```ts
import { decodeNdJson } from "../internal/ndjson.js";
```

The call site becomes `decodeNdJson<NdJsonQueryEvent>(...)`. Leave `raiseOnErrorEvent` where it is — Task 3 writes a batch-specific sibling, because the two error events carry different fields.

- [ ] **Step 3: Verify TypeScript behaviour is unchanged**

Run: `cd typescript && npm test`
Expected: 143 passed. **No test file changes.** If a test needed editing, the move was not behaviour-preserving — revert and redo it.

- [ ] **Step 4: Move the Python line splitters**

Create `python/packages/driver/src/arcadedb_driver/_internal/ndjson.py`. Move `_iter_ndjson_lines` and `_aiter_ndjson_lines` from `facade/stream.py` verbatim, renaming them to `iter_ndjson_lines` and `aiter_ndjson_lines`. Give the module this docstring:

```python
"""Splitting an ndjson byte stream into lines, for every endpoint that streams one.

Split on `"\\n"` and nothing else. `httpx`'s own `iter_lines()` cannot be used: it splits on
`str.splitlines()` semantics, which treats U+0085, U+2028 and U+2029 as line terminators. JSON
permits all three raw inside a string, so a single record containing one is torn into two
fragments, neither of which parses. Verified on httpx 0.28.1.

Lives here rather than in `facade/stream.py` because two endpoints stream ndjson - query/command
and batch - and the splitting is identical for both.
"""
```

- [ ] **Step 5: Point `stream.py` at it**

In `facade/stream.py`, delete both moved functions and import them:

```python
from .._internal.ndjson import aiter_ndjson_lines, iter_ndjson_lines
```

Update the two call sites in `_stream_events` / `_astream_events`. Keep `stream.py`'s module docstring paragraph about `iter_lines()` — it explains the same hazard to a reader of *that* module; add a pointer to `_internal/ndjson.py` rather than deleting it.

- [ ] **Step 6: Verify Python behaviour is unchanged**

Run: `cd python && uv run pytest && uv run mypy`
Expected: 231 passed, mypy clean. **No test file changes**, same rule as Step 3.

- [ ] **Step 7: Commit**

```bash
git add typescript/packages/driver/src python/packages/driver/src
git commit -m "refactor: make the ndjson decoder reusable for a second streaming endpoint"
```

---

### Task 2: Row serialization, both languages

One pure function per language turning structured rows into the server's line format. This is where the spec's §3 corruption trap is closed, so it is the task most worth testing hard. No I/O — every test here is offline and instant.

**Files:**
- Create: `typescript/packages/driver/src/internal/batch-rows.ts`
- Test: `typescript/packages/driver/test/batch-rows.test.ts`
- Create: `python/packages/driver/src/arcadedb_driver/_internal/batch_rows.py`
- Test: `python/packages/driver/tests/test_batch_rows.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - TS: `VertexRow`, `EdgeRow`, and `serializeRows(vertices: Iterable<VertexRow>, edges: Iterable<EdgeRow>): string`
  - Python: `VertexRow`, `EdgeRow` (TypedDicts) and `serialize_rows(vertices: Iterable[VertexRow], edges: Iterable[EdgeRow]) -> str`

Both return the complete ndjson payload as text, newline-terminated per line. Streaming the *request* body incrementally is deliberately out of scope: the server reads the body incrementally either way, and a caller with a payload too large to materialize should be told so rather than have the client pretend. Say this in the doc comment.

- [ ] **Step 1: Write the failing TypeScript tests**

Create `typescript/packages/driver/test/batch-rows.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { serializeRows } from "../src/internal/batch-rows.js";

const lines = (s: string) => s.split("\n").filter((l) => l !== "").map((l) => JSON.parse(l));

describe("serializeRows", () => {
  it("flattens properties beside the control keys, never nested", () => {
    // The whole point of the structured row type. The server ACCEPTS a nested
    // `properties` object and stores a property literally called "properties",
    // answering 200 with correct counters - silent data corruption. See the spec's
    // section 3 and ArcadeData/arcadedb#7570.
    const [row] = lines(serializeRows([{ type: "Person", id: "p1", properties: { name: "Alice" } }], []));
    expect(row).toEqual({ "@type": "vertex", "@class": "Person", "@id": "p1", name: "Alice" });
    expect(row).not.toHaveProperty("properties");
  });

  it("emits every vertex before any edge", () => {
    // Not cosmetic: the server resolves an edge's @from/@to only against temp ids
    // declared EARLIER in the same payload, and answers 400 otherwise - possibly
    // after earlier chunks have already committed.
    const out = lines(
      serializeRows(
        [{ type: "Person", id: "a" }, { type: "Person", id: "b" }],
        [{ type: "Knows", from: "a", to: "b" }],
      ),
    );
    expect(out.map((r) => r["@type"])).toEqual(["vertex", "vertex", "edge"]);
  });

  it("omits @id when a vertex has no id", () => {
    const [row] = lines(serializeRows([{ type: "Person", properties: { name: "Anon" } }], []));
    expect(row).not.toHaveProperty("@id");
    expect(row).toEqual({ "@type": "vertex", "@class": "Person", name: "Anon" });
  });

  it("serializes edge endpoints and properties", () => {
    const [row] = lines(serializeRows([], [{ type: "Knows", from: "a", to: "#1:7", properties: { since: 2020 } }]));
    expect(row).toEqual({ "@type": "edge", "@class": "Knows", "@from": "a", "@to": "#1:7", since: 2020 });
  });

  it("terminates every line with a newline, including the last", () => {
    // A body whose final line has no terminator is a body that ends before its
    // announced length: the server answers 408, never a 200 with a short count.
    const out = serializeRows([{ type: "Person" }], [{ type: "Knows", from: "a", to: "b" }]);
    expect(out.endsWith("\n")).toBe(true);
    expect(out.split("\n").filter((l) => l !== "")).toHaveLength(2);
  });

  it("produces an empty string for no rows", () => {
    expect(serializeRows([], [])).toBe("");
  });

  it("lets a property named like a control key through untouched", () => {
    // Properties live in their own object in our type, so a property called
    // "type" or "from" cannot collide with a control field. This is the second
    // reason for the structured row shape (spec D2).
    const [row] = lines(serializeRows([{ type: "Person", properties: { type: "civilian", from: "Rome" } }], []));
    expect(row).toEqual({ "@type": "vertex", "@class": "Person", type: "civilian", from: "Rome" });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd typescript && npx vitest run test/batch-rows.test.ts`
Expected: FAIL — cannot resolve `../src/internal/batch-rows.js`.

- [ ] **Step 3: Implement the TypeScript serializer**

Create `typescript/packages/driver/src/internal/batch-rows.ts`:

```ts
/**
 * Turning structured rows into ArcadeDB's GraphBatch ndjson line format.
 *
 * The line format is NOT in the OpenAPI contract - all three request media types are declared
 * `{"type": "string"}` with a one-line description. It was established against a live
 * 26.10.1-SNAPSHOT server and reported upstream as ArcadeData/arcadedb#7570:
 *
 *     {"@type":"vertex","@class":"Person","@id":"p1","name":"Alice"}
 *     {"@type":"edge","@class":"Knows","@from":"p1","@to":"p2","since":2020}
 *
 * Two properties of this function are load-bearing rather than stylistic:
 *
 * 1. **Properties are flattened beside the control keys, never nested.** The gRPC sibling
 *    `GraphBatchRecord` has a `properties` map field, so nesting is the natural guess - and the
 *    server ACCEPTS it, answers 200 with correct counters, and stores a property literally named
 *    `properties` holding the map. Nothing fails until someone queries for a field that is not
 *    there. Taking `properties` as its own object in the row type and flattening it here means a
 *    caller cannot produce that payload.
 * 2. **Every vertex is emitted before any edge.** The server resolves an edge's `@from`/`@to`
 *    against temp ids declared earlier in the SAME payload only, and answers 400 otherwise. Since
 *    a batch is not atomic, that 400 can arrive after earlier chunks have durably committed, and
 *    retrying duplicates them. Vertices and edges arrive as separate arguments precisely so the
 *    wrong order cannot be expressed.
 *
 * The whole payload is materialized as one string. The request body is streamed to the server
 * either way, so this costs a caller memory only for the payload they already hold; a caller whose
 * payload does not fit in memory needs a different design, and should be told that rather than be
 * handed a client that pretends otherwise.
 */

/** A vertex to create. `properties` are the record's own fields; `id` is a temporary id an edge in the same call can reference. */
export interface VertexRow {
  /** The vertex type name, e.g. `"Person"`. Sent as `@class`. */
  type: string;
  /** Optional temporary id, referenced by an edge's `from`/`to` in the same call and returned in the summary's `idMapping`. Vertices without one are counted in `verticesWithoutId`. */
  id?: string;
  properties?: Record<string, unknown>;
}

/** An edge to create, referencing vertices by temporary id or by RID. */
export interface EdgeRow {
  /** The edge type name, e.g. `"Knows"`. Sent as `@class`. */
  type: string;
  /** Source: a temp id declared by a vertex in this same call, or a literal `#bucket:position` RID. */
  from: string;
  /** Target: same rules as `from`. */
  to: string;
  properties?: Record<string, unknown>;
}

function line(control: Record<string, string>, properties: Record<string, unknown> | undefined): string {
  return `${JSON.stringify({ ...control, ...properties })}\n`;
}

export function serializeRows(vertices: Iterable<VertexRow>, edges: Iterable<EdgeRow>): string {
  let out = "";
  for (const v of vertices) {
    const control: Record<string, string> = { "@type": "vertex", "@class": v.type };
    if (v.id !== undefined) control["@id"] = v.id;
    out += line(control, v.properties);
  }
  for (const e of edges) {
    out += line({ "@type": "edge", "@class": e.type, "@from": e.from, "@to": e.to }, e.properties);
  }
  return out;
}
```

- [ ] **Step 4: Run the TypeScript tests to verify they pass**

Run: `cd typescript && npx vitest run test/batch-rows.test.ts`
Expected: 7 passed.

- [ ] **Step 5: Write the failing Python tests**

Create `python/packages/driver/tests/test_batch_rows.py`:

```python
from __future__ import annotations

import json

from arcadedb_driver._internal.batch_rows import serialize_rows


def _lines(payload: str) -> list[dict]:
    return [json.loads(line) for line in payload.split("\n") if line]


def test_properties_are_flattened_never_nested() -> None:
    # The whole point of the structured row type. The server ACCEPTS a nested
    # `properties` object and stores a property literally called "properties",
    # answering 200 with correct counters - silent data corruption. See the spec's
    # section 3 and ArcadeData/arcadedb#7570.
    (row,) = _lines(serialize_rows([{"type": "Person", "id": "p1", "properties": {"name": "Alice"}}], []))
    assert row == {"@type": "vertex", "@class": "Person", "@id": "p1", "name": "Alice"}
    assert "properties" not in row


def test_every_vertex_precedes_every_edge() -> None:
    # Not cosmetic: the server resolves an edge's @from/@to only against temp ids
    # declared EARLIER in the same payload, and answers 400 otherwise - possibly
    # after earlier chunks have already committed.
    rows = _lines(
        serialize_rows(
            [{"type": "Person", "id": "a"}, {"type": "Person", "id": "b"}],
            [{"type": "Knows", "from_": "a", "to": "b"}],
        )
    )
    assert [row["@type"] for row in rows] == ["vertex", "vertex", "edge"]


def test_id_is_omitted_when_absent() -> None:
    (row,) = _lines(serialize_rows([{"type": "Person", "properties": {"name": "Anon"}}], []))
    assert row == {"@type": "vertex", "@class": "Person", "name": "Anon"}


def test_edge_endpoints_and_properties() -> None:
    (row,) = _lines(serialize_rows([], [{"type": "Knows", "from_": "a", "to": "#1:7", "properties": {"since": 2020}}]))
    assert row == {"@type": "edge", "@class": "Knows", "@from": "a", "@to": "#1:7", "since": 2020}


def test_every_line_is_newline_terminated() -> None:
    # A body whose final line has no terminator is a body that ends before its
    # announced length: the server answers 408, never a 200 with a short count.
    payload = serialize_rows([{"type": "Person"}], [{"type": "Knows", "from_": "a", "to": "b"}])
    assert payload.endswith("\n")
    assert len([line for line in payload.split("\n") if line]) == 2


def test_no_rows_is_the_empty_payload() -> None:
    assert serialize_rows([], []) == ""


def test_a_property_named_like_a_control_key_passes_through() -> None:
    # Properties live in their own dict in our type, so a property called "type"
    # or "from" cannot collide with a control field (spec D2).
    (row,) = _lines(serialize_rows([{"type": "Person", "properties": {"type": "civilian", "from": "Rome"}}], []))
    assert row == {"@type": "vertex", "@class": "Person", "type": "civilian", "from": "Rome"}
```

- [ ] **Step 6: Run the Python tests to verify they fail**

Run: `cd python && uv run pytest packages/driver/tests/test_batch_rows.py -v`
Expected: FAIL — `ModuleNotFoundError: arcadedb_driver._internal.batch_rows`.

- [ ] **Step 7: Implement the Python serializer**

Create `python/packages/driver/src/arcadedb_driver/_internal/batch_rows.py`. Carry the **same** reasoning in the module docstring as the TypeScript twin — both readers need it, and the two files are siblings, not translations:

```python
"""Turning structured rows into ArcadeDB's GraphBatch ndjson line format.

The line format is NOT in the OpenAPI contract - all three request media types are declared
`{"type": "string"}` with a one-line description. It was established against a live
26.10.1-SNAPSHOT server and reported upstream as ArcadeData/arcadedb#7570::

    {"@type":"vertex","@class":"Person","@id":"p1","name":"Alice"}
    {"@type":"edge","@class":"Knows","@from":"p1","@to":"p2","since":2020}

Two properties of `serialize_rows` are load-bearing rather than stylistic:

1. **Properties are flattened beside the control keys, never nested.** The gRPC sibling
   `GraphBatchRecord` has a `properties` map field, so nesting is the natural guess - and the
   server ACCEPTS it, answers 200 with correct counters, and stores a property literally named
   `properties` holding the map. Nothing fails until someone queries for a field that is not
   there. Taking `properties` as its own dict in the row type and flattening it here means a
   caller cannot produce that payload.
2. **Every vertex is emitted before any edge.** The server resolves an edge's `@from`/`@to`
   against temp ids declared earlier in the SAME payload only, and answers 400 otherwise. Since
   a batch is not atomic, that 400 can arrive after earlier chunks have durably committed, and
   retrying duplicates them. Vertices and edges arrive as separate arguments precisely so the
   wrong order cannot be expressed.

The whole payload is materialized as one string. The request body is streamed to the server
either way, so this costs a caller memory only for the payload they already hold; a caller whose
payload does not fit in memory needs a different design, and should be told that rather than be
handed a client that pretends otherwise.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, NotRequired, TypedDict


class VertexRow(TypedDict):
    """A vertex to create."""

    type: str
    """The vertex type name, e.g. `"Person"`. Sent as `@class`."""
    id: NotRequired[str]
    """Optional temporary id, referenced by an edge's `from`/`to` in the same call and returned
    in the summary's `idMapping`. Vertices without one are counted in `verticesWithoutId`."""
    properties: NotRequired[dict[str, Any]]


class EdgeRow(TypedDict):
    """An edge to create, referencing vertices by temporary id or by RID."""

    type: str
    """The edge type name, e.g. `"Knows"`. Sent as `@class`."""
    from_: str
    """Source: a temp id declared by a vertex in this same call, or a literal
    `#bucket:position` RID. Spelled with a trailing underscore because `from` is a Python
    keyword; the wire name is `@from`."""
    to: str
    """Target: same rules as `from_`."""
    properties: NotRequired[dict[str, Any]]


def _line(control: dict[str, str], properties: dict[str, Any] | None) -> str:
    return json.dumps({**control, **(properties or {})}) + "\n"


def serialize_rows(vertices: Iterable[VertexRow], edges: Iterable[EdgeRow]) -> str:
    """Serializes rows to the ndjson payload - vertices first, properties flattened."""
    out = []
    for vertex in vertices:
        control = {"@type": "vertex", "@class": vertex["type"]}
        if "id" in vertex:
            control["@id"] = vertex["id"]
        out.append(_line(control, vertex.get("properties")))
    for edge in edges:
        control = {"@type": "edge", "@class": edge["type"], "@from": edge["from_"], "@to": edge["to"]}
        out.append(_line(control, edge.get("properties")))
    return "".join(out)
```

**Note the `from_` spelling**, already used by Step 5's tests. `from` is a Python keyword and cannot be a TypedDict key in class syntax, so the Python row type spells it `from_` while TypeScript spells it `from`. This is the same asymmetry `ArcadeDBError.help_` already carries for the same reason — say so in the docstring and point at `errors.py`, so the next reader meets one explanation rather than two coincidences.

- [ ] **Step 8: Run the Python tests to verify they pass**

Run: `cd python && uv run pytest packages/driver/tests/test_batch_rows.py -v && uv run mypy`
Expected: 7 passed, mypy clean.

- [ ] **Step 9: Commit**

```bash
git add typescript/packages/driver/src/internal/batch-rows.ts typescript/packages/driver/test/batch-rows.test.ts \
        python/packages/driver/src/arcadedb_driver/_internal/batch_rows.py python/packages/driver/tests/test_batch_rows.py
git commit -m "feat: serialize batch rows to the GraphBatch ndjson line format"
```

---

### Task 3: TypeScript `batchLoad` and `batchLoadStream`

**Files:**
- Create: `typescript/packages/driver/src/facade/batch.ts`
- Modify: `typescript/packages/driver/src/index.ts` (add both methods to `ArcadeDBDatabase`)
- Test: `typescript/packages/driver/test/batch.test.ts`

**Interfaces:**
- Consumes: `serializeRows`, `VertexRow`, `EdgeRow` from `../internal/batch-rows.js`; `decodeNdJson<T>` from `../internal/ndjson.js`.
- Produces: `BatchOptions`, `BatchSummary`, `NdJsonBatchEvent`, `batchLoad(client, database, args)`, `batchLoadStream(client, database, args)`; and on `ArcadeDBDatabase`, `batchLoad(args)` and `batchLoadStream(args)`.

- [ ] **Step 1: Write the failing tests**

Create `typescript/packages/driver/test/batch.test.ts`. The helpers below are lifted from the existing `test/stream.test.ts` — read that file first and reuse its style rather than inventing a second mocking idiom.

```ts
import { describe, expect, it, vi } from "vitest";
import { ArcadeDBError, createClient } from "../src/index.js";
import type { NdJsonBatchEvent } from "../src/index.js";

function ndjsonResponse(lines: string[], status = 200): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(new TextEncoder().encode(line + "\n"));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "content-type": "application/x-ndjson" } });
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

async function collect(iter: AsyncGenerator<NdJsonBatchEvent>): Promise<NdJsonBatchEvent[]> {
  const events: NdJsonBatchEvent[] = [];
  for await (const event of iter) events.push(event);
  return events;
}

const ROWS = {
  vertices: [{ type: "Person", id: "a", properties: { name: "Ann" } }],
  edges: [{ type: "Knows", from: "a", to: "#1:7" }],
};

describe("ArcadeDBDatabase.batchLoad", () => {
  it("POSTs the serialized ndjson payload to /api/v1/batch/{database}", async () => {
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse({ verticesCreated: 1, edgesCreated: 1 }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").batchLoad(ROWS);

    expect(captured?.method).toBe("POST");
    expect(new URL(captured!.url).pathname).toBe("/api/v1/batch/mydb");
    expect(captured?.headers.get("content-type")).toBe("application/x-ndjson");
    const body = await captured!.clone().text();
    expect(body.split("\n").filter((l) => l !== "").map((l) => JSON.parse(l))).toEqual([
      { "@type": "vertex", "@class": "Person", "@id": "a", name: "Ann" },
      { "@type": "edge", "@class": "Knows", "@from": "a", "@to": "#1:7" },
    ]);
  });

  it("passes tuning options through as query parameters, spelled as the contract spells them", async () => {
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse({}, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").batchLoad({ ...ROWS, options: { commitEvery: 5000, lightEdges: true } });

    const url = new URL(captured!.url);
    expect(url.searchParams.get("commitEvery")).toBe("5000");
    expect(url.searchParams.get("lightEdges")).toBe("true");
  });

  it("omits a query parameter entirely when its option is absent", async () => {
    // Not "sends an empty value": an absent option must leave the parameter off the
    // URL, so the server applies its own default rather than parsing "".
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse({}, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").batchLoad({ ...ROWS, options: { commitEvery: 10 } });

    const url = new URL(captured!.url);
    expect(url.searchParams.has("commitEvery")).toBe(true);
    expect(url.searchParams.has("batchSize")).toBe(false);
    expect(url.searchParams.has("wal")).toBe(false);
  });

  it("throws ArcadeDBError when the server refuses the load", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ error: "Missing @class at line 1", verticesCreated: 0, partialCommit: false }, 400),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(server.db("mydb").batchLoad(ROWS)).rejects.toBeInstanceOf(ArcadeDBError);
  });
});

describe("ArcadeDBDatabase.batchLoadStream", () => {
  it("sends Accept: application/x-ndjson", async () => {
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return ndjsonResponse([JSON.stringify({ summary: { verticesCreated: 1 } })]);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await collect(server.db("mydb").batchLoadStream(ROWS));

    expect(captured?.headers.get("accept")).toBe("application/x-ndjson");
  });

  it("yields every progress event, then the summary", async () => {
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ progress: { phase: "vertices", verticesCreated: 1, idMapping: { a: "#1:0" } } }),
        JSON.stringify({ progress: { phase: "edges", edgesCreated: 1 } }),
        JSON.stringify({ summary: { verticesCreated: 1, edgesCreated: 1, idMappingStreamed: true, idMappingSize: 1 } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").batchLoadStream(ROWS));

    expect(events).toHaveLength(3);
    expect(events[0]?.progress?.phase).toBe("vertices");
    expect(events[2]?.summary).toBeDefined();
  });

  it("passes idMapping fragments through without merging them (D5)", async () => {
    // The facade must NOT accumulate. The server streams the mapping precisely so a
    // million-vertex load never has to hold a million entries client-side; merging
    // here would reintroduce exactly the cost streaming exists to avoid.
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ progress: { idMapping: { a: "#1:0" } } }),
        JSON.stringify({ progress: { idMapping: { b: "#1:1" } } }),
        JSON.stringify({ summary: { idMappingStreamed: true, idMappingSize: 2 } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").batchLoadStream(ROWS));

    expect(events[0]?.progress?.idMapping).toEqual({ a: "#1:0" });
    expect(events[1]?.progress?.idMapping).toEqual({ b: "#1:1" });
    expect(events[2]?.summary).not.toHaveProperty("idMapping");
  });

  it("throws ArcadeDBError when the load fails BEFORE the stream starts (D6, channel one)", async () => {
    // The status line has not been sent yet, so the server can still answer with a
    // real HTTP status and the buffered error body.
    const fetchMock = vi.fn(async () => jsonResponse({ error: "Missing @class at line 1" }, 400));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(collect(server.db("mydb").batchLoadStream(ROWS))).rejects.toBeInstanceOf(ArcadeDBError);
  });

  it("throws ArcadeDBError carrying the in-band status when the terminal line is an error (D6, channel two)", async () => {
    // Once the stream has started the 200 status line cannot be taken back, so the
    // failure travels in band. It must fail the caller the SAME way channel one does.
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ progress: { verticesCreated: 1 } }),
        JSON.stringify({ error: { error: "boom", status: 400, partialCommit: true } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(collect(server.db("mydb").batchLoadStream(ROWS))).rejects.toMatchObject({ status: 400 });
  });

  it("yields the events that arrived before an in-band error, then throws", async () => {
    // The throw must not swallow work the caller was already told about: a partial
    // commit is durable, and those progress counts are how a caller learns what
    // may have landed.
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ progress: { verticesCreated: 2 } }),
        JSON.stringify({ error: { error: "boom", status: 500 } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const seen: NdJsonBatchEvent[] = [];
    await expect(
      (async () => {
        for await (const event of server.db("mydb").batchLoadStream(ROWS)) seen.push(event);
      })(),
    ).rejects.toBeInstanceOf(ArcadeDBError);
    expect(seen).toHaveLength(1);
    expect(seen[0]?.progress?.verticesCreated).toBe(2);
  });

  it("records that status is an unclassified fallback when statusMapped is false (D6)", async () => {
    // The contract says: key on `exception` here, not on `status`, because 500 is
    // the fallback rather than the status the buffered encoding would have chosen.
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ error: { error: "engine failure", status: 500, statusMapped: false, exception: "java.lang.IllegalStateException" } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(collect(server.db("mydb").batchLoadStream(ROWS))).rejects.toMatchObject({
      status: 500,
      exception: "java.lang.IllegalStateException",
    });
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd typescript && npx vitest run test/batch.test.ts`
Expected: FAIL — cannot resolve `../src/facade/batch.js`.

- [ ] **Step 3: Implement `facade/batch.ts`**

```ts
import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { ArcadeDBError } from "../errors.js";
import { decodeNdJson } from "../internal/ndjson.js";
import { type EdgeRow, serializeRows, type VertexRow } from "../internal/batch-rows.js";

type RawClient = Client<paths>;

export type NdJsonBatchEvent = components["schemas"]["NdJsonBatchEvent"];

/**
 * The buffered summary.
 *
 * CORRECTED DURING EXECUTION - this plan originally widened the type here with
 * `& { idMappingStreamed?: boolean }`, on the claim that `idMappingStreamed` was "a field in no
 * schema". That claim was FALSE, and the widening was in the wrong place. `NdJsonBatchEvent.summary`
 * declares `idMappingStreamed` (with `commitIndex` and `idMappingSize`), and that is the type the
 * STREAMING path returns. `BatchResponse` is the BUFFERED response, which never sends the field at
 * all - it sends `idMapping`. So there was nothing here to widen.
 *
 * `BatchErrorEvent` below is a different matter and its widening is real: `NdJsonBatchEvent.error`
 * genuinely omits `error` and `exception`, which the server does send, and the contract's own
 * `statusMapped` text tells a caller to key on `exception`. See ArcadeData/arcadedb#7570.
 */
export type BatchSummary = components["schemas"]["BatchResponse"];

/** The 17 tuning parameters, named exactly as the contract names them. */
export interface BatchOptions {
  batchSize?: number;
  lightEdges?: boolean;
  wal?: boolean;
  parallelFlush?: boolean;
  preAllocateEdgeChunks?: boolean;
  edgeListInitialSize?: number;
  bidirectional?: boolean;
  commitEvery?: number;
  expectedEdgeCount?: number;
  commitRetries?: number;
  commitRetryDelayMs?: number;
  vertexBatchSize?: number;
  expectedVertexCount?: number;
  expectedRecords?: number;
  ordinalBase?: number;
  idMapping?: string;
  refMode?: string;
}

export interface BatchLoadArgs {
  vertices?: Iterable<VertexRow>;
  edges?: Iterable<EdgeRow>;
  options?: BatchOptions;
}

const PATH = "/api/v1/batch/{database}" as const;

function requestInit(args: BatchLoadArgs, database: string, accept?: string) {
  return {
    params: { path: { database }, query: (args.options ?? {}) as Record<string, never> },
    body: serializeRows(args.vertices ?? [], args.edges ?? []) as unknown as never,
    headers: { "Content-Type": "application/x-ndjson", ...(accept ? { Accept: accept } : {}) },
  };
}

export async function batchLoad(client: RawClient, database: string, args: BatchLoadArgs): Promise<BatchSummary> {
  const { data, error, response } = await client.POST(PATH, requestInit(args, database));
  if (!response.ok) throw ArcadeDBError.fromResponse(response, error);
  return data as BatchSummary;
}

/**
 * D6: the two error channels collapse into one throw.
 *
 * A load that fails BEFORE the first acknowledgement answers with a real HTTP status and the
 * buffered error body, because the status line has not been sent yet. A load that fails AFTER
 * the first progress line cannot do that - the status line is already on the wire and cannot be
 * taken back - so the failure arrives in band, under a 200, carrying the status the buffered
 * encoding would have used. Both raise `ArcadeDBError` here, so a caller's `for await` fails
 * identically whichever channel the failure used; when the failure happened is the only
 * difference between them, and it is not something a caller can act on.
 *
 * `statusMapped: false` means `status` is an unclassified 500 fallback rather than the status the
 * buffered encoding would have chosen - the contract says to key on `exception` there, so the
 * thrown error carries it.
 */
async function* raiseOnErrorEvent(events: AsyncGenerator<NdJsonBatchEvent>): AsyncGenerator<NdJsonBatchEvent> {
  for await (const event of events) {
    if (event.error !== undefined) {
      const { status, statusMapped, error: message, exception } = event.error;
      throw new ArcadeDBError(status ?? 500, {
        error: message ?? "the batch load reported an error",
        exception,
        detail: statusMapped === false ? "status is an unclassified fallback; key on exception" : undefined,
      });
    }
    yield event;
  }
}

export async function* batchLoadStream(
  client: RawClient,
  database: string,
  args: BatchLoadArgs,
): AsyncGenerator<NdJsonBatchEvent> {
  const { error, data, response } = await client.POST(PATH, {
    ...requestInit(args, database, "application/x-ndjson"),
    parseAs: "stream",
  });
  if (!response.ok) throw ArcadeDBError.fromResponse(response, error);
  if (data == null) return;
  yield* raiseOnErrorEvent(decodeNdJson<NdJsonBatchEvent>(data as ReadableStream<Uint8Array>));
}
```

Check `ArcadeDBError`'s constructor signature in `src/errors.ts` before writing the `throw` — match its actual shape rather than the sketch above, and adjust if `exception`/`detail` are not fields it takes.

- [ ] **Step 4: Wire both methods onto `ArcadeDBDatabase`**

In `typescript/packages/driver/src/index.ts`, add two methods beside the existing `queryStream`/`commandStream`, matching their delegation style exactly. Each gets a doc comment; `batchLoad`'s must state the non-atomicity and duplicate-on-retry hazard, because that is the one a caller meets without warning.

- [ ] **Step 5: Run the full TypeScript gate**

Run: `cd typescript && npm run lint && npm run typecheck && npm test`
Expected: all green, 143 + the new tests.

- [ ] **Step 6: Commit**

```bash
git add typescript/packages/driver/src typescript/packages/driver/test/batch.test.ts
git commit -m "feat(driver): batchLoad and batchLoadStream over /batch"
```

---

### Task 4: Python `batch_load` and `batch_load_stream`, sync and async

The generator dropped this operation entirely, so both twins are hand-written over the pooled httpx client — the same shape as `facade/timeseries.py`'s `write`. Read that method first; it is the model.

**Files:**
- Create: `python/packages/driver/src/arcadedb_driver/facade/batch.py`
- Modify: `python/packages/driver/src/arcadedb_driver/__init__.py` (sync `ArcadeDBDatabase`)
- Modify: `python/packages/driver/src/arcadedb_driver/aio.py` (async `AsyncArcadeDBDatabase`)
- Test: `python/packages/driver/tests/test_batch.py`

**Interfaces:**
- Consumes: `serialize_rows`, `VertexRow`, `EdgeRow` from `.._internal.batch_rows`; `iter_ndjson_lines`, `aiter_ndjson_lines` from `.._internal.ndjson`; `_raise_for_status` / `_araise_for_status` — move these two from `facade/stream.py` into `_internal/ndjson.py` as `raise_for_status` / `araise_for_status` in this task's Step 1, since a second module now needs them.
- Produces: `batch_load`, `batch_load_stream`, `abatch_load`, `abatch_load_stream`; and on the database classes, `batch_load(...)` / `batch_load_stream(...)` (sync) and their `Async` twins.

- [ ] **Step 1: Move the status helpers alongside the line splitters**

`facade/stream.py`'s `_raise_for_status` and `_araise_for_status` are needed by `batch.py` too. Move both into `_internal/ndjson.py` (created in Task 1), renaming to `raise_for_status` / `araise_for_status`, and import them back into `stream.py`. Run `uv run pytest` — 231 + Task 2's 7 must still pass with no test edits.

- [ ] **Step 2: Write the failing tests**

Create `python/packages/driver/tests/test_batch.py`, matching `tests/test_stream.py`'s existing httpx-mocking style — **read that file first and reuse its transport-stubbing helper** rather than inventing a second one.

Write each of these, for the sync twin and again for the async twin:

```python
def test_batch_load_posts_the_serialized_payload() -> None:
    """POSTs to /api/v1/batch/{database} with Content-Type: application/x-ndjson and a body
    whose lines are the serialized vertices followed by the serialized edges."""


def test_batch_load_passes_options_as_query_parameters() -> None:
    """{"commitEvery": 5000, "lightEdges": True} becomes ?commitEvery=5000&lightEdges=true,
    spelled exactly as the contract spells them."""


def test_an_absent_option_sends_no_parameter_at_all() -> None:
    """Not an empty value - the parameter must be absent from the URL entirely, so the server
    applies its own default rather than parsing ""."""


def test_batch_load_raises_arcadedb_error_on_a_refused_load() -> None:
    """A 400 with the partial-commit body raises, like every other facade method."""


def test_batch_load_stream_sends_accept_ndjson() -> None:
    """The streamed variant is selected by Accept, and only by Accept."""


def test_batch_load_stream_yields_progress_then_summary() -> None:
    """Every progress event in order, then exactly one summary."""


def test_batch_load_stream_does_not_merge_id_mapping_fragments() -> None:
    """D5: each progress event keeps its own idMapping fragment and the summary keeps
    idMappingStreamed. The facade must NOT accumulate - the server streams the mapping
    precisely so a million-vertex load never holds a million entries client-side."""


def test_a_failure_before_the_stream_starts_raises(  ) -> None:
    """D6 channel one: the status line has not been sent, so the server answers with a real
    HTTP status and the buffered error body."""


def test_an_in_band_error_event_raises_with_its_own_status() -> None:
    """D6 channel two: once the 200 is on the wire it cannot be taken back, so the failure
    arrives in band carrying the status the buffered encoding would have used. It must fail
    the caller the same way channel one does."""


def test_events_before_an_in_band_error_are_yielded_first() -> None:
    """The throw must not swallow work the caller was already told about: a partial commit is
    durable, and those progress counts are how a caller learns what may have landed."""


def test_status_mapped_false_is_recorded_on_the_error() -> None:
    """The contract says to key on `exception` when statusMapped is false, because 500 is an
    unclassified fallback rather than the status the buffered encoding would have chosen."""
```

Plus one the sync/async split makes possible, and which review has repeatedly failed to catch by eye:

```python
def test_sync_and_async_docstrings_match() -> None:
    # Issue #30: the twins are hand-maintained and drift silently. Compare each pair's
    # __doc__ directly instead of trusting a reviewer to diff two files by eye.
    import inspect

    from arcadedb_driver.facade import batch

    for sync_name, async_name in [("batch_load", "abatch_load"), ("batch_load_stream", "abatch_load_stream")]:
        sync_doc = inspect.getdoc(getattr(batch, sync_name)) or ""
        async_doc = inspect.getdoc(getattr(batch, async_name)) or ""
        assert sync_doc == async_doc, f"{sync_name} and {async_name} docstrings have drifted"
```

If the async docstring genuinely needs a sentence the sync one does not, this test is what forces that difference to be deliberate: state the exception in the test rather than deleting it.

- [ ] **Step 3: Run to verify they fail**

Run: `cd python && uv run pytest packages/driver/tests/test_batch.py -v`
Expected: FAIL — `ModuleNotFoundError: arcadedb_driver.facade.batch`.

- [ ] **Step 4: Implement `facade/batch.py`**

Write the four functions. The sync pair:

```python
def batch_load(client: Client, database: str, *, vertices=..., edges=..., options=None) -> dict[str, Any]:
    raw = client.get_httpx_client().post(
        _batch_url(database),
        content=serialize_rows(vertices or [], edges or []).encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson"},
        params=_params(options),
    )
    raise_for_status(raw)
    body: dict[str, Any] = raw.json()
    return body


def batch_load_stream(client: Client, database: str, *, vertices=..., edges=..., options=None):
    with client.get_httpx_client().stream(
        "POST",
        _batch_url(database),
        content=serialize_rows(vertices or [], edges or []).encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson", "Accept": "application/x-ndjson"},
        params=_params(options),
    ) as response:
        raise_for_status(response)
        for line in iter_ndjson_lines(response.iter_text()):
            if not line.strip():
                continue
            yield _raise_on_error_event(json.loads(line))
```

with `_batch_url` following `timeseries.py`'s `quote(database, safe="")` spelling, `_params` dropping every `None` option (an omitted option must send no parameter at all, not an empty one), and `_raise_on_error_event` implementing D6 exactly as Task 3's TypeScript twin does — carry the same doc comment reasoning, in this module's voice.

Then the async twins, `abatch_load` / `abatch_load_stream`, using `get_async_httpx_client()`, `araise_for_status` and `aiter_ndjson_lines`. **Docstrings must match their sync twins word for word** apart from the async spelling — Step 2's test enforces this.

Type the options as a `TypedDict` with all 17 keys, `NotRequired` on each, named exactly as the contract names them.

- [ ] **Step 5: Wire the methods onto both database classes**

`__init__.py` gets `batch_load` and `batch_load_stream`; `aio.py` gets the async twins. Match how `query_stream` / `command_stream` are already delegated in each file. Each method's docstring states the non-atomicity and duplicate-on-retry hazard.

- [ ] **Step 6: Run the full Python gate**

Run: `cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
Expected: all green.

- [ ] **Step 7: Verify the skip allowlist is untouched**

Run: `cd python && uv run python scripts/check_codegen_skips.py`
Expected: "OK: the generator skipped exactly the 4 allowlisted operations." `/batch` stays skipped — we wrapped it by hand, we did not make the generator emit it.

- [ ] **Step 8: Commit**

```bash
git add python/packages/driver/src python/packages/driver/tests/test_batch.py
git commit -m "feat(driver): batch_load and batch_load_stream, sync and async"
```

---

### Task 5: End-to-end against a real container

Everything so far is mocked. This proves the line format against the server that defined it — and it is the only test that would catch the §3 corruption if a later refactor reintroduced nesting.

**Files:**
- Modify: `typescript/e2e/` (add a batch spec, following the existing files' container fixture)
- Modify: `python/e2e/` (add `test_batch.py`; reuse `conftest.py`'s `database` fixture)

- [ ] **Step 1: Write the TypeScript e2e**

Create vertex and edge types over HTTP first (there is no DDL in the batch endpoint), then:

```ts
it("loads vertices and edges and resolves temp ids to RIDs", async () => {
  const summary = await db.batchLoad({
    vertices: [{ type: "Person", id: "a", properties: { name: "Ann" } },
               { type: "Person", id: "b", properties: { name: "Ben" } }],
    edges: [{ type: "Knows", from: "a", to: "b", properties: { since: 2020 } }],
  });
  expect(summary.verticesCreated).toBe(2);
  expect(summary.edgesCreated).toBe(1);
  expect(Object.keys(summary.idMapping ?? {})).toEqual(expect.arrayContaining(["a", "b"]));
});

it("stores properties as real fields, not nested under 'properties'", async () => {
  // The regression guard for the corruption of the spec's section 3. If a refactor
  // ever nests properties again, the load still returns 200 and correct counters -
  // only this query notices.
  await db.batchLoad({ vertices: [{ type: "Person", id: "c", properties: { name: "Cat" } }] });
  const rows = await db.query({ language: "sql", command: "SELECT FROM Person WHERE name = 'Cat'" });
  expect(rows.result).toHaveLength(1);
});

it("streams progress before exactly one summary", async () => { /* commitEvery: 1 */ });
```

- [ ] **Step 2: Run it**

Run: `cd typescript && npm run e2e`
Expected: all green, including the three new cases.

- [ ] **Step 3: Write the Python e2e twin**

Create `python/e2e/test_batch.py` with the same three cases, sync and async, using `conftest.py`'s existing `database` fixture. Written out so the file stands alone:

```python
def test_batch_load_creates_vertices_and_edges(database: str, server) -> None:
    """Loads two vertices and one edge, asserting the counters and that every declared temp id
    resolved to a real RID in the returned idMapping."""


def test_properties_are_stored_as_real_fields(database: str, server) -> None:
    """The regression guard for the corruption of the spec's section 3. If a refactor ever nests
    properties again, the load still answers 200 with correct counters - only a query for the
    property by name notices. This is the ONLY test in the suite that would."""


def test_batch_load_stream_reports_progress_before_its_summary(database: str, server) -> None:
    """With commitEvery=1, at least one progress event arrives before exactly one summary."""
```

The DDL (`CREATE VERTEX TYPE Person`, `CREATE PROPERTY Person.name STRING`, `CREATE EDGE TYPE Knows`) goes over HTTP in a fixture — the batch endpoint has no DDL of its own, the same reason `conftest.py`'s `grpc_timeseries_type` fixture creates its type over HTTP.

- [ ] **Step 4: Run it**

Run: `cd python && uv run pytest e2e -v -k batch`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add typescript/e2e python/e2e
git commit -m "test(e2e): batch load against a real container, including the nesting regression guard"
```

---

### Task 6: The prose

**Files:**
- Modify: `typescript/packages/driver/README.md`
- Modify: `python/packages/driver/README.md`
- Modify: `typescript/CLAUDE.md`, `python/CLAUDE.md` (one line each)

- [ ] **Step 1: Write the README sections**

Each README gets a batch-load section, in its own voice, stating:

1. What `batchLoad` / `batch_load` does and the two-argument shape, with **why** vertices and edges are separate: the ordering rule is a server constraint, and separate arguments make the violation unrepresentable rather than merely documented.
2. **A batch is not atomic.** It commits every `commitEvery` records; a mid-stream failure leaves earlier chunks durably committed. Because temp ids are not keys, **retrying the whole payload duplicates the vertices that already committed.** The partial-commit counters on a 400 are an upper bound on what is durable, not an exact count. This is the single most important paragraph in the section.
3. **Temp ids are request-scoped.** A vertex loaded by an earlier call must be referenced by its RID.
4. **`bytesRead` verifies a chunked upload arrived whole.** A short body answers 408, never a 200 with a truncated count.
5. The streaming method, and D5: progress events carry `idMapping` fragments and the summary carries `idMappingStreamed` instead of the map, so a caller wanting the whole mapping accumulates it or uses the buffered method. Say why — holding a million-entry map is the cost streaming exists to avoid.
6. D6: both error channels raise the same way, and what `statusMapped: false` means.
7. D7: this is `batchLoad`, and the gRPC package's `bulkInsert` is a **different** operation; the gRPC counterpart of this one is `GraphBatchLoad`. One sentence, in both READMEs — the near-miss is exactly what a reader resolves wrongly by guessing.
8. That `text/csv` is not exposed and why (spec §8).

- [ ] **Step 2: Add the CLAUDE.md lines**

One line in each workspace file noting that `/batch` is wrapped by hand — generator-skipped in Python, typed-but-unwrapped in TypeScript before this — and that `_internal/batch_rows` owns the undocumented line format.

- [ ] **Step 3: Full gate, both languages**

```bash
cd typescript && npm run lint && npm run typecheck && npm test; cd ..
cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run python scripts/check_codegen_skips.py; cd ..
git status --short
```

Expected: all green; the only untracked entry is `.idea/`, which is never staged.

- [ ] **Step 4: Confirm the drift gate is untouched**

```bash
cd typescript && npm run generate; cd ..
cd python && ./scripts/generate.sh && ./scripts/generate-grpc.sh; cd ..
git status --short
```

Expected: no diff. This plan changes no contract.

- [ ] **Step 5: Commit**

```bash
git add typescript/packages/driver/README.md python/packages/driver/README.md typescript/CLAUDE.md python/CLAUDE.md
git commit -m "docs: batch load, its non-atomicity, and why it is not called bulkLoad"
```
