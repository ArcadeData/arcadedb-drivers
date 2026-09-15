# M7: HTTP ndjson Streaming for Query and Command — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a caller consume `/query` and `/command` results row by row as they arrive, in both HTTP clients.

**Architecture:** No transport is written. Both generated layers can already stream — `openapi-fetch` via `parseAs: "stream"`, `openapi-python-client` via the pooled `httpx` client's `.stream()` — so base URL, auth and error mapping are shared because there is only one path in each language. What M7 adds is a **transform**: bytes → lines → `NdJsonQueryEvent` → an async iterable.

**Tech Stack:** `openapi-fetch` 0.17, `httpx`, vitest, pytest, mypy, ruff, eslint.

**Spec:** `docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md` (§4, M7) — **see Task 1: that section's premise is false and is corrected before anything is built from it.**

**Issue:** ArcadeData/arcadedb-drivers#39. Upstream: ArcadeData/arcadedb#7306 (streaming half). Batch was split to #52.

## Global Constraints

- Generated code is **never** hand-edited. Do not touch `contracts/` — M7 changes no contract, so the drift gate must stay green with no regeneration.
- `EXPECTED_SKIPS` in `python/scripts/check_codegen_skips.py` stays exactly its four entries. `/batch` remains skipped; it belongs to #52.
- **No gRPC changes.** Neither gRPC package is part of this milestone.
- Python's sync and async facades are hand-maintained in parallel (`unasync` is a non-goal). Every sync method needs its `Async` twin, and the twins must carry the same *behavioural facts* in their docstrings — documentation drift between them is a defect here, already filed once as #30 and found again in M5.
- Media type, verbatim: `application/x-ndjson`. Endpoints, verbatim: `POST /api/v1/query/{database}`, `POST /api/v1/command/{database}`.
- Branch: `feat/m7-ndjson-streaming`, off `main`.

## Decisions

**D-M7-1 — no transport is written; the generated clients already stream.** The spec assumed otherwise and was wrong in both languages. Verified:

| | spec assumed | verified |
|---|---|---|
| TypeScript | `openapi-fetch` buffers the response | `parseAs: "stream"` returns `response.body` unparsed — `openapi-fetch@0.17.0`: `if (parseAs === "stream") { return response.body; }` |
| Python | `openapi-python-client` parses it whole | `get_httpx_client()` / `get_async_httpx_client()` return real `httpx.Client` / `httpx.AsyncClient`, which have `.stream()` |

This is not a simplification of the design — it removes the design's headline risk. The spec called sharing base URL, auth and error mapping "the requirement, because two ways to authenticate or to raise is the defect this milestone is most likely to introduce". With one transport per language that defect cannot occur. openapi-fetch also handles a non-ok response independently of `parseAs` — always reading text and JSON-parsing into `{ error, response }` — so `unwrap()` and `ArcadeDBError` are unchanged.

**D-M7-2 — the stream yields events, not rows.** `NdJsonQueryEvent` carries exactly one of `record`, `stats` or `error` per line. Surfacing only `record` would discard two things a caller needs: `stats`, the trailer carrying the same `limit`/`returned`/`truncated` the buffered response reports at top level; and `error`, **a failure raised after the 200 was already sent**, which is the whole reason the contract has an in-band error at all — the status line cannot be taken back once the stream has started. A caller that iterates rows and ignores the trailer cannot tell a complete result from a truncated one, which is the same hazard `QueryEnvelope` documents for the buffered path.

**D-M7-3 — an in-band `error` event raises.** It is a failure, and a consumer writing `for await (const e of stream)` would otherwise treat it as data or silently stop. Raise `ArcadeDBError` so the streaming and buffered paths fail the same way — one error type for one server condition, which is what D-M7-1's "only one path" buys. The status is 200; that is honest, and M4 already established `ArcadeDBError` can carry a 2xx.

**D-M7-4 — the buffered methods are untouched.** `query`/`command` keep returning `QueryEnvelope` and keep sending no `Accept` header. Streaming is a separate method, not a mode. A caller who does not ask gets byte-identical behaviour, which is also what makes this milestone safe to ship.

---

### Task 1: Correct the design doc's M7 section

**Files:** Modify `docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md` (§4 M7 only).

This task exists because implementing from a document known to be wrong is how the error spreads — it already reached issue #39, which has been corrected separately.

- [ ] **Step 1: Read the section and verify the claim is false**

```bash
sed -n '/^### M7 —/,/^### M8/p' docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md
grep -n 'parseAs === "stream"' typescript/node_modules/openapi-fetch/dist/index.mjs
cd python && uv run python -c "
from arcadedb_driver._generated.client import Client
c = Client(base_url='http://x')
print(type(c.get_httpx_client()).__name__, hasattr(c.get_httpx_client(), 'stream'))
print(type(c.get_async_httpx_client()).__name__, hasattr(c.get_async_httpx_client(), 'stream'))
"; cd ..
```

Expected: the section claims neither generated layer can stream; the greps show both can.

- [ ] **Step 2: Rewrite the section**

It must state what M7 delivers (query and command only — batch is #52 and why), D-M7-1's table with the verification for each row, and that the risk the old text named cannot occur because there is one transport per language. Keep the corrected framing short; this is a design record, not an essay.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md
git commit -m "$(cat <<'EOF'
docs: correct M7's premise - both generated layers can already stream

§4 M7 said neither generated layer can express a streamed response, so a
streaming path would have to sit beside the generated client, and that
sharing its base URL, auth and error mapping was the milestone's central
risk. Both halves are wrong: openapi-fetch takes `parseAs: "stream"` and
returns response.body unparsed, and openapi-python-client's pooled client is
a real httpx.Client with .stream().

So there is no second transport, and the risk the section named cannot occur.
What M7 adds is a transform - bytes to lines to NdJsonQueryEvent - not a
transport. Batch is split to #52: it is unwrapped in both clients today, so
it means introducing the endpoint rather than adding a streaming mode to it.

Refs #39
EOF
)"
```

---

### Task 2: `queryStream` and `commandStream` on `@arcadedb/driver`

**Files:**
- Create: `typescript/packages/driver/src/facade/stream.ts`
- Modify: `typescript/packages/driver/src/facade/data.ts` (`asQueryResponse` becomes a real discriminator), `typescript/packages/driver/src/index.ts`
- Test: `typescript/packages/driver/test/stream.test.ts`, `typescript/packages/driver/test/data.test.ts`

**Interfaces:**
- Consumes: `components["schemas"]["NdJsonQueryEvent"]`, the `RawClient`, `ArcadeDBError`.
- Produces: `export type NdJsonQueryEvent`; `export async function* queryStream(client, database, sessionId, opts): AsyncGenerator<NdJsonQueryEvent>` and `commandStream` likewise; `queryStream`/`commandStream` methods on `ArcadeDBDatabase`.

- [ ] **Step 1: Write the failing tests**

`test/stream.test.ts`, in the style of `test/data.test.ts` (a `fetchMock` returning a `Response`, passed to `createClient`). A streaming response is built from a `ReadableStream`:

```ts
function ndjsonResponse(lines: string[], status = 200): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(new TextEncoder().encode(line + "\n"));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "content-type": "application/x-ndjson" } });
}
```

Cover:
- `queryStream` sends `Accept: application/x-ndjson` and POSTs to `/api/v1/query/{database}` with the same body `query` builds.
- It yields each event in order — two `record` events then a `stats` trailer — and yields the trailer rather than swallowing it (D-M7-2).
- **A line split across two chunks is reassembled.** Enqueue `{"record":{"a":` and `1}}\n` as separate chunks and assert one event. This is the defect a naive `decode().split("\n")` per chunk has, and it appears only under chunk boundaries the server chooses — so a test that feeds whole lines proves nothing about it.
- A trailing chunk without a final newline still yields its event.
- An empty stream yields nothing and does not throw.
- An in-band `error` event raises `ArcadeDBError` (D-M7-3), and events yielded before it were still delivered.
- A non-2xx raises `ArcadeDBError` with the status, exactly as `query` does.
- `commandStream` reaches `/api/v1/command/{database}`.

- [ ] **Step 2: Run them and see them fail**

```bash
cd typescript && npx vitest run packages/driver/test/stream.test.ts; cd ..
```

Expected: all fail — `db.queryStream` is undefined.

- [ ] **Step 3: Implement `facade/stream.ts`**

Use `parseAs: "stream"` on the existing client so auth, base URL and error mapping come for free:

```ts
const { data, error, response } = await client.POST("/api/v1/query/{database}", {
  params: { path: { database }, header: sessionHeader(sessionId) },
  body: buildQueryBody(opts),
  headers: { Accept: "application/x-ndjson" },
  parseAs: "stream",
});
```

Then a line decoder over the `ReadableStream`. **Buffer across chunks** — a chunk boundary can fall mid-line, and mid-multibyte-character; use `TextDecoder` with `{ stream: true }` so a UTF-8 sequence split across chunks is not mangled. Flush whatever remains after the last chunk. Skip blank lines. Non-2xx goes through the same `ArcadeDBError` path the buffered methods use.

Export the event type, and give the module a doc comment explaining D-M7-1: that this deliberately rides the generated client rather than fetching directly, and why that matters.

- [ ] **Step 4: Turn `asQueryResponse` into a real discriminator**

`facade/data.ts`'s helper currently throws on any ndjson event, with a comment saying the branch is unreachable because the client never sends `Accept: application/x-ndjson`. That stops being true in this task. Rewrite it and its comment so it discriminates rather than asserts — the buffered path still wants a `QueryResponse` and should still reject an event, but the reason changes from "we never ask for this" to "this call did not ask for it". Update `test/data.test.ts`'s cases accordingly.

- [ ] **Step 5: Wire the methods onto `ArcadeDBDatabase`**

`queryStream` and `commandStream` beside `query`/`command`. They are async generators, so they need no `await import` dance — but check how `ArcadeDBDatabase` exposes its other methods and match it. Export the event type from `index.ts`.

- [ ] **Step 6: Full gate**

```bash
cd typescript && npx vitest run packages/driver/test/ && npm run typecheck && npm run lint && npm test; cd ..
```

- [ ] **Step 7: Commit**

```bash
git add typescript/packages/driver/src typescript/packages/driver/test
git commit -m "$(cat <<'EOF'
feat(driver): queryStream and commandStream over application/x-ndjson

Rides the generated client with `parseAs: "stream"` rather than fetching
directly, so base URL, auth and error mapping are shared by construction -
there is no second transport to keep in step. What is hand-written is the
transform: a chunk-buffering line decoder that yields NdJsonQueryEvent.

Yields events, not rows. The `stats` trailer carries the same limit/returned/
truncated the buffered response reports at top level, and an `error` event is
a failure raised AFTER the 200 was sent - the status cannot be taken back
once the stream has started, so it arrives in band. That error raises
ArcadeDBError, so the streaming and buffered paths fail the same way.

asQueryResponse stops being an assertion and becomes the discriminator it was
written to anticipate in #36.

Refs #39
EOF
)"
```

---

### Task 3: `query_stream` and `command_stream` on `arcadedb-driver`, sync and async

**Files:**
- Create: `python/packages/driver/src/arcadedb_driver/facade/stream.py`
- Modify: `python/packages/driver/src/arcadedb_driver/__init__.py`, `aio.py`
- Test: `python/packages/driver/tests/test_stream.py`

**Interfaces:**
- Consumes: the generated `Client`'s `get_httpx_client()` / `get_async_httpx_client()`, `ArcadeDBError`, `REQUEST_ID_HEADER`.
- Produces: `query_stream` / `command_stream` on `ArcadeDBDatabase` and `AsyncArcadeDBDatabase`, yielding parsed events.

- [ ] **Step 1: Write the failing tests**

`tests/test_stream.py`, using `respx` as `tests/test_data.py` does. `respx` can return a streaming body; check how that library expresses it in the installed version before writing, and prefer its supported mechanism over hand-rolling one.

Cover the same properties as Task 2, plus the two that are Python-specific:
- `iter_lines()` handles line splitting, so the split-line case is the library's job — but assert it anyway, because this is the property most likely to regress if someone swaps the implementation.

> **Superseded during execution (2026-09-12).** `iter_lines()` turned out to be the wrong tool and
> the shipped code does not use it. Its `LineDecoder` splits on `str.splitlines()` semantics, which
> include U+0085, U+2028 and U+2029 — legal raw characters inside a JSON string that the server does
> not escape — so a record carrying one is split mid-JSON. The implementation hand-rolls splitting
> on `"\n"` alone over `iter_text()`/`aiter_text()` instead, matching the TypeScript twin. See
> `facade/stream.py`'s module docstring, and §4 M7 of the design doc. This step and the snippet
> below are left as written, because they record what was planned; the code is what shipped.
- The response is **closed** when the caller abandons the iterator early. `httpx.stream` is a context manager; a generator that yields inside it must not leak the connection when the consumer breaks. Assert with an explicit `.close()`/`aclose()` on the generator, the same way `arcadedb-driver-grpc`'s stream tests do.

- [ ] **Step 2: Run them and see them fail**

```bash
cd python && uv run pytest packages/driver/tests/test_stream.py -v; cd ..
```

- [ ] **Step 3: Implement**

Both the sync and async versions live in `facade/stream.py`, side by side — `facade/timeseries.py` and `facade/dashboards.py` already do that, and `python/CLAUDE.md` warns not to assume `facade/` means sync-only.

Use the pooled client, which is the precedent `facade/timeseries.py`'s hand-written `write` already set:

```python
with self._client.get_httpx_client().stream(
    "POST", _query_url(self._database), json=body,
    headers={"Accept": "application/x-ndjson"},
) as response:
    ...
    for line in response.iter_lines():
        ...
```

Raise `ArcadeDBError` on a non-2xx — read the body first, since a streaming response has not been read yet — and on an in-band `error` event. Keep the sync and async docstrings carrying the same behavioural facts.

- [ ] **Step 4: Wire onto both database classes**

Exactly as `ts`/`vector` are exposed on each; read that code rather than assuming its form.

- [ ] **Step 5: Full gate**

```bash
cd python && uv run pytest packages/driver/tests/test_stream.py -v && uv run mypy && uv run ruff check . && uv run ruff format --check . && uv run pytest; cd ..
```

- [ ] **Step 6: Commit**

```bash
git add python/packages/driver/src python/packages/driver/tests
git commit -m "$(cat <<'EOF'
feat(driver): query_stream and command_stream, sync and async

Rides the generated client's pooled httpx client with .stream(), the same
escape hatch facade/timeseries.py's hand-written write already uses, so base
URL, auth and timeout are shared rather than reconstructed. No second
transport exists to drift.

Yields events rather than rows, so the stats trailer and an in-band error -
a failure raised after the 200 was already sent - both reach the caller. The
error raises ArcadeDBError, matching the buffered path.

Refs #39
EOF
)"
```

---

### Task 4: README prose and end-to-end verification

**Files:** Modify `typescript/packages/driver/README.md`, `python/packages/driver/README.md`; add e2e cases to `typescript/e2e/data-plane.test.ts` and `python/e2e/test_data_plane.py`.

- [ ] **Step 1: Write the e2e tests**

Against a real container, in both languages. Insert enough rows that the server actually chunks the response — a handful will arrive in one chunk and prove less than it appears. Assert:
- the rows arrive and the **`stats` trailer** is among the events;
- the trailer's `returned` matches the number of `record` events seen;
- a `limit` low enough to truncate produces `truncated: true` in the trailer, so the property D-M7-2 exists for is covered end to end;
- the **buffered** `query` on the same data still returns the same rows, byte-identical in shape — D-M7-4.

- [ ] **Step 2: Run both e2e suites**

```bash
cd typescript && npm run e2e; cd ..
cd python && uv run pytest e2e -v; cd ..
```

- [ ] **Step 3: Write the README sections**

One per HTTP package, in that file's own voice. Each must state:
- the two methods and that they yield **events**, not rows, with exactly one of `record`, `stats` or `error` per event;
- what the `stats` trailer carries and why ignoring it loses the same information ignoring `truncated` loses on the buffered path;
- that an `error` event is a failure raised **after** the 200 was sent — the status cannot be taken back — and that this client raises `ArcadeDBError` for it, so both paths fail alike;
- that the buffered `query`/`command` are unchanged and send no `Accept` header;
- that `/batch` streaming is not here, with a pointer to #52.

- [ ] **Step 4: Full gate, then commit**

```bash
cd typescript && npm run lint && npm run typecheck && npm test; cd ..
cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run python scripts/check_codegen_skips.py; cd ..
git status --short
```

```bash
git add typescript/packages/driver/README.md python/packages/driver/README.md typescript/e2e python/e2e
git commit -m "$(cat <<'EOF'
docs(streaming): document the trailer, the in-band error and what is unchanged

Adds the streaming section to both HTTP READMEs and the end-to-end coverage
behind it, over enough rows that the server actually chunks the response - a
handful arrive in one chunk and prove less than they appear to.

Records the two things a caller cannot infer from the types: the stats
trailer carries the same limit/returned/truncated the buffered response
reports at top level, so ignoring it loses exactly what ignoring `truncated`
loses; and an `error` event is a failure raised after the 200 was already
sent, which is why it arrives in band at all.

Refs #39
EOF
)"
```

---

### Task 5: Open the pull request

- [ ] **Step 1: Re-run everything from clean**

```bash
cd typescript && npm run lint && npm run typecheck && npm test && cd ..
cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy \
  && uv run pytest && uv run python scripts/check_codegen_skips.py && cd ..
```

Expected: all exit 0; the skip set is still its four entries, `/batch` among them.

- [ ] **Step 2: Confirm the drift gate is untouched**

M7 changes no contract, so regeneration must produce no diff.

```bash
cd typescript && npm run generate && cd ..
cd python && ./scripts/generate.sh && ./scripts/generate-grpc.sh && cd ..
git status --short
```

Expected: only `?? .idea/`.

- [ ] **Step 3: Push and open the PR**

```bash
git push -u origin feat/m7-ndjson-streaming
gh pr create --base main --milestone '0.2.0 — the 26.10.1 contract' \
  --label enhancement,http-driver,typescript,python,e2e \
  --title 'feat: ndjson streaming for query and command' \
  --body 'Closes #39.'
```

Expand that body before creating: D-M7-1's corrected premise with its evidence, why events rather than rows, the in-band error, what stays unchanged, and that batch is #52.
