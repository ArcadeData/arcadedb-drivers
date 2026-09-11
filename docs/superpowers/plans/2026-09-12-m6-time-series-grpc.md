# M6: Time Series Over gRPC — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ArcadeDB's four time-series RPCs usable from both gRPC drivers, with the streaming ones wrapped and the transaction-capable ones bound.

**Architecture:** Two hand-written wrappers per language, mirroring the two that already exist: `TimeSeriesWriteStream` is client-streaming and mirrors `insertStream`; `TimeSeriesQuery` is server-streaming and mirrors `streamQuery`. `TimeSeriesQuery` and `TimeSeriesLatest` additionally go on the transaction handles, because their request messages carry `transaction`. `TimeSeriesWrite` stays raw-only. No HTTP client changes, no contract change.

**Tech Stack:** `@connectrpc/connect` (TypeScript), `grpc_tools.protoc` + `grpc.aio` (Python), vitest, pytest, mypy, ruff, eslint.

**Spec:** `docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md` (§4, M6) — **but see Task 1: that section contains a factual error this plan corrects before implementing against it.**

**Issue:** ArcadeData/arcadedb-drivers#38. Upstream: ArcadeData/arcadedb#7305.

## Global Constraints

- Generated code is **never** hand-edited: `typescript/packages/driver-grpc/src/gen/`, `python/packages/driver-grpc/src/arcadedb_driver_grpc/_generated/`.
- Do not touch `contracts/`. M6 changes no contract; the drift gate must stay green with no regeneration.
- **No HTTP client changes at all.** `@arcadedb/driver` and `arcadedb-driver` are untouched by this milestone.
- Python's sync and async facades are maintained by hand in parallel (`unasync` is an explicit non-goal). Every sync method needs its `Async` twin, and the twins must carry the same *behavioural facts* in their docstrings, not merely the same code — documentation drift between twins is a defect here, already filed once as #30 and found again during M5.
- RPC names, verbatim: `TimeSeriesWrite`, `TimeSeriesWriteStream`, `TimeSeriesQuery`, `TimeSeriesLatest`.
- Branch: `feat/m6-timeseries-grpc`, off `main`.

## Decisions

**D-M6-1 — `precision` is required in the wrapper's request type, in both languages.** This is the one decision that prevents silent data corruption. The two transports disagree about what an omitted precision means:

| transport | omitted `precision` means | why |
|---|---|---|
| HTTP `POST /ts/{database}/write` | **nanoseconds** | documented default on the query parameter |
| gRPC `TimeSeriesWriteRequest.precision` | **milliseconds** | proto3 zero value is `TS_PRECISION_MILLISECONDS = 0` |

A caller moving a working HTTP ingest to gRPC and dropping the parameter gets every timestamp misread by a factor of 10⁶, with no error on either side. Proto3 cannot distinguish "omitted" from "explicitly milliseconds" on a non-`optional` enum field, so the client cannot detect it either. Making the wrapper's `precision` required removes the failure by construction. Callers who want milliseconds say so.

**D-M6-2 — wrap the streaming RPCs, bind what the message allows, alias nothing.** This follows M5's parity rule (D-M5-1) rather than the spec's older sketch, which predates it. The proto settles the rest:

| RPC | shape | carries `transaction` | treatment |
|---|---|---|---|
| `TimeSeriesWriteStream` | client-streaming | no | facade wrapper, top-level only |
| `TimeSeriesQuery` | server-streaming | yes | facade wrapper **and** bound on the handles |
| `TimeSeriesLatest` | unary | yes | bound on the handles; `raw` at top level |
| `TimeSeriesWrite` | unary | no | `raw` only, documented |

Note the exclusion of `TimeSeriesWrite` from the handles is stronger than `insertStream`'s: `insertStream` is absent from the handle because a *server bug* (arcadedb#6607, since fixed) made its `TransactionContext` meaningless, whereas `TimeSeriesWriteRequest` has no `transaction` field **in the contract at all**. Say which kind of exclusion it is wherever it is documented; they have different futures.

**D-M6-3 — the write summary's partial success must reach the caller intact.** `TimeSeriesWriteSummary` carries `received`, `written`, `dropped`, `unknown_types`, `non_time_series_types`, `unavailable_types` and `execution_time_ms`. A write can return a **successful RPC** while silently dropping points — `written < received` with the reasons in three separate repeated fields. This is the `truncated`-class hazard of this milestone: a caller who checks only that the call did not raise has not checked that the data landed. Return the summary whole, never reduce it to a boolean or a count, and document the trap.

**D-M6-4 — every chunk carries the full envelope, and no workaround is invented without evidence.** `TimeSeriesWriteChunk` declares `database`, `credentials`, `type` and `precision` on every chunk, with no `session_id`/`chunk_seq`/`last` — so the envelope is simpler than `InsertChunk`'s and the wrapper sets all four on every chunk, which is the contract-faithful reading. Do **not** port `insertStream`'s `options.database` mirror: that exists for arcadedb#6597, a specific server bug on a different RPC, and copying a workaround to an RPC never shown to need it is how cargo-cult code starts. Task 4's e2e is what proves multi-chunk streaming actually lands every point.

---

### Task 1: Correct the design doc's M6 section

**Files:**
- Modify: `docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md` (§4, M6 only)

**Interfaces:** Consumes nothing. Produces a spec section later tasks can be checked against.

This task exists because implementing from a document known to be wrong is how the error spreads further — it already reached issue #38, which has been corrected separately.

- [ ] **Step 1: Read the current M6 section**

```bash
sed -n '/^### M6 — Time series over gRPC/,/^### M7/p' docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md
```

It claims `POST /ts/{database}/write` being in `EXPECTED_SKIPS` means "`arcadedb-driver` can read time series over HTTP and cannot write it", and poses an open question about whether gRPC `TimeSeriesWrite` retires that gap.

- [ ] **Step 2: Verify the claim is false before rewriting it**

```bash
grep -n 'def write' python/packages/driver/src/arcadedb_driver/facade/timeseries.py
```

Expected: two hits — a sync `write` and an async `write`, both taking `line_protocol` and `precision`. The generator does skip the endpoint; the facade hand-wrote it on top of the generated client's pooled httpx client. So there is no gap, and the open question is moot.

- [ ] **Step 3: Rewrite the section**

Replace the false paragraph and the open question with an accurate one. It must say:
- what M6 actually delivers (the four RPCs, per D-M6-2's table);
- that the HTTP write path already exists in both languages and is hand-written, with the reason the generator skips it;
- the inference that caused the error, stated plainly so it is not repeated: **a skipped endpoint means the generator dropped it, not that a user cannot call it.** `EXPECTED_SKIPS` answers the first question; only `facade/` answers the second;
- that Prometheus remote `read`/`write` are the endpoints genuinely unwrapped in both languages.

Also add D-M6-1's precision table to that section — a cross-transport unit mismatch belongs in the design record, not only in a code comment.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md
git commit -m "$(cat <<'EOF'
docs: correct M6's premise - Python's HTTP time-series write is not missing

§4 M6 said arcadedb-driver could read time series over HTTP but not write
it, and asked M6 to decide whether gRPC TimeSeriesWrite retired that gap.
Both were wrong. openapi-python-client does skip POST /ts/{database}/write
because its body is text/plain, but facade/timeseries.py hand-wrote the
operation on the generated client's pooled httpx client - sync and async.

The inference that produced the error is the part worth keeping: a skipped
endpoint means the generator dropped it, not that a user cannot call it.
EXPECTED_SKIPS answers the first question; only facade/ answers the second.

Also records the precision asymmetry M6 is designed around: an omitted
precision means nanoseconds over HTTP and milliseconds over gRPC, because
proto3's zero value for the enum is TS_PRECISION_MILLISECONDS.

Refs #38
EOF
)"
```

---

### Task 2: The TypeScript gRPC time-series surface

**Files:**
- Modify: `typescript/packages/driver-grpc/src/stream.ts`, `typescript/packages/driver-grpc/src/index.ts`, `typescript/packages/driver-grpc/src/transaction.ts`
- Test: `typescript/packages/driver-grpc/test/stream.test.ts`, `typescript/packages/driver-grpc/test/transaction.test.ts`

**Interfaces:**
- Consumes: the generated `ArcadeDbService` client and the `TimeSeriesWriteChunk`, `TimeSeriesWriteSummary`, `TimeSeriesQueryRequest`, `TimeSeriesQueryResult`, `TimeSeriesLatestRequest`, `TimeSeriesPoint`, `TimeSeriesPrecision` messages, all already generated.
- Produces: `export interface TimeSeriesWriteStreamRequest`; `export function createTimeSeriesWriteStream(raw)` and `createTimeSeriesQuery(raw)`, both wired onto `ArcadeDBGrpcClient` as `timeSeriesWriteStream` and `timeSeriesQuery`; `timeSeriesQuery` and `timeSeriesLatest` methods on `TransactionHandle`.

- [ ] **Step 1: Read the two wrappers you are mirroring**

```bash
sed -n '38,140p' typescript/packages/driver-grpc/src/stream.ts
```

`createStreamQuery` is the server-streaming shape (an async generator); `createInsertStream` is the client-streaming shape (envelope bookkeeping over an `AsyncIterable` of batches). Match their structure, their naming and their comment density. Note `createInsertStream`'s `options.database` mirror and its comment — do **not** copy that mirror (D-M6-4); it is a workaround for a bug on a different RPC.

- [ ] **Step 2: Write the failing tests**

In `test/stream.test.ts`, following the file's existing style for the two wrappers already covered:

- `timeSeriesWriteStream` sends one wire chunk per input batch, each carrying `database`, `type` and `precision`, and the points unaltered.
- It returns the `TimeSeriesWriteSummary` **whole** — a test asserting `dropped`, `unknownTypes` and `written` all survive, not just that the call resolved (D-M6-3).
- An empty batch iterable is accepted and yields a summary rather than throwing.
- `timeSeriesQuery` yields each `TimeSeriesQueryResult` the server streams, in order, and surfaces `truncated` and `last` on the results it yields.

In `test/transaction.test.ts`, following the bind tests added for the vector RPCs in M5 — and keeping the property those tests exist for: populate `rollback`/`readOnly`/`commit`/`timeoutMs` on a forged `TransactionContext` and assert they do **not** ride through, because asserting only the id and database would pass against a merge implementation:

- `tx.timeSeriesQuery(...)` and `tx.timeSeriesLatest(...)` force the handle's `database` and `transaction` onto a request that named another of each.
- The caller's own request object is not mutated.

The two that carry the design decisions, written out because a paraphrase of them is exactly
what would get watered down — the rest follow the file's existing patterns:

```ts
it("returns the write summary whole, including a partial success (D-M6-3)", async () => {
  // A SUCCESSFUL RPC can still drop points. A test asserting only that the call
  // resolved would pass against a wrapper that threw the reasons away, which is
  // the failure mode this assertion exists for.
  const raw = {
    timeSeriesWriteStream: async () => ({
      received: 5n, written: 3n, dropped: 2n,
      unknownTypes: ["nosuchtype"], nonTimeSeriesTypes: [], unavailableTypes: ["cold"],
      executionTimeMs: 7n,
    }),
  };
  const writeStream = createTimeSeriesWriteStream(raw as never);

  const summary = await writeStream({
    database: "db", type: "cpu", precision: TimeSeriesPrecision.TS_PRECISION_SECONDS,
    chunks: (async function* () { yield [] as TimeSeriesPoint[]; })(),
  });

  expect(summary.written).toBe(3n);
  expect(summary.dropped).toBe(2n);
  expect(summary.unknownTypes).toEqual(["nosuchtype"]);
  expect(summary.unavailableTypes).toEqual(["cold"]);
});

it("sends database, type and precision on EVERY chunk, not just the first (D-M6-4)", async () => {
  const sent: TimeSeriesWriteChunkInit[] = [];
  const raw = {
    timeSeriesWriteStream: async (chunks: AsyncIterable<TimeSeriesWriteChunkInit>) => {
      for await (const c of chunks) sent.push(c);
      return { received: 2n, written: 2n, dropped: 0n };
    },
  };
  const writeStream = createTimeSeriesWriteStream(raw as never);

  await writeStream({
    database: "db", type: "cpu", precision: TimeSeriesPrecision.TS_PRECISION_SECONDS,
    chunks: (async function* () {
      yield [{ type: "cpu", timestamp: 1n }] as TimeSeriesPoint[];
      yield [{ type: "cpu", timestamp: 2n }] as TimeSeriesPoint[];
    })(),
  });

  expect(sent).toHaveLength(2);
  for (const chunk of sent) {
    expect(chunk.database).toBe("db");
    expect(chunk.type).toBe("cpu");
    expect(chunk.precision).toBe(TimeSeriesPrecision.TS_PRECISION_SECONDS);
  }
});
```

Adjust the mock shape to whatever `createInsertStream`'s existing tests use — read them first; the
point is the two assertions, not this snippet's plumbing.

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd typescript && npx vitest run packages/driver-grpc/test/stream.test.ts packages/driver-grpc/test/transaction.test.ts; cd ..
```

Expected: the new cases FAIL — the methods do not exist.

- [ ] **Step 4: Implement**

Add the two wrappers to `stream.ts` and wire them onto `ArcadeDBGrpcClient` in `index.ts` beside `streamQuery` and `insertStream`, with doc comments matching the existing ones' depth. `TimeSeriesWriteStreamRequest` takes `database`, `type`, a **required** `precision` (D-M6-1 — the doc comment must say why, naming the HTTP/gRPC mismatch), optional `credentials`, and `chunks: AsyncIterable<TimeSeriesPoint[]>`, one wire chunk per element.

Add `timeSeriesQuery` and `timeSeriesLatest` to `TransactionHandle` in `transaction.ts`, routed through the same `bindTransaction` as every other handle method. Do not introduce a second binding path.

- [ ] **Step 5: Run the tests and the gate**

```bash
cd typescript && npx vitest run packages/driver-grpc/test/ && npm run typecheck && npm run lint && npm test; cd ..
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add typescript/packages/driver-grpc/src typescript/packages/driver-grpc/test
git commit -m "$(cat <<'EOF'
feat(driver-grpc): time series over gRPC - write stream, query, latest

Wraps the two RPCs a bare stub drives badly: TimeSeriesWriteStream is
client-streaming and mirrors insertStream's envelope bookkeeping;
TimeSeriesQuery is server-streaming and mirrors streamQuery. TimeSeriesQuery
and TimeSeriesLatest are also bound on TransactionHandle, because their
request messages carry `transaction` - TimeSeriesWriteRequest does not, so
TimeSeriesWrite stays reachable through `raw` alone.

`precision` is REQUIRED on the write-stream request, deliberately. An omitted
precision means nanoseconds over HTTP and milliseconds over gRPC, because
proto3's zero value for the enum is TS_PRECISION_MILLISECONDS and the wire
cannot distinguish "omitted" from "explicitly milliseconds". Requiring it
removes a silent 10^6 timestamp error by construction.

The write summary is returned whole: a successful RPC can still report
written < received, with the reasons in unknown_types, non_time_series_types
and unavailable_types.

Refs #38
EOF
)"
```

---

### Task 3: The Python gRPC time-series surface, sync and async

**Files:**
- Modify: `python/packages/driver-grpc/src/arcadedb_driver_grpc/stream.py`, `aio.py`, `transaction.py`, `__init__.py`
- Test: `python/packages/driver-grpc/tests/test_stream.py`, `tests/test_transaction.py`, `tests/test_aio.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: the generated stub and the same messages as Task 2.
- Produces: `time_series_write_stream` and `time_series_query` on the sync and async clients; `time_series_query` and `time_series_latest` on `TransactionHandle` and `AsyncTransactionHandle`.

- [ ] **Step 1: Extend the recording servicer**

`tests/conftest.py`'s `RecordingServicer` implements only the RPCs existing tests touch. Add handlers for `TimeSeriesWriteStream`, `TimeSeriesQuery` and `TimeSeriesLatest`, following the shape of the `InsertStream` and `StreamQuery` handlers already there — the first consumes a request iterator and returns a summary, the second yields results. Add the lists to record into:

```python
        self.ts_chunks: list[pb2.TimeSeriesWriteChunk] = []
        self.ts_query_requests: list[pb2.TimeSeriesQueryRequest] = []
        self.ts_latest_requests: list[pb2.TimeSeriesLatestRequest] = []
```

- [ ] **Step 2: Write the failing tests**

Mirror Task 2's cases, in this workspace's style, sync in `test_stream.py` / `test_transaction.py` and async in `test_aio.py`. The same two properties matter: the write summary must come back whole (assert `dropped` and `unknown_types`, not just that it returned), and the bind tests must populate the inline `TransactionContext` flags and assert they are cleared.

The two that carry the design decisions:

```python
def test_write_stream_returns_the_summary_whole(fake_server) -> None:
    # A successful RPC can still drop points. Asserting only that it returned
    # would pass against a wrapper that discarded the reasons.
    target, servicer = fake_server
    servicer.ts_summary = messages.TimeSeriesWriteSummary(
        received=5, written=3, dropped=2, unknown_types=["nosuchtype"], unavailable_types=["cold"]
    )
    with create_client(target) as client:
        summary = client.time_series_write_stream(
            database="db",
            type="cpu",
            precision=messages.TS_PRECISION_SECONDS,
            chunks=iter([[]]),
        )

    assert summary.written == 3
    assert summary.dropped == 2
    assert list(summary.unknown_types) == ["nosuchtype"]
    assert list(summary.unavailable_types) == ["cold"]


def test_write_stream_sets_the_envelope_on_every_chunk(fake_server) -> None:
    target, servicer = fake_server
    points = [messages.TimeSeriesPoint(type="cpu", timestamp=1)]
    with create_client(target) as client:
        client.time_series_write_stream(
            database="db",
            type="cpu",
            precision=messages.TS_PRECISION_SECONDS,
            chunks=iter([points, points]),
        )

    assert len(servicer.ts_chunks) == 2
    for chunk in servicer.ts_chunks:
        assert chunk.database == "db"
        assert chunk.type == "cpu"
        assert chunk.precision == messages.TS_PRECISION_SECONDS
```

Settle the argument style (keyword arguments here versus a request dataclass like
`InsertStreamRequest`) against `insert_stream`'s actual signature before writing these, and adjust
the snippet rather than the convention.

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd python && uv run pytest packages/driver-grpc/tests -v; cd ..
```

Expected: the new cases FAIL.

- [ ] **Step 4: Implement**

`time_series_write_stream` and `time_series_query` in `stream.py` (sync) and `aio.py` (async), mirroring `insert_stream` and `stream_query` respectively. A required `precision` argument, with the D-M6-1 reasoning in the docstring. `time_series_query` and `time_series_latest` on both transaction handles, through the existing `_bind`.

Keep the sync and async docstrings carrying the same behavioural facts — this is the defect M5 hit and #30 records.

- [ ] **Step 5: Run the tests and the gate**

```bash
cd python && uv run pytest packages/driver-grpc/tests -v && uv run mypy && uv run ruff check . && uv run ruff format --check . && uv run pytest; cd ..
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add python/packages/driver-grpc/src python/packages/driver-grpc/tests
git commit -m "$(cat <<'EOF'
feat(driver-grpc): time series over gRPC, sync and async

The Python twin of the TypeScript surface: time_series_write_stream mirrors
insert_stream, time_series_query mirrors stream_query, and both transaction
handles gain time_series_query and time_series_latest through the existing
_bind. TimeSeriesWrite stays raw-only - its request message carries no
transaction field.

`precision` is a required argument for the reason the TypeScript commit
gives: omitted means nanoseconds over HTTP and milliseconds over gRPC.

Refs #38
EOF
)"
```

---

### Task 4: README prose and end-to-end verification

**Files:**
- Modify: `typescript/packages/driver-grpc/README.md`, `python/packages/driver-grpc/README.md`
- Test: `typescript/e2e/grpc.test.ts`, `python/e2e/test_grpc.py`, `python/e2e/test_grpc_aio.py`

- [ ] **Step 1: Establish the time-series DDL against a live container**

As in M5, work this out with a scratch script under the session scratchpad **before** touching a test file. Docker is running and `arcadedata/arcadedb:26.10.1-SNAPSHOT` is pulled; use a host port at 2481 or above, since 2480 is taken on this machine. The gRPC plugin is off by default — the suite starts the server with `-Darcadedb.server.plugins=GRPC:...` and a root password of at least 8 characters, or port 50051 is simply closed.

You need a time-series type that accepts points and can be read back. Record the exact statements.

**If you cannot get points to write and read back within roughly a dozen attempts, STOP and report BLOCKED** with what you tried and what the server said. Do not write an e2e that asserts an empty result: it passes identically against a working and a broken client.

- [ ] **Step 2: Write the e2e tests**

In both languages, against a real container:
- a **multi-chunk** `timeSeriesWriteStream` — at least two chunks — asserting the returned summary reports `written` equal to the total points sent and `dropped` zero. Multi-chunk is the point: it is what proves D-M6-4's per-chunk envelope actually works, which no unit test with a fake servicer can establish.
- `timeSeriesQuery` returning those points, asserting a **non-empty** row set.
- `timeSeriesLatest` returning the most recent point.
- at least one of query/latest driven **through a transaction handle**, not only the top-level client.

- [ ] **Step 3: Run both e2e suites**

```bash
cd typescript && npm run e2e; cd ..
cd python && uv run pytest e2e -v; cd ..
```

- [ ] **Step 4: Write the README sections**

One per gRPC package, in that file's own voice. Each must state:
- the four RPCs and which of the four treatments each gets (D-M6-2's table);
- that `TimeSeriesWrite` is `raw`-only because its message carries no `transaction` field — a **contract** exclusion, unlike `insertStream`'s absence from the handle, which was a server bug since fixed;
- that `precision` is required, and why: omitted means nanoseconds over HTTP and milliseconds over gRPC, and proto3 cannot tell "omitted" from "explicitly milliseconds";
- that the write summary can report `written < received` on a **successful** call, with reasons in `unknown_types`, `non_time_series_types` and `unavailable_types` — and that checking only for an exception is not checking that the data landed.

Update each README's existing enumeration of what is reachable only through `raw` so it stays accurate.

- [ ] **Step 5: Full gate, then commit**

```bash
cd typescript && npm run lint && npm run typecheck && npm test; cd ..
cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run python scripts/check_codegen_skips.py; cd ..
git status --short
```

```bash
git add typescript/packages/driver-grpc/README.md python/packages/driver-grpc/README.md typescript/e2e python/e2e
git commit -m "$(cat <<'EOF'
docs(timeseries): document the precision trap and the partial-success summary

Adds the time-series section to both gRPC READMEs and the end-to-end
coverage behind it: a MULTI-CHUNK write stream, which is the only thing that
proves the per-chunk envelope works - a unit test against a fake servicer
cannot - plus query and latest, one of them driven through a transaction
handle.

Records the two things a caller cannot infer from the types: an omitted
precision means nanoseconds over HTTP and milliseconds over gRPC, and a
SUCCESSFUL write can still report written < received with the reasons in
three separate repeated fields.

Refs #38
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

Expected: all exit 0, and the skip set is still its four entries.

- [ ] **Step 2: Confirm the drift gate is untouched**

M6 changes no contract, so regeneration must produce no diff.

```bash
cd typescript && npm run generate && cd ..
cd python && ./scripts/generate.sh && ./scripts/generate-grpc.sh && cd ..
git status --short
```

Expected: only `?? .idea/`.

- [ ] **Step 3: Push and open the PR**

```bash
git push -u origin feat/m6-timeseries-grpc
gh pr create --base main --milestone '0.2.0 — the 26.10.1 contract' \
  --label enhancement,grpc-driver,typescript,python,e2e \
  --title 'feat: time series over gRPC' \
  --body 'Closes #38.'
```

Expand that body before creating: the four RPCs and their treatments, the precision trap with its table, the partial-success summary, the multi-chunk e2e evidence, and that the drift gate and skip set are unchanged.
