# M5: Vector Search Across All Four Clients — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ArcadeDB's three vector-search endpoints reachable ergonomically from all four driver packages.

**Architecture:** On HTTP, a `vector` facade namespace on `ArcadeDBDatabase` mirroring the existing `ts` namespace, built on the generated operations (all three endpoints are JSON in, JSON out, so neither generator skips them). On gRPC, three methods on the transaction handles only — the raw stub already exposes the unary RPCs directly, so the sole thing worth hand-writing is the `_bind` path that forces the handle's own `database` and `transaction` onto the request.

**Tech Stack:** `openapi-typescript` + `openapi-fetch`, `openapi-python-client` + `httpx`, `@connectrpc/connect`, `grpc_tools.protoc`, vitest, pytest, mypy, ruff, eslint.

**Spec:** `docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md` (§4, M5)

**Issue:** ArcadeData/arcadedb-drivers#37. Upstream: ArcadeData/arcadedb#7306 (vector half).

## Global Constraints

- Generated code is **never** hand-edited: `typescript/packages/driver/src/generated/`, `typescript/packages/driver-grpc/src/gen/`, `python/packages/*/src/*/_generated/`.
- Do not touch `contracts/`. This milestone changes no contract; the drift gate must stay green with no regeneration.
- Python's `EXPECTED_SKIPS` in `python/scripts/check_codegen_skips.py` must remain the same four entries. None of the three vector endpoints may appear there — they are JSON-bodied and must generate.
- TypeScript: Node >= 20, ESM-only. Python: floor 3.10, run from `python/` via `uv run`.
- Python's sync and async facades are maintained by hand in parallel (`unasync` is an explicit non-goal — see `python/CLAUDE.md`). Every new sync method needs its `Async` twin.
- Endpoint paths, verbatim: `POST /api/v1/vector/{database}/search`, `POST /api/v1/vector/{database}/hybrid`, `POST /api/v1/vector/{database}/fulltext`.
- Generated Python operation modules, verbatim: `_generated.api.vector.vector_search`, `.hybrid_search`, `.full_text_search`.
- gRPC RPC names, verbatim: `VectorSearch`, `HybridSearch`, `FullTextSearch`.
- Branch: `feat/m5-vector-search`, off `main`.

## Two decisions this plan makes, refining the spec

**D-M5-1 — gRPC gets transaction-handle methods only, no top-level facade aliases.** The spec's §4 M5 says the three RPCs "get facade methods". Reading the generated clients shows a top-level method would be a pure alias: `raw.vectorSearch(req)` (TS) and `raw.VectorSearch(req)` (Python) already work, and the existing gRPC facades wrap only what a bare stub drives badly — `streamQuery`, `insertStream`, `transaction`. A named passthrough is exactly what D4's parity bar rejects. What the raw stub *cannot* do safely is bind a call to an open transaction, and all three requests carry `database` (field 1) and `transaction` (field 15, 15 and 8 respectively), so that is where the hand-written code goes.

**D-M5-2 — the HTTP facade returns each response whole and unaltered**, as `queryTimeSeries` and `executeQuery` already do. `VectorSearchResponse` and `HybridSearchResponse` carry `truncated`, `count`, `scoring` and `sparse` alongside `results`; a facade returning `results` alone would silently drop the one field this repository's prose conventions single out as load-bearing. `FullTextSearchResponse` carries **no** `truncated` — document that asymmetry rather than manufacturing a uniform shape.

---

### Task 1: The `vector` namespace on `@arcadedb/driver`

**Files:**
- Create: `typescript/packages/driver/src/facade/vector.ts`
- Modify: `typescript/packages/driver/src/index.ts`
- Test: `typescript/packages/driver/test/vector.test.ts`, `typescript/packages/driver/test/treeshake.test.ts`

**Interfaces:**
- Consumes: `components["schemas"]["VectorSearchRequest" | "VectorSearchResponse" | "HybridSearchRequest" | "HybridSearchResponse" | "FullTextSearchRequest" | "FullTextSearchResponse"]` from `../generated/schema.js`; `unwrap` from `../internal/unwrap.js`.
- Produces: `export type VectorSearchOptions/VectorSearchResult/HybridSearchOptions/HybridSearchResult/FullTextSearchOptions/FullTextSearchResult`, and `export async function vectorSearch/hybridSearch/fullTextSearch(client: RawClient, database: string, opts): Promise<…Result>`. `index.ts` gains `class VectorNamespace` with methods `search`, `hybrid`, `fulltext`, reached as `db.vector`.

- [ ] **Step 1: Write the failing tests**

Create `typescript/packages/driver/test/vector.test.ts`. Mirror the mocking style of `test/data.test.ts` — a `fetchMock` returning a `Response`, passed to `createClient`.

```ts
import { describe, expect, it, vi } from "vitest";
import { ArcadeDBError, createClient } from "../src/index.js";

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("db.vector.search", () => {
  it("POSTs to /api/v1/vector/{database}/search with the request body unaltered", async () => {
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse({ results: [], count: 0, truncated: false }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").vector.search({ indexName: "v_idx", queryVector: [0.1, 0.2], k: 5 });

    expect(captured?.method).toBe("POST");
    expect(new URL(captured!.url).pathname).toBe("/api/v1/vector/mydb/search");
    await expect(captured!.clone().json()).resolves.toEqual({ indexName: "v_idx", queryVector: [0.1, 0.2], k: 5 });
  });

  it("returns the whole response, including truncated, and does not unwrap to results (D-M5-2)", async () => {
    const body = { results: [{ rid: "#1:0", score: 0.9 }], count: 1, truncated: true, scoring: "cosine", indexName: "v_idx", sparse: false, candidateLimit: 100 };
    const fetchMock = vi.fn(async () => jsonResponse(body, 200));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").vector.search({ indexName: "v_idx", queryVector: [0.1] });

    expect(result).toEqual(body);
  });

  it("throws ArcadeDBError on a non-2xx", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: "no such index" }, 400));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(server.db("mydb").vector.search({ indexName: "nope", queryVector: [0.1] })).rejects.toThrow(ArcadeDBError);
  });

  it("percent-encodes a database name with a slash in the path", async () => {
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse({ results: [] }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("od/db").vector.search({ indexName: "v_idx", queryVector: [0.1] });

    expect(new URL(captured!.url).pathname).toBe("/api/v1/vector/od%2Fdb/search");
  });
});

describe("db.vector.hybrid", () => {
  it("POSTs to /api/v1/vector/{database}/hybrid and returns the whole response", async () => {
    let captured: Request | undefined;
    const body = { results: [], count: 0, truncated: false, fused: true, fusionStrategy: "rrf", vectorIndexName: "v_idx", fulltextIndexName: "ft_idx" };
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse(body, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").vector.hybrid({ vectorIndexName: "v_idx", queryVector: [0.1], fulltextQuery: "cat" });

    expect(new URL(captured!.url).pathname).toBe("/api/v1/vector/mydb/hybrid");
    expect(result).toEqual(body);
  });
});

describe("db.vector.fulltext", () => {
  it("POSTs to /api/v1/vector/{database}/fulltext and returns the whole response", async () => {
    let captured: Request | undefined;
    const body = { results: [{ rid: "#2:1" }], count: 1, indexName: "ft_idx", similarity: "bm25" };
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse(body, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").vector.fulltext({ queryText: "cat" });

    expect(new URL(captured!.url).pathname).toBe("/api/v1/vector/mydb/fulltext");
    expect(result).toEqual(body);
  });

  it("has no truncated field in its contract, unlike search and hybrid (D-M5-2)", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ results: [], count: 0 }, 200));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").vector.fulltext({ queryText: "cat" });

    expect("truncated" in result).toBe(false);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd typescript && npx vitest run packages/driver/test/vector.test.ts; cd ..
```

Expected: every test FAILS — `db.vector` is undefined.

- [ ] **Step 3: Write `facade/vector.ts`**

```ts
import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { unwrap } from "../internal/unwrap.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

/** Body accepted by `db.vector.search()`. `indexName` and `queryVector` are the contract's only required fields. */
export type VectorSearchOptions = components["schemas"]["VectorSearchRequest"];
/** Body accepted by `db.vector.hybrid()`. `vectorIndexName` and `queryVector` are required. */
export type HybridSearchOptions = components["schemas"]["HybridSearchRequest"];
/** Body accepted by `db.vector.fulltext()`. `queryText` is the only required field. */
export type FullTextSearchOptions = components["schemas"]["FullTextSearchRequest"];

/**
 * The whole response, not just `results`.
 *
 * `truncated` means the server stopped short of the full candidate set, so `results` is
 * incomplete - the same hazard `QueryEnvelope` documents for `query`. A caller reading only
 * `results` works off a partial answer without being told. That is why these three methods
 * return the response object as the server sent it rather than unwrapping to the rows.
 */
export type VectorSearchResult = components["schemas"]["VectorSearchResponse"];
/** As {@link VectorSearchResult}; also carries `fused`, `fusionStrategy` and the per-leg breakdown. */
export type HybridSearchResult = components["schemas"]["HybridSearchResponse"];
/**
 * As {@link VectorSearchResult}, with one asymmetry worth knowing: `FullTextSearchResponse` has
 * **no `truncated` field** in the contract, while the vector and hybrid responses do. Absence of
 * `truncated` here is the contract's shape, not a server that forgot to send it, so there is no
 * value to default and nothing this client can assert about completeness either way.
 */
export type FullTextSearchResult = components["schemas"]["FullTextSearchResponse"];

/**
 * Executes `POST /api/v1/vector/{database}/search` - kNN over a named vector index.
 *
 * `efSearch` and the result-limit bounds are validated SERVER-side; this client sends what it is
 * given and does not pre-validate, so a rejection for an out-of-range `efSearch` arrives as an
 * `ArcadeDBError` from the server rather than as a local throw.
 */
export async function vectorSearch(client: RawClient, database: string, opts: VectorSearchOptions): Promise<VectorSearchResult> {
  return unwrap(client.POST("/api/v1/vector/{database}/search", { params: { path: { database } }, body: opts }));
}

/** Executes `POST /api/v1/vector/{database}/hybrid` - combined vector and full-text retrieval. Bounds are server-validated; see {@link vectorSearch}. */
export async function hybridSearch(client: RawClient, database: string, opts: HybridSearchOptions): Promise<HybridSearchResult> {
  return unwrap(client.POST("/api/v1/vector/{database}/hybrid", { params: { path: { database } }, body: opts }));
}

/** Executes `POST /api/v1/vector/{database}/fulltext`. Bounds are server-validated; see {@link vectorSearch}. */
export async function fullTextSearch(client: RawClient, database: string, opts: FullTextSearchOptions): Promise<FullTextSearchResult> {
  return unwrap(client.POST("/api/v1/vector/{database}/fulltext", { params: { path: { database } }, body: opts }));
}
```

- [ ] **Step 4: Wire `db.vector` into `index.ts`**

Add the namespace class beside `TimeSeriesNamespace`, using the same lazy-import pattern **and copying the rationale into its doc comment** — the pattern exists so a bundler can keep `facade/vector.js` out of a chunk that only reaches `query`/`command`/`transaction`, and `test/treeshake.test.ts` enforces it.

```ts
/**
 * Vector, hybrid and full-text retrieval - the `db.vector` namespace.
 *
 * Each method dynamically imports `facade/vector.js` on first call, for the reason
 * `TimeSeriesNamespace`'s doc comment gives: `db.vector` stays a synchronous property access, only
 * the first call pays the import cost, and a code-splitting bundler can keep `facade/vector.js` out
 * of a chunk that only reaches the data plane. `test/treeshake.test.ts` is what holds that.
 */
class VectorNamespace {
  constructor(
    private readonly client: RawClient,
    private readonly database: string,
  ) {}

  /** kNN over a named vector index. */
  async search(opts: VectorSearchOptions): Promise<VectorSearchResult> {
    const { vectorSearch } = await import("./facade/vector.js");
    return vectorSearch(this.client, this.database, opts);
  }

  /** Combined vector and full-text retrieval, fused server-side. */
  async hybrid(opts: HybridSearchOptions): Promise<HybridSearchResult> {
    const { hybridSearch } = await import("./facade/vector.js");
    return hybridSearch(this.client, this.database, opts);
  }

  /** Full-text search over a named index or type. */
  async fulltext(opts: FullTextSearchOptions): Promise<FullTextSearchResult> {
    const { fullTextSearch } = await import("./facade/vector.js");
    return fullTextSearch(this.client, this.database, opts);
  }
}
```

Then, on `ArcadeDBDatabase`, expose it exactly the way `ts` is exposed (match the existing property/getter style in that class — read it first, do not guess), and add to the export block:

```ts
export type { VectorSearchOptions, VectorSearchResult, HybridSearchOptions, HybridSearchResult, FullTextSearchOptions, FullTextSearchResult } from "./facade/vector.js";
export type { VectorNamespace };
```

`VectorNamespace` is exported as a **type only**, matching `TimeSeriesNamespace`: a consumer can name `db.vector`'s type without being able to `new` one and bypass the plumbing that hands it a `RawClient`.

- [ ] **Step 5: Extend the tree-shake test**

Read `typescript/packages/driver/test/treeshake.test.ts` and add `facade/vector.js` to whatever assertion it makes about chunks reachable from the data plane, in the same form the existing `facade/timeseries.js` entry takes.

- [ ] **Step 6: Run the tests and the full gate**

```bash
cd typescript && npx vitest run packages/driver/test/vector.test.ts && npm run typecheck && npm run lint && npm test; cd ..
```

Expected: all of `vector.test.ts` PASSES, typecheck exits 0, lint clean, full unit suite green at 96 + the new tests.

- [ ] **Step 7: Commit**

```bash
git add typescript/packages/driver/src/facade/vector.ts typescript/packages/driver/src/index.ts \
        typescript/packages/driver/test/vector.test.ts typescript/packages/driver/test/treeshake.test.ts
git commit -m "$(cat <<'EOF'
feat(driver): the db.vector namespace - search, hybrid and fulltext

Wraps the three endpoints ArcadeData/arcadedb#7306 added. All three are JSON
in and JSON out, so the generated layer already had them; this is the facade.

Each method returns the response WHOLE rather than unwrapping to `results`.
VectorSearchResponse and HybridSearchResponse carry `truncated`, and a caller
reading only the rows would work off a partial answer without being told -
the same hazard QueryEnvelope documents for query. FullTextSearchResponse has
no `truncated` in the contract at all; that asymmetry is documented rather
than smoothed over.

efSearch and the result-limit bounds are validated server-side. This client
does not pre-validate them, so an out-of-range value is rejected by the
server, not locally.

Refs #37
EOF
)"
```

---

### Task 2: The `vector` namespace on `arcadedb-driver` (Python, sync and async)

**Files:**
- Create: `python/packages/driver/src/arcadedb_driver/facade/vector.py`
- Modify: `python/packages/driver/src/arcadedb_driver/__init__.py`, `python/packages/driver/src/arcadedb_driver/aio.py`
- Test: `python/packages/driver/tests/test_vector.py`

**Interfaces:**
- Consumes: the generated operations `_generated.api.vector.vector_search`, `.hybrid_search`, `.full_text_search`, each exposing `sync_detailed(database, *, client, body) -> Response[ErrorResponse | VectorSearchResponse]` and `asyncio_detailed(...)` with the same shape; the generated models `VectorSearchRequest`, `HybridSearchRequest`, `FullTextSearchRequest` and their responses; `ArcadeDBError` from `..errors`.
- Produces: `class VectorNamespace` (sync) and `class AsyncVectorNamespace`, each with `search`, `hybrid`, `fulltext`; reached as `database.vector` on `ArcadeDBDatabase` and `AsyncArcadeDBDatabase`.

- [ ] **Step 1: Confirm the generated models round-trip a realistic payload**

Before writing the facade, settle a real risk rather than assuming it away. `facade/timeseries.py` is hand-written because the contract types per-element scalars as `"type": "object"`, and the generated `from_dict` calls `dict(value)` on each element and raises — silently misclassifying for `query`. The vector responses type `results` as an array of `object` too. The difference *should* be that a vector result element genuinely IS a JSON object, so `dict(value)` succeeds.

Verify it, do not assume:

```bash
cd python && uv run python -c "
from arcadedb_driver._generated.models.vector_search_response import VectorSearchResponse
from arcadedb_driver._generated.models.full_text_search_response import FullTextSearchResponse
r = VectorSearchResponse.from_dict({'results': [{'@rid': '#1:0', 'score': 0.91}], 'count': 1, 'truncated': True, 'scoring': 'cosine'})
print('vector ok:', r.count, r.truncated, r.results)
f = FullTextSearchResponse.from_dict({'results': [{'@rid': '#2:1'}], 'count': 1, 'similarity': 'bm25'})
print('fulltext ok:', f.count, f.results)
"; cd ..
```

Expected: both print without raising. **If either raises**, stop: the facade must then return the parsed JSON body directly the way `facade/timeseries.py` does, with the same kind of comment explaining why, and the plan's Step 3 changes shape. Report which before continuing.

- [ ] **Step 2: Write the failing tests**

Create `python/packages/driver/tests/test_vector.py`. This uses `respx`, the same way `tests/test_data.py` does.

```python
import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, basic_auth
from arcadedb_driver.aio import AsyncArcadeDBServer

BASE_URL = "http://db.test"


def server() -> ArcadeDBServer:
    return ArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "playwithdata"))


def async_server() -> AsyncArcadeDBServer:
    return AsyncArcadeDBServer(base_url=BASE_URL, auth=basic_auth("root", "playwithdata"))


@respx.mock
def test_search_posts_the_request_body() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/mydb/search").mock(
        return_value=httpx.Response(200, json={"results": [], "count": 0, "truncated": False})
    )
    with server() as srv:
        srv.db("mydb").vector.search(index_name="v_idx", query_vector=[0.1, 0.2], k=5)

    sent = route.calls.last.request
    assert sent.method == "POST"
    import json as _json
    assert _json.loads(sent.content) == {"indexName": "v_idx", "queryVector": [0.1, 0.2], "k": 5}


@respx.mock
def test_search_returns_the_whole_response_not_just_results() -> None:
    # D-M5-2. A caller reading only `results` works off a partial answer when
    # `truncated` is true, without being told - the hazard QueryEnvelope documents.
    respx.post(f"{BASE_URL}/api/v1/vector/mydb/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [{"@rid": "#1:0", "score": 0.91}],
                "count": 1,
                "truncated": True,
                "scoring": "cosine",
                "indexName": "v_idx",
            },
        )
    )
    with server() as srv:
        result = srv.db("mydb").vector.search(index_name="v_idx", query_vector=[0.1])

    assert result.count == 1
    assert result.truncated is True
    assert result.scoring == "cosine"
    assert result.results == [{"@rid": "#1:0", "score": 0.91}]


@respx.mock
def test_search_percent_encodes_the_database_name() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/od%2Fdb/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    with server() as srv:
        srv.db("od/db").vector.search(index_name="v_idx", query_vector=[0.1])

    assert route.called


@respx.mock
def test_search_raises_arcadedb_error_with_a_request_id() -> None:
    respx.post(f"{BASE_URL}/api/v1/vector/mydb/search").mock(
        return_value=httpx.Response(
            400, json={"error": "no such index"}, headers={"X-Request-Id": "req-7"}
        )
    )
    with server() as srv, pytest.raises(ArcadeDBError) as caught:
        srv.db("mydb").vector.search(index_name="nope", query_vector=[0.1])

    assert caught.value.status == 400
    assert caught.value.request_id == "req-7"


@respx.mock
def test_hybrid_posts_to_the_hybrid_endpoint() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/mydb/hybrid").mock(
        return_value=httpx.Response(200, json={"results": [], "count": 0, "fused": True})
    )
    with server() as srv:
        result = srv.db("mydb").vector.hybrid(
            vector_index_name="v_idx", query_vector=[0.1], fulltext_query="cat"
        )

    assert route.called
    assert result.fused is True


@respx.mock
def test_fulltext_posts_to_the_fulltext_endpoint() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/vector/mydb/fulltext").mock(
        return_value=httpx.Response(200, json={"results": [{"@rid": "#2:1"}], "count": 1, "similarity": "bm25"})
    )
    with server() as srv:
        result = srv.db("mydb").vector.fulltext(query_text="cat")

    assert route.called
    assert result.count == 1
    assert result.similarity == "bm25"


@respx.mock
@pytest.mark.asyncio
async def test_async_search_returns_the_whole_response() -> None:
    respx.post(f"{BASE_URL}/api/v1/vector/mydb/search").mock(
        return_value=httpx.Response(200, json={"results": [], "count": 0, "truncated": True})
    )
    async with async_server() as srv:
        result = await srv.db("mydb").vector.search(index_name="v_idx", query_vector=[0.1])

    assert result.truncated is True


@respx.mock
@pytest.mark.asyncio
async def test_async_hybrid_and_fulltext_reach_their_endpoints() -> None:
    hybrid = respx.post(f"{BASE_URL}/api/v1/vector/mydb/hybrid").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    fulltext = respx.post(f"{BASE_URL}/api/v1/vector/mydb/fulltext").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    async with async_server() as srv:
        await srv.db("mydb").vector.hybrid(vector_index_name="v_idx", query_vector=[0.1])
        await srv.db("mydb").vector.fulltext(query_text="cat")

    assert hybrid.called and fulltext.called
```

**Two things to settle against the existing code before running this**, rather than assuming the
snippet is right: whether the facade takes keyword arguments (`index_name=...`) or a request
model, and the exact spelling of `ArcadeDBError`'s request-id attribute. Read `tests/test_data.py`
and `facade/timeseries.py` and match whatever they do; adjust the snippet, not the convention.
Likewise check whether `AsyncArcadeDBServer` is the right name and entry point in `aio.py`.

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd python && uv run pytest packages/driver/tests/test_vector.py -v; cd ..
```

Expected: all FAIL — `database.vector` does not exist.

- [ ] **Step 4: Write `facade/vector.py`**

Both the sync `VectorNamespace` and the async `AsyncVectorNamespace` live in this one module, side by side — `facade/timeseries.py` and `facade/dashboards.py` already do exactly that, and `python/CLAUDE.md` warns not to assume `facade/` means sync-only.

Each method calls the generated `sync_detailed` / `asyncio_detailed`, checks the status the way the other facades do, raises `ArcadeDBError` on a non-2xx, and returns the parsed response model unaltered. Do not unwrap to `results` (D-M5-2). Carry the server-side-bounds note from Task 1 into the docstrings.

- [ ] **Step 5: Wire `database.vector` into both facades**

`ArcadeDBDatabase` in `__init__.py` gains a `vector` property returning `VectorNamespace(self._client, self.name)`, written exactly like the existing `ts` property directly above it. `AsyncArcadeDBDatabase` in `aio.py` gains the `Async` twin. Keep both in sync by hand — that duplication is deliberate.

- [ ] **Step 6: Run the tests and the full gate**

```bash
cd python && uv run pytest packages/driver/tests/test_vector.py -v && uv run mypy && uv run ruff check . && uv run ruff format --check . && uv run pytest; cd ..
```

Expected: the new tests PASS, mypy clean, ruff and format clean, full unit suite green at 148 + the new tests.

- [ ] **Step 7: Commit**

```bash
git add python/packages/driver/src/arcadedb_driver/facade/vector.py \
        python/packages/driver/src/arcadedb_driver/__init__.py \
        python/packages/driver/src/arcadedb_driver/aio.py \
        python/packages/driver/tests/test_vector.py
git commit -m "$(cat <<'EOF'
feat(driver): the database.vector namespace, sync and async

Wraps the three endpoints ArcadeData/arcadedb#7306 added, on the generated
operations - unlike facade/timeseries.py, these needed no hand-written
transport: the bodies are JSON and the generated response models round-trip a
real payload, which was checked rather than assumed.

Returns each response whole rather than unwrapping to `results`, so
`truncated` reaches the caller. FullTextSearchResponse has no `truncated` in
the contract; that asymmetry is documented, not smoothed over.

Refs #37
EOF
)"
```

---

### Task 3: Vector search through the gRPC transaction handles

**Files:**
- Modify: `typescript/packages/driver-grpc/src/transaction.ts`, `python/packages/driver-grpc/src/arcadedb_driver_grpc/transaction.py`, `python/packages/driver-grpc/src/arcadedb_driver_grpc/aio.py`
- Test: `typescript/packages/driver-grpc/test/transaction.test.ts`, `python/packages/driver-grpc/tests/test_transaction.py`, `python/packages/driver-grpc/tests/conftest.py` (the `RecordingServicer` needs handlers for the three new RPCs), plus the async transaction test file

**Interfaces:**
- Consumes: the generated `VectorSearchRequest`/`HybridSearchRequest`/`FullTextSearchRequest` messages and the `ArcadeDbService` stub, both already generated.
- Produces: `vectorSearch`, `hybridSearch`, `fullTextSearch` on `TransactionHandle` (TS); `vector_search`, `hybrid_search`, `full_text_search` on `TransactionHandle` and `AsyncTransactionHandle` (Python).

**Read before writing:** per D-M5-1 this task adds **no top-level client methods**. `raw.vectorSearch(req)` / `raw.VectorSearch(req)` already work and need no alias. Only the transaction-bound path is hand-written.

- [ ] **Step 1: Extend the recording servicer**

`python/packages/driver-grpc/tests/conftest.py`'s `RecordingServicer` implements only the RPCs the
existing tests touch. Add handlers for `VectorSearch`, `HybridSearch` and `FullTextSearch` that
record the request and answer with a configured response, following the shape of the
`ExecuteCommand` handler already there, plus the lists to record into:

```python
        self.vector_requests: list[pb2.VectorSearchRequest] = []
        self.hybrid_requests: list[pb2.HybridSearchRequest] = []
        self.fulltext_requests: list[pb2.FullTextSearchRequest] = []
```

- [ ] **Step 2: Write the failing tests**

In `python/packages/driver-grpc/tests/test_transaction.py`, in the style of the existing
`_bind` tests. Note the existing tests populate `rollback`/`read_only`/`commit`/`timeout_ms` on the
forged `TransactionContext` deliberately: asserting only `transaction_id` and `database` would go
green for a `_bind` written with `MergeFrom` instead of `CopyFrom`. Keep that.

```python
def test_vector_search_through_the_handle_is_bound(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        tx.vector_search(
            messages.VectorSearchRequest(
                database="somewhere-else",
                index_name="v_idx",
                query_vector=[0.1, 0.2],
                transaction=messages.TransactionContext(
                    transaction_id="tx-forged",
                    rollback=True,
                    read_only=True,
                    commit=True,
                    timeout_ms=5,
                ),
            )
        )

    sent = servicer.vector_requests[0]
    assert sent.database == "db"
    assert sent.transaction.transaction_id == "tx-42"
    # CopyFrom, not MergeFrom: the caller's inline flags must NOT ride through.
    assert sent.transaction.rollback is False
    assert sent.transaction.read_only is False
    assert sent.transaction.commit is False
    assert sent.transaction.timeout_ms == 0
    # The payload the caller actually cares about is untouched.
    assert sent.index_name == "v_idx"
    assert list(sent.query_vector) == pytest.approx([0.1, 0.2])


def test_the_callers_vector_request_object_is_left_unchanged(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    request = messages.VectorSearchRequest(index_name="v_idx", query_vector=[0.1])
    with create_client(target) as client, client.transaction("db") as tx:
        tx.vector_search(request)

    assert servicer.vector_requests[0].database == "db"
    assert request.database == ""
    assert request.transaction.transaction_id == ""


def test_hybrid_and_fulltext_through_the_handle_are_bound(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        tx.hybrid_search(
            messages.HybridSearchRequest(database="elsewhere", vector_index_name="v_idx", query_vector=[0.1])
        )
        tx.full_text_search(messages.FullTextSearchRequest(database="elsewhere", query_text="cat"))

    assert servicer.hybrid_requests[0].database == "db"
    assert servicer.hybrid_requests[0].transaction.transaction_id == "tx-42"
    assert servicer.fulltext_requests[0].database == "db"
    assert servicer.fulltext_requests[0].transaction.transaction_id == "tx-42"
```

Write the async twins of all three in the async transaction test file, matching how that file
already mirrors the sync cases.

For TypeScript, add the equivalent three cases to
`typescript/packages/driver-grpc/test/transaction.test.ts`, asserting the same four properties
(database forced, transaction id forced, caller flags cleared, caller object unmutated) in whatever
form that file's existing `executeQuery` bind tests use — read them and match, do not invent a
second idiom.

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd typescript && npx vitest run packages/driver-grpc/test/transaction.test.ts; cd ..
cd python && uv run pytest packages/driver-grpc/tests/test_transaction.py -v; cd ..
```

Expected: the new cases FAIL — the methods do not exist.

- [ ] **Step 4: Add the three methods to each handle**

Copy the shape of the `execute_query` / `executeQuery` method already on each handle exactly — same signature shape, same `timeout`/`metadata` passthrough, same `self._bind(request)` call. Do not introduce a second binding mechanism; `_bind` is the safety property, and a method that sets the transaction field from caller input instead reopens ArcadeData/arcadedb#5040-#5042 for that one call.

- [ ] **Step 5: Run the tests and both gates**

```bash
cd typescript && npx vitest run packages/driver-grpc/test/transaction.test.ts && npm run typecheck && npm run lint && npm test; cd ..
cd python && uv run pytest packages/driver-grpc/tests/test_transaction.py -v && uv run mypy && uv run ruff check . && uv run ruff format --check . && uv run pytest; cd ..
```

Expected: all green in both workspaces.

- [ ] **Step 6: Commit**

```bash
git add typescript/packages/driver-grpc/src/transaction.ts typescript/packages/driver-grpc/test/transaction.test.ts \
        python/packages/driver-grpc/tests/conftest.py \
        python/packages/driver-grpc/src/arcadedb_driver_grpc/transaction.py \
        python/packages/driver-grpc/src/arcadedb_driver_grpc/aio.py \
        python/packages/driver-grpc/tests/test_transaction.py
git commit -m "$(cat <<'EOF'
feat(driver-grpc): vector search through the transaction handles

VectorSearch, HybridSearch and FullTextSearch are unary, so the generated stub
already drives them well and a top-level facade method would be a pure alias -
the parity bar in the M4 design rejects exactly that. What the raw stub cannot
do safely is bind a call to an open transaction, and all three requests carry
`database` and `transaction`, so that is the part worth hand-writing.

Each new method goes through the same `_bind` as every other handle method:
the caller's database and transaction are discarded and the handle's forced on,
against a COPY of the request. That override is what keeps #5040-#5042
unrepeatable, and a method binding any other way would reopen them for itself.

Refs #37
EOF
)"
```

---

### Task 4: README prose and end-to-end verification

**Files:**
- Modify: `typescript/packages/driver/README.md`, `python/packages/driver/README.md`, `typescript/packages/driver-grpc/README.md`, `python/packages/driver-grpc/README.md`
- Test: `typescript/e2e/data-plane.test.ts`, `python/e2e/test_data_plane.py` (or a new `vector` e2e file in each, whichever matches the existing layout)

**Interfaces:**
- Consumes: everything from Tasks 1-3.
- Produces: nothing other tasks read.

- [ ] **Step 1: Establish how a vector index is actually created**

The e2e tests need a real vector index and real embedded vectors, and the exact DDL is the part most likely to cost time. Work it out against a live container **first**, with a scratch script, before touching a test file:

```bash
docker run --rm -d --name m5probe -p 2481:2480 \
  -e JAVA_OPTS="-Darcadedb.server.rootPassword=playwithdata" arcadedata/arcadedb:26.10.1-SNAPSHOT
```

Create a database, a type with a vector property, insert a handful of rows with small embeddings, create the index, and confirm `POST /api/v1/vector/{db}/search` returns rows. Record the exact statements — they go into the fixture. Stop the container when done (`docker rm -f m5probe`).

If a working index cannot be produced within a reasonable effort, **stop and report** rather than writing an e2e test that asserts an empty result set: a vector search returning zero rows passes just as happily against a broken client as a working one, and is worse than no test.

- [ ] **Step 2: Write the e2e tests**

In both languages, against a real container: create the index and rows from Step 1's recipe, then assert `search` returns a **non-empty** `results` with the nearest row first, `hybrid` returns results, and `fulltext` matches a known term. Assert on `count`/`truncated` too, so D-M5-2 is covered end to end and not only in unit tests.

- [ ] **Step 3: Run both e2e suites**

```bash
cd typescript && npm run e2e; cd ..
cd python && uv run pytest e2e -v; cd ..
```

Expected: green, including the new cases. TypeScript e2e needs Node >= 22.22.

- [ ] **Step 4: Write the README sections**

One section per package, in that file's own voice. Each must state:
- what the three methods are and the shape they return;
- that the response comes back **whole**, and what `truncated` means for a caller who reads only `results`;
- that `FullTextSearchResponse` has no `truncated` at all, and that this is the contract's shape rather than a missing field;
- that `efSearch` and the result-limit bounds are validated **server-side**, so a rejection arrives as an error from the server and not as a local throw.

For the two gRPC READMEs, additionally state that the three RPCs are reached through `raw` outside a transaction and through the transaction handle inside one, and why there is no top-level wrapper (D-M5-1). Update each gRPC README's existing enumeration of what is reachable only via `raw` so it stays accurate.

- [ ] **Step 5: Full gate, then commit**

```bash
cd typescript && npm run lint && npm run typecheck && npm test; cd ..
cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run python scripts/check_codegen_skips.py; cd ..
git status --short
```

Expected: everything exits 0; `git status --short` shows only the files you intend plus the pre-existing `?? .idea/`.

```bash
git add typescript/packages/driver/README.md python/packages/driver/README.md \
        typescript/packages/driver-grpc/README.md python/packages/driver-grpc/README.md \
        typescript/e2e python/e2e
git commit -m "$(cat <<'EOF'
docs(vector): document the namespace, the bounds and the truncated asymmetry

Adds the vector section to all four READMEs and the end-to-end coverage
behind it: a real index, real embeddings, and assertions on a NON-EMPTY
result set - a vector search returning zero rows passes just as happily
against a broken client as a working one.

Records the two things a caller cannot infer from the types: efSearch and the
result-limit bounds are server-validated, so an out-of-range value is refused
by the server rather than locally; and FullTextSearchResponse carries no
`truncated` where the vector and hybrid responses do.

Refs #37
EOF
)"
```

---

### Task 5: Open the pull request

**Files:** none.

- [ ] **Step 1: Re-run everything from clean**

```bash
cd typescript && npm run lint && npm run typecheck && npm test && cd ..
cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy \
  && uv run pytest && uv run python scripts/check_codegen_skips.py && cd ..
```

Expected: every command exits 0, and the skip set is still the same four entries — none of the vector endpoints may have appeared in it.

- [ ] **Step 2: Confirm the drift gate is untouched**

This milestone changes no contract, so regeneration must produce no diff at all.

```bash
cd typescript && npm run generate && cd ..
cd python && ./scripts/generate.sh && ./scripts/generate-grpc.sh && cd ..
git status --short
```

Expected: only `?? .idea/`.

- [ ] **Step 3: Push and open the PR**

```bash
git push -u origin feat/m5-vector-search
gh pr create --base main --milestone '0.2.0 — the 26.10.1 contract' \
  --label enhancement,http-driver,grpc-driver,typescript,python \
  --title 'feat: vector search across all four clients' \
  --body 'Closes #37.'
```

Expand that body before creating: state the two decisions (D-M5-1, D-M5-2) with their reasoning, the e2e evidence that the searches return non-empty results, and that the skip set and drift gate are unchanged.
